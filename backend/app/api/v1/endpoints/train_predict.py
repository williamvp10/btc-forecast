from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api import deps
from app.schemas.train_predict import TrainRequest, TrainResponse, PredictRequest, PredictResponse
from app.services.pipeline import refresh_all_and_features
from app.services.ml.training import train_model
from app.services.ml.inference import predict_horizon, get_active_model
from app.db.models.metadata import Market


router = APIRouter()


@router.post("/train", response_model=TrainResponse)
def train(req: TrainRequest, db: Session = Depends(deps.get_db)):
    if req.interval != "1d":
        raise HTTPException(status_code=400, detail="Only interval=1d is supported")

    try:
        refresh_all_and_features(db, symbol=req.symbol, feature_set=req.feature_set)
        db.commit()
        artifact = train_model(
            db,
            symbol=req.symbol,
            interval=req.interval,
            feature_set=req.feature_set,
            lookback=req.lookback,
            lr=req.lr,
            weight_decay=req.weight_decay,
            batch_size=req.batch_size,
            max_epochs=req.max_epochs,
            min_epochs=req.min_epochs,
            patience=req.patience,
            min_delta=req.min_delta,
            seed=req.seed,
            holdout_from=req.holdout_from,
        )
        tp = artifact.training_params or {}
        training_params = {
            k: tp.get(k)
            for k in [
                "lookback",
                "lr",
                "weight_decay",
                "batch_size",
                "max_epochs",
                "min_epochs",
                "patience",
                "min_delta",
                "seed",
                "holdout_from",
                "in_features",
                "optimizer",
                "loss",
                "feature_cols",
                "model_hparams",
            ]
            if k in tp
        }
        return {
            "status": "success",
            "model_id": str(artifact.id),
            "trained_at": artifact.trained_at,
            "data_start": artifact.data_start,
            "data_end": artifact.data_end,
            "metrics": artifact.metrics or {},
            "training_params": training_params,
        }
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Training failed")


@router.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest, db: Session = Depends(deps.get_db)):
    if req.interval != "1d":
        raise HTTPException(status_code=400, detail="Only interval=1d is supported")
    if req.horizon_days < 1 or req.horizon_days > 7:
        raise HTTPException(status_code=400, detail="horizon_days must be between 1 and 7")

    m = db.query(Market).filter(Market.symbol == req.symbol).first()
    if not m:
        raise HTTPException(status_code=404, detail="Market not found")

    try:
        refresh_all_and_features(db, symbol=req.symbol, feature_set="full")
        db.commit()

        artifact = get_active_model(db, market_id=m.id, interval=req.interval)
        if not artifact:
            raise HTTPException(status_code=503, detail="No active model available")

        preds, created = predict_horizon(db, symbol=req.symbol, interval=req.interval, horizon_days=req.horizon_days)
        cached = created == 0
        valid_until = preds[-1].target_time

        return {
            "status": "success",
            "cached": cached,
            "model_id": str(preds[0].model_id),
            "as_of_time": preds[0].as_of_time,
            "generated_at": preds[0].generated_at,
            "valid_until": valid_until,
            "horizon_days": req.horizon_days,
            "predictions": [
                {
                    "horizon_days": p.horizon_days,
                    "target_time": p.target_time,
                    "pred_open": p.pred_open,
                    "pred_high": p.pred_high,
                    "pred_low": p.pred_low,
                    "pred_close": p.pred_close,
                    "pred_volume": p.pred_volume,
                    "pred_components": p.pred_components,
                }
                for p in preds
            ],
        }
    except HTTPException:
        db.rollback()
        raise
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
