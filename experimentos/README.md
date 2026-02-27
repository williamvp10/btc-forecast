# Experimentos — BTC Transformer 1D (OHLCV)

Esta carpeta organiza experimentos reproducibles del modelo Transformer (predicción multiobjetivo OHLCV) con logs claros y salidas persistidas por experimento.

## Estructura

- `notebooks/`: un notebook por experimento.
- `modelos/<nombre_experimento>/`: pesos y artefactos (`config_transformer_btc_1d.json`, `metrics_transformer_btc_1d.json`, scalers).
- `predicciones/<nombre_experimento>/`: CSV de predicciones en test.
- `figuras/<nombre_experimento>/`: gráficos generados (loss, series, scatter, residuales, último mes, velas).

## Cómo ejecutar

1. Abrir un notebook en `notebooks/`.
2. Ejecutar todas las celdas.
3. Revisar el bloque de métricas al final y las imágenes guardadas en `figuras/<experimento>/`.
