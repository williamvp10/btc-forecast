from datetime import datetime
from typing import Any, Dict, Optional, List

from pydantic import BaseModel, Field


class TrainRequest(BaseModel):
    symbol: str = Field(default="XBX-USD")
    interval: str = Field(default="1d")
    feature_set: str = Field(default="full")

    lookback: int = Field(default=60, ge=10, le=365)
    lr: float = Field(default=1e-4, gt=0)
    weight_decay: float = Field(default=5e-4, ge=0)
    batch_size: int = Field(default=256, ge=8, le=4096)
    max_epochs: int = Field(default=60, ge=1, le=500)
    min_epochs: int = Field(default=10, ge=0, le=500)
    patience: int = Field(default=12, ge=0, le=200)
    min_delta: float = Field(default=1e-4, ge=0)
    seed: int = Field(default=42, ge=0, le=2_147_483_647)
    holdout_from: str = Field(default="2025-06-01")


class TrainResponse(BaseModel):
    status: str
    model_id: str
    trained_at: datetime
    data_start: datetime
    data_end: datetime
    metrics: Dict[str, Any]
    training_params: Optional[Dict[str, Any]] = None


class PredictRequest(BaseModel):
    symbol: str = Field(default="XBX-USD")
    interval: str = Field(default="1d")
    horizon_days: int = Field(default=1, ge=1, le=7)


class PredictionItem(BaseModel):
    horizon_days: int
    target_time: datetime
    pred_open: float
    pred_high: float
    pred_low: float
    pred_close: float
    pred_volume: float
    pred_components: Optional[Dict[str, Any]] = None


class PredictResponse(BaseModel):
    status: str
    cached: bool
    model_id: str
    as_of_time: datetime
    generated_at: datetime
    valid_until: datetime
    horizon_days: int
    predictions: List[PredictionItem]
