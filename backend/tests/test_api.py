import io
import json
import os
import shutil
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.ml.training import train_models


@pytest.fixture(scope="module")
def client(sample_frame, tmp_path_factory):
    root = tmp_path_factory.mktemp("api")
    artifacts = root / "artifacts"
    train_path = root / "train.csv"
    test_path = root / "test.csv"
    sample_frame.to_csv(train_path, index=False)
    sample_frame.drop(columns=["是否流失"]).head(8).to_csv(test_path, index=False)
    trained = train_models(sample_frame, artifacts, quick=True)
    (artifacts / "active.json").write_text(json.dumps({"version": trained["version"]}), encoding="utf-8")

    import os
    os.environ["CHURN_DB_PATH"] = str(root / "test.db")
    os.environ["CHURN_ARTIFACT_DIR"] = str(artifacts)
    os.environ["CHURN_UPLOAD_DIR"] = str(root / "uploads")
    os.environ["CHURN_TRAIN_PATH"] = str(train_path)
    os.environ["CHURN_TEST_PATH"] = str(test_path)
    os.environ["CHURN_FRONTEND_DIST"] = str(root / "dist")

    from backend.main import create_app
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def auth(client):
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def submit_batch(client, auth, filename, content, timeout=120):
    response = client.post(
        "/api/predict/batch",
        files={"file": (filename, io.BytesIO(content), "text/csv")},
        headers=auth,
    )
    assert response.status_code == 202, response.text
    job = response.json()["data"]
    assert job["job_id"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/predict/batch/{job['job_id']}", headers=auth).json()["data"]
        if job["status"] in {"succeeded", "failed"}:
            break
        time.sleep(0.02)
    assert job["status"] == "succeeded", job.get("error")
    assert job["processed"] == job["total"]
    return job["result"]


def test_health_checks_real_dependencies(client):
    data = client.get("/api/health").json()["data"]
    assert data["status"] == "ok"
    assert data["database"] is True
    assert data["model_available"] is True


def test_login_rejects_invalid_password(client):
    response = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert response.status_code == 401


def test_data_overview_requires_auth_and_returns_real_counts(client, auth, sample_frame):
    assert client.get("/api/data/overview").status_code == 401
    response = client.get("/api/data/overview", headers=auth)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["train_rows"] == 240
    assert data["test_rows"] == 8
    expected = {str(int(key)): int(value) for key, value in sample_frame["是否流失"].value_counts().sort_index().items()}
    assert data["label_distribution"] == expected
    assert len(data["feature_columns"]) > 5


def test_feature_selection_experiment_compares_lasso_subsets(client, auth):
    response = client.post("/api/model/feature-selection", json={"quick": True}, headers=auth)
    assert response.status_code == 202
    job = response.json()["data"]
    assert job["job_id"]
    assert job["total"] == 3

    deadline = time.time() + 180
    while time.time() < deadline:
        job = client.get(f"/api/model/feature-selection/{job['job_id']}", headers=auth).json()["data"]
        if job["status"] in {"succeeded", "failed"}:
            break
        time.sleep(0.02)
    assert job["status"] == "succeeded", job.get("error")
    result = job["result"]
    assert len(result["results"]) == 3
    assert result["results"][0]["name"] == "全特征基线"
    assert all(0 <= item["auc"] <= 1 for item in result["results"])
    assert all(item["feature_count"] >= 1 for item in result["results"])
    assert all(item.get("skipped") or "recall" in item for item in result["results"])

    latest = client.get("/api/model/feature-selection", headers=auth).json()["data"]
    assert latest["results"] == result["results"]


def test_system_info_exposes_runtime_model_and_routes(client, auth):
    response = client.get("/api/system/info", headers=auth)
    assert response.status_code == 200
    data = response.json()["data"]

    assert data["name"]
    assert data["version"]
    assert data["python"]
    assert data["database"]["engine"] == "SQLite"
    assert data["model"]["version"]
    assert data["model"]["feature_count"] > 0
    assert data["dependencies"]["xgboost"]
    assert data["dependencies"]["shap"]
    assert data["modules"]

    paths = {route["path"] for route in data["routes"]}
    assert "/api/system/info" in paths
    assert "/api/model/explainability" in paths
    assert all(route["methods"] for route in data["routes"])


def test_data_eda_returns_correlations_and_bins(client, auth):
    response = client.get("/api/data/eda", headers=auth)
    assert response.status_code == 200
    data = response.json()["data"]

    assert data["row_count"] == 240
    assert 0 <= data["churn_rate"] <= 1
    assert data["features"]
    assert all(item["bins"] for item in data["features"])
    correlations = [abs(item["correlation"]) for item in data["features"]]
    assert correlations == sorted(correlations, reverse=True)

    matrix = data["correlation"]
    assert len(matrix["features"]) == len(matrix["matrix"])
    assert all(len(row) == len(matrix["features"]) for row in matrix["matrix"])


def test_feature_dependency_returns_points(client, auth):
    response = client.get("/api/analysis/dependency", headers=auth)
    assert response.status_code == 200
    data = response.json()["data"]

    assert data["feature"]
    assert data["features"]
    assert data["points"]
    assert {"value", "shap_value"} <= set(data["points"][0])

    selected = client.get("/api/analysis/dependency", params={"feature": data["feature"]}, headers=auth).json()["data"]
    assert selected["feature"] == data["feature"]
    assert client.get("/api/analysis/dependency", params={"feature": "不存在的特征"}, headers=auth).status_code == 404


def test_sample_and_model_evaluation(client, auth):
    sample = client.get("/api/data/sample", headers=auth).json()["data"]
    assert sample["customer_id"] == 0
    assert "平均月费用" in sample["record"]

    evaluation = client.get("/api/model/evaluate", headers=auth).json()["data"]
    assert evaluation["model_name"] == "XGBoost"
    assert evaluation["metrics"]["xgboost"]["auc"] >= 0.5
    assert evaluation["metrics"]["logistic_regression"]["pr_auc"] > 0


def test_model_explainability_reports_attribution_quality(client, auth):
    response = client.get("/api/model/explainability", headers=auth)
    assert response.status_code == 200
    data = response.json()["data"]

    top = data["concentration"]
    assert 0 < top["top10_share"] <= 1
    assert len(top["features"]) == min(10, len(top["features"]))
    assert all(item["importance"] >= 0 for item in top["features"])

    agreement = data["model_agreement"]
    assert agreement["total"] > 0
    assert 0 <= agreement["rate"] <= 1
    assert len(agreement["logistic_top_features"]) > 0

    assert data["sample_count"] > 0
    assert set(data["risk_groups"]) <= {"低风险", "中风险", "高风险"}
    assert sum(group["count"] for group in data["risk_groups"].values()) == data["sample_count"]
    for group in data["risk_groups"].values():
        assert group["top_features"]
        assert group["top_features"][0]["mean_abs_shap"] >= group["top_features"][-1]["mean_abs_shap"]


def test_evaluation_report_exports_markdown_summary(client, auth):
    response = client.get("/api/model/evaluation-report", headers=auth)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    report = response.content.decode("utf-8")

    assert "# 模型评估摘要" in report
    assert "核心指标对比" in report
    assert "| AUC |" in report
    assert "混淆矩阵" in report
    assert "解释性评估" in report
    assert "内部验证集" in report


def test_sensitivity_analysis_covers_multiple_depths(client, auth):
    response = client.post("/api/model/sensitivity", json={"quick": True}, headers=auth)
    assert response.status_code == 202
    job = response.json()["data"]
    assert job["job_id"]
    assert job["status"] in {"queued", "running"}
    assert job["total"] == 6

    deadline = time.time() + 120
    while time.time() < deadline:
        job = client.get(f"/api/model/sensitivity/{job['job_id']}", headers=auth).json()["data"]
        if job["status"] in {"succeeded", "failed"}:
            break
        time.sleep(0.02)
    assert job["status"] == "succeeded", job.get("error")
    result = job["result"]
    assert [item["max_depth"] for item in result["results"]] == [6, 8, 10, 12, 14, 16]
    assert all(0 <= item["auc"] <= 1 for item in result["results"])
    assert all(item["fit_seconds"] >= 0 for item in result["results"])
    assert all(0 <= item["recall"] <= 1 for item in result["results"])

    latest = client.get("/api/model/sensitivity", headers=auth).json()["data"]
    assert latest["results"] == result["results"]


def test_single_prediction_persists_shap_explanation(client, auth):
    record = client.get("/api/data/sample", headers=auth).json()["data"]["record"]
    response = client.post("/api/predict/churn", json={"record": record}, headers=auth)
    assert response.status_code == 200
    data = response.json()["data"]
    assert 0 <= data["probability"] <= 1
    assert data["top_features"]
    assert data["model_version"].startswith("v")

    explanation = client.get("/api/analysis/shap", params={"customer_id": 0}, headers=auth)
    assert explanation.status_code == 200
    assert explanation.json()["data"]["top_features"]


def test_global_shap_and_swarm_are_available(client, auth):
    response = client.get("/api/analysis/features", headers=auth)
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["global"]) > 0
    assert len(data["swarm"]) > 0


