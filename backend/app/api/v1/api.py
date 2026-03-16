from fastapi import APIRouter
from app.api.v1.endpoints import ingestion, market, train_predict

api_router = APIRouter()
api_router.include_router(ingestion.router, prefix="/ingest", tags=["ingestion"])
api_router.include_router(market.router, prefix="/market", tags=["market"])
api_router.include_router(train_predict.router, tags=["ml"])
