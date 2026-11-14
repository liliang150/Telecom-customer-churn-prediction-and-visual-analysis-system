from __future__ import annotations

import json
import re
import shutil
import threading
from pathlib import Path

import joblib


class ModelNotReadyError(RuntimeError):
    pass


class ActiveModelDeletionError(RuntimeError):
    pass


class ArtifactStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, dict] = {}
        self._lock = threading.Lock()

    @property
    def active_pointer(self) -> Path:
        return self.root / "active.json"

    def active_version(self) -> str | None:
        if not self.active_pointer.exists():
            return None
        try:
            return json.loads(self.active_pointer.read_text(encoding="utf-8"))["version"]
        except (json.JSONDecodeError, KeyError, OSError):
            return None

    def activate(self, version: str) -> None:
        with self._lock:
            if not (self.root / version / "model.joblib").is_file():
                raise FileNotFoundError(f"模型版本不存在：{version}")
            temporary = self.root / "active.tmp"
            temporary.write_text(json.dumps({"version": version}), encoding="utf-8")
            temporary.replace(self.active_pointer)

    def delete(self, version: str) -> None:
        if not re.fullmatch(r"v\d{20}", version):
            raise FileNotFoundError(f"模型版本不存在：{version}")
        with self._lock:
            if version == self.active_version():
                raise ActiveModelDeletionError("当前上线模型不能删除")
            path = self.root / version
            if not (path / "model.joblib").is_file():
                raise FileNotFoundError(f"模型版本不存在：{version}")
            shutil.rmtree(path)
            self._cache.pop(version, None)

    def load_active(self) -> dict:
        version = self.active_version()
        if not version:
            raise ModelNotReadyError("尚未上线模型，请先完成模型训练")
        with self._lock:
            if version not in self._cache:
                path = self.root / version / "model.joblib"
                if not path.is_file():
                    raise ModelNotReadyError("当前模型文件不可用，请重新训练或切换版本")
                self._cache[version] = joblib.load(path)
            return self._cache[version]

    def explanations(self) -> dict:
        version = self.active_version()
        if not version:
            raise ModelNotReadyError("尚未上线模型")
        path = self.root / version / "explanations.json"
        if not path.is_file():
            raise ModelNotReadyError("当前模型缺少 SHAP 解释产物")
        return json.loads(path.read_text(encoding="utf-8"))

    def versions(self) -> list[dict]:
        active = self.active_version()
        records = []
        for path in sorted(self.root.glob("v*/metadata.json"), reverse=True):
            metadata = json.loads(path.read_text(encoding="utf-8"))
            metadata["active"] = metadata["version"] == active
            records.append(metadata)
        records.sort(key=lambda item: item["created_at"], reverse=True)
        return records
