import pytest

from backend.ml.risk import retention_advice, risk_level


@pytest.mark.parametrize(
    ("probability", "expected"),
    [(0.0, "低风险"), (0.3999, "低风险"), (0.4, "中风险"), (0.6999, "中风险"), (0.7, "高风险"), (1.0, "高风险")],
)
def test_risk_level_uses_business_thresholds(probability, expected):
    assert risk_level(probability) == expected


def test_retention_advice_uses_top_positive_reasons():
    reasons = [
        {"feature": "平均客户服务电话次数", "shap_value": 0.3},
        {"feature": "当月使用分钟数与前三个月平均值的百分比变化", "shap_value": 0.2},
    ]
    advice = retention_advice(0.82, reasons)
    assert "优先" in advice
    assert "客服" in advice
    assert "使用" in advice


def test_retention_advice_includes_probability_and_actual_fee():
    reasons = [{"feature": "平均月费用", "feature_value": 189.5, "shap_value": 0.4}]

    advice = retention_advice(0.92, reasons)

    assert "92.0%" in advice
    assert "189.5 元" in advice
    assert "资费" in advice


def test_retention_advice_uses_actual_service_call_count():
    reasons = [{"feature": "平均客户服务电话次数", "feature_value": 4.0, "shap_value": 0.3}]

    advice = retention_advice(0.81, reasons)

    assert "4 次" in advice
    assert "客服回访" in advice


def test_retention_advice_mentions_protective_factor():
    reasons = [
        {"feature": "平均月费用", "feature_value": 125.0, "shap_value": 0.4},
        {"feature": "每月平均使用分钟数", "feature_value": 620.0, "shap_value": -0.2},
    ]

    advice = retention_advice(0.76, reasons)

    assert "620 分钟" in advice
    assert "降低流失风险" in advice
    assert "保持" in advice


def test_retention_advice_fallback_still_identifies_customer_reason():
    reasons = [{"feature": "地理区域", "feature_value": 16.0, "shap_value": 0.3}]

    advice = retention_advice(0.82, reasons)

    assert "82.0%" in advice
    assert "地理区域" in advice
    assert "个性化回访" in advice
