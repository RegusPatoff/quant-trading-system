# Comprobaciones de Fase 1A — 2026-11-16

- Conda 24.1.2: entorno `quant-trading` creado desde `environment.yml`.
- `conda run -n quant-trading python --version`: Python 3.11.11.
- Paquete `quant-trading-system` 0.1.0 instalado en modo editable.
- `conda run -n quant-trading python -m pytest -q`: **12 passed**.
- `conda run -n quant-trading python -m compileall -q src tests strategies`: sin errores.
- `conda run -n quant-trading python -m pip check`: sin dependencias rotas.
- `git check-ignore`: comprobados `.env`, `.env.production`, `.lean/credentials`,
  `data/sample.csv`, `logs/run.log` y caché Python; todos excluidos.

La primera ejecución de pytest en sandbox produjo 1 passed y 11 errores por
acceso denegado a temporales, con advertencias de caché. Repetida fuera del
sandbox, finalizó con 12 passed. No se modificó la política PowerShell.

Pendiente: backtest en QuantConnect Cloud, validación de las APIs en el motor,
verificación de órdenes/resultados y reproducción en un segundo ordenador.
No se ha autenticado QuantConnect ni IBKR, comprado datos, contratado servicios,
activado paper/real, hecho commit ni push.
