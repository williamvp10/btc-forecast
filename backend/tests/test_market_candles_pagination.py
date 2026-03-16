from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.db.session import SessionLocal
from app.db.models.metadata import Market
from app.db.models.timeseries import Candle


def test_market_candles_order_desc_returns_latest_block_before_end():
    db = SessionLocal()
    try:
        m = Market(symbol="XBX-USD", base_asset="BTC", quote_asset="USD", source="coindesk_xbx")
        db.add(m)
        db.flush()

        base = datetime(2026, 3, 1, tzinfo=timezone.utc)
        for i in range(10):
            t = base + timedelta(days=i)
            db.add(
                Candle(
                    market_id=m.id,
                    interval="1d",
                    open_time=t,
                    open=float(i),
                    high=float(i) + 1,
                    low=float(i) - 1,
                    close=float(i) + 0.5,
                    volume=float(i) * 10,
                )
            )
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    end = "2026-03-06T00:00:00Z"
    r = client.get(f"/api/v1/market/candles?symbol=XBX-USD&interval=1d&end={end}&limit=3&order=desc")
    assert r.status_code == 200, r.text
    payload = r.json()
    assert len(payload) == 3
    assert payload[0]["open_time"].startswith("2026-03-04")
    assert payload[1]["open_time"].startswith("2026-03-05")
    assert payload[2]["open_time"].startswith("2026-03-06")
