from pydantic import BaseModel
from datetime import datetime
from typing import Dict, Any

class CandleSchema(BaseModel):
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    class Config:
        from_attributes = True

class FgiDailySchema(BaseModel):
    open_time: datetime
    fgi: int | None = None
    fgi_norm: float | None = None

    class Config:
        from_attributes = True


class FeatureSchema(BaseModel):
    open_time: datetime
    values: Dict[str, Any]
