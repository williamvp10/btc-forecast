from sqlalchemy import Column, Integer, String, Float, ForeignKey, TIMESTAMP, Boolean, UniqueConstraint, func
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid

from app.db.base_class import Base
from app.db.models.metadata import Market

class ModelArtifact(Base):
    __tablename__ = "model_artifacts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    market_id = Column(Integer, ForeignKey("markets.id"), nullable=False, index=True)
    interval = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False, index=True)
    trained_at = Column(TIMESTAMP(timezone=True), nullable=False)
    
    data_start = Column(TIMESTAMP(timezone=True), nullable=False)
    data_end = Column(TIMESTAMP(timezone=True), nullable=False)
    
    target = Column(String, nullable=False)  # e.g., 'ohlcv_structured'
    feature_set = Column(String, nullable=False)  # e.g., 'full'
    window_size_days = Column(Integer, nullable=False)
    horizon_days = Column(Integer, nullable=False)
    
    storage_provider = Column(String, nullable=False)  # 'local', 's3'
    storage_uri = Column(String, nullable=False)
    checksum = Column(String, nullable=False)

    training_params = Column(JSONB, nullable=True)
    metrics = Column(JSONB, nullable=True)
    
    is_active = Column(Boolean, default=False, nullable=False, index=True)
    
    predictions = relationship("Prediction", back_populates="model")
    market = relationship("Market")

class Prediction(Base):
    __tablename__ = "predictions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    model_id = Column(UUID(as_uuid=True), ForeignKey("model_artifacts.id"), nullable=False, index=True)
    market_id = Column(Integer, ForeignKey("markets.id"), nullable=False, index=True)
    
    as_of_time = Column(TIMESTAMP(timezone=True), nullable=False, index=True)  # Data as-of time (last candle time used)
    target_time = Column(TIMESTAMP(timezone=True), nullable=False, index=True) # Prediction target time
    horizon_days = Column(Integer, nullable=False)

    generated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), index=True)
    
    pred_open = Column(Float, nullable=False)
    pred_high = Column(Float, nullable=False)
    pred_low = Column(Float, nullable=False)
    pred_close = Column(Float, nullable=False)
    pred_volume = Column(Float, nullable=False)
    
    pred_components = Column(JSONB, nullable=True) # Optional structured components
    
    model = relationship("ModelArtifact", back_populates="predictions")
    market = relationship("Market")

    __table_args__ = (
        UniqueConstraint('model_id', 'market_id', 'as_of_time', 'target_time', name='uq_prediction'),
    )
