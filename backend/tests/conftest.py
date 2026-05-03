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
DEFAULT_SQLITE_PATH = BASE_DIR / "btc_forecast_test.sqlite"
TEST_DB_URL = os.environ.get("SQLALCHEMY_DATABASE_URI") or f"sqlite+pysqlite:///{DEFAULT_SQLITE_PATH}"
os.environ["SQLALCHEMY_DATABASE_URI"] = TEST_DB_URL

@pytest.fixture(scope="session", autouse=True)
def configure_test_db():
    if TEST_DB_URL.startswith("sqlite"):
        DEFAULT_SQLITE_PATH.unlink(missing_ok=True)

    alembic_ini = str(BASE_DIR / "alembic.ini")
    cfg = Config(alembic_ini)
    command.upgrade(cfg, "head")
    yield


@pytest.fixture()
def db_engine() -> Engine:
    connect_args = {"check_same_thread": False} if TEST_DB_URL.startswith("sqlite") else {}
    return create_engine(TEST_DB_URL, connect_args=connect_args)


@pytest.fixture(autouse=True)
def clean_db(db_engine: Engine):
    tables = ["predictions", "model_artifacts", "features", "candles", "fgi_daily", "macro_daily", "markets"]
    with db_engine.begin() as conn:
        dialect = conn.engine.dialect.name
        if dialect == "sqlite":
            conn.execute(text("PRAGMA foreign_keys=OFF"))
            for t in tables:
                conn.execute(text(f"DELETE FROM {t}"))
            conn.execute(text("PRAGMA foreign_keys=ON"))
        elif dialect == "mysql":
            conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
            for t in tables:
                conn.execute(text(f"TRUNCATE TABLE {t}"))
            conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
        else:
            joined = ", ".join(tables)
            conn.execute(text(f"TRUNCATE TABLE {joined} RESTART IDENTITY CASCADE"))
    yield
