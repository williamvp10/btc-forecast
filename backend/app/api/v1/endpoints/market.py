from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.api import deps
from app.db.models.timeseries import Candle, FgiDaily, Feature
from app.db.models.metadata import Market
from app.schemas.timeseries import CandleSchema, FeatureSchema, FgiDailySchema
from app.services.pipeline import compute_and_store_features

router = APIRouter()

@router.get("/candles", response_model=List[CandleSchema])
def get_candles(
    symbol: str = Query(..., description="Symbol identifier e.g. XBX-USD"),
    interval: str = "1d",
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = 1000,
    order: str = "asc",
    db: Session = Depends(deps.get_db)
):
    m = db.query(Market).filter(Market.symbol == symbol).first()
    if not m:
        raise HTTPException(status_code=404, detail="Market not found")

    query = db.query(Candle).filter(
        Candle.market_id == m.id,
        Candle.interval == interval
    )
    
    if start:
        query = query.filter(Candle.open_time >= start)
    if end:
        query = query.filter(Candle.open_time <= end)

    if order not in ["asc", "desc"]:
        raise HTTPException(status_code=400, detail="order must be asc or desc")

    if order == "desc":
        rows = query.order_by(Candle.open_time.desc()).limit(limit).all()
        return list(reversed(rows))

    query = query.order_by(Candle.open_time.asc()).limit(limit)
    return query.all()

@router.get("/fgi", response_model=List[FgiDailySchema])
def get_fgi(
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = 2000,
    db: Session = Depends(deps.get_db),
):
    query = db.query(FgiDaily)
    if start:
        query = query.filter(FgiDaily.open_time >= start)
    if end:
        query = query.filter(FgiDaily.open_time <= end)
    query = query.order_by(FgiDaily.open_time.asc()).limit(limit)
    return query.all()


@router.get("/features", response_model=List[FeatureSchema])
def get_features(
    symbol: str = Query(..., description="Symbol identifier e.g. XBX-USD"),
    interval: str = "1d",
    feature_set: str = "full",
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = 1000,
    db: Session = Depends(deps.get_db)
):
    if interval != "1d":
        raise HTTPException(status_code=400, detail="Only interval=1d is supported")

    m = db.query(Market).filter(Market.symbol == symbol).first()
    if not m:
        raise HTTPException(status_code=404, detail="Market not found")

    query = db.query(Feature).filter(
        Feature.market_id == m.id,
        Feature.interval == interval,
        Feature.feature_set == feature_set,
    )
    if start:
        query = query.filter(Feature.open_time >= start)
    if end:
        query = query.filter(Feature.open_time <= end)
    query = query.order_by(Feature.open_time.asc()).limit(limit)
    rows = query.all()

    if not rows:
        compute_and_store_features(db, symbol=symbol, interval=interval, feature_set=feature_set)
        db.commit()
        query = db.query(Feature).filter(
            Feature.market_id == m.id,
            Feature.interval == interval,
            Feature.feature_set == feature_set,
        )
        if start:
            query = query.filter(Feature.open_time >= start)
        if end:
            query = query.filter(Feature.open_time <= end)
        query = query.order_by(Feature.open_time.asc()).limit(limit)
        rows = query.all()

    return [{"open_time": r.open_time, "values": r.values} for r in rows]
