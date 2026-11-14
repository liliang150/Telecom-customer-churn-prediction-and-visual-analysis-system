from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile

from backend.dependencies import get_current_user, require_admin
from backend.ml.eda import build_eda
from backend.ml.preprocessing import clean_dataframe, prepare_features
from backend.schemas import DataConfirmRequest, VersionRequest, success
from backend.services import records

router = APIRouter(prefix="/api/data", tags=["数据管理"])


@router.get("/overview")
def overview(request: Request, _=Depends(get_current_user)):
    return success(request.app.state.data_service.overview())


@router.get("/sample")
def sample(request: Request, _=Depends(get_current_user)):
    return success(request.app.state.data_service.sample())


@router.get("/eda")
def eda(request: Request, _=Depends(get_current_user)):
    return success(build_eda(request.app.state.data_service.train()))


@router.post("/upload")
async def upload(kind: str, file: UploadFile, request: Request, _=Depends(get_current_user)):
    if kind not in {"train", "predict"}:
        raise HTTPException(status_code=422, detail="kind 必须为 train 或 predict")
    service = request.app.state.data_service
    try:
        frame, content = await service.parse_upload(file)
        cleaned, report = service.validate_upload(kind, frame)
        saved_name = service.save_upload(file.filename or "data.csv", content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return success(
        {"saved_name": saved_name, "kind": kind, "status": "pending", "report": report, "preview": records(cleaned.head(8))}
    )


@router.post("/confirm")
def confirm_upload(payload: DataConfirmRequest, request: Request, _=Depends(require_admin)):
    try:
        return success(request.app.state.data_service.confirm_upload(payload.saved_name, payload.kind))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/versions")
def data_versions(request: Request, _=Depends(get_current_user)):
    return success(request.app.state.data_service.versions())


@router.post("/versions/activate")
def activate_data_version(payload: VersionRequest, request: Request, _=Depends(require_admin)):
    try:
        return success(request.app.state.data_service.activate_version(payload.version))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/clean")
async def clean(file: UploadFile, request: Request, _=Depends(get_current_user)):
    try:
        frame, _ = await request.app.state.data_service.parse_upload(file)
        cleaned, report = clean_dataframe(frame)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return success({"report": report, "preview": records(cleaned.head(8))})


@router.post("/features/generate")
async def generate_features(file: UploadFile, request: Request, _=Depends(get_current_user)):
    try:
        frame, _ = await request.app.state.data_service.parse_upload(file)
        features = prepare_features(frame)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return success({"rows": len(features), "feature_columns": features.columns.tolist(), "preview": records(features.head(8))})