def test_batch_prediction_runs_as_background_job(client, auth, sample_frame):
    content = sample_frame.drop(columns=["是否流失"]).head(24).to_csv(index=False).encode()
    response = client.post(
        "/api/predict/batch",
        files={"file": ("customers.csv", io.BytesIO(content), "text/csv")},
        headers=auth,
    )
    assert response.status_code == 202
    job = response.json()["data"]
    assert job["job_id"]
    assert job["status"] in {"queued", "running"}
    assert job["total"] == 24
    assert job["processed"] == 0

    deadline = time.time() + 60
    while time.time() < deadline:
        job = client.get(f"/api/predict/batch/{job['job_id']}", headers=auth).json()["data"]
        if job["status"] in {"succeeded", "failed"}:
            break
        time.sleep(0.02)
    assert job["status"] == "succeeded", job.get("error")
    assert job["progress"] == 1
    assert job["processed"] == job["total"] == 24
    assert job["result"]["batch_id"]


def test_batch_prediction_risk_filter_and_export(client, auth, sample_frame):
    content = sample_frame.drop(columns=["是否流失"]).to_csv(index=False).encode()
    batch = submit_batch(client, auth, "customers.csv", content)
    assert batch["total"] == 240
    assert batch["batch_id"]

    risk = client.get(
        "/api/analysis/risk",
        params={"risk_level": "高风险", "page": 1, "page_size": 10},
        headers=auth,
    ).json()["data"]
    assert risk["total"] == batch["high"]
    assert len(risk["items"]) <= 10
    assert set(risk["distribution"]) == {"低风险", "中风险", "高风险"}

    exported = client.get(f"/api/predict/batches/{batch['batch_id']}/export", headers=auth)
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert len(exported.content.decode("utf-8-sig").splitlines()) == 241


