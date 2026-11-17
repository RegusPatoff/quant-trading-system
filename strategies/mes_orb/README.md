# MES Opening Range Breakout — investigación v0.1.3

Hipótesis: las rupturas del rango inicial podrían tener una ventaja estadística;
una EMA direccional podría mejorarla. Ninguna está validada. Solo backtesting.
`main.py` es autónomo, sin bibliotecas externas ni archivos auxiliares en Cloud.
No instala LEAN CLI ni conecta IBKR. La estrategia anterior permanece intacta.

## Datos, contratos y tiempo

- Fuente prevista: futuros estadounidenses de QuantConnect Cloud (AlgoSeek) y
  US Futures Security Master para mapeo/ajustes. Confirmar disponibilidad en la cuenta.
- MES: `Futures.Indices.MICRO_SP_500_E_MINI`, minuto, sin fill-forward,
  con datos extendidos. Filtro de contratos: 0–90 días.
- Serie continua: `OPEN_INTEREST`, `BACKWARDS_RATIO`, contrato frontal (`depth=0`).
  Sirve solo para EMA y su comparación con el cierre continuo de la misma barra.
- Negociación: `future.mapped`, contrato individual sin ajuste. El rango, ruptura,
  stop, objetivo y fills nunca utilizan precios ajustados del continuo.
- Un cambio de mapeo cierra la posición antigua sin abrir una nueva, descarta
  el rango, reinicia EMA/consolidadores y bloquea entradas esa fecha de Nueva York.
  También se excluyen contratos que vencen hoy o mañana.
- Zona del algoritmo: `America/New_York`. Los timestamps de barras de LEAN están
  en la zona del exchange; se convierten mediante su identificador y `zoneinfo`,
  respetando DST. No se confunde la zona UTC del archivo fuente con la de la barra.
  No se añade una hora fija Chicago/NY: MES puede estar configurado en LEAN con
  exchange NY y, en ese caso, la conversión no desplaza la barra. El log inicial
  muestra `exchange_time_zone`. Solo se consumen minutos de duración exacta cuya
  hora de fin coincide con la del algoritmo; barras futuras o retrasadas se omiten.
- Se usan consolidadores nativos de cinco minutos actualizados manualmente,
  continuo primero y contrato después. `scan(end_time)` emite al cierre exacto.

## Reglas

1. Reiniciar el estado de sesión por fecha de Nueva York. Formar máximos/mínimos
   con cada minuto de `[09:30, 09:45)` por defecto. Exigir todos los minutos reales.
2. Evaluar barras **cerradas y completas** de cinco minutos posteriores al rango:
   primera señal posible 09:50, última 11:25 con corte exclusivo a las 11:30.
   Un cierre por encima del máximo permite long; por debajo del mínimo, short.
   No se exige un cruce desde la barra anterior: es un cierre fuera del rango.
3. EMA nativa sobre cierres continuos de cinco minutos, incluida sesión extendida.
   Warm-up de siete días calendario. **Solo B** exige indicador listo y cierre
   continuo sincronizado. En A, EMA ausente, no lista o desincronizada no bloquea
   señales; sus valores de filtro en el log `signal` son `null`.
   No se reinicia cada mañana; tras rollover se reinicia para evitar mezclar escalas.
4. En A no se aplica dirección EMA; en B, cierre continuo > EMA para long o < EMA
   para short. Comparar el cierre raw del contrato con EMA ajustada sería incorrecto.
5. Enviar una entrada a mercado **después** de conocer el cierre de cinco minutos,
   desde su callback en `on_data`. Orden asíncrona: LEAN decide el fill con datos
   posteriores disponibles; no se presupone ejecución al cierre que dio la señal.
   Máximo un intento de entrada por sesión, aunque se rechace. No hay reentradas.
6. Stop en el extremo opuesto del rango. Objetivo a 1,5 R desde el precio medio
   realmente ejecutado, redondeado hacia fuera al tick. Con fills parciales se
   recalcula el objetivo y se protege únicamente la cantidad abierta.
7. A las 15:55 se bloquean entradas, cancelan órdenes y solicita liquidación.
   Un control adicional en `on_data` repite el proceso. No hay rollover de posiciones.

