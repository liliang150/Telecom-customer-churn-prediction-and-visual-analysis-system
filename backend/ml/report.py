from __future__ import annotations


def _number(value, digits: int = 4) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _percent(value, digits: int = 2) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return str(value)


def build_evaluation_report(metadata: dict, explainability: dict | None = None, sensitivity: dict | None = None) -> str:
    lines: list[str] = ["# 模型评估摘要", ""]
    lines.append(f"- 模型版本：`{metadata.get('version', '—')}`")
    lines.append(f"- 模型名称：{metadata.get('model_name', 'XGBoost')}")
    lines.append(f"- 训练时间：{metadata.get('created_at', '—')}")
    lines.append(f"- 训练数据：{metadata.get('rows', '—')} 行")
    split = metadata.get("data_split") or {}
    if split:
        lines.append(
            f"- 数据划分：拟合 {split.get('fit_rows', '—')} / 校准 {split.get('calibration_rows', '—')} / 内部验证 {split.get('validation_rows', '—')}"
        )
    lines.append(f"- 评估范围：{metadata.get('evaluation_scope', '内部验证集')}")
    lines.append("")

    metrics = metadata.get("metrics") or {}
    lines.append("## 核心指标对比")
    lines.append("")
    lines.append("| 指标 | XGBoost | 逻辑回归 |")
    lines.append("| --- | --- | --- |")
    for label, key, digits in (
        ("AUC", "auc", 4),
        ("PR-AUC", "pr_auc", 4),
        ("Recall", "recall", 4),
        ("Precision", "precision", 4),
        ("F1", "f1", 4),
        ("KS", "ks", 4),
        ("Brier", "brier", 4),
        ("分类阈值", "threshold", 4),
    ):
        xgboost = (metrics.get("xgboost") or {}).get(key)
        logistic = (metrics.get("logistic_regression") or {}).get(key)
        lines.append(f"| {label} | {_number(xgboost, digits)} | {_number(logistic, digits)} |")
    lines.append("")

    lines.append("## 混淆矩阵")
    lines.append("")
    for key, label in (("xgboost", "XGBoost"), ("logistic_regression", "逻辑回归")):
        item = metrics.get(key) or {}
        matrix = item.get("confusion_matrix")
        if not matrix:
            continue
        lines.append(f"**{label}**（阈值 {_number(item.get('threshold'))}）")
        lines.append("")
        lines.append("| 真实 \\ 预测 | 未流失 | 已流失 |")
        lines.append("| --- | --- | --- |")
        lines.append(f"| 未流失 | {matrix[0][0]} | {matrix[0][1]} |")
        lines.append(f"| 已流失 | {matrix[1][0]} | {matrix[1][1]} |")
        lines.append("")

    cross_validation = metadata.get("cross_validation") or {}
    if cross_validation:
        lines.append("## 交叉验证")
        lines.append("")
        lines.append("| 模型 | 折数 | AUC 均值 | AUC 标准差 |")
        lines.append("| --- | --- | --- | --- |")
        for key, label in (("xgboost", "XGBoost"), ("logistic_regression", "逻辑回归")):
            item = cross_validation.get(key)
            if item:
                lines.append(
                    f"| {label} | {item.get('folds', '—')} | {_number(item.get('auc_mean'))} | {_number(item.get('auc_std'))} |"
                )
        lines.append("")

    if explainability:
        lines.append("## 解释性评估")
        lines.append("")
        concentration = explainability.get("concentration") or {}
        agreement = explainability.get("model_agreement") or {}
        lines.append(f"- 归因集中度（前 10 个特征占全部平均 |SHAP|）：{_percent(concentration.get('top10_share'))}")
        lines.append(
            f"- 模型一致率：{agreement.get('overlap', '—')} / {agreement.get('total', '—')}（{_percent(agreement.get('rate'))}）"
        )
        lines.append(f"- 评估样本数：{explainability.get('sample_count', '—')}")
        lines.append("")
        groups = explainability.get("risk_groups") or {}
        if groups:
            lines.append("| 风险等级 | 样本数 | Top 3 归因因素 |")
            lines.append("| --- | --- | --- |")
            for level in ("低风险", "中风险", "高风险"):
                group = groups.get(level)
                if not group:
                    continue
                names = "、".join(item["feature"] for item in group.get("top_features", [])[:3])
                lines.append(f"| {level} | {group.get('count', '—')} | {names} |")
            lines.append("")

    if sensitivity and sensitivity.get("results"):
        lines.append("## 参数敏感性分析")
        lines.append("")
        lines.append(f"- 实验数据：{sensitivity.get('sample_rows', '—')} 行 · {sensitivity.get('feature_count', '—')} 个特征")
        lines.append("")
        lines.append("| 最大树深 | AUC | Recall | Precision | F1 | 训练耗时（秒） |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for item in sensitivity["results"]:
            lines.append(
                f"| {item.get('max_depth')} | {_number(item.get('auc'))} | {_number(item.get('recall'))} | "
                f"{_number(item.get('precision'))} | {_number(item.get('f1'))} | {_number(item.get('fit_seconds'), 1)} |"
            )
        lines.append("")
        if sensitivity.get("note"):
            lines.append(f"> {sensitivity['note']}")
            lines.append("")

    lines.append("## 说明")
    lines.append("")
    lines.append("- 上述指标均来自内部验证集，该部分样本未参与模型拟合、概率校准或阈值选择。")
    lines.append("- SHAP 反映模型预测依据，不代表业务因果关系。")
    lines.append("- 参数敏感性实验仅改变最大树深，其余参数与数据划分保持一致。")
    lines.append("- 若训练数据或模型版本发生变化，请重新训练后再次导出本摘要。")
    return "\n".join(lines)
