# Backend BTC Forecast

Backend API-first para:
- Ingestar y servir OHLCV/feature-sets desde PostgreSQL.
- Entrenar y registrar un único modelo (el mejor identificado en el TFM).
- Generar predicción diaria (t+1) y proyección semanal (t+1..t+7) solo para visualización.
- Consultar predicciones históricas y sus trazas (modelo, datos, timestamps).

Referencia metodológica:
- [TFM_v6.md](file:///Users/williamvasquez/Library/CloudStorage/OneDrive-Personal/Documentos/William/cursos%20Online/Masters/IA%20VIU/trabajo%20fin%20master/proyecto_grado/TFM_versiones/Hito_3/TFM_v6.md)

## Stack y principios
- FastAPI + OpenAPI/Swagger automático.
- SQLAlchemy (ORM) + PostgreSQL (fuente de verdad).
- Alembic para migraciones (propuesta).
- Modelo de IA en memoria (caché en proceso) para inferencia.
- Contratos JSON estables, versionados en `/api/v1`.

## Datos (DB-first): CoinDesk (XBX) + FGI + macro (Yahoo Finance)

Este backend persiste únicamente los datos esenciales extraídos de:
- CoinDesk Data API (índice XBX): OHLCV 1D.
- `https://api.alternative.me/fng/`: Fear & Greed Index (FGI) diario.
- Macro (Yahoo Finance vía `yfinance`, como en el experimento): `sp500`, `dxy`, `vix`, `gold` + retornos/volatilidades.

Los features del modelo (base + técnicos + macro + FGI) se calculan y persisten en DB (tabla `features`) a partir de estas tablas, siguiendo las fórmulas de:
- [02_Feature_Engineering.ipynb](file:///Users/williamvasquez/Library/CloudStorage/OneDrive-Personal/Documentos/William/cursos%20Online/Masters/IA%20VIU/trabajo%20fin%20master/btc-forecast/experimentos_final/02_Feature_Engineering.ipynb)

Referencia de extracción (OHLCV + FGI):
- [01_Data_Extraction.ipynb](file:///Users/williamvasquez/Library/CloudStorage/OneDrive-Personal/Documentos/William/cursos%20Online/Masters/IA%20VIU/trabajo%20fin%20master/btc-forecast/experimentos_final/01_Data_Extraction.ipynb)

En producción, el backend no requiere CSV: los endpoints `/api/v1/train` y `/api/v1/predict` hacen refresh incremental de fuentes externas y recalculan/persisten features cuando corresponde.

## Modelo del MVP (único)

Se implementa únicamente el modelo OHLCV estructurado del TFM:
- Tipo: Transformer encoder-only de regresión (`TransformerEncoderRegressor`)
- Lookback: 60 días
- Salida: 5 componentes estructurados (`out_dim=5`) reconstruibles a niveles
- Hparams reportados (TFM): `d_model=64`, `n_heads=4`, `n_layers=3`, `ff_dim=128`, `dropout=0.2`

## Arquitectura del backend (propuesta de módulos)

- `app/main.py`: crea FastAPI, middlewares, routers, startup/shutdown.
- `app/core/config.py`: configuración desde variables de entorno.
- `app/db/session.py`: engine + sessionmaker.
- `app/db/models/*.py`: modelos ORM.
- `app/schemas/*.py`: modelos Pydantic (requests/responses).
- `app/services/pipeline.py`: refresh fuentes externas + cálculo/persistencia de features (DB-first).
- `app/services/features.py`: fórmulas de features (técnicas) alineadas al notebook.
- `app/services/ml/cache.py`: caché del modelo activo en memoria (por símbolo/intervalo).
- `app/services/ml/training.py`: entrenamiento (asíncrono), evaluación y persistencia de artefactos.
- `app/services/ml/inference.py`: predicción t+1 y proyección t+7.

## PostgreSQL: esquema minimalista (MVP)

Convenciones:
- Timestamps: `timestamptz` en UTC.
- Números: `double precision` (Float).
- Idempotencia: `UNIQUE` para evitar duplicados.

### markets
Market lógico (en el MVP: `XBX-USD`).
- `id` (PK)
- `symbol` (TEXT, UNIQUE, NOT NULL)
- `base_asset` (TEXT, NOT NULL)
- `quote_asset` (TEXT, NOT NULL)
- `source` (TEXT, NOT NULL)

### candles
OHLCV real.
- `id` (PK)
- `market_id` (FK -> markets.id, NOT NULL)
- `interval` (TEXT, NOT NULL) — `1d`
- `open_time` (TIMESTAMPTZ, NOT NULL)
- `open`, `high`, `low`, `close`, `volume` (NUMERIC, NOT NULL)

Constraints:
- `UNIQUE(market_id, interval, open_time)`
- `CHECK(high >= GREATEST(open, close))`
- `CHECK(low <= LEAST(open, close))`
- `CHECK(volume >= 0)`

### fgi_daily
FGI diario desde `alternative.me`.
- `id` (PK)
- `open_time` (TIMESTAMPTZ, NOT NULL, UNIQUE)
- `fgi` (INT, NULLABLE)
- `fgi_norm` (DOUBLE PRECISION, NULLABLE) — `fgi / 100.0`

### macro_daily
Macro diario (como en el experimento, vía Yahoo Finance).
- `id` (PK)
- `open_time` (TIMESTAMPTZ, NOT NULL, UNIQUE)
- `sp500`, `dxy`, `vix`, `gold` (DOUBLE PRECISION, NULLABLE)
- `log_ret_*`, `vol_7d_*` (DOUBLE PRECISION, NULLABLE)

### features
Features calculadas para entrenamiento e inferencia (snapshot por día).
- `id` (PK)
- `market_id` (FK -> markets.id, NOT NULL)
- `interval` (TEXT, NOT NULL) — `1d`
- `open_time` (TIMESTAMPTZ, NOT NULL)
- `feature_set` (TEXT, NOT NULL) — `tech|full`
- `values` (JSONB, NOT NULL) — mapa `{feature_name: value}`

Constraints:
- `UNIQUE(market_id, interval, open_time, feature_set)`

### model_artifacts
Registro de modelos entrenados y activos.
- `id` (UUID PK)
- `market_id` (FK -> markets.id, NOT NULL)
- `interval` (TEXT, NOT NULL)
- `name` (TEXT, NOT NULL)
- `trained_at` (TIMESTAMPTZ, NOT NULL)
- `data_start`, `data_end` (TIMESTAMPTZ, NOT NULL)
- `target` (TEXT, NOT NULL) — `ohlcv_structured`
- `feature_set` (TEXT, NOT NULL) — `tech|full`
- `window_size_days` (INT, NOT NULL) — 60
- `horizon_days` (INT, NOT NULL) — 1
- `storage_provider` (TEXT, NOT NULL) — `local|s3|gcs`
- `storage_uri` (TEXT, NOT NULL)
- `checksum` (TEXT, NOT NULL)
- `is_active` (BOOL, NOT NULL DEFAULT false)

### predictions
Predicciones persistidas (una fila por fecha objetivo).
- `id` (UUID PK)
- `model_id` (UUID FK -> model_artifacts.id, NOT NULL)
- `market_id` (FK -> markets.id, NOT NULL)
- `as_of_time` (TIMESTAMPTZ, NOT NULL) — último día de datos usado (corte)
- `target_time` (TIMESTAMPTZ, NOT NULL) — fecha del OHLCV predicho
- `horizon_days` (INT, NOT NULL) — 1..7
- `generated_at` (TIMESTAMPTZ, NOT NULL) — timestamp de generación
- `pred_open`, `pred_high`, `pred_low`, `pred_close`, `pred_volume` (NUMERIC, NOT NULL)
- `pred_components` (JSONB, NULLABLE) — opcional (5 componentes estructurados)

Constraints:
- `UNIQUE(model_id, market_id, as_of_time, target_time)`

Índices:
- `(market_id, target_time)`
- `(market_id, as_of_time)`

## Migraciones y pruebas

Variables de entorno:
- Usa las variables de [.env.example](file:///Users/williamvasquez/Library/CloudStorage/OneDrive-Personal/Documentos/William/cursos%20Online/Masters/IA%20VIU/trabajo%20fin%20master/btc-forecast/backend/.env.example)
- Driver de Postgres: `psycopg` (SQLAlchemy URL `postgresql+psycopg://...`).
- CoinDesk:
  - `COINDESK_API_KEY` (si aplica al plan)
  - `COINDESK_MARKET` (OHLCV BTC, default `sda`)
- Logging: `LOG_LEVEL` (default `INFO`)
Migraciones:
- Este backend no ejecuta Alembic al arrancar; ejecuta `alembic upgrade head` manualmente cuando recrees la DB/tablas.

Migraciones:
- `alembic upgrade head`
- La migración [2dbea70e6d61_mvp_minimal_schema.py](file:///Users/williamvasquez/Library/CloudStorage/OneDrive-Personal/Documentos/William/cursos%20Online/Masters/IA%20VIU/trabajo%20fin%20master/btc-forecast/backend/alembic/versions/2dbea70e6d61_mvp_minimal_schema.py) elimina tablas del esquema anterior.

Pruebas:
- `pytest -q`

## API (REST) — contratos y comportamiento

Convenciones:
- Base: `/api/v1`
- JSON en UTF-8
- Paginación por `limit` + `cursor` (o `offset`) en endpoints de listas.
- Respuestas de error en formato `application/problem+json`.

Formato de error (Problem Details):
```json
{
  "type": "https://example.com/problems/validation-error",
  "title": "Validation error",
  "status": 422,
  "detail": "Invalid query parameter",
  "instance": "/api/v1/candles",
  "errors": [{"loc": ["query", "start"], "msg": "invalid datetime", "type": "value_error"}]
}
```

### Health
- `GET /health/live`
  - 200 si el proceso está vivo.
- `GET /health/ready`
  - 200 si DB responde y existe modelo activo cargable; 503 si no.

### Ingesta (MVP)
- `POST /api/v1/ingest/metadata`
  - Crea (idempotente) el `market` `XBX-USD`.
- `POST /api/v1/ingest/fgi`
  - Descarga y persiste FGI diario desde `alternative.me` (idempotente por `open_time`).
La actualización de OHLCV (CoinDesk) + FGI (alternative.me) + macro (Yahoo Finance) ocurre automáticamente dentro de:
- `POST /api/v1/train`
- `POST /api/v1/predict`

### Entrenamiento (único)
- `POST /api/v1/train`
  - Actualiza fuentes externas → calcula features → persiste en DB → entrena Transformer → retorna métricas.
  - En `metrics` incluye también `features_used` y `metrics_ohlcv_val` (MAE/RMSE por columna e invalid rates).
  - Retorna `training_params` (defaults notebook 06: `lr=1e-4`, `weight_decay=5e-4`, `batch_size=256`, `max_epochs=60`, `min_epochs=10`, `patience=12`, `min_delta=1e-4`, `seed=42`, `holdout_from=2025-06-01` + hparams del Transformer).

### Predicción (inteligente)
- `POST /api/v1/predict`
  - Soporta `horizon_days` 1..7.
  - Si ya existe predicción para el último `as_of_time` disponible (y todos los target_time requeridos): la retorna (cached).
  - Si no: genera la trayectoria autoregresiva (t+1..t+h), la persiste en DB y la retorna.

Notas de coherencia OHLCV:
- Anti-gap: `pred_open` se fija al `close` de la vela previa (real o predicha) para evitar discontinuidades entre velas consecutivas en la visualización.
  - Esto se aplica solo a la reconstrucción de niveles en inferencia (servicio de predicción), sin afectar el entrenamiento ni otros módulos.
  - El componente estructurado `gap_open` puede seguir registrándose en `pred_components` como traza del modelo, pero no se usa para el nivel `open` retornado.
  - Si existen predicciones cacheadas con `pred_open` distinto, el servicio las normaliza al servirlas para mantener la coherencia.

Ejemplo:
```bash
curl -X POST 'http://127.0.0.1:8000/api/v1/predict' \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"XBX-USD","interval":"1d","horizon_days":7}'
```

### OHLCV real (histórico)
- `GET /api/v1/market/candles?symbol=XBX-USD&interval=1d&start=...&end=...&limit=...`
  - 200: lista ordenada por `open_time` ascendente.

### FGI (histórico)
- `GET /api/v1/market/fgi?start=...&end=...&limit=...`
  - 200: lista ordenada por `open_time` ascendente.

### Features (histórico, on-demand)
- `GET /api/v1/market/features?symbol=XBX-USD&interval=1d&feature_set=full&start=...&end=...&limit=...`
  - `feature_set=tech`: base + técnicas.
  - `feature_set=full`: base + técnicas + `fgi`/`fgi_norm` + macro (Yahoo Finance).

## Caché del modelo en memoria

Estrategia:
- Al inicio (startup), cargar el modelo activo por `(symbol, interval, target)`.
- En activación de modelo: invalidar y recargar (atomic swap).
- Proteger con lock para evitar condiciones de carrera entre requests concurrentes.

## Logging y observabilidad

Logging:
- JSON estructurado con campos mínimos: `timestamp`, `level`, `service`, `request_id`, `route`, `status_code`, `latency_ms`.
- No loggear secretos ni payloads sensibles.

Monitorización:
- Healthchecks: `live`/`ready`.
- Métricas (propuesta): latencias p50/p95, errores por endpoint, estado del modelo en memoria.

## Pruebas (unitarias e integración)

Unitarias:
- Validación de payloads Pydantic y queries.
- Funciones de cálculo/reconstrucción de OHLCV estructurado.

Integración:
- API con `TestClient` contra PostgreSQL de test.
- Caso mínimo: ingesta de sample CSV → consulta OHLCV → consulta FGI → consulta features.
