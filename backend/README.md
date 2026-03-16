# Backend — BTC Forecast (MVP)

Servicio backend (API-first) para operar un MVP de pronóstico diario de BTC sobre OHLCV 1D del índice CoinDesk XBX. El sistema ingesta datos externos, persiste series y features en PostgreSQL, entrena un único modelo basado en transformers y sirve predicciones con trazabilidad.

## Capacidades
- Ingesta incremental de OHLCV 1D (CoinDesk XBX) y variables exógenas (FGI + macro).
- Persistencia en PostgreSQL como fuente de verdad (`candles`, `fgi_daily`, `macro_daily`).
- Cálculo y persistencia de feature sets en DB (`features`, JSONB) para entrenamiento e inferencia.
- Entrenamiento bajo demanda y registro del modelo/artefactos/métricas (`model_artifacts`, `model_metrics`).
- Predicción diaria (t+1) y proyección 7 días (t+1..t+7) solo para visualización (`predictions`).

## Stack
- FastAPI (OpenAPI/Swagger).
- SQLAlchemy + PostgreSQL.
- Alembic (migraciones).
- PyTorch con caché en memoria para inferencia.

## Estándar temporal y consistencia
- Todo en UTC; la clave diaria de alineación es `open_time`.
- Idempotencia por `UNIQUE` en tablas de series y snapshots.
- Sanidad OHLCV: `high >= max(open, close)`, `low <= min(open, close)`, `volume >= 0`.

## Ejecución local

### Requisitos
- Python (según tu entorno) y PostgreSQL accesible.

### Instalación
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configuración
Variables de entorno en [.env.example](file:///Users/williamvasquez/Library/CloudStorage/OneDrive-Personal/Documentos/William/cursos%20Online/Masters/IA%20VIU/trabajo%20fin%20master/btc-forecast/backend/.env.example):
- `DATABASE_URL` (formato SQLAlchemy `postgresql+psycopg://...`)
- `COINDESK_API_KEY` (si aplica)
- `COINDESK_MARKET` (por defecto `sda`)
- `LOG_LEVEL` (por defecto `INFO`)

### Migraciones
Este servicio no ejecuta migraciones automáticamente en el arranque.
```bash
alembic upgrade head
```

### Arranque del servidor
```bash
./run_server.sh
```

Swagger/OpenAPI:
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/openapi.json`

## API (resumen)

Base: `/api/v1`

### Health
- `GET /health/live`
- `GET /health/ready`

### Operación del MVP
- `POST /api/v1/train`
  - Refresh fuentes externas → persistir series → recalcular/persistir features → entrenar → registrar artefacto/métricas.
- `POST /api/v1/predict`
  - Refresh fuentes → asegurar features → devolver predicción cacheada o generar t+1..t+7 y persistir.

Ejemplo:
```bash
curl -X POST 'http://127.0.0.1:8000/api/v1/predict' \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"XBX-USD","interval":"1d","horizon_days":7}'
```

### Lecturas (históricos)
- `GET /api/v1/market/candles`
- `GET /api/v1/market/fgi`
- `GET /api/v1/market/features`

## Esquema de datos (MVP)
Tablas principales:
- `markets`: mercados lógicos (MVP: `XBX-USD`).
- `candles`: OHLCV real (`UNIQUE(market_id, interval, open_time)` + checks de sanidad).
- `fgi_daily`: Fear & Greed Index diario (idempotente por `open_time`).
- `macro_daily`: variables macro diarias (Yahoo Finance vía `yfinance`).
- `features`: snapshots por día y `feature_set` (`values` como JSONB).
- `model_artifacts` / `model_metrics`: registro de modelos entrenados y métricas.
- `predictions`: predicciones persistidas con trazabilidad.

## Pruebas
```bash
pytest -q
```

## Estructura del proyecto (backend)
- `app/main.py`: aplicación FastAPI.
- `app/api/`: routers `/api/v1`.
- `app/core/`: configuración.
- `app/db/`: modelos ORM y sesión DB.
- `app/services/`: ingesta, pipeline de features y servicios ML (training/inference).
- `alembic/`: migraciones.