## Riesgo y salidas serializadas

MES: multiplicador **5 USD/punto**, tick **0,25 puntos = 1,25 USD/contrato**.
Se comprueban estos valores contra metadatos de LEAN antes de entrar.

Riesgo de precio = `abs(precio_entrada - stop) × 5 × contratos`.
Se comprueban tanto anchura del rango por contrato como riesgo total de la entrada,
incluido el desplazamiento de la ruptura y slippage supuesto. No solo la anchura.
Si el fill efectivo supera el límite, se solicita salida inmediata; esto no puede
impedir que un gap ya haya generado más riesgo. El límite no incluye comisiones
ni garantiza pérdida máxima o ejecución del stop a su precio.

La pérdida diaria se mide desde equity al inicio de la fecha NY, incluyendo
realizado, no realizado y costes ya descontados. Al alcanzar el límite se bloquea
la sesión y solicita cierre; además no se entra si riesgo previsto más pérdida
acumulada agota el presupuesto diario. No es un límite garantizado ante gaps.

**No hay dos órdenes de salida competidoras:**

- Se mantiene un stop-market por la cantidad abierta, creado al recibir fills.
- El take-profit es **sintético**, confirmado cuando un cierre de minuto alcanza
  o supera su nivel. No es una orden limitada ni se activa por un mero toque intrabar.
- Para objetivo, horario, fallo o rollover: cancelar entrada residual y stop,
  esperar estado terminal y solo entonces enviar cierre a mercado por el saldo real.
- Si el stop se ejecuta durante la cancelación, se reconcilia el saldo antes del
  cierre. Cualquier fill parcial de stop inicia cancelación del resto y cierre
  serializado. Nunca se mantiene una orden target simultánea al stop.
- Las cancelaciones no confirmadas bloquean el cierre alternativo; se reintentan
  en nuevas barras. Los rechazos se registran, bloquean nuevas entradas y provocan
  salida de emergencia. Tres rechazos de cierre invalidan y detienen el backtest.
- La identidad entry/stop/exit se conserva por ID, incluso si cambia la etiqueta
  al rechazar, actualizar o cancelar. No se reemplaza la etiqueta al actualizar
  cantidad o solicitar cancelación. Un fill tardío de entrada durante el cierre
  se incluye en el saldo real que se liquidará; no se crea un stop nuevo en esa fase.
- Si queda un cierre parcial pendiente, se espera: no se duplica. Si termina
  cancelado/rechazado con saldo residual, el siguiente `on_data` reevalúa ese saldo.

Esta elección evita el OCO emulado con dos órdenes activas y su posible doble fill,
pero cambia el comportamiento frente a un take-profit limitado de 1,5 R. La salida
puede ocurrir peor o mejor y existe un intervalo sin stop después de cancelarlo.
Una orden límite de venta exige su precio o mejor (de compra, su precio o menor),
pero no garantiza ejecución: influyen liquidez, cola y fills parciales. Aquí un
toque del máximo/mínimo sin cierre al otro lado **no dispara el objetivo**. Tras
confirmarlo, se permanece en proceso de salida aunque el precio retroceda durante
la cancelación; el cierre a mercado no garantiza conservar el precio objetivo.
Si también se activa el stop en ese minuto, no se reconstruye el recorrido OHLC:
prevalecen los eventos/fills que LEAN entregue y se reconcilia el saldo antes de salir.
No afirma seguridad de producción; carreras, parciales y cancelaciones deben
validarse en LEAN. Tampoco se garantiza estar plano exactamente a las 15:55 si no
hay datos/mercado o el cierre se rechaza. Un estado residual invalida la prueba.

## Parámetros en QuantConnect

Todos son hipótesis iniciales, no valores optimizados. Los límites monetarios
no están calibrados al capital real del usuario.

