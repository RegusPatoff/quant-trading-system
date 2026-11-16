
# Quant Trading System

Entorno personal de investigación con Python y QuantConnect LEAN.
Fase 1A: **solo investigación y backtesting**. SPY es una prueba técnica;
no decide el mercado de producción. MES y acciones siguen previstos.

## Instalación en PowerShell

Desde la raíz del repositorio:

```powershell
conda env create --file environment.yml --yes
conda run -n quant-trading python --version
conda run -n quant-trading python -m pytest
conda run -n quant-trading python -m compileall -q src tests strategies
conda run -n quant-trading python -m pip check
```

Si ya existe el entorno, inspecciónalo antes de actualizarlo con
`conda env update -n quant-trading --file environment.yml`.
No hace falta activar el entorno ni modificar la política de PowerShell.
En VS Code, con la extensión Python de Microsoft: `Python: Select Interpreter`
→ `quant-trading`. Cada ordenador debe crear su propio entorno desde el repositorio.

Python, pytest, pip y setuptools tienen versiones fijadas; las dependencias
transitivas se resuelven con Conda. `environment.yml` no es un lock completo.
El Python del motor cloud lo gestiona QuantConnect.

## Primer backtest

Sigue [las instrucciones del editor web](docs/first_backtest.md).
No ejecutes el algoritmo con Python local: `AlgorithmImports` lo proporciona LEAN.
Las pruebas locales no validan las APIs ni la ejecución del motor.

## Estructura y seguridad

- `src/quant_trading/`: utilidades locales y validación de configuración.
- `config/`: metadatos de ejemplo, no configuración del motor LEAN.
- `strategies/lean_smoke_test/main.py`: archivo autónomo para el editor web.
- `tests/`: pruebas deterministas.
- `docs/`: procedimiento y decisiones.

No se crean carpetas vacías. Riesgo de producción, alertas, conciliación y
recuperación están pendientes. No hay integración de bróker ni motor propio.

Presupuesto máximo: **50 €/mes**, excluidos capital y comisiones. Esta fase usa
QuantConnect Free y no requiere contratar servicios. LEAN CLI, Researcher Seat,
nodos y datos se evaluarán con aprobación previa. IBKR Pro queda para el futuro.
No hay configuración paper ni real; cualquier despliegue requiere autorización.

No guardes credenciales, cuentas, saldos, datos licenciados ni logs privados en Git.
Revisa siempre los cambios antes de un commit: `.gitignore` no detecta secretos.
La reproducción en un segundo equipo y el backtest cloud están pendientes.
Consulta [las decisiones de Fase 1A](docs/phase_1a.md).

## Objetivos
- Investigación cuantitativa.
- Backtesting de estrategias.
- Paper trading.
- Trading automático mediante Interactive Brokers.

## Tecnologías
- Python
- QuantConnect LEAN
- Interactive Brokers
- GitHub
- Codex
