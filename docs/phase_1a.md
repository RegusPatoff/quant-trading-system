# Decisiones de Fase 1A

- Entorno Conda `quant-trading`, Python 3.11 y paquete editable con estructura `src`.
- Sin dependencias de ejecución externas. pytest valida configuración; no simula LEAN.
- Backtest en QuantConnect Free mediante copia manual de un único archivo.
- No se instala LEAN CLI ni se conecta ningún bróker.
- El algoritmo es autónomo; no importa el paquete local.
- No se elige mercado de producción. MES, small caps y cortos no están implementados.
- La lógica futura usará LEAN; no habrá un motor de ejecución paralelo.
- Paper, real, riesgo operativo, alertas y recuperación requieren fases posteriores.

Free incluye un nodo gratuito de backtest según la documentación consultada.
Antes de ampliaciones se revisarán precios, impuestos, datos y recursos para
respetar 50 €/mes; no se presume que Researcher Seat más nodos quepan en el límite.

Próximo paso: ejecutar y revisar el backtest cloud, reproducir el entorno en otro
equipo y elegir la primera hipótesis de investigación.

Fuentes:
- https://www.quantconnect.com/docs/v2/cloud-platform/organizations/tier-features
- https://www.quantconnect.com/pricing/
