# Frontend — BTC Forecast (MVP)

Aplicación web del MVP para visualizar histórico OHLCV y predicciones del backend. El frontend consume datos exclusivamente desde la API (no calcula features ni predicciones en el cliente) y presenta un dashboard con look “TradingView-like” para velas, más un apartado de entrenamiento/estado para trazabilidad mínima.


## Alcance (MVP)
- Navegación en una sola ruta (`/`) con Tabs:
  - Dashboard (mercado + predicción + gráfico)
  - Entrenamiento & Estado (entrenar bajo demanda + trazabilidad)
- Predicción 1 día (t+1) y proyección 7 días (t+1..t+7) solo para visualización.
- Estados claros de carga/vacío/error y validación básica antes de renderizar series.

## Stack
- Next.js (App Router) + React + TypeScript.
- Tailwind CSS + shadcn/ui (Radix).
- Charts:
  - Velas/zoom/pan: `lightweight-charts`.
  - Componentes UI y overlays: shadcn/ui.

## Integracion con el backend
Durante desarrollo y produccion, Next.js puede actuar como proxy hacia el backend mediante rewrites:
- `/api/*` → `${BACKEND_URL}/api/*`
- `/health/*` → `${BACKEND_URL}/health/*`

Configuracion recomendada:
- `BACKEND_URL`: URL interna del backend vista desde el contenedor frontend. En Docker Compose debe ser `http://backend:8000`.
- `NEXT_PUBLIC_BACKEND_URL`: dejar vacia para usar el mismo dominio del frontend y evitar CORS o referencias a `localhost`.

En produccion con un unico dominio publico, el navegador debe consumir `/api/*` y `/health/*` sobre ese mismo host; Next.js reenviara esas rutas al backend.

## Ejecución local

### Requisitos
- Node.js (según tu entorno) y un backend accesible.

### Instalación
```bash
npm install
```

### Configuración
Crea un `.env.local` en `frontend/`:
```bash
BACKEND_URL=http://localhost:8000
```

### Arranque
```bash
npm run dev
```

Abrir:
- `http://localhost:3000`

## Scripts
```bash
npm run lint
npm run test
npm run build
npm run start
```

## Estructura del proyecto (frontend)
- `src/app/page.tsx`: página principal con Tabs (Dashboard / Entrenamiento & Estado).
- `src/components/candles-chart.tsx`: gráfico principal de velas (real + predicción/proyección).
- `src/lib/api.ts`: cliente de API (rutas `/api/v1/*` vía proxy del frontend).

## Nota de producto
La proyección semanal (7 días) se muestra únicamente como visualización y no constituye recomendación financiera.
