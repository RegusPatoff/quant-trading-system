from AlgorithmImports import *


class LeanSmokeTest(QCAlgorithm):
    """Prueba técnica de backtest; no es una estrategia de producción."""

    def initialize(self):
        if self.live_mode:
            raise RuntimeError("Fase 1A: este ejemplo solo admite backtesting")

        self.set_start_date(2024, 1, 2)
        self.set_end_date(2024, 3, 28)
        self.set_cash(100_000)
        self.set_time_zone(TimeZones.NEW_YORK)
        self.set_brokerage_model(BrokerageName.QUANTCONNECT_BROKERAGE, AccountType.CASH)
        security = self.add_equity("SPY", Resolution.DAILY)
        security.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
        security.set_slippage_model(ConstantSlippageModel(0.01))
        self._symbol = security.symbol
        self._entry_submitted = False
        self.debug("mode=backtest strategy=lean_smoke_test version=0.1.0")

    def on_data(self, data: Slice):
        if self._entry_submitted or not data.bars.contains_key(self._symbol):
            return
        # Una única solicitud de entrada; LEAN gestiona la orden y su ejecución.
        self._entry_submitted = True
        self.set_holdings(self._symbol, 0.10)

    def on_order_event(self, order_event: OrderEvent):
        self.debug(f"mode=backtest order_id={order_event.order_id} status={order_event.status}")