| Nombre | Inicial | Significado |
|---|---:|---|
| `opening_range_minutes` | `15` | 5–300, múltiplo de 5 y termina antes del corte |
| `ema_period` | `50` | 2–500 cierres completos de cinco minutos |
| `use_ema_filter` | `false` | A=`false`; B=`true` |
| `reward_risk` | `1.5` | Relación objetivo/distancia al stop |
| `contracts` | `1` | Entero 1–10, sin dimensionamiento dinámico |
| `entry_cutoff` | `11:30` | HH:MM NY, exclusivo, máximo 15:50 |
| `max_trade_risk_usd` | `150` | Límite de riesgo de precio total por entrada |
| `max_daily_loss_usd` | `200` | Bloqueo/cierre por pérdida de equity de sesión |
| `slippage_ticks` | `1` | 0–20 ticks por ejecución como hipótesis |
| `start_date` | `2026-01-01` | Inicio del año objetivo |
| `end_date` | `2026-12-31` | Fin del periodo objetivo; no solicita datos futuros |
| `end_date_effective` | `2026-11-16` | Corte que realmente recibe `set_end_date` |
| `log_level` | `minimal` | `minimal` para periodos largos; `verbose` para depuración corta |

La primera ejecución cubre **2026-01-01 a 2026-11-16**, condicionada a disponibilidad
de datos en Cloud. No se ha verificado su cobertura. Se exige inicio ≤ corte
efectivo ≤ objetivo y corte efectivo anterior al día actual de Nueva York, usando
el reloj real del equipo del motor, no su reloj de simulación. No hay recorte
automático ni datos inventados. Cuando 2026 haya concluido y el histórico esté
disponible, basta cambiar `end_date_effective` a `2026-12-31`.

## Costes y registros

Se utiliza el brokerage model de IBKR **solo como simulación**, incluida su
comisión nativa para futuros. No se reproduce ni certifica la tarifa personal
de IBKR Pro. Un inicializador adicional conserva los modelos de margen/fill/fees
y sustituye únicamente slippage por `FixedTickSlippageModel(slippage_ticks)`.
No es liquidez, profundidad, spread variable ni impacto de mercado calibrados.

El modelo Python no hereda de otra clase y expone la interfaz documentada
`get_slippage_approximation(asset, order)`. Devuelve un desplazamiento **positivo
en puntos por unidad**, calculado con `asset.symbol_properties.minimum_price_variation`
por `slippage_ticks`. LEAN aplica el signo adverso al precio de compra o venta
según su fill model; el modelo no multiplica por precio, cantidad ni multiplicador.

| Slippage configurado | Puntos MES por fill | Coste teórico por contrato y lado |
|---|---:|---:|
| 0 ticks | 0,00 | 0,00 USD |
| 1 tick | 0,25 | 1,25 USD |
| 2 ticks | 0,50 | 2,50 USD |

Un recorrido completo de un contrato con un tick adverso en cada lado representa
2,50 USD de slippage supuesto, además de comisiones. No depende del nivel de MES.
La tabla describe el desplazamiento del modelo, no garantiza el precio efectivo:
pueden intervenir bid/ask, gaps, datos disponibles y reglas del fill model.
En particular, el `FutureFillModel` combina en stops el nivel del stop y el precio
corriente con el desplazamiento mediante mínimos/máximos. Por eso la estimación
informativa no mide necesariamente el desplazamiento efectivo de cada stop fill.

**Corrección de unidades:** en v0.1.0/v0.1.1 se pasaban puntos a
`ConstantSlippageModel`, cuyo argumento es una fracción del precio. Para un tick
MES, `0.25` significaba 25 %, no 0,25 puntos. Los resultados de esas versiones
no deben aceptarse como backtests con costes de un tick: deben repetirse con v0.1.2.

