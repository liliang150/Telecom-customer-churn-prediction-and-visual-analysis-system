import joblib
import numpy as np
import pytest
from sklearn.metrics import f1_score, precision_score, recall_score

from backend.ml.prediction import ChurnPredictor
from backend.ml.training import optimize_threshold, train_models


def _brute_force_threshold(labels, probabilities, min_recall):
    labels = np.asarray(labels, dtype=int)
    probabilities = np.asarray(probabilities, dtype=float)
    rows = []
    for threshold in np.unique(np.concatenate(([0.0], probabilities, [1.0]))):
        predictions = (probabilities >= threshold).astype(int)
        rows.append(
            {
                "threshold": float(threshold),
                "recall": float(recall_score(labels, predictions, zero_division=0)),
                "precision": float(precision_score(labels, predictions, zero_division=0)),
                "f1": float(f1_score(labels, predictions, zero_division=0)),
            }
        )
    eligible = [row for row in rows if row["recall"] >= min_recall]
    return max(eligible or rows, key=lambda row: (row["f1"], row["precision"], row["recall"], -row["threshold"]))



def test_training_saves_versioned_bundle_and_explains_prediction(sample_frame, tmp_path):
    result = train_models(sample_frame, tmp_path, quick=True)

    assert (tmp_path / result["version"] / "model.joblib").is_file()
    assert result["metrics"]["xgboost"]["auc"] >= 0.5
    assert result["metrics"]["logistic_regression"]["pr_auc"] > 0
    assert result["cross_validation"]["xgboost"]["folds"] == 2
    assert result["cross_validation"]["logistic_regression"]["auc_mean"] > 0
    assert result["evaluation_scope"] == "内部验证集（未参与模型拟合、概率校准或阈值选择）"
    assert result["validation_rows"] == 60
    assert result["data_split"] == {"fit_rows": 120, "calibration_rows": 60, "validation_rows": 60}
    assert result["calibration"]["method"] == "sigmoid"
    assert result["threshold_optimization"]["xgboost"]["optimized_on"] == "校准集"
    assert result["threshold"] == result["metrics"]["xgboost"]["threshold"]
    assert result["feature_columns"]
    assert "客户ID" not in result["feature_columns"]
    assert len(result["global_shap"]) > 0

    bundle = joblib.load(tmp_path / result["version"] / "model.joblib")
    predictor = ChurnPredictor(bundle)
    prediction = predictor.predict(sample_frame.iloc[[0]].drop(columns=["是否流失"]))
    matrix = predictor._matrix(sample_frame.iloc[[0]].drop(columns=["是否流失"]))
    calibrated_probability = bundle["calibrated_model"].predict_proba(matrix)[0, 1]
    assert prediction["probability"] == calibrated_probability
    assert 0 <= prediction["probability"] <= 1
    assert prediction["risk_level"] in {"低风险", "中风险", "高风险"}
    assert len(prediction["top_features"]) > 0
    assert "base_value" in prediction


def test_threshold_optimization_meets_recall_target():
    labels = np.array([0, 0, 0, 1, 1, 1])
    probabilities = np.array([0.1, 0.2, 0.6, 0.4, 0.55, 0.8])

    result = optimize_threshold(labels, probabilities, min_recall=1.0)

    assert result["threshold"] <= 0.4
    assert result["recall"] == 1.0
    assert result["target_met"] is True


def test_threshold_optimization_matches_brute_force_selection():
    rng = np.random.default_rng(2026)
    labels = rng.integers(0, 2, 500)
    probabilities = np.round(rng.random(500), 2)

    actual = optimize_threshold(labels, probabilities, min_recall=0.75)
    expected = _brute_force_threshold(labels, probabilities, 0.75)

    assert actual["threshold"] == pytest.approx(expected["threshold"])
    assert actual["recall"] == pytest.approx(expected["recall"])
    assert actual["precision"] == pytest.approx(expected["precision"])
    assert actual["f1"] == pytest.approx(expected["f1"])
    assert actual["target_met"] is True
