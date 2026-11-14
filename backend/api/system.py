from __future__ import annotations

import platform
import sys

from fastapi import APIRouter, Depends, Request

from backend.dependencies import get_current_user
from backend.schemas import success

router = APIRouter(prefix="/api/system", tags=["系统信息"])

MODULES = [
    {"name": "风险总览", "description": "按预测批次汇总客户风险规模、概率分布、区域差异与高风险客户清单。"},
    {"name": "重点客户", "description": "按风险等级、区域、费用和客户编号筛选客户，并可查看单客户 SHAP 归因。"},
    {"name": "特征分析", "description": "展示全局 SHAP 重要性、蜂群图和单特征依赖关系。"},
    {"name": "流失预测", "description": "支持单客户实时预测与批量文件预测，批量任务在后台执行并可查看进度。"},
    {"name": "数据与模型", "description": "管理训练数据版本、模型版本、模型评估、解释性评估与参数敏感性实验。"},
    {"name": "系统信息", "description": "展示运行时环境、当前模型与数据版本、依赖版本和接口清单。"},
]


def _version(module_name: str) -> str | None:
    try:
        module = __import__(module_name)
    except ImportError:
        return None
    return getattr(module, "__version__", None)


def _routes(app) -> list[dict]:
    items = []
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/"):
            continue
        methods = sorted(method for method in getattr(route, "methods", set()) if method not in {"HEAD", "OPTIONS"})
        if not methods:
            continue
        tags = getattr(route, "tags", None) or ["其他"]
        items.append(
            {
                "path": path,
                "methods": methods,
                "name": getattr(route, "name", ""),
                "tag": tags[0],
            }
        )
    items.sort(key=lambda item: (item["tag"], item["path"]))
    return items


@router.get("/info")
def info(request: Request, _=Depends(get_current_user)):
    app = request.app
    store = app.state.model_store
    model = None
    try:
        bundle = store.load_active()
        metadata = bundle["metadata"]
        metrics = (metadata.get("metrics") or {}).get("xgboost") or {}
        model = {
            "version": metadata.get("version"),
            "created_at": metadata.get("created_at"),
            "rows": metadata.get("rows"),
            "feature_count": len(bundle.get("feature_columns") or []),
            "auc": metrics.get("auc"),
            "recall": metrics.get("recall"),
        }
    except Exception:
        model = None
    settings = app.state.settings
    return success(
        {
            "name": "电信客户流失预测与可视化分析系统",
            "version": app.version,
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "database": {"engine": "SQLite", "file": settings.database_path.name},
            "model": model,
            "data_version": app.state.data_service.active_version(),
            "dependencies": {
                "fastapi": _version("fastapi"),
                "xgboost": _version("xgboost"),
                "shap": _version("shap"),
                "pandas": _version("pandas"),
                "numpy": _version("numpy"),
                "scikit-learn": _version("sklearn"),
            },
            "routes": _routes(app),
            "modules": MODULES,
        }
    )
