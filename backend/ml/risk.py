def risk_level(probability: float) -> str:
    if probability >= 0.7:
        return "高风险"
    if probability >= 0.4:
        return "中风险"
    return "低风险"


def _actionable_feature(item: dict) -> tuple[str, str] | None:
    name = str(item.get("feature", ""))
    label = name
    unit = ""
    scale = 1.0
    if "客服" in name or "服务" in name or name == "service_call_count":
        label = "平均客户服务电话次数" if name == "service_call_count" else name
        action = "安排客服回访，逐项确认并闭环处理服务问题"
        unit = " 次"
    elif "掉线" in name or name == "dropped_call_count":
        label = "平均掉线语音呼叫数" if name == "dropped_call_count" else name
        action = "排查掉线及网络质量问题，并跟踪处理结果"
        unit = " 次"
    elif "费用" in name or "消费" in name or name == "monthly_fee_change_rate":
        action = "核对套餐与账单，提供更匹配实际需求的资费方案"
        if "百分比变化" in name or name == "monthly_fee_change_rate":
            label = "当月费用较前三个月平均值变化"
            unit = "%"
            scale = 100.0
        else:
            unit = " 元"
    elif "分钟" in name or "呼叫" in name or "通话" in name or name in {"usage_change_rate", "avg_call_minutes_3m"}:
        if name == "usage_change_rate":
            label = "当月使用分钟数较前三个月平均值变化"
        elif name == "avg_call_minutes_3m":
            label = "过去三个月的平均每月使用分钟数"
        action = "结合通信使用情况回访需求，推荐与实际使用量匹配的套餐"
        if "百分比变化" in name or name == "usage_change_rate":
            unit = "%"
            scale = 100.0
        else:
            unit = " 分钟"
    elif "设备" in name or "手机" in name:
        action = "提供终端检测或换机权益"
    else:
        return None

    reason = label
    value = item.get("feature_value")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        formatted = f"{value * scale:.2f}".rstrip("0").rstrip(".")
        reason = f"{label}为{formatted}{unit}"
    return reason, action


def retention_advice(probability: float, top_features: list[dict]) -> str:
    level = risk_level(probability)
    positive = [item for item in top_features if item.get("shap_value", 0) > 0]
    negative = [item for item in top_features if item.get("shap_value", 0) < 0]
    positive_details = [detail for item in positive if (detail := _actionable_feature(item)) is not None]
    negative_details = [detail for item in negative if (detail := _actionable_feature(item)) is not None]
    summary = f"该客户流失概率为{probability:.1%}，"

    if level == "低风险":
        if negative_details:
            return summary + f"{negative_details[0][0]}是当前主要保护因素，建议保持常规服务并持续关注使用变化。"
        return summary + "当前风险较低，建议保持常规服务并持续关注使用变化。"

    prefix = "建议优先挽留" if level == "高风险" else "建议主动关注"
    if positive_details:
        reasons = "、".join(reason for reason, _ in positive_details[:2])
        actions = list(dict.fromkeys(action for _, action in positive_details))
        advice = summary + f"主要受{reasons}影响，{prefix}：" + "；".join(actions[:3]) + "。"
    else:
        names = [str(item.get("feature")) for item in positive if item.get("feature")][:2]
        reason = "、".join(names) if names else "多项客户特征的综合变化"
        advice = summary + f"主要风险因素为{reason}，{prefix}结合客户画像开展个性化回访，确认需求并跟踪处理结果。"

    if negative_details:
        advice += f"同时，{negative_details[0][0]}，属于当前降低流失风险的因素，建议保持相关服务体验。"
    return advice
