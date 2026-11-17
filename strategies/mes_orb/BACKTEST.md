# Pruebas manuales MES ORB en QuantConnect Cloud

## Guardado del archivo en Cloud

`main.py` se ha reducido eliminando comentarios/docstrings y reformateando el
código, sin cambiar su AST ejecutable. Conserva versión 0.1.3 y todas sus reglas.
Ocupa 31.095 caracteres con LF, o 31.672 contando finales CRLF de Windows.
Una prueba automática verifica el límite de 32.000 incluso con CRLF/UTF-16.
Las explicaciones permanecen en README y en este documento.
Tras la reducción: `pytest -q --tb=short` produjo **121 passed** y
`compileall -q src tests strategies` terminó sin errores. No se ejecutó LEAN.

Si aparece `File main.py not saved`, no interpretes un mensaje posterior `Built`
como confirmación de que se compiló el contenido nuevo. Sustituye todo el archivo,
espera a que el guardado termine sin error y compila de nuevo. Puedes recargar el
proyecto antes de compilar para comprobar que el código nuevo quedó persistido.

## Versión 0.1.3: 2026 provisional y logs mínimos

Objetivo: año natural 2026. **Primer corte efectivo: 2026-11-16**, anterior a la
fecha de esta preparación (2026-11-17); cobertura en QuantConnect no verificada.
Solo cambian fechas y observabilidad. No hay optimización ni nuevos filtros.

Comprobaciones locales finales:

- `conda run -n quant-trading python -m pytest -q -s --tb=short`: **120 passed**.
- `conda run -n quant-trading python -m compileall -q src tests strategies`: correcto.
- `conda run -n quant-trading python -m pip check`: sin dependencias rotas.
- `git diff --check`: correcto.
- Escenario anual sintético: 14 líneas, **2.853 bytes JSON**; **3.749 bytes**
  incluyendo 64 bytes adicionales por línea. No son resultados de un backtest.

Se probaron fechas, límites de logging, métricas de entrada/salida iguales entre
minimal/verbose, conciliación mensual/anual, clasificación ganadora/perdedora/cero,
ausencia de doble descuento de slippage, cierre registrado una sola vez, sesiones
sin datos, anomalías acotadas y estados residuales inválidos. Se mantienen las
pruebas de órdenes, EMA, reloj y FixedTickSlippageModel. Una comparación inicial
tuvo 119 passed y 1 fallo por incluir el timestamp exclusivo de verbose; se corrigió
la comparación para excluir ese metadato, sin modificar lógica de trading.

No se ejecutó LEAN, ningún backtest ni se instalaron dependencias. Disponibilidad
de datos, integración en Cloud, tiempos de ejecución y estado real de las órdenes
siguen pendientes. Las pruebas de volumen no incluyen mensajes propios del motor.

En un proyecto existente, los parámetros del panel prevalecen sobre los valores
del código: revisa y establece expresamente estos cinco parámetros:

| Parámetro | Primera ejecución |
|---|---|
| `start_date` | `2026-01-01` |
| `end_date` | `2026-12-31` |
| `end_date_effective` | `2026-11-16` |
| `log_level` | `minimal` |
| `use_ema_filter` | `false` para A; `true` para B |

Mantén el resto de valores de trading. Si aparece una solicitud de pago, detente.
Después de finalizar 2026 y comprobar que existe el histórico, cambia únicamente
`end_date_effective` a `2026-12-31`. No se permite un corte de hoy o futuro.

Si falta la sesión reciente: revisa `last_session_with_data`, contadores mensuales,
mensajes del motor y órdenes. Ese campo solo confirma algún minuto real en horario
de estudio, **no una jornada completa**. Para comprobar la última sesión, haz una
prueba corta `verbose` con las tres fechas coherentes y consulta `session_summary`.
Si 2026-11-16 no tiene cobertura suficiente, retrocede `end_date_effective` a la
última sesión confirmada y vuelve a ejecutar; registra ambos cortes y la razón.
No hay retroceso automático ni relleno de huecos. No interpretes cero operaciones
o `valid=true` como prueba de disponibilidad de datos.

## Qué compartir después de la prueba larga

- La línea `parameters`, las líneas `month_summary` y la línea `summary` completas.
- Cualquier `anomaly`, error o advertencia de datos del motor.
- Estadísticas oficiales: retorno, equity final, drawdown, total de operaciones,
  fees y duración/exposición/rotación cuando estén disponibles.
