import os
import pathlib
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from alembic import command
from alembic.config import Config

BASE_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))
TEST_DB_URL = os.environ.get("SQLALCHEMY_DATABASE_URI") or "postgresql+psycopg://postgres:root@localhost/btc_forecast_test"
os.environ["SQLALCHEMY_DATABASE_URI"] = TEST_DB_URL

def _ensure_test_db(db_url: str, db_name: str) -> None:
    admin_url = db_url.rsplit("/", 1)[0] + "/postgres"
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": db_name},
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))


@pytest.fixture(scope="session", autouse=True)
def configure_test_db():
    db_name = "btc_forecast_test"
    _ensure_test_db(TEST_DB_URL, db_name)

    alembic_ini = str(BASE_DIR / "alembic.ini")
    cfg = Config(alembic_ini)
    command.upgrade(cfg, "head")
    yield


@pytest.fixture()
def db_engine() -> Engine:
    return create_engine(TEST_DB_URL)


@pytest.fixture(autouse=True)
def clean_db(db_engine: Engine):
    with db_engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE predictions RESTART IDENTITY CASCADE"))
        conn.execute(text("TRUNCATE TABLE model_artifacts RESTART IDENTITY CASCADE"))
        conn.execute(text("TRUNCATE TABLE features RESTART IDENTITY CASCADE"))
        conn.execute(text("TRUNCATE TABLE candles RESTART IDENTITY CASCADE"))
        conn.execute(text("TRUNCATE TABLE fgi_daily RESTART IDENTITY CASCADE"))
        conn.execute(text("TRUNCATE TABLE macro_daily RESTART IDENTITY CASCADE"))
        conn.execute(text("TRUNCATE TABLE markets RESTART IDENTITY CASCADE"))
    yield
