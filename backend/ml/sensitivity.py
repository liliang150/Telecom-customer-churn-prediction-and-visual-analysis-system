from __future__ import annotations

import time
from datetime import datetime, timezone

import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

from backend.ml.preprocessing import LABEL_COLUMN, clean_dataframe, prepare_features
from backend.ml.training import evaluate_model, optimize_threshold

DEFAULT_DEPTHS = (6, 8, 10, 12, 14, 16)


def evaluate_depth_sensitivity(frame: pd.DataFrame, depths=DEFAULT_DEPTHS, quick: bool = False, progress=None) -> dict:
    cleaned, _ = clean_dataframe(frame)
    labels = pd.to_numeric(cleaned[LABEL_COLUMN], errors="raise").astype(int)
    features = prepare_features(cleaned)

    development_x, validation_x, development_y, validation_y = train_test_split(
        features, labels, test_size=0.25, random_state=42, stratify=labels
    )
    fit_x, calibration_x, fit_y, calibration_y = train_test_split(
        development_x, development_y, test_size=1 / 3, random_state=42, stratify=development_y
    )
    class_ratio = float((fit_y == 0).sum() / max((fit_y == 1).sum(), 1))

    results = []
    for index, depth in enumerate(depths):
        started = time.perf_counter()
        model = XGBClassifier(
            objective="binary:logistic",
            n_estimators=24 if quick else 800,
            max_depth=int(depth),
            learning_rate=0.1 if quick else 0.03,
            subsample=0.9 if quick else 0.7,
            colsample_bytree=0.85 if quick else 0.5,
            min_child_weight=2 if quick else 15,
            reg_lambda=2 if quick else 15,
            scale_pos_weight=class_ratio,
            random_state=42,
            n_jobs=2 if quick else 8,
            tree_method="hist",
            eval_metric="logloss",
        )
        model.fit(fit_x, fit_y)
        calibrated = CalibratedClassifierCV(model, method="sigmoid", cv="prefit")
        calibrated.fit(calibration_x, calibration_y)
        threshold = optimize_threshold(calibration_y, calibrated.predict_proba(calibration_x)[:, 1])
        metrics = evaluate_model(calibrated, validation_x, validation_y, threshold["threshold"])
        results.append(
            {
                "max_depth": int(depth),
                "auc": float(metrics["auc"]),
                "pr_auc": float(metrics["pr_auc"]),
                "recall": float(metrics["recall"]),
                "precision": float(metrics["precision"]),
                "f1": float(metrics["f1"]),
                "ks": float(metrics["ks"]),
                "brier": float(metrics["brier"]),
                "threshold": float(threshold["threshold"]),
                "fit_seconds": round(time.perf_counter() - started, 1),
            }
        )
        if progress:
            progress(index + 1, len(depths), int(depth))

    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "depths": [int(depth) for depth in depths],
        "quick": bool(quick),
        "sample_rows": int(len(cleaned)),
        "feature_count": int(features.shape[1]),
        "data_split": {
            "fit_rows": int(len(fit_x)),
            "calibration_rows": int(len(calibration_x)),
            "validation_rows": int(len(validation_x)),
        },
        "results": results,
        "note": "只改变 XGBoost 最大树深，其余参数、三段拆分与阈值优化规则保持一致；指标来自内部验证集。",
    }