- Confirmación en Orders/Trades de que no hay posiciones ni órdenes residuales,
  ni posiciones mantenidas a otra sesión. Comparte muestras de fills si hay dudas.

No adjuntes credenciales ni información de cuentas reales. Las métricas internas
son P&L de operaciones cerradas menos fees, no la equity/retorno oficial del motor.
Consulta el diccionario de claves mensuales en README. Exige `journal_consistent=true`,
`valid=true`, `invested=false`, `open_orders=0` y `unfinished_trade=false`, y revisa
también `anomalies`: valid no certifica integridad del dataset ni ventaja estadística.

Para depuración usa `verbose` solo en periodos cortos. Mantén iguales las fechas
y todos los parámetros de trading al comprobar paridad minimal/verbose; cambiar
el nivel no debe cambiar operaciones ni métricas del libro. Los logs verbose pueden
superar la cuota y perder el resumen; las pruebas de volumen solo cubren minimal.

## Limitación preexistente que debe investigarse aparte

El cierre de 15:55 no se adapta a festivos con cierre anticipado. El backtest largo
puede revelar overnight o una liquidación diferida. No se ha corregido alterando
la estrategia: esos casos invalidan la aceptación intradía y requieren revisión
separada. Un bloqueo por overnight también puede involucrar estado contable pendiente;
revisar cartera y fills para distinguirlo de una posición realmente abierta.

## Corrección de slippage v0.1.2

El modelo ahora devuelve puntos por tick mediante la interfaz Python oficial de
slippage. Los resultados anteriores de v0.1.0/v0.1.1, si se ejecutaron, deben
repetirse: `ConstantSlippageModel(0.25)` representa 25 % del precio, no un tick MES.
No cambian entradas, salidas, filtro EMA, contadores ni parámetros iniciales.

Pruebas locales nuevas: 0/1/2 ticks → 0/0,25/0,50 puntos; 1 tick MES → 1,25 USD;
independencia del precio y del signo/cantidad de la orden; instalación del modelo
desde el parámetro y regresión de P&L sin doble descuento. No ejecutan LEAN.

Comprobaciones realizadas: `conda run -n quant-trading python -m pytest -q`:
**104 passed** (88 anteriores más 16 nuevas); `conda run -n quant-trading python -m
compileall -q src tests strategies`: sin errores; `git diff --check`: correcto.
No se han ejecutado backtests ni instalado dependencias. La integración Python/LEAN
y los fills efectivos quedan pendientes del backtest manual en Cloud.

## Revisión técnica v0.1.1 — 2026-11-17

- `conda run -n quant-trading python -m pytest -q`: **88 passed**.
- `conda run -n quant-trading python -m compileall -q src tests strategies`: sin errores.
- `git diff --check`: sin errores de espacios.

Se añadieron regresiones para ORB básico sin acceso a EMA, sincronización de B,
timestamps atrasados/futuros, objetivo por cierre, conversión Chicago/NY en invierno,
verano y alrededor de DST, identidad estable de órdenes y contadores sin duplicados.
Se probaron métodos de cancelación/cierre con entradas y salidas controladas:
pendientes, rechazo de cancelación, saldo parcial, stop ejecutado mientras se cancela,
cierre pendiente sin duplicación y límite de rechazos. Se conserva y prueba el guard
que rechaza paper/real. Estos dobles **no ejecutan ni reproducen LEAN**.

Problemas corregidos: A exigía EMA lista/sincronizada; el chequeo de timestamp de
minuto ocurría después de consumir la barra; etiquetas modificadas por cancelación
o actualización podían perder la identidad entry/stop/exit. No se han cambiado
los valores iniciales de trading. El target continúa siendo sintético por cierre.

## Comprobación inicial v0.1.0 — 2026-11-17

- `conda run -n quant-trading python -m pytest -q`: **51 passed** (12 existentes
  y 39 de MES ORB). Se ejecutó fuera del sandbox para permitir temporales.
- `conda run -n quant-trading python -m compileall -q src tests strategies`: sin errores.
- `conda run -n quant-trading python -m pip check`: sin dependencias rotas.
- `git diff --check`: sin errores de espacios.
- La estrategia `lean_smoke_test` no se ha modificado.

Las pruebas iniciales MES ORB ejecutaban las funciones puras del mismo `main.py` mediante AST,
sin importar ni sustituir LEAN. Cubren parámetros, única diferencia A/B, riesgo,
objetivos/tick, minutos faltantes y decisión de serializar salidas. **No prueban**
el estado del motor, suscripciones, cartera ni la secuencia de eventos de órdenes.
En ninguna de las dos revisiones se ha ejecutado un backtest ni instalado dependencias.

