from __future__ import annotations

import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from backend.ml.preprocessing import LABEL_COLUMN, clean_dataframe, prepare_features
from backend.ml.training import evaluate_model, optimize_threshold

LASSO_C_VALUES = (0.1, 0.3)
METRIC_KEYS = ("auc", "pr_auc", "recall", "precision", "f1", "ks", "brier")


def _evaluate(fit_x, calibration_x, validation_x, fit_y, calibration_y, validation_y, quick: bool) -> dict:
    class_ratio = float((fit_y == 0).sum() / max((fit_y == 1).sum(), 1))
    started = time.perf_counter()
    model = XGBClassifier(
        objective="binary:logistic",
        n_estimators=24 if quick else 800,
        max_depth=4 if quick else 10,
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
    return {
        **{key: float(metrics[key]) for key in METRIC_KEYS},
        "threshold": float(threshold["threshold"]),
        "seconds": round(time.perf_counter() - started, 1),
    }


def _select_features(fit_x: pd.DataFrame, fit_y: pd.Series, strength: float) -> list[str]:
    filled = fit_x.fillna(fit_x.median())
    scaled = StandardScaler().fit_transform(filled)
    model = LogisticRegression(
        penalty="l1",
        solver="liblinear",
        C=strength,
        max_iter=400,
        class_weight="balanced",
        random_state=42,
    )
    model.fit(scaled, fit_y)
    mask = np.abs(model.coef_[0]) > 1e-8
    return [column for column, keep in zip(fit_x.columns, mask) if keep]


def evaluate_feature_selection(frame: pd.DataFrame, quick: bool = False, progress=None) -> dict:
    cleaned, _ = clean_dataframe(frame)
    labels = pd.to_numeric(cleaned[LABEL_COLUMN], errors="raise").astype(int)
    features = prepare_features(cleaned)

    development_x, validation_x, development_y, validation_y = train_test_split(
        features, labels, test_size=0.25, random_state=42, stratify=labels
    )
    fit_x, calibration_x, fit_y, calibration_y = train_test_split(
        development_x, development_y, test_size=1 / 3, random_state=42, stratify=development_y
    )

    total = len(LASSO_C_VALUES) + 1
    results = []
    baseline = _evaluate(fit_x, calibration_x, validation_x, fit_y, calibration_y, validation_y, quick)
    results.append({"name": "全特征基线", "feature_count": int(features.shape[1]), "selected_all": True, **baseline})
    if progress:
        progress(1, total, "全特征基线")

    for index, strength in enumerate(LASSO_C_VALUES, start=2):
        selected = _select_features(fit_x, fit_y, strength)
        selected_all = not selected or len(selected) >= features.shape[1]
        columns = list(fit_x.columns) if selected_all else selected
        metrics = _evaluate(
            fit_x[columns],
            calibration_x[columns],
            validation_x[columns],
            fit_y,
            calibration_y,
            validation_y,
            quick,
        )
        results.append({"name": f"Lasso C={strength}", "feature_count": len(columns), "selected_all": selected_all, **metrics})
        if progress:
            progress(index, total, f"Lasso C={strength}")

    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "sample_rows": int(len(cleaned)),
        "feature_count": int(features.shape[1]),
        "data_split": {
            "fit_rows": int(len(fit_x)),
            "calibration_rows": int(len(calibration_x)),
            "validation_rows": int(len(validation_x)),
        },
        "results": results,
        "note": "Lasso（L1 逻辑回归）仅在拟合集上选择特征，避免信息泄漏；各方案使用相同拆分、校准与阈值优化规则，指标均来自内部验证集。",
    }
