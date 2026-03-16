import json
from datetime import datetime, timezone, timedelta

import pandas as pd
from fastapi.testclient import TestClient

from app.main import app


def test_ingest_metadata_creates_market():
    client = TestClient(app)
    r = client.post("/api/v1/ingest/metadata")
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["status"] == "success"
    assert payload["symbol"] == "XBX-USD"
    assert isinstance(payload["market_id"], int)


def test_ingest_candles_and_readback(tmp_path):
    client = TestClient(app)
    client.post("/api/v1/ingest/metadata")

    csv_path = tmp_path / "xbx.csv"
    df = pd.DataFrame(
        [
            {"timestamp": "2026-03-13 00:00:00+00:00", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10},
            {"timestamp": "2026-03-14 00:00:00+00:00", "open": 1.5, "high": 2.5, "low": 1.0, "close": 2.0, "volume": 12},
        ]
    )
    df.to_csv(csv_path, index=False)

    r = client.post("/api/v1/ingest/candles", params={"csv_path": str(csv_path)})
    assert r.status_code == 200, r.text
    assert r.json()["rows"] == 2

    r2 = client.get("/api/v1/market/candles", params={"symbol": "XBX-USD", "interval": "1d", "limit": 10})
    assert r2.status_code == 200, r2.text
    out = r2.json()
    assert len(out) == 2
    assert out[0]["open"] == 1.0


def test_ingest_fgi_mock(monkeypatch):
    client = TestClient(app)

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": [
                    {"timestamp": "03-13-2026", "value": "10"},
                    {"timestamp": "03-14-2026", "value": "20"},
                ]
            }

    def fake_get(*args, **kwargs):
        return FakeResp()

    import app.services.ingestion as ingestion_mod

    monkeypatch.setattr(ingestion_mod.requests, "get", fake_get)

    r = client.post("/api/v1/ingest/fgi")
    assert r.status_code == 200, r.text
    assert r.json()["rows"] == 2

    r2 = client.get("/api/v1/market/fgi", params={"limit": 10})
    assert r2.status_code == 200, r2.text
    out = r2.json()
    assert len(out) == 2
    assert out[0]["fgi"] == 10
    assert abs(out[0]["fgi_norm"] - 0.10) < 1e-9


def test_features_computation_full(tmp_path, monkeypatch):
    client = TestClient(app)
    client.post("/api/v1/ingest/metadata")

    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    days = 140
    rows = []
    for i in range(days):
        ts = start + timedelta(days=i)
        base = 10000.0 + i
        rows.append(
            {
                "timestamp": ts.isoformat().replace("+00:00", "Z"),
                "open": base,
                "high": base + 10,
                "low": base - 10,
                "close": base + 1,
                "volume": 1000 + i,
            }
        )
    csv_path = tmp_path / "xbx_long.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    r = client.post("/api/v1/ingest/candles", params={"csv_path": str(csv_path)})
    assert r.status_code == 200, r.text

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            data = []
            for i in range(days):
                ts = start + timedelta(days=i)
                data.append({"timestamp": ts.strftime("%m-%d-%Y"), "value": "50"})
            return {"data": data}

    def fake_get(*args, **kwargs):
        return FakeResp()

    import app.services.ingestion as ingestion_mod

    monkeypatch.setattr(ingestion_mod.requests, "get", fake_get)
    r2 = client.post("/api/v1/ingest/fgi")
    assert r2.status_code == 200, r2.text

    query_start = (start + timedelta(days=120)).isoformat()
    r3 = client.get(
        "/api/v1/market/features",
        params={"symbol": "XBX-USD", "interval": "1d", "feature_set": "full", "start": query_start, "limit": 5},
    )
    assert r3.status_code == 200, r3.text
    out = r3.json()
    assert len(out) == 5
    values = out[0]["values"]
    assert "log_return" in values
    assert "rsi_14" in values
    assert "sma_100" in values
    assert "fgi" in values
    assert "fgi_norm" in values


def test_sync_incremental_candles(tmp_path, monkeypatch):
    client = TestClient(app)
    client.post("/api/v1/ingest/metadata")

    import app.services.sync as sync_mod

    def fake_download_all_days(*args, **kwargs):
        df_raw = pd.DataFrame(
            [
                {"TIMESTAMP": 1773619200, "OPEN": 1, "HIGH": 2, "LOW": 0.5, "CLOSE": 1.5, "VOLUME": 10},
                {"TIMESTAMP": 1773705600, "OPEN": 1.5, "HIGH": 2.5, "LOW": 1.0, "CLOSE": 2.0, "VOLUME": 12},
            ]
        )
        return df_raw, {}

    def fake_download_days_since(*args, **kwargs):
        return pd.DataFrame(
            [
                {"timestamp": "2026-03-15 00:00:00+00:00", "open": 2.0, "high": 3.0, "low": 1.5, "close": 2.5, "volume": 11.0},
            ]
        )

    monkeypatch.setattr(sync_mod, "download_all_days", fake_download_all_days)
    monkeypatch.setattr(sync_mod, "download_days_since", fake_download_days_since)
    monkeypatch.setattr(sync_mod, "fetch_fgi_history", lambda: pd.DataFrame(columns=["timestamp", "fgi", "fgi_norm"]))

    out_csv = tmp_path / "xbx_out.csv"
    r1 = client.post("/api/v1/ingest/sync", params={"csv_path": str(out_csv), "lookback_days": 0})
    assert r1.status_code == 200, r1.text
    payload1 = r1.json()
    assert payload1["status"] == "success"

    r2 = client.post("/api/v1/ingest/sync", params={"csv_path": str(out_csv), "lookback_days": 0})
    assert r2.status_code == 200, r2.text
    payload2 = r2.json()
    assert payload2["status"] == "success"

    r3 = client.get("/api/v1/market/candles", params={"symbol": "XBX-USD", "interval": "1d", "limit": 10})
    assert r3.status_code == 200, r3.text
    out = r3.json()
    assert len(out) == 3
