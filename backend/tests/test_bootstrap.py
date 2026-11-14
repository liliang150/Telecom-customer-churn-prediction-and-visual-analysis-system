import json
import subprocess
import sys
from pathlib import Path

from sqlalchemy import func, select

from backend.database import PredictionBatch, create_session_factory
from scripts.bootstrap import main


def test_bootstrap_script_supports_direct_execution():
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "scripts/bootstrap.py", "--help"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_bootstrap_is_idempotent(sample_frame, tmp_path, monkeypatch):
    artifacts = tmp_path / "artifacts"
    database = tmp_path / "bootstrap.db"
    train = tmp_path / "train.csv"
    test = tmp_path / "test.csv"
    sample_frame.to_csv(train, index=False)
    sample_frame.drop(columns=["是否流失"]).head(8).to_csv(test, index=False)
    monkeypatch.setenv("CHURN_DB_PATH", str(database))
    monkeypatch.setenv("CHURN_ARTIFACT_DIR", str(artifacts))
    monkeypatch.setenv("CHURN_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("CHURN_TRAIN_PATH", str(train))
    monkeypatch.setenv("CHURN_TEST_PATH", str(test))

    assert main(["--quick"]) == 0
    active = json.loads((artifacts / "active.json").read_text(encoding="utf-8"))
    assert active["version"]
    assert main(["--quick"]) == 0

    engine, sessions = create_session_factory(database)
    with sessions() as session:
        assert session.scalar(select(func.count(PredictionBatch.id))) == 1
    engine.dispose()
