from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap
from sklearn.calibration import CalibratedClassifierCV
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from backend.ml.preprocessing import ID_COLUMN, LABEL_COLUMN, clean_dataframe, prepare_features


def _json_value(value):
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, np.ndarray):
        return _json_value(value.tolist())
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    return value


def _curve_points(x, y, limit=160):
    if len(x) <= limit:
        indices = np.arange(len(x))
    else:
        indices = np.linspace(0, len(x) - 1, limit, dtype=int)
    return [{"x": float(x[index]), "y": float(y[index])} for index in indices]


def evaluate_model(model: Pipeline, matrix: pd.DataFrame, labels: pd.Series, threshold: float = 0.5) -> dict:
    probabilities = model.predict_proba(matrix)[:, 1]
    predictions = (probabilities >= threshold).astype(int)
    false_positive, true_positive, _ = roc_curve(labels, probabilities)
    precision, recall, _ = precision_recall_curve(labels, probabilities)
    matrix_values = confusion_matrix(labels, predictions)
    return {
        "auc": float(roc_auc_score(labels, probabilities)),
        "pr_auc": float(average_precision_score(labels, probabilities)),
        "recall": float(recall_score(labels, predictions, zero_division=0)),
        "precision": float(precision_score(labels, predictions, zero_division=0)),
        "f1": float(f1_score(labels, predictions, zero_division=0)),
        "brier": float(brier_score_loss(labels, probabilities)),
        "ks": float(np.max(true_positive - false_positive)),
        "threshold": float(threshold),
        "confusion_matrix": matrix_values.tolist(),
        "roc_curve": _curve_points(false_positive, true_positive),
        "pr_curve": _curve_points(recall, precision),
    }


def optimize_threshold(labels, probabilities, min_recall: float = 0.75) -> dict:
    labels = np.asarray(labels, dtype=int)
    probabilities = np.asarray(probabilities, dtype=float)
    thresholds = np.unique(np.concatenate(([0.0], probabilities, [1.0])))

    order = np.argsort(-probabilities, kind="mergesort")
    sorted_labels = labels[order]
    sorted_probabilities = probabilities[order]
    true_positive = np.cumsum(sorted_labels)
    total_positive = int(true_positive[-1]) if len(true_positive) else 0

    predicted = np.searchsorted(-sorted_probabilities, -thresholds, side="right")
    tp = np.where(predicted > 0, true_positive[np.maximum(predicted - 1, 0)], 0)
    recalls = tp / total_positive if total_positive else np.zeros_like(tp, dtype=float)
    precisions = np.divide(tp, predicted, out=np.zeros_like(tp, dtype=float), where=predicted > 0)
    f1s = np.divide(
        2 * precisions * recalls,
        precisions + recalls,
        out=np.zeros_like(tp, dtype=float),
        where=(precisions + recalls) > 0,
    )

    eligible = recalls >= min_recall
    target_met = bool(eligible.any())
    candidates = np.where(eligible)[0] if target_met else np.arange(len(thresholds))
    ranked = candidates[
        np.lexsort((-thresholds[candidates], recalls[candidates], precisions[candidates], f1s[candidates]))
    ]
    selected = int(ranked[-1])
    return {
        "threshold": float(thresholds[selected]),
        "recall": float(recalls[selected]),
        "precision": float(precisions[selected]),
        "f1": float(f1s[selected]),
        "min_recall": float(min_recall),
        "target_met": target_met,
        "objective": "满足最低召回率约束后最大化 F1；无可用阈值时最大化 F1",
        "optimized_on": "校准集",
    }


