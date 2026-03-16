# MVP App (monorepo)

Esta carpeta agrupa todo lo relacionado con el desarrollo del MVP de forecasting de Bitcoin.

## Estructura
```
mvp/
  backend/
  frontend/
  experiments/
```

## Arquitectura de alto nivel MVP

A continuación se muestra la arquitectura de alto nivel del MVP en formato Mermaid. El backend se representa como un único bloque que encapsula la API, la base de datos PostgreSQL y los modelos de predicción en memoria, y se comunica con el frontend vía HTTP.

```mermaid
flowchart TB
 subgraph subGraph0["Frontend (Next.js)"]
        A["Dashboard"]
  end
 subgraph subGraph1["Backend (FastAPI)"]
        B1["API (/api/v1)"]
        B2[("PostgreSQL")]
        B3["Modelos en memoria (inferencia + cache)"]
        B4["datos historicos"]
  end
 subgraph subGraph2["Fuentes externas"]
        E1["CoinDesk (XBX OHLCV)"]
        E2["Yahoo Finance (yfinance macro)"]
        E3["Fear & Greed Index (alternative.me)"]
  end
    B1 -- SQLAlchemy --> B2
    B1 -- Load model / Predict --> B3
    B3 -- Predicciones --> B1
    B1 --> B4
    B4 --> E1 & E3 & E2
    E1 --> B4
    E2 --> B4
    E3 --> B4
    A -- HTTP --> subGraph1
```

## Alcance del MVP
- Datos:
  - OHLCV histórico (BTC) desde CoinDesk (índice XBX).
  - Fear & Greed Index (FGI) diario desde `https://api.alternative.me/fng/`.
  - Series macro (Yahoo Finance vía `yfinance`): `sp500`, `dxy`, `vix`, `gold` + retornos y volatilidades.
  - Features calculadas (técnicas + macro + FGI) para entrenamiento e inferencia.
- Persistencia: PostgreSQL como fuente de verdad para históricos, features, modelos y predicciones.
- Backend: FastAPI para ingesta incremental, serving de datos y gestión de modelos/predicciones.
- Frontend: Next.js + Tailwind + shadcn/ui para visualización.
