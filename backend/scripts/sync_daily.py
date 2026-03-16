import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from app.db.session import SessionLocal
from app.services.sync import sync_daily


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--candles-csv-path", default=str((BASE_DIR.parent / "data" / "_inputs" / "xbx_coindesk_ohlcv_1d_clean.csv").resolve()))
    p.add_argument("--lookback-days", type=int, default=3)
    args = p.parse_args()

    db = SessionLocal()
    try:
        out = sync_daily(db, candles_csv_path=args.candles_csv_path, lookback_days=args.lookback_days)
        print(out)
    finally:
        db.close()


if __name__ == "__main__":
    main()
