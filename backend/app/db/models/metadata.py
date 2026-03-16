from sqlalchemy import Column, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class Market(Base):
    __tablename__ = "markets"
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, nullable=False, index=True)
    base_asset = Column(String, nullable=False)
    quote_asset = Column(String, nullable=False)
    source = Column(String, nullable=False)

    candles = relationship("Candle", back_populates="market")

    __table_args__ = (
        UniqueConstraint("symbol", name="uq_markets_symbol"),
    )
