from __future__ import annotations

import numpy as np
import pandas as pd

ID_COLUMN = "客户ID"
LABEL_COLUMN = "是否流失"

ENGINEERED_FEATURES = {
    "usage_change_rate": "当月使用分钟数与前三个月平均值的百分比变化",
    "monthly_fee_change_rate": "当月费用与前三个月平均值的百分比变化",
    "service_call_count": "平均客户服务电话次数",
    "dropped_call_count": "平均掉线语音呼叫数",
    "avg_call_minutes_3m": "过去三个月的平均每月使用分钟数",
}


def clean_dataframe(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    data = frame.copy()
    data.columns = [str(column).strip() for column in data.columns]
    rows_before = len(data)
    data = data.loc[:, ~data.columns.str.match(r"^Unnamed(?::|\s|$)")]
    data = data.dropna(axis=1, how="all")
    duplicates_removed = 0
    if ID_COLUMN in data.columns:
        duplicates_removed = int(data[ID_COLUMN].duplicated().sum())
        data = data.drop_duplicates(subset=[ID_COLUMN], keep="first")
    else:
        duplicates_removed = int(data.duplicated().sum())
        data = data.drop_duplicates(keep="first")
    data = data.reset_index(drop=True)
    report = {
        "rows_before": int(rows_before),
        "rows_after": int(len(data)),
        "duplicates_removed": duplicates_removed,
        "missing_values": int(data.isna().sum().sum()),
        "column_count": int(len(data.columns)),
    }
    return data, report


def _number(value):
    return None if pd.isna(value) else float(value)


def _field_profile(series: pd.Series) -> dict:
    numeric = pd.to_numeric(series, errors="coerce")
    finite = numeric[np.isfinite(numeric)]
    infinite = int(np.isinf(numeric).sum())
    invalid = series.notna() & numeric.isna()
    cleaned = series.replace([np.inf, -np.inf], np.nan)
    profile = {
        "name": str(series.name),
        "dtype": str(series.dtype),
        "missing": int(series.isna().sum() + infinite),
        "missing_rate": float((series.isna().sum() + infinite) / max(len(series), 1)),
        "unique": int(cleaned.nunique(dropna=True)),
        "non_numeric": int(invalid.sum()),
        "infinite": infinite,
        "minus_one": int((numeric == -1).sum()),
        "numeric": None,
    }
    if len(finite):
        profile["numeric"] = {
            "mean": _number(finite.mean()),
            "std": _number(finite.std()),
            "min": _number(finite.min()),
            "max": _number(finite.max()),
        }
    return profile


def _dataset_profile(frame: pd.DataFrame) -> dict:
    return {"row_count": int(len(frame)), "fields": [_field_profile(frame[column]) for column in frame.columns]}


def _population_stability_index(train: pd.Series, test: pd.Series) -> float | None:
    train_values = pd.to_numeric(train, errors="coerce")
    test_values = pd.to_numeric(test, errors="coerce")
    train_values = train_values[np.isfinite(train_values)].to_numpy(dtype=float)
    test_values = test_values[np.isfinite(test_values)].to_numpy(dtype=float)
    if len(train_values) < 2 or len(test_values) == 0 or np.unique(train_values).size < 2:
        return None
    quantiles = np.unique(np.quantile(train_values, np.linspace(0, 1, 11)))
    if len(quantiles) < 2:
        return None
    bins = quantiles.copy()
    bins[0], bins[-1] = -np.inf, np.inf
    expected = np.histogram(train_values, bins=bins)[0] / len(train_values)
    actual = np.histogram(test_values, bins=bins)[0] / len(test_values)
    expected = np.clip(expected, 1e-6, None)
    actual = np.clip(actual, 1e-6, None)
    return float(np.sum((actual - expected) * np.log(actual / expected)))


def build_quality_report(train: pd.DataFrame, test: pd.DataFrame | None = None) -> dict:
    train_columns = {column for column in train.columns if column != LABEL_COLUMN}
    if test is None or test.empty:
        return {
            "train": _dataset_profile(train),
            "test": None,
            "schema": None,
            "drift": [],
            "drift_note": "未提供预测数据，跳过 schema 对比与 PSI 漂移分析",
        }
    test_columns = set(test.columns)
    common = [column for column in train.columns if column in test_columns and column not in {ID_COLUMN, LABEL_COLUMN}]
    type_mismatches = [
        column
        for column in common
        if pd.api.types.is_numeric_dtype(train[column]) != pd.api.types.is_numeric_dtype(test[column])
    ]
    drift = []
    for column in common:
        psi = _population_stability_index(train[column], test[column])
        status = "样本不足" if psi is None else "显著漂移" if psi >= 0.25 else "轻微漂移" if psi >= 0.1 else "稳定"
        drift.append({"name": column, "psi": psi, "status": status})
    drift.sort(key=lambda item: item["psi"] if item["psi"] is not None else -1, reverse=True)
    return {
        "train": _dataset_profile(train),
        "test": _dataset_profile(test),
        "schema": {
            "missing_in_test": sorted(train_columns - test_columns),
            "extra_in_test": sorted(test_columns - train_columns),
            "missing_in_train": sorted(test_columns - train_columns),
            "type_mismatches": type_mismatches,
        },
        "drift": drift,
        "drift_note": "PSI < 0.1 为稳定，0.1–0.25 为轻微漂移，≥ 0.25 为显著漂移；仅比较共同数值字段",
    }


def prepare_features(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    data.columns = [str(column).strip() for column in data.columns]
    data = data.loc[:, ~data.columns.str.match(r"^Unnamed(?::|\s|$)")]
    features = data.drop(columns=[ID_COLUMN, LABEL_COLUMN], errors="ignore")
    features = features.dropna(axis=1, how="all")
    for column in features.columns:
        features[column] = pd.to_numeric(features[column], errors="coerce")
    features = features.replace([float("inf"), float("-inf")], pd.NA)

    for target, source in ENGINEERED_FEATURES.items():
        if source in data.columns:
            values = pd.to_numeric(data[source], errors="coerce")
            if target in {"usage_change_rate", "monthly_fee_change_rate"}:
                values = values / 100.0
            features[target] = values
    return features
