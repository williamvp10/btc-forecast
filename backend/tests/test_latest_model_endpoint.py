from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.db.session import SessionLocal
from app.db.models.metadata import Market
from app.db.models.ml import ModelArtifact


def test_latest_model_endpoint_returns_active_model():
    db = SessionLocal()
    try:
        m = Market(symbol="XBX-USD", base_asset="BTC", quote_asset="USD", source="coindesk_xbx")
        db.add(m)
        db.flush()

        now = datetime(2026, 3, 16, tzinfo=timezone.utc)
        artifact = ModelArtifact(
            market_id=m.id,
            interval="1d",
            name="transformer_full",
            trained_at=now,
            data_start=now - timedelta(days=90),
            data_end=now - timedelta(days=1),
            target="ohlcv_structured",
            feature_set="full",
            window_size_days=60,
            horizon_days=1,
            storage_provider="local",
            storage_uri="/tmp/fake.pt",
            checksum="x",
            is_active=True,
            metrics={"rmse_close_val": 123.4},
            training_params={"lookback": 60, "lr": 0.0001},
        )
        db.add(artifact)
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    r = client.get("/api/v1/model/latest?symbol=XBX-USD&interval=1d&active_only=true")
    assert r.status_code == 200, r.text
    assert r.headers.get("cache-control") == "no-store"
    payload = r.json()
    assert payload["status"] == "success"
    assert payload["model"]["model_id"]
    assert payload["model"]["symbol"] == "XBX-USD"
    assert payload["model"]["interval"] == "1d"
    assert payload["model"]["is_active"] is True
    assert payload["model"]["metrics"]["rmse_close_val"] == 123.4

