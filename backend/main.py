from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from backend.api import analysis, auth, data, model, predict, system
from backend.artifacts import ArtifactStore, ModelNotReadyError
from backend.config import Settings
from backend.database import create_session_factory
from backend.schemas import success
from backend.services import (
    BatchPredictionJobService,
    DataService,
    FeatureSelectionJobService,
    SensitivityJobService,
    TrainingJobService,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = app.state.settings
    store = app.state.model_store
    try:
        store.load_active()
        model_version = store.active_version()
    except ModelNotReadyError:
        model_version = None
    train_rows = len(app.state.data_service.train())
    print(f"\n  系统已就绪", flush=True)
    print(f"  模型版本：{model_version or '（未就绪）'}", flush=True)
    print(f"  训练数据：{train_rows} 行  |  数据库：{settings.database_path.name}", flush=True)
    print(f"  服务访问：http://127.0.0.1:8000\n", flush=True)
    yield
    # shutdown
    try:
        app.state.data_service._read_cached.cache_clear()
    except Exception:
        pass
    try:
        app.state.engine.dispose()
    except Exception:
        pass
    print("\n  系统已关闭。\n", flush=True)


def create_app() -> FastAPI:
    settings = Settings.from_env()
    app = FastAPI(title="电信客户流失预测与可视化分析系统", version="1.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine, app.state.SessionLocal = create_session_factory(settings.database_path)
    app.state.model_store = ArtifactStore(settings.artifact_dir)
    app.state.data_service = DataService(settings.train_path, settings.test_path, settings.upload_dir)
    app.state.training_service = TrainingJobService(app.state.data_service, settings.artifact_dir)
    app.state.batch_service = BatchPredictionJobService(app.state.SessionLocal, app.state.model_store)
    app.state.sensitivity_service = SensitivityJobService(app.state.data_service, app.state.model_store)
    app.state.feature_selection_service = FeatureSelectionJobService(app.state.data_service, app.state.model_store)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth.router)
    app.include_router(data.router)
    app.include_router(model.router)
    app.include_router(predict.router)
    app.include_router(analysis.router)
    app.include_router(system.router)

    @app.exception_handler(ModelNotReadyError)
    async def model_not_ready(_: Request, exc: ModelNotReadyError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.get("/api/health")
    def health(request: Request):
        database_ok = False
        try:
            with request.app.state.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                database_ok = True
        except Exception:
            database_ok = False
        try:
            request.app.state.model_store.load_active()
            model_available = True
        except ModelNotReadyError:
            model_available = False
        return success(
            {
                "status": "ok" if database_ok and model_available else "degraded",
                "database": database_ok,
                "model_available": model_available,
                "model_version": request.app.state.model_store.active_version(),
            }
        )

    if settings.frontend_dist.is_dir():
        assets = settings.frontend_dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str):
            if full_path.startswith("api/"):
                return JSONResponse(status_code=404, content={"detail": "接口不存在"})
            index = settings.frontend_dist / "index.html"
            if index.is_file():
                return FileResponse(index)
            return JSONResponse(status_code=404, content={"detail": "前端尚未构建"})

    return app


app = create_app()
