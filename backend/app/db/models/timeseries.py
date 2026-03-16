from sqlalchemy import Column, Integer, String, Float, ForeignKey, TIMESTAMP, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base_class import Base
from app.db.models.metadata import Market

class Candle(Base):
    __tablename__ = "candles"
    id = Column(Integer, primary_key=True, index=True)
    market_id = Column(Integer, ForeignKey("markets.id"), nullable=False, index=True)
    interval = Column(String, nullable=False, index=True)  # e.g., '1d'
    open_time = Column(TIMESTAMP(timezone=True), nullable=False, index=True)
    
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)

    market = relationship("Market", back_populates="candles")

    __table_args__ = (
        UniqueConstraint('market_id', 'interval', 'open_time', name='uq_candle_market_interval_time'),
        CheckConstraint('high >= GREATEST(open, close)', name='check_high_max'),
        CheckConstraint('low <= LEAST(open, close)', name='check_low_min'),
        CheckConstraint('volume >= 0', name='check_volume_positive'),
    )

class FgiDaily(Base):
    __tablename__ = "fgi_daily"
    id = Column(Integer, primary_key=True, index=True)
    open_time = Column(TIMESTAMP(timezone=True), nullable=False, index=True)
    fgi = Column(Integer, nullable=True)
    fgi_norm = Column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint("open_time", name="uq_fgi_daily_open_time"),
    )


class MacroDaily(Base):
    __tablename__ = "macro_daily"
    id = Column(Integer, primary_key=True, index=True)
    open_time = Column(TIMESTAMP(timezone=True), nullable=False, index=True)

    sp500 = Column(Float, nullable=True)
    log_ret_sp500 = Column(Float, nullable=True)
    vol_7d_sp500 = Column(Float, nullable=True)

    dxy = Column(Float, nullable=True)
    log_ret_dxy = Column(Float, nullable=True)
    vol_7d_dxy = Column(Float, nullable=True)

    vix = Column(Float, nullable=True)
    log_ret_vix = Column(Float, nullable=True)
    vol_7d_vix = Column(Float, nullable=True)

    gold = Column(Float, nullable=True)
    log_ret_gold = Column(Float, nullable=True)
    vol_7d_gold = Column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint("open_time", name="uq_macro_daily_open_time"),
    )


class Feature(Base):
    __tablename__ = "features"
    id = Column(Integer, primary_key=True, index=True)
    market_id = Column(Integer, ForeignKey("markets.id"), nullable=False, index=True)
    interval = Column(String, nullable=False, index=True)
    open_time = Column(TIMESTAMP(timezone=True), nullable=False, index=True)
    feature_set = Column(String, nullable=False, index=True)
    values = Column(JSONB, nullable=False)

    __table_args__ = (
        UniqueConstraint("market_id", "interval", "open_time", "feature_set", name="uq_feature_market_interval_time_set"),
    )