def test_dashboard_uses_stored_predictions(client, auth, sample_frame):
    content = sample_frame.drop(columns=["是否流失"]).to_csv(index=False).encode()
    submit_batch(client, auth, "customers.csv", content)
    data = client.get("/api/analysis/dashboard", headers=auth).json()["data"]
    assert data["kpis"]["train_customers"] == 240
    assert data["kpis"]["predicted_customers"] >= 240
    assert len(data["probability_distribution"]) == 10
    assert len(data["risk_distribution"]) == 3
    assert data["kpis"]["high_risk_customers"] > 8
    assert len(data["high_risk_customers"]) == data["kpis"]["high_risk_customers"]
    assert all(item["risk_level"] == "高风险" for item in data["high_risk_customers"])
    probabilities = [item["probability"] for item in data["high_risk_customers"]]
    assert probabilities == sorted(probabilities, reverse=True)
    first_customer = data["high_risk_customers"][0]
    assert set(first_customer) == {"customer_id", "probability", "risk_level", "region", "monthly_fee", "top_features"}
    assert len(first_customer["top_features"]) == 1
    assert set(first_customer["top_features"][0]) == {"feature"}


def test_dashboard_filters_by_selected_batch(client, auth, sample_frame):
    predict_frame = sample_frame.drop(columns=["是否流失"])
    first = submit_batch(client, auth, "first.csv", predict_frame.to_csv(index=False).encode())
    second = submit_batch(client, auth, "second.csv", predict_frame.iloc[:120].to_csv(index=False).encode())

    latest = client.get("/api/analysis/dashboard", headers=auth).json()["data"]
    assert latest["batch_id"] == second["batch_id"]
    assert latest["kpis"]["predicted_customers"] == 120

    selected = client.get(f"/api/analysis/dashboard?batch_id={first['batch_id']}", headers=auth).json()["data"]
    assert selected["batch_id"] == first["batch_id"]
    assert selected["kpis"]["predicted_customers"] == first["total"]
    assert selected["kpis"]["high_risk_customers"] == first["high"]


