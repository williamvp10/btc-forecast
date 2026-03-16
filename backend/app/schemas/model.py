from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel


class LatestModelItem(BaseModel):
    model_id: str
    symbol: str
    interval: str
    name: str
    trained_at: datetime
    data_start: datetime
    data_end: datetime
    target: str
    feature_set: str
    window_size_days: int
    horizon_days: int
    is_active: bool
    metrics: Dict[str, Any]
    training_params: Optional[Dict[str, Any]] = None


class LatestModelResponse(BaseModel):
    status: str
    model: LatestModelItem

