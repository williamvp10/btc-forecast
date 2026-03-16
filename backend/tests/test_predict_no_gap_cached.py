from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from app.db.models.metadata import Market
from app.db.models.ml import ModelArtifact, Prediction
from app.db.models.timeseries import Candle
from app.db.session import SessionLocal
from app.services.ml import inference


def test_predict_horizon_corrects_cached_open_to_prev_close(monkeypatch):
    def fake_load_model_bundle(artifact):
        return None, np.zeros(1, dtype=np.float32), np.ones(1, dtype=np.float32), np.zeros(5, dtype=np.float32), np.ones(5, dtype=np.float32)

    monkeypatch.setattr(inference, "_load_model_bundle", fake_load_model_bundle)

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
                open=99,
                high=101,
                low=98,
                close=100,
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
            pred_close = 100 + h
            db.add(
                Prediction(
                    model_id=artifact.id,
                    market_id=m.id,
                    as_of_time=now_day,
                    target_time=target,
                    horizon_days=h,
                    pred_open=999,
                    pred_high=max(999, pred_close),
                    pred_low=min(999, pred_close),
                    pred_close=pred_close,
                    pred_volume=11,
                    pred_components=None,
                    generated_at=now_day,
                )
            )
        db.commit()

        preds, created = inference.predict_horizon(db, symbol="XBX-USD", interval="1d", horizon_days=7)
        assert created == 0
        assert len(preds) == 7

        prev_close = 100.0
        for p in preds:
            assert float(p.pred_open) == pytest.approx(prev_close)
            prev_close = float(p.pred_close)

        preds_db = (
            db.query(Prediction)
            .filter(Prediction.market_id == m.id, Prediction.as_of_time == now_day)
            .order_by(Prediction.horizon_days.asc())
            .all()
        )
        prev_close = 100.0
        for p in preds_db:
            assert float(p.pred_open) == pytest.approx(prev_close)
            prev_close = float(p.pred_close)
    finally:
        db.close()