def test_dashboard_skips_unused_quality_report(client, auth, monkeypatch):
    data_service = client.app.state.data_service
    original_overview = data_service.overview
    calls = []

    def tracked_overview():
        calls.append(1)
        return original_overview()

    monkeypatch.setattr(data_service, "overview", tracked_overview)
    response = client.get("/api/analysis/dashboard", headers=auth)
    assert response.status_code == 200
    assert calls == []


def test_upload_rejects_training_data_without_label(client, auth, sample_frame):
    content = sample_frame.drop(columns=["是否流失"]).to_csv(index=False).encode()
    response = client.post(
        "/api/data/upload?kind=train",
        files={"file": ("invalid.csv", io.BytesIO(content), "text/csv")},
        headers=auth,
    )
    assert response.status_code == 422
    assert "是否流失" in response.json()["detail"]


def test_upload_rejects_prediction_data_missing_required_features(client, auth, sample_frame):
    content = sample_frame.drop(columns=["是否流失", "平均月费用"]).to_csv(index=False).encode()
    response = client.post(
        "/api/data/upload?kind=predict",
        files={"file": ("invalid.csv", io.BytesIO(content), "text/csv")},
        headers=auth,
    )
    assert response.status_code == 422
    assert "平均月费用" in response.json()["detail"]


def test_data_upload_confirmation_creates_restorable_versions(sample_frame, tmp_path):
    from backend.services import DataService

    train_path = tmp_path / "train.csv"
    test_path = tmp_path / "test.csv"
    sample_frame.to_csv(train_path, index=False)
    sample_frame.drop(columns=["是否流失"]).to_csv(test_path, index=False)
    service = DataService(train_path, test_path, tmp_path / "uploads")
    first = sample_frame.copy()
    first["平均月费用"] = first["平均月费用"] + 10
    second = sample_frame.copy()
    second["平均月费用"] = second["平均月费用"] + 20

    first_name = service.save_upload("first.csv", first.to_csv(index=False).encode())
    assert service.train()["平均月费用"].tolist() == pytest.approx(sample_frame["平均月费用"].tolist())
    first_version = service.confirm_upload(first_name, "train")
    second_name = service.save_upload("second.csv", second.to_csv(index=False).encode())
    service.confirm_upload(second_name, "train")

    assert len(service.versions()) == 2
    restored = service.activate_version(first_version["version"])
    assert restored["active"] is True
    assert service.train()["平均月费用"].tolist() == pytest.approx(first["平均月费用"].tolist())
    assert service.active_version() == first_version["version"]


