from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import SessionLocal
from app.db.models.metadata import Market
from app.db.models.ml import ModelArtifact, Prediction
from app.db.models.timeseries import Candle


def test_train_endpoint_success(monkeypatch):
    client = TestClient(app)

    def fake_refresh(db, **kwargs):
        m = db.query(Market).filter(Market.symbol == "XBX-USD").first()
        if not m:
            m = Market(symbol="XBX-USD", base_asset="BTC", quote_asset="USD", source="coindesk_xbx")
            db.add(m)
            db.flush()
        return {"candles_rows": 0, "fgi_rows": 0, "macro_rows": 0, "feature_rows": 0}

    def fake_train_model(db, **kwargs):
        m = db.query(Market).filter(Market.symbol == "XBX-USD").first()
        now = datetime.now(timezone.utc)
        artifact = ModelArtifact(
            market_id=m.id,
            interval="1d",
            name="transformer_full",
            trained_at=now,
            data_start=now - timedelta(days=10),
            data_end=now,
            target="ohlcv_structured",
            feature_set="full",
            window_size_days=60,
            horizon_days=1,
            storage_provider="local",
            storage_uri="/tmp/fake.pt",
            checksum="x",
            is_active=True,
            metrics={"mse_components_val": 0.1},
        )
        db.add(artifact)
        db.commit()
        db.refresh(artifact)
        return artifact

    import app.api.v1.endpoints.train_predict as tp

    monkeypatch.setattr(tp, "refresh_all_and_features", fake_refresh)
    monkeypatch.setattr(tp, "train_model", fake_train_model)

    r = client.post("/api/v1/train", json={"symbol": "XBX-USD", "interval": "1d", "feature_set": "full"})
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["status"] == "success"
    assert "model_id" in payload
    assert payload["metrics"]["mse_components_val"] == 0.1
    assert payload.get("training_params") is not None


def test_predict_endpoint_cached(monkeypatch):
    client = TestClient(app)

    def fake_refresh(db, **kwargs):
        return {"candles_rows": 0, "fgi_rows": 0, "macro_rows": 0, "feature_rows": 0}

    import app.api.v1.endpoints.train_predict as tp

    monkeypatch.setattr(tp, "refresh_all_and_features", fake_refresh)
    def fake_predict_horizon(db, symbol, interval, horizon_days):
        m = db.query(Market).filter(Market.symbol == symbol).first()
        preds = (
            db.query(Prediction)
            .filter(Prediction.market_id == m.id)
            .order_by(Prediction.target_time.asc())
            .limit(int(horizon_days))
            .all()
        )
        return preds, 0

    monkeypatch.setattr(tp, "predict_horizon", fake_predict_horizon)

    db = SessionLocal()
    try:
        m = Market(symbol="XBX-USD", base_asset="BTC", quote_asset="USD", source="coindesk_xbx")
        db.add(m)
        db.flush()

        now_day = datetime(2026, 3, 15, tzinfo=timezone.utc)
        db.add(
            Candle(
                market_id=m.id,
                interval="1d",
                open_time=now_day,
                open=1,
                high=2,
                low=0.5,
                close=1.5,
                volume=10,
            )
        )
        artifact = ModelArtifact(
            market_id=m.id,
            interval="1d",
            name="transformer_full",
            trained_at=now_day,
            data_start=now_day - timedelta(days=10),
            data_end=now_day,
            target="ohlcv_structured",
            feature_set="full",
            window_size_days=60,
            horizon_days=1,
            storage_provider="local",
            storage_uri="/tmp/fake.pt",
            checksum="x",
            is_active=True,
        )
        db.add(artifact)
        db.flush()

        for h in range(1, 8):
            target = now_day + timedelta(days=h)
            db.add(
                Prediction(
                    model_id=artifact.id,
                    market_id=m.id,
                    as_of_time=now_day,
                    target_time=target,
                    horizon_days=h,
                    pred_open=1,
                    pred_high=2,
                    pred_low=0.5,
                    pred_close=1.6,
                    pred_volume=11,
                    pred_components=None,
                    generated_at=now_day,
                )
            )
        db.commit()
    finally:
        db.close()

    r = client.post("/api/v1/predict", json={"symbol": "XBX-USD", "interval": "1d", "horizon_days": 7})
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["status"] == "success"
    assert payload["cached"] is True
    assert payload["horizon_days"] == 7
    assert len(payload["predictions"]) == 7