## Primer backtest de funcionamiento

1. Abre tu organización Free. Crea un proyecto Python `MES_ORB_Research`.
2. Copia **todo** `strategies/mes_orb/main.py` en `main.py` del editor web.
   Incluye la clase `FixedTickSlippageModel` al final del archivo.
   No copies otros archivos ni ejecutes este archivo con Python local.
3. En el panel Project, usa **Add New Parameter** para registrar los parámetros
   de la tabla del README. La lógica usa los valores iniciales si no se añaden;
   para trazabilidad es preferible registrarlos explícitamente.
4. Fija `start_date=2026-01-01`, `end_date=2026-12-31`,
   `end_date_effective=2026-11-16`, `log_level=minimal`, `contracts=1`,
   `use_ema_filter=false`, `slippage_ticks=1`; conserva el resto sin modificar.
5. Compila y pulsa **Backtest** usando el nodo gratuito. No pulses Deploy Live ni
   aceptes compras o ampliaciones. Codex no ejecuta ni envía este backtest.
6. Revisa logs, órdenes y posiciones. No basta una curva de equity sin errores.

Como antecedente, el usuario informó 6.541 barras MES de minuto en 2024-10-07–2024-10-11.
Ese recuento no se ha verificado aquí y no es una cifra exigible a este algoritmo:
suscripciones, símbolo raw/continuo, warm-up y cómputo de sesiones pueden diferir.

## Criterios de aceptación funcional

- Logs `parameters` correctos, `mode=backtest`, versión y variante identificadas.
- Datos de contrato `mapped` recibidos; **solo B** exige EMA lista y sincronizada.
  En A, un indicador no inicializado no debe impedir señales ni intentos de entrada.
- `signal` siempre tras una barra cerrada de cinco minutos posterior al rango,
  con todos los minutos del rango y antes del corte. Primera posible 09:50 NY.
- Todas las órdenes apuntan al contrato individual, nunca al continuo.
- Como máximo un intento de entrada por fecha NY; cantidad configurada y riesgo
  calculado con 5 USD/punto. Inspeccionar stops, targets y redondeo de tick.
- Target sintético por cierre de minuto; confirmar cancelación del stop antes
  del cierre alternativo. No deben coexistir órdenes ejecutables stop/target.
- Para cada entrada, comprobar una salida neta equivalente, sin posición inversa.
  Con parciales, agrupar fills; número de órdenes no equivale a operaciones.
- Verificar solicitud de cierre 15:55, instante del fill y ausencia de overnight.
  No aceptar una salida retrasada a otra sesión ni costes inexplicados.
- `summary`: `invested=false`, `open_orders=0`, `unfinished_trade=false`, y
  entradas igual a operaciones cerradas. Contrastar netos/fees con el informe.
- Una prueba sin operaciones puede ser válida como ejecución, pero no valida
  el recorrido de órdenes. Revisar `skip` y ampliar la prueba solo después.

## Diagnósticos disponibles en verbose (conservados desde v0.1.2)

1. `parameters`: versión `0.1.3`, `slippage_model=fixed_ticks`, filtro correcto, parámetros de trading sin cambios,
   `exchange_time_zone` coherente. No aplicar manualmente un desplazamiento horario.
2. `breakout_detected`: `bar_end` = `time_ny`, cinco minutos completos, rango ya
   cerrado. `signal` no debe aparecer fuera de 09:50–11:25 con valores iniciales.
   En A, campos EMA de `signal` a `null`; ausencia de EMA no bloquea la entrada.
3. `target_trigger`: cierre de minuto al otro lado del nivel. Un simple toque
   intrabar no es suficiente. El posterior fill de salida puede diferir del target.
4. Cierre por horario: `exit_requested` con `session_close_1555`, seguido de
   `exit_state`/`cancel_requested` para órdenes pendientes. `accepted=true` solo
   significa solicitud aceptada, **no cancelación confirmada**.
5. Antes de `exit_submitted`, todas las órdenes incompatibles deben haber llegado
   a estado terminal. El registro debe mostrar `open_orders=0` y cantidad de cierre
   opuesta al saldo real. No enviar otro cierre mientras el anterior siga abierto.
6. Si el stop ejecuta durante la cancelación, el cierre residual debe reducirse o
   no enviarse si ya está plano. Revisar también fills tardíos/parciales de entrada.
   No debe aparecer protección nueva después de iniciarse el proceso de salida.
