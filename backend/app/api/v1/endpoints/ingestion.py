from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from app.api import deps
from app.services.ingestion import upsert_market, ingest_coindesk_candles_1d_from_csv, ingest_fgi_daily_from_api
from app.services.sync import sync_daily
from app.db.session import SessionLocal
import os
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

DATA_DIR = os.path.abspath(os.path.join(os.getcwd(), "../data"))

def run_ingestion_task(candles_csv_path: str):
    db = SessionLocal()
    try:
        m = upsert_market(db)
        ingest_coindesk_candles_1d_from_csv(db, candles_csv_path, m.id)
        ingest_fgi_daily_from_api(db)
    except Exception as e:
        logger.error(f"Background ingestion failed: {e}")
    finally:
        db.close()


def run_sync_task(candles_csv_path: str, lookback_days: int):
    db = SessionLocal()
    try:
        sync_daily(db, candles_csv_path=candles_csv_path, lookback_days=lookback_days)
    except Exception as e:
        logger.error(f"Background sync failed: {e}")
    finally:
        db.close()

@router.post("/metadata")
def trigger_ingest_metadata(db: Session = Depends(deps.get_db)):
    try:
        m = upsert_market(db)
        return {"status": "success", "market_id": m.id, "symbol": m.symbol}
    except Exception as e:
        logger.error(f"Metadata ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/candles")
def trigger_ingest_candles(
    candles_csv: str = "xbx_coindesk_ohlcv_1d_clean.csv",
    csv_path: str | None = None,
    db: Session = Depends(deps.get_db),
):
    candles_path = csv_path or os.path.join(DATA_DIR, "_inputs", candles_csv)
    if not os.path.exists(candles_path):
        raise HTTPException(status_code=404, detail=f"Data file not found: {candles_path}")
    m = upsert_market(db)
    n = ingest_coindesk_candles_1d_from_csv(db, candles_path, m.id)
    return {"status": "success", "rows": n, "file": candles_path}


@router.post("/fgi")
def trigger_ingest_fgi(db: Session = Depends(deps.get_db)):
    n = ingest_fgi_daily_from_api(db)
    return {"status": "success", "rows": n}


@router.post("/all")
def trigger_ingest_all(
    background_tasks: BackgroundTasks,
    candles_csv: str = "xbx_coindesk_ohlcv_1d_clean.csv",
    csv_path: str | None = None,
):
    candles_path = csv_path or os.path.join(DATA_DIR, "_inputs", candles_csv)
    if not os.path.exists(candles_path):
        raise HTTPException(status_code=404, detail=f"Data file not found: {candles_path}")
    background_tasks.add_task(run_ingestion_task, candles_path)
    return {"status": "accepted", "message": "Ingestion started in background", "file": candles_path}


@router.post("/sync")
def trigger_sync(
    candles_csv: str = "xbx_coindesk_ohlcv_1d_clean.csv",
    csv_path: str | None = None,
    lookback_days: int = 3,
    db: Session = Depends(deps.get_db),
):
    candles_path = csv_path or os.path.join(DATA_DIR, "_inputs", candles_csv)
    out = sync_daily(db, candles_csv_path=candles_path, lookback_days=lookback_days)
    return {"status": "success", **out}


@router.post("/sync/background")
def trigger_sync_background(
    background_tasks: BackgroundTasks,
    candles_csv: str = "xbx_coindesk_ohlcv_1d_clean.csv",
    csv_path: str | None = None,
    lookback_days: int = 3,
):
    candles_path = csv_path or os.path.join(DATA_DIR, "_inputs", candles_csv)
    background_tasks.add_task(run_sync_task, candles_path, lookback_days)
    return {"status": "accepted", "message": "Sync started in background", "file": candles_path, "lookback_days": lookback_days}
