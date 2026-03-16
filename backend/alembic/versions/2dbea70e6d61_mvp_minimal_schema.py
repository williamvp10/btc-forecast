"""MVP minimal schema

Revision ID: 2dbea70e6d61
Revises: e7e0b6fa31d1
Create Date: 2026-03-16 03:01:34.060268

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '2dbea70e6d61'
down_revision: Union[str, Sequence[str], None] = 'e7e0b6fa31d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("DROP TABLE IF EXISTS predictions CASCADE")
    op.execute("DROP TABLE IF EXISTS model_metrics CASCADE")
    op.execute("DROP TABLE IF EXISTS model_artifacts CASCADE")
    op.execute("DROP TABLE IF EXISTS features CASCADE")
    op.execute("DROP TABLE IF EXISTS candles CASCADE")
    op.execute("DROP TABLE IF EXISTS symbols CASCADE")
    op.execute("DROP TABLE IF EXISTS exchanges CASCADE")
    op.execute("DROP TABLE IF EXISTS assets CASCADE")

    op.create_table(
        "markets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("base_asset", sa.String(), nullable=False),
        sa.Column("quote_asset", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", name="uq_markets_symbol"),
    )
    op.create_index(op.f("ix_markets_id"), "markets", ["id"], unique=False)
    op.create_index(op.f("ix_markets_symbol"), "markets", ["symbol"], unique=True)

    op.create_table(
        "candles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("interval", sa.String(), nullable=False),
        sa.Column("open_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False),
        sa.CheckConstraint("high >= GREATEST(open, close)", name="check_high_max"),
        sa.CheckConstraint("low <= LEAST(open, close)", name="check_low_min"),
        sa.CheckConstraint("volume >= 0", name="check_volume_positive"),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("market_id", "interval", "open_time", name="uq_candle_market_interval_time"),
    )
    op.create_index(op.f("ix_candles_id"), "candles", ["id"], unique=False)
    op.create_index(op.f("ix_candles_market_id"), "candles", ["market_id"], unique=False)
    op.create_index(op.f("ix_candles_interval"), "candles", ["interval"], unique=False)
    op.create_index(op.f("ix_candles_open_time"), "candles", ["open_time"], unique=False)

    op.create_table(
        "fgi_daily",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("open_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("fgi", sa.Integer(), nullable=True),
        sa.Column("fgi_norm", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("open_time", name="uq_fgi_daily_open_time"),
    )
    op.create_index(op.f("ix_fgi_daily_id"), "fgi_daily", ["id"], unique=False)
    op.create_index(op.f("ix_fgi_daily_open_time"), "fgi_daily", ["open_time"], unique=True)

    op.create_table(
        "model_artifacts",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("interval", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("trained_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("data_start", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("data_end", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("target", sa.String(), nullable=False),
        sa.Column("feature_set", sa.String(), nullable=False),
        sa.Column("window_size_days", sa.Integer(), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("storage_provider", sa.String(), nullable=False),
        sa.Column("storage_uri", sa.String(), nullable=False),
        sa.Column("checksum", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_model_artifacts_id"), "model_artifacts", ["id"], unique=False)
    op.create_index(op.f("ix_model_artifacts_market_id"), "model_artifacts", ["market_id"], unique=False)
    op.create_index(op.f("ix_model_artifacts_interval"), "model_artifacts", ["interval"], unique=False)
    op.create_index(op.f("ix_model_artifacts_is_active"), "model_artifacts", ["is_active"], unique=False)
    op.create_index(op.f("ix_model_artifacts_name"), "model_artifacts", ["name"], unique=False)

    op.create_table(
        "predictions",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column("model_id", postgresql.UUID(), nullable=False),
        sa.Column("market_id", sa.Integer(), nullable=False),
        sa.Column("as_of_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("target_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("pred_open", sa.Float(), nullable=False),
        sa.Column("pred_high", sa.Float(), nullable=False),
        sa.Column("pred_low", sa.Float(), nullable=False),
        sa.Column("pred_close", sa.Float(), nullable=False),
        sa.Column("pred_volume", sa.Float(), nullable=False),
        sa.Column("pred_components", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["model_id"], ["model_artifacts.id"]),
        sa.ForeignKeyConstraint(["market_id"], ["markets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_id", "market_id", "as_of_time", "target_time", name="uq_prediction"),
    )
    op.create_index(op.f("ix_predictions_id"), "predictions", ["id"], unique=False)
    op.create_index(op.f("ix_predictions_model_id"), "predictions", ["model_id"], unique=False)
    op.create_index(op.f("ix_predictions_market_id"), "predictions", ["market_id"], unique=False)
    op.create_index(op.f("ix_predictions_as_of_time"), "predictions", ["as_of_time"], unique=False)
    op.create_index(op.f("ix_predictions_target_time"), "predictions", ["target_time"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE IF EXISTS predictions CASCADE")
    op.execute("DROP TABLE IF EXISTS model_artifacts CASCADE")
    op.execute("DROP TABLE IF EXISTS fgi_daily CASCADE")
    op.execute("DROP TABLE IF EXISTS candles CASCADE")
    op.execute("DROP TABLE IF EXISTS markets CASCADE")

    op.create_table(
        "assets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_assets_id"), "assets", ["id"], unique=False)
    op.create_index(op.f("ix_assets_symbol"), "assets", ["symbol"], unique=True)

    op.create_table(
        "exchanges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_exchanges_id"), "exchanges", ["id"], unique=False)
    op.create_index(op.f("ix_exchanges_name"), "exchanges", ["name"], unique=True)

    op.create_table(
        "model_artifacts",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("trained_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("data_start", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("data_end", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("target", sa.String(), nullable=False),
        sa.Column("feature_set", sa.String(), nullable=False),
        sa.Column("window_size_days", sa.Integer(), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("storage_provider", sa.String(), nullable=False),
        sa.Column("storage_uri", sa.String(), nullable=False),
        sa.Column("checksum", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_model_artifacts_id"), "model_artifacts", ["id"], unique=False)
    op.create_index(op.f("ix_model_artifacts_is_active"), "model_artifacts", ["is_active"], unique=False)
    op.create_index(op.f("ix_model_artifacts_name"), "model_artifacts", ["name"], unique=False)

    op.create_table(
        "model_metrics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("model_id", postgresql.UUID(), nullable=False),
        sa.Column("split", sa.String(), nullable=False),
        sa.Column("metric", sa.String(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["model_id"], ["model_artifacts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_id", "split", "metric", name="uq_model_metric"),
    )
    op.create_index(op.f("ix_model_metrics_id"), "model_metrics", ["id"], unique=False)
    op.create_index(op.f("ix_model_metrics_model_id"), "model_metrics", ["model_id"], unique=False)

    op.create_table(
        "symbols",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("exchange_id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("quote_asset", sa.String(), nullable=True),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["exchange_id"], ["exchanges.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("exchange_id", "asset_id", "quote_asset", name="uq_symbol_exchange_asset_quote"),
    )
    op.create_index(op.f("ix_symbols_id"), "symbols", ["id"], unique=False)
    op.create_index(op.f("ix_symbols_symbol"), "symbols", ["symbol"], unique=True)

    op.create_table(
        "candles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol_id", sa.Integer(), nullable=False),
        sa.Column("interval", sa.String(), nullable=False),
        sa.Column("open_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False),
        sa.CheckConstraint("high >= GREATEST(open, close)", name="check_high_max"),
        sa.CheckConstraint("low <= LEAST(open, close)", name="check_low_min"),
        sa.CheckConstraint("volume >= 0", name="check_volume_positive"),
        sa.ForeignKeyConstraint(["symbol_id"], ["symbols.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol_id", "interval", "open_time", name="uq_candle_symbol_interval_time"),
    )
    op.create_index(op.f("ix_candles_id"), "candles", ["id"], unique=False)
    op.create_index(op.f("ix_candles_symbol_id"), "candles", ["symbol_id"], unique=False)
    op.create_index(op.f("ix_candles_interval"), "candles", ["interval"], unique=False)
    op.create_index(op.f("ix_candles_open_time"), "candles", ["open_time"], unique=False)

    op.create_table(
        "features",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol_id", sa.Integer(), nullable=False),
        sa.Column("interval", sa.String(), nullable=False),
        sa.Column("open_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("feature_set", sa.String(), nullable=False),
        sa.Column("values", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["symbol_id"], ["symbols.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol_id", "interval", "open_time", "feature_set", name="uq_feature_symbol_interval_time_set"),
    )
    op.create_index(op.f("ix_features_id"), "features", ["id"], unique=False)
    op.create_index(op.f("ix_features_symbol_id"), "features", ["symbol_id"], unique=False)
    op.create_index(op.f("ix_features_interval"), "features", ["interval"], unique=False)
    op.create_index(op.f("ix_features_open_time"), "features", ["open_time"], unique=False)
    op.create_index(op.f("ix_features_feature_set"), "features", ["feature_set"], unique=False)

    op.create_table(
        "predictions",
        sa.Column("id", postgresql.UUID(), nullable=False),
        sa.Column("model_id", postgresql.UUID(), nullable=False),
        sa.Column("symbol_id", sa.Integer(), nullable=False),
        sa.Column("as_of_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("target_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("pred_open", sa.Float(), nullable=False),
        sa.Column("pred_high", sa.Float(), nullable=False),
        sa.Column("pred_low", sa.Float(), nullable=False),
        sa.Column("pred_close", sa.Float(), nullable=False),
        sa.Column("pred_volume", sa.Float(), nullable=False),
        sa.Column("pred_components", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["model_id"], ["model_artifacts.id"]),
        sa.ForeignKeyConstraint(["symbol_id"], ["symbols.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_id", "symbol_id", "as_of_time", "target_time", name="uq_prediction"),
    )
    op.create_index(op.f("ix_predictions_id"), "predictions", ["id"], unique=False)
    op.create_index(op.f("ix_predictions_model_id"), "predictions", ["model_id"], unique=False)
    op.create_index(op.f("ix_predictions_symbol_id"), "predictions", ["symbol_id"], unique=False)
    op.create_index(op.f("ix_predictions_as_of_time"), "predictions", ["as_of_time"], unique=False)
    op.create_index(op.f("ix_predictions_target_time"), "predictions", ["target_time"], unique=False)
