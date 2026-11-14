from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import UploadFile
from sqlalchemy import Integer, cast, func

from backend.artifacts import ArtifactStore
from backend.database import Prediction, PredictionBatch
from backend.ml.prediction import ChurnPredictor
from backend.ml.preprocessing import ID_COLUMN, LABEL_COLUMN, build_quality_report, clean_dataframe, prepare_features
from backend.ml.risk import retention_advice, risk_level
from backend.ml.feature_selection import LASSO_C_VALUES, evaluate_feature_selection
from backend.ml.sensitivity import DEFAULT_DEPTHS, evaluate_depth_sensitivity
from backend.ml.training import train_models


def records(frame: pd.DataFrame) -> list[dict]:
    return json.loads(frame.to_json(orient="records", force_ascii=False))


class DataService:
    def __init__(self, train_path: Path, test_path: Path, upload_dir: Path):
        self.train_path = train_path
        self.test_path = test_path
        self.upload_dir = upload_dir
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.versions_dir = upload_dir.parent / "versions"

    @property
    def version_pointer(self) -> Path:
        return self.versions_dir / "active.json"

    @staticmethod
    @lru_cache(maxsize=8)
    def _read_cached(path: str, modified: int) -> pd.DataFrame:
        return pd.read_csv(path)

    def _read(self, path: Path) -> pd.DataFrame:
        if not path.is_file():
            return pd.DataFrame()
        return self._read_cached(str(path), path.stat().st_mtime_ns).copy()

    def train(self) -> pd.DataFrame:
        return self._read(self.train_path)

    def test(self) -> pd.DataFrame:
        return self._read(self.test_path)

    def test_exists(self) -> bool:
        return self.test_path.is_file() and self.test_path.stat().st_size > 0

    def overview(self) -> dict:
        train = self.train()
        test = self.test()
        test_has_data = self.test_exists() and len(test) > 0
        label_distribution = {}
        if LABEL_COLUMN in train.columns:
            counts = train[LABEL_COLUMN].value_counts().sort_index()
            label_distribution = {str(int(key)): int(value) for key, value in counts.items()}
        overview = {
            "train_rows": int(len(train)),
            "test_rows": int(len(test)) if test_has_data else None,
            "test_available": test_has_data,
            "column_count": int(len(train.columns)),
            "missing_values": int(train.isna().sum().sum()),
            "duplicate_ids": int(train[ID_COLUMN].duplicated().sum()) if ID_COLUMN in train else 0,
            "label_distribution": label_distribution,
            "feature_columns": [column for column in train.columns if column not in {ID_COLUMN, LABEL_COLUMN}],
            "preview": records(train.head(8)),
            "test_has_label": bool(test_has_data and LABEL_COLUMN in test.columns),
            "data_version": self.active_version(),
            "quality_report": build_quality_report(train, test if test_has_data else None),
        }
        return overview

    def sample(self) -> dict:
        if not self.test_exists():
            return {"customer_id": None, "record": {}}
        test = self.test()
        if test.empty:
            return {"customer_id": None, "record": {}}
        row = test.iloc[[0]]
        customer_id = int(row.iloc[0][ID_COLUMN]) if ID_COLUMN in row.columns else None
        record_frame = row.drop(columns=[LABEL_COLUMN], errors="ignore")
        return {"customer_id": customer_id, "record": records(record_frame)[0] if len(record_frame) > 0 else {}}

    @staticmethod
    def parse_content(filename: str, content: bytes) -> pd.DataFrame:
        suffix = Path(filename).suffix.lower()
        if suffix not in {".csv", ".xlsx", ".xls"}:
            raise ValueError("仅支持 CSV、XLSX 或 XLS 文件")
        if not content:
            raise ValueError("上传文件为空")
        try:
            if suffix == ".csv":
                frame = pd.read_csv(io.BytesIO(content))
            else:
                frame = pd.read_excel(io.BytesIO(content))
        except Exception as exc:
            raise ValueError(f"文件解析失败：{exc}") from exc
        if frame.empty:
            raise ValueError("文件中没有可处理的数据")
        return frame

    @classmethod
    async def parse_upload(cls, file: UploadFile) -> tuple[pd.DataFrame, bytes]:
        content = await file.read()
        return cls.parse_content(file.filename or "", content), content

    def save_upload(self, filename: str, content: bytes) -> str:
        safe_name = re.sub(r"[^\w.\-\u4e00-\u9fff]", "_", filename or "data.csv")
        path = self.upload_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}_{safe_name}"
        path.write_bytes(content)
        return path.name

    def validate_upload(self, kind: str, frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
        if kind not in {"train", "predict"}:
            raise ValueError("kind 必须为 train 或 predict")
        cleaned, report = clean_dataframe(frame)
        if kind == "train":
            if LABEL_COLUMN not in cleaned.columns:
                raise ValueError(f"训练数据必须包含标签字段：{LABEL_COLUMN}")
            labels = pd.to_numeric(cleaned[LABEL_COLUMN], errors="coerce")
            if labels.isna().any() or labels.nunique() != 2 or not set(labels.unique()).issubset({0, 1}):
                raise ValueError("标签字段必须同时包含 0 和 1 两类有效样本")
        required = [column for column in self.train().columns if column != LABEL_COLUMN]
        missing = [column for column in required if column not in cleaned.columns]
        if missing:
            raise ValueError("文件缺少必需特征：" + "、".join(missing[:6]))
        if prepare_features(cleaned).shape[1] == 0:
            raise ValueError("文件没有可用于建模或预测的特征")
        return cleaned, report

    def _staged_path(self, saved_name: str) -> Path:
        if Path(saved_name).name != saved_name:
            raise ValueError("暂存文件名无效")
        path = self.upload_dir / saved_name
        if not path.is_file():
            raise FileNotFoundError("暂存文件不存在或已处理")
        return path

    def active_version(self) -> str | None:
        if not self.version_pointer.is_file():
            return None
        try:
            return json.loads(self.version_pointer.read_text(encoding="utf-8"))["version"]
        except (json.JSONDecodeError, KeyError, OSError):
            return None

    def _set_active_version(self, version: str) -> None:
        self.versions_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.versions_dir / "active.tmp"
        temporary.write_text(json.dumps({"version": version}), encoding="utf-8")
        temporary.replace(self.version_pointer)

    @staticmethod
    def _copy_atomic(source: Path, target: Path) -> None:
        temporary = target.with_name(target.name + ".tmp")
        shutil.copyfile(source, temporary)
        temporary.replace(target)

    @staticmethod
    def _file_hash(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def confirm_upload(self, saved_name: str, kind: str) -> dict:
        staged = self._staged_path(saved_name)
        frame = self.parse_content(saved_name, staged.read_bytes())
        cleaned, _ = self.validate_upload(kind, frame)
        version = datetime.now(timezone.utc).strftime("d%Y%m%d%H%M%S%f")
        version_dir = self.versions_dir / version
        version_dir.mkdir(parents=True, exist_ok=False)
        target = self.train_path if kind == "train" else self.test_path
        cleaned.to_csv(version_dir / target.name, index=False)
        metadata = {
            "version": version,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            "source_file": saved_name,
            "train_rows": int(len(cleaned)) if kind == "train" else int(len(self.train())),
            "train_hash": self._file_hash(version_dir / target.name),
        }
        (version_dir / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._copy_atomic(version_dir / target.name, target)
        self._set_active_version(version)
        staged.unlink()
        return {**metadata, "active": True}

    def versions(self) -> list[dict]:
        active = self.active_version()
        items = []
        for path in self.versions_dir.glob("d*/metadata.json"):
            metadata = json.loads(path.read_text(encoding="utf-8"))
            metadata["active"] = metadata["version"] == active
            items.append(metadata)
        items.sort(key=lambda item: item["created_at"], reverse=True)
        return items

    def activate_version(self, version: str) -> dict:
        if Path(version).name != version:
            raise ValueError("数据版本无效")
        version_dir = self.versions_dir / version
        metadata_path = version_dir / "metadata.json"
        if not metadata_path.is_file() or not (version_dir / "train.csv").is_file():
            raise FileNotFoundError(f"数据版本不存在：{version}")
        self._copy_atomic(version_dir / "train.csv", self.train_path)
        # 旧版本可能还保存了 test.csv，兼容恢复；新版本不保存也不恢复
        legacy_test = version_dir / "test.csv"
        if legacy_test.is_file():
            self._copy_atomic(legacy_test, self.test_path)
        self._set_active_version(version)
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        return {**metadata, "active": True}


class TrainingAlreadyRunningError(RuntimeError):
    pass


class TrainingJobService:
    def __init__(self, data_service: DataService, output_dir: Path, trainer=None):
        self.data_service = data_service
        self.output_dir = output_dir
        self._trainer = trainer
        self._jobs: dict[str, dict] = {}
        self._active_job_id: str | None = None
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="model-training")

    def submit(self, quick: bool = False, trainer=None) -> dict:
        with self._lock:
            if self._active_job_id is not None:
                raise TrainingAlreadyRunningError("已有模型训练任务正在执行，请等待完成后再试")
            job_id = uuid.uuid4().hex[:16]
            self._jobs[job_id] = {
                "job_id": job_id,
                "status": "queued",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "result": None,
                "error": None,
            }
            self._active_job_id = job_id
            self._executor.submit(self._run, job_id, quick, trainer)
            return dict(self._jobs[job_id])

    def _run(self, job_id: str, quick: bool, trainer) -> None:
        with self._lock:
            self._jobs[job_id]["status"] = "running"
            self._jobs[job_id]["started_at"] = datetime.now(timezone.utc).isoformat()
        try:
            handler = trainer or self._trainer or train_models
            result = handler(self.data_service.train(), self.output_dir, quick=quick)
            with self._lock:
                self._jobs[job_id].update(
                    status="succeeded", result=result, finished_at=datetime.now(timezone.utc).isoformat()
                )
        except Exception as exc:
            with self._lock:
                self._jobs[job_id].update(
                    status="failed", error=str(exc), finished_at=datetime.now(timezone.utc).isoformat()
                )
        finally:
            with self._lock:
                self._active_job_id = None

    def status(self, job_id: str) -> dict:
        with self._lock:
            if job_id not in self._jobs:
                raise LookupError("训练任务不存在")
            return dict(self._jobs[job_id])


class PredictionService:
    def __init__(self, db, store: ArtifactStore):
        self.db = db
        self.store = store

    @staticmethod
    def _region(record: dict) -> str | None:
        value = record.get("地理区域")
        return None if pd.isna(value) else str(value)

    @staticmethod
    def _monthly_fee(record: dict) -> float | None:
        value = record.get("平均月费用")
        return None if pd.isna(value) else float(value)

    def single(self, record: dict) -> dict:
        if not record:
            raise ValueError("客户特征不能为空")
        bundle = self.store.load_active()
        predictor = ChurnPredictor(bundle)
        frame = pd.DataFrame([record])
        result = predictor.predict(frame)
        version = bundle["metadata"]["version"]
        customer_id = str(record.get(ID_COLUMN, f"single-{uuid.uuid4().hex[:8]}"))
        entity = Prediction(
            batch_id=None,
            customer_id=customer_id,
            probability=result["probability"],
            risk_level=result["risk_level"],
            region=self._region(record),
            monthly_fee=self._monthly_fee(record),
            model_version=version,
            payload_json=json.dumps(record, ensure_ascii=False, default=str),
            shap_json=json.dumps(result, ensure_ascii=False),
            advice=result["advice"],
        )
        self.db.add(entity)
        self.db.commit()
        return {
            "customer_id": customer_id,
            "model_version": version,
            "predicted_at": entity.created_at.isoformat(),
            **result,
        }

    def batch(self, frame: pd.DataFrame, filename: str, progress=None) -> dict:
        bundle = self.store.load_active()
        cleaned, report = clean_dataframe(frame)
        missing = [column for column in bundle["raw_feature_columns"] if column not in cleaned.columns]
        if missing:
            raise ValueError("文件缺少必需特征：" + "、".join(missing[:6]))
        predictor = ChurnPredictor(bundle)
        probabilities, matrix = predictor.predict_batch(cleaned)
        total = len(cleaned)
        if progress:
            progress(0, total)
        transformed = predictor.model.named_steps["imputer"].transform(matrix)
        if total:
            blocks = []
            chunk_size = 2000
            for start in range(0, total, chunk_size):
                stop = min(start + chunk_size, total)
                blocks.append(np.asarray(predictor.explainer.shap_values(transformed[start:stop])))
                if progress:
                    progress(stop, total)
            values = np.vstack(blocks)
        else:
            values = np.zeros((0, len(predictor.feature_columns)))
        version = bundle["metadata"]["version"]
        batch_id = uuid.uuid4().hex[:16]
        levels = [risk_level(float(value)) for value in probabilities]
        counts = {level: levels.count(level) for level in ["低风险", "中风险", "高风险"]}
        batch = PredictionBatch(
            id=batch_id,
            filename=filename,
            total=len(cleaned),
            low=counts["低风险"],
            medium=counts["中风险"],
            high=counts["高风险"],
            model_version=version,
        )
        self.db.add(batch)
        self.db.flush()
        now = datetime.now(timezone.utc)
        rows = []
        source_records = records(cleaned)
        for index, (probability, level, record) in enumerate(zip(probabilities, levels, source_records)):
            order = np.argsort(-np.abs(values[index]))[:6]
            top_features = [
                {
                    "feature": predictor.feature_columns[feature_index],
                    "feature_value": float(matrix.iloc[index, feature_index]) if pd.notna(matrix.iloc[index, feature_index]) else None,
                    "shap_value": float(values[index, feature_index]),
                }
                for feature_index in order
            ]
            rows.append(
                {
                    "batch_id": batch_id,
                    "customer_id": str(record.get(ID_COLUMN, index)),
                    "probability": float(probability),
                    "risk_level": level,
                    "region": self._region(record),
                    "monthly_fee": self._monthly_fee(record),
                    "model_version": version,
                    "payload_json": None,
                    "shap_json": json.dumps(top_features, ensure_ascii=False),
                    "advice": retention_advice(float(probability), top_features),
                    "created_at": now,
                }
            )
        if rows:
            self.db.execute(Prediction.__table__.insert(), rows)
        self.db.commit()
        if progress:
            progress(total, total)
        return {
            "batch_id": batch_id,
            "filename": filename,
            "total": len(cleaned),
            "low": counts["低风险"],
            "medium": counts["中风险"],
            "high": counts["高风险"],
            "model_version": version,
            "cleaning_report": report,
        }

    @staticmethod
    def _latest_batch_id(db) -> str | None:
        return db.query(PredictionBatch.id).order_by(PredictionBatch.created_at.desc(), PredictionBatch.id.desc()).limit(1).scalar()

    def _prediction_scope(self, batch_id: str | None = None):
        selected = batch_id if batch_id is not None else self._latest_batch_id(self.db)
        query = self.db.query(Prediction)
        if selected:
            return query.filter(Prediction.batch_id == selected), selected
        return query.filter(Prediction.batch_id.is_(None)), None

    @staticmethod
    def _risk_aggregates(base):
        distribution_rows = base.with_entities(Prediction.risk_level, func.count(Prediction.id)).group_by(Prediction.risk_level).all()
        distribution = {level: 0 for level in ["低风险", "中风险", "高风险"]}
        distribution.update({level: int(count) for level, count in distribution_rows})
        region_rows = base.with_entities(
            Prediction.region,
            func.count(Prediction.id),
            func.sum(cast(Prediction.risk_level == "高风险", Integer)),
        ).group_by(Prediction.region).all()
        regions = [
            {"region": name or "未知", "total": int(total), "high": int(high or 0), "high_rate": float((high or 0) / total)}
            for name, total, high in region_rows
        ]
        regions.sort(key=lambda item: item["total"], reverse=True)
        return distribution, regions

    def risk(self, batch_id=None, risk_level_filter=None, region=None, min_fee=None, customer_id=None, page=1, page_size=20):
        base, selected_batch = self._prediction_scope(batch_id)
        distribution, regions = self._risk_aggregates(base)

        query = base
        if risk_level_filter:
            query = query.filter(Prediction.risk_level == risk_level_filter)
        if region is not None and region != "":
            query = query.filter(Prediction.region == str(region))
        if min_fee is not None:
            query = query.filter(Prediction.monthly_fee >= min_fee)
        if customer_id:
            query = query.filter(Prediction.customer_id.contains(str(customer_id)))
        total = query.count()
        items_query = query.order_by(Prediction.probability.desc())
        if page_size is not None:
            items_query = items_query.offset((page - 1) * page_size).limit(page_size)
        items = items_query.all()
        return {
            "batch_id": selected_batch,
            "total": int(total),
            "page": page,
            "page_size": page_size,
            "distribution": distribution,
            "regions": regions[:20],
            "items": [self._list_item(item) for item in items],
        }

    @staticmethod
    def _list_item(item: Prediction) -> dict:
        snapshot = json.loads(item.shap_json)
        top_features = snapshot["top_features"] if isinstance(snapshot, dict) else snapshot
        return {
            "customer_id": item.customer_id,
            "probability": item.probability,
            "risk_level": item.risk_level,
            "region": item.region or "未知",
            "monthly_fee": item.monthly_fee,
            "model_version": item.model_version,
            "top_features": top_features[:3],
            "advice": retention_advice(float(item.probability), top_features),
        }

    def explanation(self, customer_id: str) -> dict:
        item = self.db.query(Prediction).filter(Prediction.customer_id == str(customer_id)).order_by(Prediction.created_at.desc()).first()
        if item is None:
            raise LookupError("未找到该客户的预测记录，请先完成预测")
        snapshot = json.loads(item.shap_json)
        if isinstance(snapshot, list):
            snapshot = {"top_features": snapshot, "base_value": None, "output_value": None}
        return {
            "customer_id": item.customer_id,
            "probability": item.probability,
            "risk_level": item.risk_level,
            "model_version": item.model_version,
            "top_features": snapshot["top_features"],
            "advice": retention_advice(float(item.probability), snapshot["top_features"]),
            "base_value": snapshot.get("base_value"),
            "output_value": snapshot.get("output_value"),
        }

    @staticmethod
    def _dashboard_item(item) -> dict:
        snapshot = json.loads(item.shap_json)
        top_features = snapshot["top_features"] if isinstance(snapshot, dict) else snapshot
        return {
            "customer_id": item.customer_id,
            "probability": item.probability,
            "risk_level": item.risk_level,
            "region": item.region or "未知",
            "monthly_fee": item.monthly_fee,
            "top_features": [{"feature": top_features[0]["feature"]}] if top_features else [],
        }

    def dashboard(self, data_service: DataService, batch_id: str | None = None) -> dict:
        base, batch_id = self._prediction_scope(batch_id)
        probabilities = [float(value[0]) for value in base.with_entities(Prediction.probability).all()]
        histogram = np.histogram(probabilities, bins=np.linspace(0, 1, 11)) if probabilities else (np.zeros(10, dtype=int), np.linspace(0, 1, 11))
        train = data_service.train()
        distribution, regions = self._risk_aggregates(base)
        high = distribution["高风险"]
        high_rows = base.with_entities(
            Prediction.customer_id,
            Prediction.probability,
            Prediction.risk_level,
            Prediction.region,
            Prediction.monthly_fee,
            Prediction.shap_json,
        ).filter(Prediction.risk_level == "高风险").order_by(Prediction.probability.desc()).all()
        points = base.with_entities(Prediction.monthly_fee, Prediction.probability, Prediction.risk_level).limit(500).all()
        return {
            "kpis": {
                "train_customers": len(train),
                "actual_churn_rate": self._actual_churn_rate(train),
                "predicted_customers": len(probabilities),
                "high_risk_customers": high,
                "high_risk_rate": high / len(probabilities) if probabilities else 0,
                "model_auc": self.store.load_active()["metadata"]["metrics"]["xgboost"]["auc"],
            },
            "batch_id": batch_id,
            "probability_distribution": [
                {"range": f"{index / 10:.1f}-{(index + 1) / 10:.1f}", "count": int(count)}
                for index, count in enumerate(histogram[0])
            ],
            "risk_distribution": [{"name": key, "value": value} for key, value in distribution.items()],
            "regions": regions[:10],
            "high_risk_customers": [self._dashboard_item(item) for item in high_rows],
            "fee_risk_points": [{"fee": fee, "probability": probability, "risk_level": level} for fee, probability, level in points if fee is not None],
        }

    def feature_dependency(self, feature: str | None = None) -> dict:
        explanations = self.store.explanations()
        swarm = explanations.get("swarm", [])
        available = {item.get("feature") for item in swarm if item.get("feature")}
        if not available:
            raise LookupError("当前模型缺少 SHAP 解释样本")
        global_order = [item["feature"] for item in explanations.get("global", []) if item.get("feature") in available]
        features = global_order + sorted(available - set(global_order))
        selected = feature or features[0]
        points = [
            {"value": item.get("value"), "shap_value": float(item.get("shap_value") or 0.0)}
            for item in swarm
            if item.get("feature") == selected
        ]
        if not points:
            raise LookupError("该特征没有可用的解释样本")
        return {
            "feature": selected,
            "features": features,
            "points": points,
            "note": "横轴为特征原始取值，纵轴为 SHAP 贡献；SHAP > 0 推高流失风险，SHAP < 0 降低流失风险。",
        }

    @staticmethod
    def _logistic_top_features(bundle: dict, limit: int = 10) -> list[str]:
        model = bundle.get("baseline_model")
        if model is None:
            return []
        try:
            coefficients = np.abs(np.asarray(model.named_steps["classifier"].coef_[0], dtype=float))
        except (AttributeError, KeyError, IndexError):
            return []
        columns = bundle["feature_columns"]
        order = np.argsort(-coefficients)[:limit]
        return [columns[index] for index in order if index < len(columns)]

    def explainability(self) -> dict:
        bundle = self.store.load_active()
        explanations = self.store.explanations()
        global_items = explanations.get("global", [])
        swarm = explanations.get("swarm", [])
        columns = bundle["feature_columns"]
        size = len(columns)

        top_global = [item["feature"] for item in global_items[:10]]
        total_importance = float(sum(item["importance"] for item in global_items))
        top_share = float(sum(item["importance"] for item in global_items[:10]) / total_importance) if total_importance else 0.0

        logistic_top = self._logistic_top_features(bundle, limit=len(top_global) or 10)
        overlap = len(set(top_global) & set(logistic_top))

        groups: dict[str, dict] = {}
        sample_count = 0
        if size and swarm and len(swarm) % size == 0:
            rows = [swarm[index:index + size] for index in range(0, len(swarm), size)]
            if all([cell["feature"] for cell in row] == columns for row in rows):
                frame = pd.DataFrame(
                    [[cell.get("value") for cell in row] for row in rows],
                    columns=columns,
                )
                probabilities, _ = ChurnPredictor(bundle).predict_batch(frame)
                for probability, row in zip(probabilities, rows):
                    level = risk_level(float(probability))
                    bucket = groups.setdefault(level, {"count": 0, "scores": np.zeros(size)})
                    bucket["count"] += 1
                    bucket["scores"] += np.abs([float(cell.get("shap_value") or 0.0) for cell in row])
                sample_count = len(rows)

        risk_groups = {}
        for level, bucket in groups.items():
            averages = bucket["scores"] / max(bucket["count"], 1)
            order = np.argsort(-averages)[:8]
            risk_groups[level] = {
                "count": int(bucket["count"]),
                "top_features": [
                    {"feature": columns[index], "mean_abs_shap": float(averages[index])}
                    for index in order
                ],
            }

        return {
            "sample_count": sample_count,
            "concentration": {
                "top10_share": top_share,
                "features": [
                    {"feature": item["feature"], "importance": float(item["importance"])}
                    for item in global_items[:10]
                ],
            },
            "model_agreement": {
                "overlap": overlap,
                "total": len(top_global),
                "rate": overlap / len(top_global) if top_global else 0.0,
                "logistic_top_features": logistic_top,
            },
            "risk_groups": risk_groups,
            "note": "集中度表示前 10 个特征占全部平均 |SHAP| 的比例；模型一致率表示 XGBoost SHAP 与逻辑回归系数前 N 名的重合比例。",
        }

    @staticmethod
    def _actual_churn_rate(train: pd.DataFrame) -> float:
        if LABEL_COLUMN not in train or not len(train):
            return 0.0
        return float(pd.to_numeric(train[LABEL_COLUMN], errors="coerce").mean())

    def batches(self) -> list[dict]:
        items = self.db.query(PredictionBatch).order_by(PredictionBatch.created_at.desc()).limit(50).all()
        return [
            {
                "batch_id": item.id,
                "filename": item.filename,
                "total": item.total,
                "low": item.low,
                "medium": item.medium,
                "high": item.high,
                "model_version": item.model_version,
                "created_at": item.created_at.isoformat(),
            }
            for item in items
        ]

    def delete_batch(self, batch_id: str) -> dict:
        batch = self.db.query(PredictionBatch).filter(PredictionBatch.id == batch_id).first()
        if batch is None:
            raise LookupError("批次不存在")
        self.db.query(Prediction).filter(Prediction.batch_id == batch_id).delete()
        self.db.delete(batch)
        self.db.commit()
        return {"batch_id": batch_id, "deleted": True}

    def export(self, batch_id: str) -> str:
        items = self.db.query(Prediction).filter(Prediction.batch_id == batch_id).order_by(Prediction.probability.desc()).all()
        if not items:
            raise LookupError("批次不存在或没有预测结果")
        rows = []
        for item in items:
            top = json.loads(item.shap_json)
            rows.append(
                {
                    "客户ID": item.customer_id,
                    "流失概率": round(item.probability, 6),
                    "风险等级": item.risk_level,
                    "地理区域": item.region,
                    "平均月费用": item.monthly_fee,
                    "首要风险因素": top[0]["feature"] if top else "",
                    "模型版本": item.model_version,
                    "挽留建议": retention_advice(float(item.probability), top),
                }
            )
        return "\ufeff" + pd.DataFrame(rows).to_csv(index=False)


class BatchPredictionRunningError(RuntimeError):
    pass


class BatchPredictionJobService:
    def __init__(self, session_factory, store: ArtifactStore):
        self.session_factory = session_factory
        self.store = store
        self._jobs: dict[str, dict] = {}
        self._active_job_id: str | None = None
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="batch-prediction")

    def submit(self, frame: pd.DataFrame, filename: str) -> dict:
        with self._lock:
            if self._active_job_id is not None:
                raise BatchPredictionRunningError("已有批量预测任务正在执行，请等待完成后再试")
            job_id = uuid.uuid4().hex[:16]
            total = int(len(frame))
            self._jobs[job_id] = {
                "job_id": job_id,
                "status": "queued",
                "filename": filename,
                "total": total,
                "processed": 0,
                "progress": 0.0,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "result": None,
                "error": None,
            }
            self._active_job_id = job_id
            self._executor.submit(self._run, job_id, frame, filename)
            return dict(self._jobs[job_id])

    def _report(self, job_id: str, processed: int, total: int) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job["processed"] = int(processed)
            job["progress"] = float(processed / total) if total else 1.0

    def _run(self, job_id: str, frame: pd.DataFrame, filename: str) -> None:
        with self._lock:
            self._jobs[job_id]["status"] = "running"
            self._jobs[job_id]["started_at"] = datetime.now(timezone.utc).isoformat()
        session = self.session_factory()
        try:
            result = PredictionService(session, self.store).batch(
                frame, filename, progress=lambda processed, total: self._report(job_id, processed, total)
            )
            with self._lock:
                self._jobs[job_id].update(
                    status="succeeded",
                    result=result,
                    processed=self._jobs[job_id]["total"],
                    progress=1.0,
                    finished_at=datetime.now(timezone.utc).isoformat(),
                )
        except Exception as exc:
            session.rollback()
            with self._lock:
                self._jobs[job_id].update(
                    status="failed",
                    error=str(exc),
                    finished_at=datetime.now(timezone.utc).isoformat(),
                )
        finally:
            session.close()
            with self._lock:
                self._active_job_id = None

    def status(self, job_id: str) -> dict:
        with self._lock:
            if job_id not in self._jobs:
                raise LookupError("批量预测任务不存在")
            return dict(self._jobs[job_id])


class SensitivityRunningError(RuntimeError):
    pass


class SensitivityJobService:
    def __init__(self, data_service: DataService, store: ArtifactStore, evaluator=None):
        self.data_service = data_service
        self.store = store
        self._evaluator = evaluator
        self._jobs: dict[str, dict] = {}
        self._active_job_id: str | None = None
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="model-sensitivity")

    @property
    def result_path(self) -> Path:
        return self.store.root / "sensitivity.json"

    def submit(self, quick: bool = False) -> dict:
        with self._lock:
            if self._active_job_id is not None:
                raise SensitivityRunningError("已有参数敏感性实验正在执行，请等待完成后再试")
            job_id = uuid.uuid4().hex[:16]
            total = len(DEFAULT_DEPTHS)
            self._jobs[job_id] = {
                "job_id": job_id,
                "status": "queued",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "completed": 0,
                "total": total,
                "current_depth": None,
                "progress": 0.0,
                "result": None,
                "error": None,
            }
            self._active_job_id = job_id
            self._executor.submit(self._run, job_id, quick)
            return dict(self._jobs[job_id])

    def _report(self, job_id: str, done: int, total: int, depth: int) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job["completed"] = int(done)
            job["total"] = int(total)
            job["current_depth"] = int(depth)
            job["progress"] = float(done / total) if total else 1.0

    def _run(self, job_id: str, quick: bool) -> None:
        with self._lock:
            self._jobs[job_id]["status"] = "running"
            self._jobs[job_id]["started_at"] = datetime.now(timezone.utc).isoformat()
        try:
            handler = self._evaluator or evaluate_depth_sensitivity
            result = handler(
                self.data_service.train(),
                quick=quick,
                progress=lambda done, total, depth: self._report(job_id, done, total, depth),
            )
            self.result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            with self._lock:
                self._jobs[job_id].update(
                    status="succeeded",
                    result=result,
                    completed=self._jobs[job_id]["total"],
                    current_depth=None,
                    progress=1.0,
                    finished_at=datetime.now(timezone.utc).isoformat(),
                )
        except Exception as exc:
            with self._lock:
                self._jobs[job_id].update(
                    status="failed",
                    error=str(exc),
                    finished_at=datetime.now(timezone.utc).isoformat(),
                )
        finally:
            with self._lock:
                self._active_job_id = None

    def status(self, job_id: str) -> dict:
        with self._lock:
            if job_id not in self._jobs:
                raise LookupError("参数敏感性实验任务不存在")
            return dict(self._jobs[job_id])

    def latest(self) -> dict | None:
        if not self.result_path.is_file():
            return None
        try:
            return json.loads(self.result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None


class FeatureSelectionRunningError(RuntimeError):
    pass


class FeatureSelectionJobService:
    def __init__(self, data_service: DataService, store: ArtifactStore, evaluator=None):
        self.data_service = data_service
        self.store = store
        self._evaluator = evaluator
        self._jobs: dict[str, dict] = {}
        self._active_job_id: str | None = None
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="feature-selection")

    @property
    def result_path(self) -> Path:
        return self.store.root / "feature_selection.json"

    def submit(self, quick: bool = False) -> dict:
        with self._lock:
            if self._active_job_id is not None:
                raise FeatureSelectionRunningError("已有特征筛选实验正在执行，请等待完成后再试")
            job_id = uuid.uuid4().hex[:16]
            total = len(LASSO_C_VALUES) + 1
            self._jobs[job_id] = {
                "job_id": job_id,
                "status": "queued",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "completed": 0,
                "total": total,
                "current_label": None,
                "progress": 0.0,
                "result": None,
                "error": None,
            }
            self._active_job_id = job_id
            self._executor.submit(self._run, job_id, quick)
            return dict(self._jobs[job_id])

    def _report(self, job_id: str, done: int, total: int, label: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job["completed"] = int(done)
            job["total"] = int(total)
            job["current_label"] = label
            job["progress"] = float(done / total) if total else 1.0

    def _run(self, job_id: str, quick: bool) -> None:
        with self._lock:
            self._jobs[job_id]["status"] = "running"
            self._jobs[job_id]["started_at"] = datetime.now(timezone.utc).isoformat()
        try:
            handler = self._evaluator or evaluate_feature_selection
            result = handler(
                self.data_service.train(),
                quick=quick,
                progress=lambda done, total, label: self._report(job_id, done, total, label),
            )
            self.result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            with self._lock:
                self._jobs[job_id].update(
                    status="succeeded",
                    result=result,
                    completed=self._jobs[job_id]["total"],
                    current_label=None,
                    progress=1.0,
                    finished_at=datetime.now(timezone.utc).isoformat(),
                )
        except Exception as exc:
            with self._lock:
                self._jobs[job_id].update(
                    status="failed",
                    error=str(exc),
                    finished_at=datetime.now(timezone.utc).isoformat(),
                )
        finally:
            with self._lock:
                self._active_job_id = None

    def status(self, job_id: str) -> dict:
        with self._lock:
            if job_id not in self._jobs:
                raise LookupError("特征筛选实验任务不存在")
            return dict(self._jobs[job_id])

    def latest(self) -> dict | None:
        if not self.result_path.is_file():
            return None
        try:
            return json.loads(self.result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None


def select_latest_batch():
    from sqlalchemy import select

    return select(PredictionBatch.id).order_by(PredictionBatch.created_at.desc(), PredictionBatch.id.desc()).limit(1)