def train_models(frame: pd.DataFrame, output_dir: str | Path, quick: bool = False) -> dict:
    cleaned, cleaning_report = clean_dataframe(frame)
    if LABEL_COLUMN not in cleaned.columns:
        raise ValueError(f"训练数据必须包含标签字段：{LABEL_COLUMN}")
    labels = pd.to_numeric(cleaned[LABEL_COLUMN], errors="raise").astype(int)
    if labels.nunique() != 2 or not set(labels.unique()).issubset({0, 1}):
        raise ValueError("标签字段必须同时包含 0 和 1 两类样本")
    features = prepare_features(cleaned)
    if features.shape[1] == 0:
        raise ValueError("没有可用于训练的特征")

    development_x, validation_x, development_y, validation_y = train_test_split(
        features, labels, test_size=0.25, random_state=42, stratify=labels
    )
    fit_x, calibration_x, fit_y, calibration_y = train_test_split(
        development_x, development_y, test_size=1 / 3, random_state=42, stratify=development_y
    )
    class_ratio = float((fit_y == 0).sum() / max((fit_y == 1).sum(), 1))
    xgboost = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            (
                "classifier",
                XGBClassifier(
                    objective="binary:logistic",
                    n_estimators=24 if quick else 800,
                    max_depth=4 if quick else 10,
                    learning_rate=0.1 if quick else 0.03,
                    subsample=0.9,
                    colsample_bytree=0.85 if quick else 0.5,
                    min_child_weight=2 if quick else 15,
                    reg_lambda=2 if quick else 15,
                    scale_pos_weight=class_ratio,
                    random_state=42,
                    n_jobs=2 if quick else 8,
                    tree_method="hist",
                    eval_metric="logloss",
                ),
            ),
        ]
    )
    logistic = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("classifier", LogisticRegression(max_iter=800, class_weight="balanced", random_state=42)),
        ]
    )
    xgboost.fit(fit_x, fit_y)
    logistic.fit(fit_x, fit_y)
    folds = 2 if quick else 3
    splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=42)
    cross_validation = {}
    for name, estimator in (("xgboost", xgboost), ("logistic_regression", logistic)):
        scores = cross_val_score(estimator, fit_x, fit_y, scoring="roc_auc", cv=splitter, n_jobs=1)
        cross_validation[name] = {
            "folds": folds,
            "auc_mean": float(scores.mean()),
            "auc_std": float(scores.std()),
            "scores": scores.tolist(),
            "note": "仅在拟合集上进行固定配置交叉验证，用于稳定性观察，不等同于嵌套调参评估",
        }

    calibrated_xgboost = CalibratedClassifierCV(xgboost, method="sigmoid", cv="prefit")
    calibrated_logistic = CalibratedClassifierCV(logistic, method="sigmoid", cv="prefit")
    calibrated_xgboost.fit(calibration_x, calibration_y)
    calibrated_logistic.fit(calibration_x, calibration_y)
    threshold_optimization = {
        "xgboost": optimize_threshold(calibration_y, calibrated_xgboost.predict_proba(calibration_x)[:, 1]),
        "logistic_regression": optimize_threshold(calibration_y, calibrated_logistic.predict_proba(calibration_x)[:, 1]),
    }
    metrics = {
        "xgboost": evaluate_model(
            calibrated_xgboost, validation_x, validation_y, threshold_optimization["xgboost"]["threshold"]
        ),
        "logistic_regression": evaluate_model(
            calibrated_logistic, validation_x, validation_y, threshold_optimization["logistic_regression"]["threshold"]
        ),
    }
    sample = validation_x.sample(n=min(180 if quick else 300, len(validation_x)), random_state=42)
    transformed = xgboost.named_steps["imputer"].transform(sample)
    explainer = shap.TreeExplainer(xgboost.named_steps["classifier"])
    shap_values = np.asarray(explainer.shap_values(transformed))
    mean_values = np.abs(shap_values).mean(axis=0)
    global_shap = sorted(
        [
            {"feature": name, "importance": float(score)}
            for name, score in zip(features.columns, mean_values)
        ],
        key=lambda item: item["importance"],
        reverse=True,
    )
    swarm = []
    for row_index in range(min(120 if quick else 300, len(sample))):
        for feature_index, name in enumerate(features.columns):
            swarm.append(
                {
                    "feature": name,
                    "value": float(sample.iloc[row_index, feature_index]) if pd.notna(sample.iloc[row_index, feature_index]) else None,
                    "shap_value": float(shap_values[row_index, feature_index]),
                }
            )

    version = datetime.now(timezone.utc).strftime("v%Y%m%d%H%M%S%f")
    version_dir = Path(output_dir) / version
    version_dir.mkdir(parents=True, exist_ok=False)
    data_hash = hashlib.sha256(pd.util.hash_pandas_object(cleaned, index=False).values.tobytes()).hexdigest()
    metadata = {
        "version": version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_name": "XGBoost",
        "training_data_hash": data_hash,
        "rows": int(len(cleaned)),
        "test_rows": int(len(validation_x)),
        "validation_rows": int(len(validation_x)),
        "data_split": {
            "fit_rows": int(len(fit_x)),
            "calibration_rows": int(len(calibration_x)),
            "validation_rows": int(len(validation_x)),
        },
        "threshold": threshold_optimization["xgboost"]["threshold"],
        "threshold_optimization": threshold_optimization,
        "calibration": {"method": "sigmoid", "rows": int(len(calibration_x)), "fitted_on": "校准集"},
        "risk_thresholds": {"medium": 0.4, "high": 0.7},
        "evaluation_scope": "内部验证集（未参与模型拟合、概率校准或阈值选择）",
        "cleaning_report": cleaning_report,
        "metrics": metrics,
        "cross_validation": cross_validation,
    }
    bundle = {
        "model": xgboost,
        "baseline_model": logistic,
        "calibrated_model": calibrated_xgboost,
        "calibrated_baseline_model": calibrated_logistic,
        "feature_columns": features.columns.tolist(),
        "raw_feature_columns": [column for column in cleaned.columns if column not in {ID_COLUMN, LABEL_COLUMN}],
        "metadata": metadata,
        "global_shap": global_shap,
    }
    joblib.dump(bundle, version_dir / "model.joblib")
    (version_dir / "metadata.json").write_text(
        json.dumps(_json_value(metadata), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (version_dir / "explanations.json").write_text(
        json.dumps(_json_value({"global": global_shap, "swarm": swarm}), ensure_ascii=False),
        encoding="utf-8",
    )
    return _json_value(
        {
            "version": version,
            "metrics": metrics,
            "cross_validation": cross_validation,
            "feature_columns": features.columns.tolist(),
            "global_shap": global_shap,
            "training_data_hash": data_hash,
            "validation_rows": int(len(validation_x)),
            "data_split": metadata["data_split"],
            "threshold": metadata["threshold"],
            "threshold_optimization": threshold_optimization,
            "calibration": metadata["calibration"],
            "evaluation_scope": metadata["evaluation_scope"],
            "cleaning_report": cleaning_report,
        }
    )