7. Los rechazos/cancelaciones fallidas deben ser visibles; una cancelación sin
   confirmar no habilita un cierre paralelo. Registrar la hora del último fill:
   15:55 es la hora de solicitud, no una garantía de ejecución instantánea.
8. Revisar cada `session_summary`: `observed_minutes` frente a `expected_minutes=385`,
   `data_complete`, `range_complete`, `range_valid` y contadores. Una jornada con
   huecos después del rango puede tener rango válido sin cobertura completa.
9. En `summary`, reconciliar sesiones, señales y `entries_executed` con los logs
   diarios. Los contadores excluyen warm-up; cada operación con parciales cuenta
   como una entrada, no una por fill. Comparar rupturas brutas entre A/B.
10. `summary`: `slippage_estimate_is_informational=true`. Para un contrato con
    entrada y salida completas y un tick por lado, la estimación es 2,50 USD.
    Contrastar fills y fees; no restar esa estimación otra vez de `net_usd` ni equity.
    No inferir la aplicación exacta del modelo solo por ese contador: es un cálculo
    informativo. Ante dudas, inspeccionar las barras/quotes y las reglas de fill
    usadas por el motor; una comparación a cero ticks requeriría otra ejecución
    manual de diagnóstico, sin seleccionar parámetros por rentabilidad.

La cobertura de 385 minutos es un diagnóstico estricto de la jornada investigada,
no un nuevo filtro de trading ni una exigencia de rentabilidad.

No existe evidencia hasta ejecutar estas verificaciones. Cualquier error de API,
datos o invariantes debe corregirse antes de interpretar rentabilidad.

## Comparación A/B sin optimizar

1. Ejecuta A con `use_ema_filter=false` y guarda nombre `MES_ORB_A_20260101_20261116_v013`.
2. Cambia **únicamente** `use_ema_filter=true`; ejecuta B y guarda
   `MES_ORB_B_20260101_20261116_v013`.
3. Conserva el mismo código, versión del motor si aparece, fechas, capital,
   contratos, warm-up, comisiones, slippage y todos los demás parámetros.
4. Guarda registros fuera de Git si contienen datos privados/licenciados.
5. Compara operaciones, resultado neto y bruto, fees, drawdown, exposición
   (tiempo y nominal), rotación y motivos de salida. En futuros no uses margen
   como sustituto de exposición nominal: `abs(contratos × precio × 5)`.
6. Compara qué señales filtró B y su dirección. Al existir una entrada máxima
   por día, B puede operar una señal posterior que A ya no hubiera tomado.
   Esto deriva del filtro, no de cambiar la regla de una entrada diaria.

## Ficha para registrar cada ejecución

| Campo | Resultado a completar por el usuario |
|---|---|
| Fecha, proyecto, ID/nombre del backtest | Pendiente |
| Hash del archivo/commit y cambios locales | Pendiente |
| Motor/entorno Cloud si se muestra | Pendiente |
| Variante y todos los parámetros (log parameters) | Pendiente |
| Proveedor, resolución, rango, NY, sesiones, ajustes y mapeo | Según README; confirmar |
| Entradas y operaciones cerradas | Pendiente |
| Bruto, fees, neto y estimación de slippage incorporado | Pendiente |
| Drawdown, exposición y rotación (metodología incluida) | Pendiente |
| Rechazos, cancelaciones y motivos de cierre | Pendiente |
| Equity/órdenes conciliadas, sin overnight ni inversión accidental | Pendiente |
| Limitaciones o métricas no disponibles | Pendiente |

Para un hash local sin modificar el archivo:

```powershell
Get-FileHash -Algorithm SHA256 strategies/mes_orb/main.py
```

## Validaciones posteriores obligatorias

El periodo 2026 es investigación dentro de muestra, no una validación independiente.
Después se acordará un periodo
de desarrollo y otro fuera de muestra antes de ajustar parámetros, más sensibilidad
y walk-forward cuando haya suficientes operaciones. No optimizar esta ejecución.
Ensayar por separado semanas con rollover, DST, festivos y sesiones reducidas.

Los fills parciales, rechazos y carreras de cancelación requieren pruebas de
integración específicas con LEAN; el fill model estándar puede no producirlos.
No provocarlos conectando brókers ni mediante paper no autorizado. Si no aparecen
en el backtest, marcarlos **no comprobados**, no como pruebas superadas.
