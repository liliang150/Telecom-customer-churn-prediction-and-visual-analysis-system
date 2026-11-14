from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.dependencies import get_current_user, get_db
from backend.schemas import success
from backend.services import PredictionService

router = APIRouter(prefix="/api/analysis", tags=["可视化分析"])


@router.get("/shap")
def shap(customer_id: str, request: Request, db=Depends(get_db), _=Depends(get_current_user)):
    try:
        return success(PredictionService(db, request.app.state.model_store).explanation(customer_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/features")
def features(request: Request, _=Depends(get_current_user)):
    explanations = request.app.state.model_store.explanations()
    global_items = explanations["global"][:20]
    top_names = {item["feature"] for item in global_items[:12]}
    swarm = [item for item in explanations.get("swarm", []) if item["feature"] in top_names]
    return success({"global": global_items, "swarm": swarm})


@router.get("/dependency")
def dependency(
    request: Request,
    feature: str | None = None,
    db=Depends(get_db),
    _=Depends(get_current_user),
):
    try:
        return success(PredictionService(db, request.app.state.model_store).feature_dependency(feature))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/risk")
def risk(
    request: Request,
    batch_id: str | None = None,
    risk_level: str | None = None,
    region: str | None = None,
    min_fee: float | None = None,
    customer_id: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db=Depends(get_db),
    _=Depends(get_current_user),
):
    service = PredictionService(db, request.app.state.model_store)
    return success(service.risk(batch_id, risk_level, region, min_fee, customer_id, page, page_size))


@router.get("/dashboard")
def dashboard(request: Request, batch_id: str | None = None, db=Depends(get_db), _=Depends(get_current_user)):
    service = PredictionService(db, request.app.state.model_store)
    return success(service.dashboard(request.app.state.data_service, batch_id=batch_id))
