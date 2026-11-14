from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile

from backend.dependencies import get_current_user, get_db
from backend.schemas import SinglePredictRequest, success
from backend.services import BatchPredictionRunningError, PredictionService

router = APIRouter(prefix="/api/predict", tags=["流失预测"])


@router.post("/churn")
def churn(payload: SinglePredictRequest, request: Request, db=Depends(get_db), _=Depends(get_current_user)):
    try:
        return success(PredictionService(db, request.app.state.model_store).single(payload.record))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/batch", status_code=202)
async def batch(file: UploadFile, request: Request, _=Depends(get_current_user)):
    try:
        frame, _ = await request.app.state.data_service.parse_upload(file)
        job = request.app.state.batch_service.submit(frame, file.filename or "customers.csv")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except BatchPredictionRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return success(job)


@router.get("/batch/{job_id}")
def batch_status(job_id: str, request: Request, _=Depends(get_current_user)):
    try:
        return success(request.app.state.batch_service.status(job_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/batches")
def batches(request: Request, db=Depends(get_db), _=Depends(get_current_user)):
    return success(PredictionService(db, request.app.state.model_store).batches())


@router.get("/batches/{batch_id}/export")
def export(batch_id: str, request: Request, db=Depends(get_db), _=Depends(get_current_user)):
    try:
        content = PredictionService(db, request.app.state.model_store).export(batch_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="churn_{batch_id}.csv"'},
    )


@router.delete("/batches/{batch_id}")
def delete_batch(batch_id: str, request: Request, db=Depends(get_db), _=Depends(get_current_user)):
    try:
        return success(PredictionService(db, request.app.state.model_store).delete_batch(batch_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
