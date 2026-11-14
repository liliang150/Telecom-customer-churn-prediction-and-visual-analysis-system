from __future__ import annotations

import numpy as np
import pandas as pd
import shap

from backend.ml.preprocessing import prepare_features
from backend.ml.risk import retention_advice, risk_level


class ChurnPredictor:
    def __init__(self, bundle: dict):
        self.bundle = bundle
        self.model = bundle["model"]
        self.probability_model = bundle.get("calibrated_model", self.model)
        self.feature_columns = bundle["feature_columns"]
        self.explainer = shap.TreeExplainer(self.model.named_steps["classifier"])

    def _matrix(self, frame: pd.DataFrame) -> pd.DataFrame:
        features = prepare_features(frame)
        return features.reindex(columns=self.feature_columns)

    def predict(self, frame: pd.DataFrame) -> dict:
        if len(frame) != 1:
            raise ValueError("单客户预测需要且只能输入一条记录")
        matrix = self._matrix(frame)
        transformed = self.model.named_steps["imputer"].transform(matrix)
        probability = float(self.probability_model.predict_proba(matrix)[0, 1])
        values = np.asarray(self.explainer.shap_values(transformed))[0]
        expected = self.explainer.expected_value
        base_value = float(np.asarray(expected).reshape(-1)[-1])
        contributions = [
            {
                "feature": name,
                "feature_value": float(matrix.iloc[0][name]) if pd.notna(matrix.iloc[0][name]) else None,
                "shap_value": float(value),
            }
            for name, value in zip(self.feature_columns, values)
        ]
        contributions.sort(key=lambda item: abs(item["shap_value"]), reverse=True)
        top_features = contributions[:12]
        return {
            "probability": probability,
            "risk_level": risk_level(probability),
            "top_features": top_features,
            "base_value": base_value,
            "output_value": base_value + float(values.sum()),
            "advice": retention_advice(probability, top_features),
        }

    def predict_batch(self, frame: pd.DataFrame) -> tuple[np.ndarray, pd.DataFrame]:
        matrix = self._matrix(frame)
        probabilities = self.probability_model.predict_proba(matrix)[:, 1]
        return probabilities, matrix