def test_data_upload_api_waits_for_confirmation(client, auth, sample_frame):
    train_path = Path(os.environ["CHURN_TRAIN_PATH"])
    original = train_path.read_bytes()
    versions_dir = train_path.parent / "versions"
    content = sample_frame.head(24).to_csv(index=False).encode()
    try:
        uploaded = client.post(
            "/api/data/upload?kind=train",
            files={"file": ("replacement.csv", io.BytesIO(content), "text/csv")},
            headers=auth,
        )
        assert uploaded.status_code == 200
        staged = uploaded.json()["data"]
        assert staged["status"] == "pending"
        assert train_path.read_bytes() == original

        confirmed = client.post(
            "/api/data/confirm",
            json={"saved_name": staged["saved_name"], "kind": "train"},
            headers=auth,
        )
        assert confirmed.status_code == 200
        version = confirmed.json()["data"]
        assert version["active"] is True
        assert version["train_rows"] == 24
        assert client.get("/api/data/overview", headers=auth).json()["data"]["train_rows"] == 24
        versions = client.get("/api/data/versions", headers=auth).json()["data"]
        assert versions[0]["version"] == version["version"]
    finally:
        train_path.write_bytes(original)
        if versions_dir.exists():
            shutil.rmtree(versions_dir)


def test_model_versions_are_listed(client, auth):
    data = client.get("/api/model/versions", headers=auth).json()["data"]
    assert len(data) >= 1
    assert data[0]["active"] is True
    assert data[0]["training_data_hash"]


def test_model_version_delete_protects_active_and_removes_candidate(client, auth):
    artifact_dir = Path(os.environ["CHURN_ARTIFACT_DIR"])
    active = json.loads((artifact_dir / "active.json").read_text(encoding="utf-8"))["version"]
    candidate = "v20261103999999999999"
    candidate_dir = artifact_dir / candidate
    try:
        shutil.copytree(artifact_dir / active, candidate_dir)
        metadata_path = candidate_dir / "metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["version"] = candidate
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

        assert client.delete(f"/api/model/versions/{candidate}").status_code == 401
        protected = client.delete(f"/api/model/versions/{active}", headers=auth)
        assert protected.status_code == 409
        assert (artifact_dir / active).is_dir()

        deleted = client.delete(f"/api/model/versions/{candidate}", headers=auth)
        assert deleted.status_code == 200
        assert deleted.json()["data"] == {"version": candidate, "deleted": True}
        assert not candidate_dir.exists()
        versions = client.get("/api/model/versions", headers=auth).json()["data"]
        assert candidate not in {item["version"] for item in versions}
        assert client.delete(f"/api/model/versions/{candidate}", headers=auth).status_code == 404
    finally:
        if candidate_dir.exists():
            shutil.rmtree(candidate_dir)


def test_training_job_service_rejects_duplicate_tasks(tmp_path):
    from backend.services import TrainingAlreadyRunningError, TrainingJobService

    started = threading.Event()
    release = threading.Event()

    def fake_train(*args, **kwargs):
        started.set()
        release.wait(timeout=5)
        return {"version": "v-candidate"}

    data_service = type("DataServiceStub", (), {"train": lambda self: None})()
    service = TrainingJobService(data_service, tmp_path, trainer=fake_train)
    job = service.submit(quick=True)
    assert started.wait(timeout=2)
    with pytest.raises(TrainingAlreadyRunningError):
        service.submit(quick=True)
    release.set()
    for _ in range(100):
        status = service.status(job["job_id"])
        if status["status"] in {"succeeded", "failed"}:
            break
        time.sleep(0.02)
    assert status["status"] == "succeeded"
    assert status["result"]["version"] == "v-candidate"