En `verbose`, logs JSON: `parameters`, `mapping`, `skip`, `breakout_detected`, `signal`, `order`,
`protection`, `target_trigger`, `exit_requested`, `exit_state`, `cancel_requested`,
`exit_submitted`, `trade_closed`, `session_summary`, `summary`. Cada cierre registra precios medios,
cantidades, motivo, bruto, comisiones y neto. El resumen cuenta entradas con fill y
operaciones cerradas. El slippage está incorporado en los fills: el resumen muestra
además una estimación por cantidades, **no un coste adicional que deba restarse**.
`modeled_slippage_estimate_usd = sum(abs(fill_quantity) × tick × slippage_ticks × 5)`
para MES. `slippage_estimate_is_informational=true` lo identifica en `summary`.
Es una estimación del supuesto, no una medición independiente de su aplicación
efectiva por LEAN. No se registra como comisión ni se carga manualmente a la cartera.
El bruto se calcula con los precios de fill recibidos; el neto resta únicamente
las comisiones. Ejemplo: compra a 5800,25 y venta a 5809,75, un contrato MES,
producen 47,50 USD brutos. Con 1 USD total de fees, neto 46,50 USD; no se vuelven
a restar los 2,50 USD de slippage informativo.
Verificar cifras con órdenes, comisiones y cartera de LEAN; futuros tienen liquidación
diaria y sus informes pueden agrupar operaciones de forma distinta al ciclo lógico.

Contadores de diagnóstico (no condicionan las entradas):

- `sessions_seen`: fechas laborables NY observadas fuera de warm-up. Incluye
  festivos si llegan slices; no sustituye un calendario de sesiones de mercado.
- `sessions_with_complete_data`: todas las **385 barras reales de minuto** de
  `[09:30, 15:55)`, sin cambio de mapeo durante esa fecha.
- `sessions_with_valid_range`: todos los minutos del rango, máximo > mínimo y
  sin cambio de mapeo. No exige la cobertura de toda la jornada.
- `signals_detected`: cierres completos de cinco minutos fuera del rango, en
  horario de entrada y contrato no próximo al vencimiento, antes del filtro EMA,
  límites y elegibilidad. Cuenta también rupturas posteriores al primer intento;
  son barras fuera del rango, no cruces independientes.
- `entries_executed`: una por operación al primer fill, aunque sea parcial.
  `entries` se conserva como alias del mismo total para compatibilidad.

`session_summary` registra cada fecha al cambiar el día o finalizar el algoritmo,
una sola vez; el resumen total debe coincidir con la suma de esos registros.
Los recuentos brutos de rupturas deben coincidir entre A/B con mismos datos y
parámetros salvo el filtro. El log `signal` sigue identificando intentos de entrada
que han pasado todas las comprobaciones; no equivale a ejecución confirmada.

## Logging compacto y contabilidad mensual

`minimal` es el valor inicial. Emite un registro `parameters`, uno `month_summary`
por mes observado y una única línea JSON `summary`. No imprime operaciones,
rupturas, stops, mapeos ni sesiones individuales. El libro interno sigue contando
con independencia del nivel; las órdenes permanecen en Orders/Trades de Cloud.
El primer registro incluye versión, todas las fechas/parámetros y modelo de slippage.

Las claves mensuales abreviadas permiten reservar cuota para los mensajes del motor:

| Clave | Significado |
|---|---|
| `m` | Mes YYYY-MM |
| `s`, `dc`, `rv` | Sesiones observadas, con datos completos, con rango válido |
| `e`, `t` | Entradas ejecutadas, operaciones completadas |
| `w`, `l` | Operaciones ganadoras/perdedoras después de sus comisiones |
| `g` | P&L bruto firmado de operaciones cerradas |
| `fees` | Comisiones registradas durante el mes |
| `net` | `g - fees`; slippage no se resta de nuevo |

El cierre se asigna a la fecha de su último fill de salida; la comisión se reconoce
cuando llega su evento. Así, en un cruce de mes anómalo una comisión de entrada
puede estar en el mes anterior al P&L del cierre. Se conserva la suma mensual/anual.
Ganadoras/perdedoras se clasifican al cierre con todas las comisiones de la operación;
una operación neta cero cuenta en `t`, pero no en `w` ni `l`.
El mes se imprime tras registrar su última sesión y resolver cualquier operación
pendiente, o al finalizar. Cada mes y cierre se cuentan una sola vez. Los cálculos
conservan precisión interna; los importes de salida se redondean a centavos, por lo
que pueden existir diferencias de redondeo al sumar importes mensuales impresos.

