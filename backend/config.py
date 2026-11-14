from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]


def _path(env_name: str, default: Path) -> Path:
    value = os.getenv(env_name)
    return Path(value) if value else default


@dataclass(frozen=True)
class Settings:
    database_path: Path
    artifact_dir: Path
    upload_dir: Path
    train_path: Path
    test_path: Path
    frontend_dist: Path

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_path=_path("CHURN_DB_PATH", ROOT_DIR / "data" / "churn.db"),
            artifact_dir=_path("CHURN_ARTIFACT_DIR", ROOT_DIR / "artifacts"),
            upload_dir=_path("CHURN_UPLOAD_DIR", ROOT_DIR / "data" / "uploads"),
            train_path=_path("CHURN_TRAIN_PATH", ROOT_DIR / "数据集" / "train.csv"),
            test_path=_path("CHURN_TEST_PATH", ROOT_DIR / "数据集" / "test.csv"),
            frontend_dist=_path("CHURN_FRONTEND_DIST", ROOT_DIR / "frontend" / "dist"),
        )