def test_training_api_creates_candidate_and_activates_only_after_confirmation(client, auth, monkeypatch):
    artifact_dir = Path(os.environ["CHURN_ARTIFACT_DIR"])
    pointer = artifact_dir / "active.json"
    original = json.loads(pointer.read_text(encoding="utf-8"))["version"]
    candidate = "v-candidate-confirmation"
    shutil.copytree(artifact_dir / original, artifact_dir / candidate)
    candidate_metadata_path = artifact_dir / candidate / "metadata.json"
    candidate_metadata = json.loads(candidate_metadata_path.read_text(encoding="utf-8"))
    candidate_metadata["version"] = candidate
    candidate_metadata_path.write_text(json.dumps(candidate_metadata), encoding="utf-8")

    def fake_train(*args, **kwargs):
        return {"version": candidate, "metrics": candidate_metadata["metrics"]}

    monkeypatch.setattr("backend.api.model.train_models", fake_train)
    monkeypatch.setattr("backend.services.train_models", fake_train, raising=False)
    try:
        response = client.post("/api/model/train", json={"quick": True}, headers=auth)
        assert response.status_code == 202
        job_id = response.json()["data"]["job_id"]
        for _ in range(100):
            job = client.get(f"/api/model/train/{job_id}", headers=auth).json()["data"]
            if job["status"] in {"succeeded", "failed"}:
                break
            time.sleep(0.02)
        assert job["status"] == "succeeded"
        assert job["result"]["version"] == candidate
        assert json.loads(pointer.read_text(encoding="utf-8"))["version"] == original

        confirmed = client.post("/api/model/activate", json={"version": candidate}, headers=auth)
        assert confirmed.status_code == 200
        assert json.loads(pointer.read_text(encoding="utf-8"))["version"] == candidate
    finally:
        pointer.write_text(json.dumps({"version": original}), encoding="utf-8")


def test_historical_shap_snapshot_does_not_depend_on_active_model(client, auth):
    record = client.get("/api/data/sample", headers=auth).json()["data"]["record"]
    prediction = client.post("/api/predict/churn", json={"record": record}, headers=auth).json()["data"]
    pointer = Path(os.environ["CHURN_ARTIFACT_DIR"]) / "active.json"
    original = pointer.read_text(encoding="utf-8")
    try:
        pointer.write_text(json.dumps({"version": "v-missing"}), encoding="utf-8")
        response = client.get("/api/analysis/shap", params={"customer_id": prediction["customer_id"]}, headers=auth)
        assert response.status_code == 200
        snapshot = response.json()["data"]
        assert snapshot["top_features"] == prediction["top_features"]
        assert snapshot["base_value"] == prediction["base_value"]
        assert snapshot["model_version"] == prediction["model_version"]
    finally:
        pointer.write_text(original, encoding="utf-8")


def test_single_explanation_regenerates_advice_from_stored_shap(client, auth):
    import sqlite3

    record = client.get("/api/data/sample", headers=auth).json()["data"]["record"]
    prediction = client.post("/api/predict/churn", json={"record": record}, headers=auth).json()["data"]
    with sqlite3.connect(os.environ["CHURN_DB_PATH"]) as connection:
        connection.execute("UPDATE predictions SET advice = '旧通用建议' WHERE customer_id = ?", (str(prediction["customer_id"]),))

    advice = client.get("/api/analysis/shap", params={"customer_id": prediction["customer_id"]}, headers=auth).json()["data"]["advice"]

    assert advice != "旧通用建议"
    assert f"{prediction['probability']:.1%}" in advice


def test_batch_outputs_regenerate_advice_from_stored_shap(client, auth, sample_frame):
    import sqlite3

    content = sample_frame.drop(columns=["是否流失"]).head(12).to_csv(index=False).encode()
    batch_id = submit_batch(client, auth, "customers.csv", content)["batch_id"]
    with sqlite3.connect(os.environ["CHURN_DB_PATH"]) as connection:
        connection.execute("UPDATE predictions SET advice = '旧通用建议' WHERE batch_id = ?", (batch_id,))

    items = client.get("/api/analysis/risk", params={"batch_id": batch_id, "page_size": 20}, headers=auth).json()["data"]["items"]
    exported = client.get(f"/api/predict/batches/{batch_id}/export", headers=auth).content.decode("utf-8-sig")

    assert items
    assert all(item["advice"] != "旧通用建议" for item in items)
    assert all(f"{item['probability']:.1%}" in item["advice"] for item in items)
    assert "旧通用建议" not in exported
    assert "该客户流失概率为" in exported


