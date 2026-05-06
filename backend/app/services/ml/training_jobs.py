import logging
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.db.session import SessionLocal
from app.schemas.train_predict import TrainRequest
from app.services.ml.training import train_model
from app.services.pipeline import refresh_all_and_features


logger = logging.getLogger(__name__)

_MAX_JOBS = 100
_ACTIVE_STATUSES = {"queued", "running"}
_lock = threading.Lock()


@dataclass
class TrainingJob:
    job_id: str
    status: str
    stage: str
    message: str
    progress_pct: float
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    symbol: str
    interval: str
    feature_set: str
    error: str | None = None
    stage_details: dict[str, Any] | None = None
    result: dict[str, Any] | None = None


_jobs: dict[str, TrainingJob] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _build_train_result(artifact: Any) -> dict[str, Any]:
    training_params = artifact.training_params or {}
    filtered_training_params = {
        k: training_params.get(k)
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
        if k in training_params
    }
    return {
        "status": "success",
        "model_id": str(artifact.id),
        "trained_at": artifact.trained_at,
        "data_start": artifact.data_start,
        "data_end": artifact.data_end,
        "metrics": artifact.metrics or {},
        "training_params": filtered_training_params,
    }


def _serialize(job: TrainingJob) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "status": job.status,
        "stage": job.stage,
        "message": job.message,
        "progress_pct": job.progress_pct,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "symbol": job.symbol,
        "interval": job.interval,
        "feature_set": job.feature_set,
        "error": job.error,
        "stage_details": job.stage_details,
        "result": job.result,
    }


def _trim_finished_jobs() -> None:
    if len(_jobs) <= _MAX_JOBS:
        return
    finished = sorted(
        (job for job in _jobs.values() if job.status not in _ACTIVE_STATUSES),
        key=lambda item: item.created_at,
    )
    for job in finished:
        if len(_jobs) <= _MAX_JOBS:
            break
        _jobs.pop(job.job_id, None)


def get_training_job(job_id: str) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(job_id)
        return _serialize(job) if job else None


def _find_existing_active_job(symbol: str, interval: str, feature_set: str) -> dict[str, Any] | None:
    with _lock:
        active = [
            job
            for job in _jobs.values()
            if job.symbol == symbol
            and job.interval == interval
            and job.feature_set == feature_set
            and job.status in _ACTIVE_STATUSES
        ]
        if not active:
            return None
        latest = max(active, key=lambda item: item.created_at)
        return _serialize(latest)


def _update_training_job(job_id: str, **changes: Any) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        for key, value in changes.items():
            setattr(job, key, value)


def _run_training_job(job_id: str, request_data: dict[str, Any]) -> None:
    req = TrainRequest(**request_data)
    db = SessionLocal()
    _update_training_job(
        job_id,
        status="running",
        stage="refreshing_data",
        message="Actualizando datos historicos y features...",
        progress_pct=8.0,
        started_at=_utcnow(),
        error=None,
        stage_details=None,
    )
    try:
        refresh_summary = refresh_all_and_features(db, symbol=req.symbol, feature_set=req.feature_set)
        db.commit()
        _update_training_job(
            job_id,
            stage="refresh_complete",
            message="Datos historicos y features actualizados. Preparando entrenamiento...",
            progress_pct=25.0,
            stage_details=refresh_summary,
        )
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
            progress_callback=lambda payload: _update_training_job(job_id, status="running", **payload),
        )
        _update_training_job(
            job_id,
            status="success",
            stage="completed",
            message="Entrenamiento completado.",
            progress_pct=100.0,
            finished_at=_utcnow(),
            error=None,
            stage_details={"model_id": str(artifact.id)},
            result=_build_train_result(artifact),
        )
    except ValueError as exc:
        db.rollback()
        logger.warning("Training job failed validation for %s: %s", job_id, exc)
        _update_training_job(
            job_id,
            status="failed",
            stage="failed",
            message="El entrenamiento fallo por validacion de datos.",
            finished_at=_utcnow(),
            error=str(exc),
            result=None,
        )
    except Exception as exc:
        db.rollback()
        logger.exception("Training job crashed for %s", job_id)
        _update_training_job(
            job_id,
            status="failed",
            stage="failed",
            message="El entrenamiento fallo por un error interno.",
            finished_at=_utcnow(),
            error=str(exc),
            result=None,
        )
    finally:
        db.close()


def start_training_job(req: TrainRequest) -> dict[str, Any]:
    existing = _find_existing_active_job(req.symbol, req.interval, req.feature_set)
    if existing:
        return {
            "status": "accepted",
            "job_id": existing["job_id"],
            "message": "Ya existe un entrenamiento en progreso para este simbolo e intervalo",
            "created_at": existing["created_at"],
            "symbol": existing["symbol"],
            "interval": existing["interval"],
            "feature_set": existing["feature_set"],
            "existing_job": True,
        }

    job = TrainingJob(
        job_id=str(uuid.uuid4()),
        status="queued",
        stage="queued",
        message="Esperando turno para entrenar...",
        progress_pct=0.0,
        created_at=_utcnow(),
        started_at=None,
        finished_at=None,
        symbol=req.symbol,
        interval=req.interval,
        feature_set=req.feature_set,
        stage_details=None,
    )
    with _lock:
        _jobs[job.job_id] = job
        _trim_finished_jobs()

    worker = threading.Thread(target=_run_training_job, args=(job.job_id, req.model_dump()), daemon=True)
    worker.start()

    return {
        "status": "accepted",
        "job_id": job.job_id,
        "message": "Entrenamiento iniciado en background",
        "created_at": job.created_at,
        "symbol": job.symbol,
        "interval": job.interval,
        "feature_set": job.feature_set,
        "existing_job": False,
    }
