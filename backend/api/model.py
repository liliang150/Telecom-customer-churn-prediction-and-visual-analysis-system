from fastapi import APIRouter, Depends, HTTPException, Request, Response

from backend.artifacts import ActiveModelDeletionError
from backend.dependencies import get_current_user, get_db, require_admin
from backend.ml.report import build_evaluation_report
from backend.ml.training import train_models
from backend.schemas import TrainRequest, VersionRequest, success
from backend.services import (
    FeatureSelectionRunningError,
    PredictionService,
    SensitivityRunningError,
    TrainingAlreadyRunningError,
)

router = APIRouter(prefix="/api/model", tags=["模型管理"])


@router.get("/evaluate")
def evaluate(request: Request, _=Depends(get_current_user)):
    bundle = request.app.state.model_store.load_active()
    return success(bundle["metadata"])


@router.get("/explainability")
def explainability(request: Request, db=Depends(get_db), _=Depends(get_current_user)):
    return success(PredictionService(db, request.app.state.model_store).explainability())


@router.get("/evaluation-report")
def evaluation_report(request: Request, db=Depends(get_db), _=Depends(get_current_user)):
    store = request.app.state.model_store
    metadata = store.load_active()["metadata"]
    try:
        explainability = PredictionService(db, store).explainability()
    except Exception:
        explainability = None
    sensitivity = request.app.state.sensitivity_service.latest()
    content = build_evaluation_report(metadata, explainability, sensitivity)
    version = metadata.get("version", "report")
    return Response(
        content=content.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="model_evaluation_{version}.md"'},
    )


@router.get("/feature-selection")
def latest_feature_selection(request: Request, _=Depends(get_current_user)):
    return success(request.app.state.feature_selection_service.latest())


@router.post("/feature-selection", status_code=202)
def run_feature_selection(payload: TrainRequest, request: Request, _=Depends(require_admin)):
    try:
        job = request.app.state.feature_selection_service.submit(quick=payload.quick)
    except FeatureSelectionRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return success(job)


@router.get("/feature-selection/{job_id}")
def feature_selection_status(job_id: str, request: Request, _=Depends(get_current_user)):
    try:
        return success(request.app.state.feature_selection_service.status(job_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/sensitivity")
def latest_sensitivity(request: Request, _=Depends(get_current_user)):
    return success(request.app.state.sensitivity_service.latest())


@router.post("/sensitivity", status_code=202)
def run_sensitivity(payload: TrainRequest, request: Request, _=Depends(require_admin)):
    try:
        job = request.app.state.sensitivity_service.submit(quick=payload.quick)
    except SensitivityRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return success(job)


@router.get("/sensitivity/{job_id}")
def sensitivity_status(job_id: str, request: Request, _=Depends(get_current_user)):
    try:
        return success(request.app.state.sensitivity_service.status(job_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/train", status_code=202)
def train(payload: TrainRequest, request: Request, _=Depends(require_admin)):
    try:
        job = request.app.state.training_service.submit(quick=payload.quick, trainer=train_models)
    except TrainingAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return success(job)


@router.get("/train/{job_id}")
def training_status(job_id: str, request: Request, _=Depends(get_current_user)):
    try:
        return success(request.app.state.training_service.status(job_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/versions")
def versions(request: Request, _=Depends(get_current_user)):
    return success(request.app.state.model_store.versions())


@router.post("/activate")
def activate(payload: VersionRequest, request: Request, _=Depends(require_admin)):
    try:
        request.app.state.model_store.activate(payload.version)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return success({"version": payload.version, "active": True})


@router.delete("/versions/{version}")
def delete_version(version: str, request: Request, _=Depends(require_admin)):
    try:
        request.app.state.model_store.delete(version)
    except ActiveModelDeletionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return success({"version": version, "deleted": True})