def test_data_version_only_preserves_actually_uploaded_train_data(client, auth, sample_frame):
    """数据版本只保存用户实际上传的训练数据，不假设/保存默认 test.csv。"""
    train_path = Path(os.environ["CHURN_TRAIN_PATH"])
    test_path = Path(os.environ["CHURN_TEST_PATH"])
    original_train = train_path.read_bytes()
    original_test = test_path.read_bytes()
    versions_dir = train_path.parent / "versions"
    try:
        # 准备一个不同的 test.csv，确认版本恢复不会动它
        test_path.write_bytes(b"fake,test\n1,2\n3,4\n")
        content = sample_frame.head(24).to_csv(index=False).encode()
        uploaded = client.post(
            "/api/data/upload?kind=train",
            files={"file": ("train_v2.csv", io.BytesIO(content), "text/csv")},
            headers=auth,
        )
        confirmed = client.post(
            "/api/data/confirm",
            json={"saved_name": uploaded.json()["data"]["saved_name"], "kind": "train"},
            headers=auth,
        )
        version = confirmed.json()["data"]
        version_dir = versions_dir / version["version"]

        # 版本目录只有 train.csv，没有 test.csv
        assert (version_dir / "train.csv").is_file()
        assert not (version_dir / "test.csv").is_file(), "版本不应保存默认 test.csv"

        # metadata 只带 train 信息，没有 test_rows
        assert "train_rows" in version
        assert "test_rows" not in version, "版本元数据不应包含默认预测数据行数"
        assert "test_hash" not in version

        # 恢复版本只恢复 train.csv，不碰 test.csv
        test_path.write_bytes(b"another,fake\n5,6\n7,8\n")
        client.post("/api/data/versions/activate", json={"version": version["version"]}, headers=auth)
        assert test_path.read_bytes() == b"another,fake\n5,6\n7,8\n", "恢复版本不应改变 test.csv"
    finally:
        train_path.write_bytes(original_train)
        test_path.write_bytes(original_test)
        if versions_dir.exists():
            shutil.rmtree(versions_dir)


def test_overview_survives_missing_test_csv(client, auth):
    """test.csv 不存在时，overview 不应崩溃，test_rows 为 null。"""
    test_path = Path(os.environ["CHURN_TEST_PATH"])
    existed = test_path.is_file()
    backup = test_path.read_bytes() if existed else None
    try:
        if existed:
            test_path.unlink()
        resp = client.get("/api/data/overview", headers=auth)
        assert resp.status_code == 200
        data = resp.json()["data"]
        # test_rows 应该不存在或为 null，不应是假数字
        assert "test_rows" not in data or data["test_rows"] is None
        # quality_report 必须完整返回
        assert "quality_report" in data
        qr = data["quality_report"]
        assert "train" in qr  # train 质量报告必须有
        # drift 可以为空或不存在，因为没有 test 数据
        assert "drift" in qr
        # test.tab 字段不应出现在前端需要的地方——这里只确认不崩
    finally:
        if existed and backup is not None:
            test_path.write_bytes(backup)


def test_sample_returns_empty_when_no_test_csv(client, auth):
    """test.csv 不存在时，sample 接口返回空 record 而非崩溃。"""
    test_path = Path(os.environ["CHURN_TEST_PATH"])
    existed = test_path.is_file()
    backup = test_path.read_bytes() if existed else None
    try:
        if existed:
            test_path.unlink()
        resp = client.get("/api/data/sample", headers=auth)
        # 不应崩溃，返回 200 + 空 record 或 404 + 友好信息
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            data = resp.json()["data"]
            assert isinstance(data.get("record", {}), dict)
    finally:
        if existed and backup is not None:
            test_path.write_bytes(backup)
