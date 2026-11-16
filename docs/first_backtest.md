# Primer backtest gratuito en QuantConnect

## Pasos en el editor web

1. Inicia sesión en https://www.quantconnect.com/ y selecciona tu organización **Free**.
2. Crea un proyecto Python llamado `QuantTradingSmokeTest`. Si se solicita comprar
   un nodo o cambiar de plan, detente y verifica que uses el nodo gratuito.
3. Sustituye el contenido de `main.py` por el archivo completo
   `strategies/lean_smoke_test/main.py` de este repositorio. No subas otros archivos
   ni credenciales. No hay parámetros que configurar.
4. Compila con **Build** si aparece y pulsa **Backtest**. Espera la cola gratuita.
   No utilices **Deploy Live**.
5. Comprueba resultados, órdenes y logs: sin errores, mensaje
   `mode=backtest strategy=lean_smoke_test version=0.1.0` y entrada ejecutada en SPY.
   Una orden puede generar varios eventos.
6. Registra versión/commit local o cambios sin commit, fecha, versión del motor si
   está disponible, identificador del backtest y comprobaciones. Guarda resultados
   privados fuera de Git.

No necesitas LEAN CLI, datos locales ni conectar IBKR. El ejemplo rechaza live,
que también incluye paper en tiempo real. `config/backtest.example.json` solo
valida metadatos locales: no se copia al editor ni configura LEAN.

## Datos y supuestos

| Campo | Valor |
|---|---|
| Proveedor | QuantConnect Cloud, conjunto US Equity de la plataforma |
| Instrumento | SPY, ETF estadounidense, símbolo resuelto por LEAN |
| Resolución | Diaria |
| Fechas configuradas | 2024-01-02 a 2024-03-28 |
| Zona horaria | America/New_York |
| Sesión | Regular, sin extended market hours |
| Normalización | Adjusted, ajustes corporativos gestionados por LEAN |
| Capital | 100 000 USD ficticios |
| Entrada | Una solicitud de peso objetivo 10 % tras recibir la primera barra |
| Cuenta y comisiones | Modelo QuantConnect Brokerage cash y comisiones del motor |
| Slippage | ConstantSlippageModel, 0,01 USD por unidad, supuesto técnico |

LEAN determina el momento de ejecución; no se presupone ejecución al cierre de
la primera barra. No se programa salida y puede terminar con posición abierta.
Revisa fills y comisiones efectivos. Spread, impacto, financiación y préstamo no
se modelan de forma calibrada; no valida costes de IBKR.

## Aceptación

Verificar compilación, datos, recepción de barras, orden simulada ejecutada y
resultados. Registrar drawdown, operaciones, exposición y rotación cuando estén
disponibles; marcar lo restante como pendiente. No hay criterio de rentabilidad.
No existe validación fuera de muestra: es una prueba técnica, no una estrategia
candidata. pytest y compileall no prueban LEAN; falta ejecutar el backtest cloud.

Fuentes oficiales:
- https://www.quantconnect.com/docs/v2/cloud-platform/backtesting/getting-started
- https://www.quantconnect.com/docs/v2/cloud-platform/organizations/tier-features
- https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/getting-started
