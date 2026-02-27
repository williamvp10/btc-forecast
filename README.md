# MVP App (monorepo)

Esta carpeta agrupa todo lo relacionado con el desarrollo del MVP de forecasting de Bitcoin.

## Estructura
```
mvp/
  backend/
  frontend/
  experiments/
```

## Alcance del MVP
- Datos: histórico diario de Bitcoin desde Binance (OHLCV) con cálculo de features (medias móviles, retornos, volatilidad).
- Persistencia: PostgreSQL como fuente de verdad para históricos, features, modelos y predicciones.
- Backend: FastAPI para ingesta incremental, serving de datos y gestión de modelos/predicciones.
- Frontend: Next.js + Tailwind + shadcn/ui para visualización.

