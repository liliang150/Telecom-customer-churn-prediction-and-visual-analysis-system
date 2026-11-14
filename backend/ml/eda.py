from __future__ import annotations

import pandas as pd

from backend.ml.preprocessing import ID_COLUMN, LABEL_COLUMN


def _bin_rates(series: pd.Series, labels: pd.Series, count: int = 10) -> list[dict]:
    if len(series) < 2 or series.nunique(dropna=True) < 2:
        return [{"range": "全部", "rate": float(labels.mean()), "count": int(len(series))}]
    edges = None
    try:
        edges = pd.qcut(series, q=count, duplicates="drop", retbins=True)[1]
    except (ValueError, IndexError):
        edges = None
    if edges is None or len(edges) < 2:
        return [{"range": "全部", "rate": float(labels.mean()), "count": int(len(series))}]
    groups = pd.cut(series, bins=edges, include_lowest=True)
    stats = pd.DataFrame({"bin": groups, "label": labels}).groupby("bin", observed=True)["label"].agg(["mean", "count"])
    rows = [
        {
            "range": f"{interval.left:.4g} ~ {interval.right:.4g}",
            "rate": float(row["mean"]),
            "count": int(row["count"]),
        }
        for interval, row in stats.iterrows()
    ]
    return rows or [{"range": "全部", "rate": float(labels.mean()), "count": int(len(series))}]


def build_eda(frame: pd.DataFrame, top_features: int = 12, matrix_size: int = 10, bins: int = 10) -> dict:
    data = frame.copy()
    if LABEL_COLUMN not in data.columns:
        raise ValueError(f"数据缺少标签字段：{LABEL_COLUMN}")
    labels = pd.to_numeric(data[LABEL_COLUMN], errors="coerce")
    features = data.drop(columns=[ID_COLUMN, LABEL_COLUMN], errors="ignore").apply(pd.to_numeric, errors="coerce")

    scored = []
    for column in features.columns:
        if features[column].nunique(dropna=True) < 2:
            continue
        mask = features[column].notna() & labels.notna()
        if int(mask.sum()) < 3:
            continue
        value = features[column][mask].corr(labels[mask])
        if pd.isna(value):
            continue
        scored.append((column, float(value)))
    scored.sort(key=lambda item: abs(item[1]), reverse=True)
    selected = scored[:top_features]

    rows = []
    for column, correlation in selected:
        series = features[column]
        mask = series.notna() & labels.notna()
        filtered = series[mask]
        rows.append(
            {
                "feature": column,
                "correlation": correlation,
                "missing_rate": float(series.isna().mean()),
                "mean": float(filtered.mean()),
                "std": float(filtered.std()) if len(filtered) > 1 else 0.0,
                "bins": _bin_rates(filtered, labels[mask], bins),
            }
        )

    names = [item[0] for item in selected[:matrix_size]]
    matrix = features[names].corr().fillna(0).round(4).values.tolist() if names else []
    distribution = {str(int(key)): int(value) for key, value in labels.value_counts().sort_index().items()}
    return {
        "row_count": int(len(data)),
        "feature_count": int(len(features.columns)),
        "churn_rate": float(labels.mean()),
        "label_distribution": distribution,
        "features": rows,
        "correlation": {"features": names, "matrix": matrix},
        "note": "相关性为特征与流失标签的 Pearson 相关系数；分箱流失率按该特征的 10 个分位区间统计。",
    }