El resumen final distingue `result_source=internal_journal`. `gross_profit_usd` es
la suma firmada del bruto de operaciones cerradas; `net_profit_usd` resta todas las
comisiones registradas, incluidas las de operaciones incompletas si las hubiera.
**No es el retorno ni la equity oficial de LEAN**, ni incorpora el P&L no realizado
de una posición residual. Compararlo con las métricas oficiales de Cloud y descartar
una prueba con estado residual. `journal_consistent` verifica los recuentos/fees del
libro frente a los contadores globales. `valid` solo comprueba estado de ejecución,
bloqueos y conciliación interna; no certifica cobertura de datos ni rentabilidad.

En minimal se emite como máximo la primera copia de tres motivos excepcionales,
con texto acotado. Las repeticiones se cuentan en `summary.anomalies`; un estado
final inválido siempre genera además un error explícito. En verbose no se aplica
ese límite de copias. No se interceptan ni suprimen mensajes/excepciones del motor.

Una prueba sintética local mide inicio + doce meses + resumen, con margen adicional
de 64 bytes por línea, y exige **menos de 6.000 bytes**. Es una comprobación del
volumen normal propio, no una medición en Cloud: errores, límites diarios ya
consumidos o mensajes del motor pueden impedir ver el resumen. Un aborto del motor
también puede evitar que se ejecute `on_end_of_algorithm`.

## Límites de validación

Solo se ejecutan pruebas unitarias locales y sintaxis. Se prueban también métodos
con entradas/salidas controladas; esto no reproduce la cola de eventos de LEAN. Sin LEAN local
no se han validado compilación cloud, datos, margen, suscripciones dinámicas,
eventos, fills, parciales, rechazos, cancelaciones ni cierres. No se ha realizado
ningún backtest de esta estrategia. Ampliar a 2026 no constituye validación fuera
de muestra ni demuestra ventaja estadística; no se han optimizado parámetros.

Limitación preexistente relevante al ampliar el periodo: el cierre fijo 15:55 no
se adapta a sesiones reducidas. Puede quedar una posición pendiente hasta la
siguiente sesión, lo que invalida la condición intradía. Esta versión no cambia
esa regla ni la gestión de órdenes; expone el incidente y el estado residual.
También puede ocurrir que el aviso de overnight detecte un estado interno de
operación aún pendiente de registrar aunque el último fill ya la haya cerrado;
debe investigarse con verbose, no interpretarse automáticamente como posición real.

Tampoco hay tratamiento operativo completo de suspensión de datos, persistencia
o recuperación real.

## Fuentes oficiales consultadas

- [Logging y cuotas](https://www.quantconnect.com/docs/v2/writing-algorithms/logging).
- [Fechas de inicialización](https://www.quantconnect.com/docs/v2/writing-algorithms/initialization).
- [MES y contratos continuos](https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/quantconnect/us-futures-security-master).
- [Contratos individuales](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/futures/requesting-data/individual-contracts).
- [Consolidadores](https://www.quantconnect.com/docs/v2/writing-algorithms/consolidating-data/consolidator-types/time-period-consolidators).
- [Tickets, actualizaciones y cancelaciones](https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-management/order-tickets).
- [Comisiones nativas](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/transaction-fees/supported-models).
- [Slippage](https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/slippage/key-concepts).
- [ConstantSlippageModel: fracción del precio](https://github.com/QuantConnect/Lean/blob/master/Common/Orders/Slippage/ConstantSlippageModel.cs)
  e [interfaz ISlippageModel](https://github.com/QuantConnect/Lean/blob/master/Common/Orders/Slippage/ISlippageModel.cs).
- [Aplicación del slippage en FutureFillModel](https://github.com/QuantConnect/Lean/blob/master/Common/Orders/Fills/FutureFillModel.cs).
- [Especificaciones MES de CME](https://www.cmegroup.com/markets/equities/sp/micro-e-mini-sandp-500.contractSpecs.html).
- [Zonas MES en LEAN](https://github.com/QuantConnect/Lean/blob/master/Data/market-hours/market-hours-database.json).
- [Lectura de TradeBars](https://github.com/QuantConnect/Lean/blob/master/Common/Data/Market/TradeBar.cs) y
  [emisión/scan de consolidadores](https://github.com/QuantConnect/Lean/blob/master/Common/Data/Consolidators/PeriodCountConsolidatorBase.cs).
