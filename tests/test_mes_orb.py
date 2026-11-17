"""Pruebas locales del archivo autónomo, sin ejecutar ni importar LEAN.

AST permite ejecutar las mismas funciones que se copian a Cloud, sin duplicarlas
ni crear un sustituto de AlgorithmImports. Los métodos usan dobles mínimos de
entradas/salidas; no validan el motor, consolidadores ni sus eventos.
"""

import ast
import __future__
import json
import copy
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from types import MethodType, SimpleNamespace
from zoneinfo import ZoneInfo

import pytest


def test_cloud_main_fits_single_file_limit_even_with_windows_line_endings():
    path = Path(__file__).resolve().parents[1] / "strategies/mes_orb/main.py"
    source = path.read_text(encoding="utf-8")
    windows_characters = len(source.replace("\n", "\r\n").encode("utf-16-le")) // 2
    assert windows_characters < 32000


@pytest.fixture(scope="module")
def helpers():
    path = Path(__file__).resolve().parents[1] / "strategies/mes_orb/main.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    pure_nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                  or isinstance(node, ast.ImportFrom) and node.module in ("datetime", "math")
                  or isinstance(node, ast.Import) and any(alias.name == "json" for alias in node.names)
                  or isinstance(node, ast.ClassDef) and node.name in ("FixedTickSlippageModel", "ResearchJournal")]
    namespace = {}
    exec(compile(ast.Module(body=pure_nodes, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


def test_versions_differ_only_in_filter(helpers):
    read = helpers["read_parameters"]
    basic = read({}.get)
    filtered = read({"use_ema_filter": "true"}.get)
    assert basic["use_ema_filter"] is False
    assert filtered.pop("use_ema_filter") is True
    basic.pop("use_ema_filter")
    assert basic == filtered


@pytest.mark.parametrize("key,value", [
    ("opening_range_minutes", "0"), ("opening_range_minutes", "17"),
    ("opening_range_minutes", "1000000000"), ("ema_period", "1"),
    ("ema_period", "501"), ("contracts", "0"), ("contracts", "1.5"),
    ("contracts", "11"), ("use_ema_filter", "yes"), ("reward_risk", "nan"),
    ("max_trade_risk_usd", "inf"), ("max_daily_loss_usd", "-1"),
    ("entry_cutoff", "09:45"), ("entry_cutoff", "16:00"),
    ("entry_cutoff", "noon"), ("slippage_ticks", "-1"),
    ("start_date", "2018-01-01"), ("end_date", "2024-01-01"),
])
def test_reject_invalid_parameters(helpers, key, value):
    with pytest.raises(ValueError):
        helpers["read_parameters"]({key: value}.get)


def test_mes_dollar_risk_scales_with_quantity(helpers):
    risk = helpers["price_risk"]
    assert risk(5800, 5780, 1, 5) == 100
    assert risk(5780, 5800, 2, 5) == 200
    # La ruptura puede implicar más riesgo que la anchura del rango.
    assert risk(5803, 5780, 1, 5) == 115


@pytest.mark.parametrize("values", [(5800, 5780, 0, 5), (5800, 5780, 1, 0),
                                  (float("nan"), 5780, 1, 5)])
def test_invalid_risk_inputs(helpers, values):
    with pytest.raises(ValueError):
        helpers["price_risk"](*values)


@pytest.mark.parametrize("entry,stop,direction,expected", [
    (5800, 5780, 1, 5830), (5800, 5820, -1, 5770),
    (5800, 5799.75, 1, 5800.5), (5800, 5800.25, -1, 5799.5),
])
def test_targets_and_tick_rounding(helpers, entry, stop, direction, expected):
    assert helpers["target_price"](entry, stop, direction, 1.5, 0.25) == expected


@pytest.mark.parametrize("direction,stop", [(1, 5801), (-1, 5799), (1, 5800)])
def test_stop_must_be_protective(helpers, direction, stop):
    with pytest.raises(ValueError):
        helpers["target_price"](5800, stop, direction, 1.5, 0.25)


def test_range_requires_every_minute_and_excludes_end(helpers):
    start = datetime(2024, 10, 7, 9, 30)
    end = start + timedelta(minutes=15)
    observed = {start + timedelta(minutes=i) for i in range(15)}
    assert helpers["complete_window"](start, end, observed)
    observed.remove(start + timedelta(minutes=7))
    observed.add(end)
    assert not helpers["complete_window"](start, end, observed)


@pytest.mark.parametrize("quantity,roles,expected", [
    (1, ["stop"], "cancel"), (1, ["entry", "stop"], "cancel"),
    (0, ["stop"], "cancel"), (1, ["exit"], "wait"),
    (1, ["stop", "exit"], "cancel"), (1, [], "flatten"),
    (-1, [], "flatten"), (0, [], "done"),
])
def test_exit_serialization(helpers, quantity, roles, expected):
    assert helpers["exit_action"](quantity, roles) == expected


@pytest.fixture(scope="module")
def methods(helpers):
    """Extrae métodos reales para pruebas unitarias con dependencias controladas."""
    path = Path(__file__).resolve().parents[1] / "strategies/mes_orb/main.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    algorithm = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                     and node.name == "MesOpeningRangeBreakout")
    namespace = dict(helpers)
    namespace["OrderStatus"] = Status
    code = ast.Module(body=[node for node in algorithm.body if isinstance(node, ast.FunctionDef)], type_ignores=[])
    exec(compile(code, str(path), "exec", flags=__future__.annotations.compiler_flag), namespace)
    return namespace


class Status(Enum):
    SUBMITTED = 1
    CANCEL_PENDING = 2
    INVALID = 3
    CANCELED = 4
    FILLED = 5


def bind_methods(state, methods, *names):
    # Dependencias de observabilidad de los métodos: no implementan un motor.
    if not hasattr(state, "_journal"):
        state._journal = methods["ResearchJournal"]()
    if not hasattr(state, "time"):
        state.time = datetime(2024, 10, 7, 15, 55)
    if not hasattr(state, "_anomaly"):
        state._anomaly = lambda *args: None
    for name in names:
        setattr(state, name, MethodType(methods[name], state))
    return state


@pytest.fixture
def signal_case(helpers, methods):
    start = datetime(2024, 10, 7, 9, 30)
    end = datetime(2024, 10, 7, 9, 50)
    symbol = type("SymbolInput", (), {"id": SimpleNamespace(date=datetime(2024, 12, 20))})()
    logs, submitted = [], []
    state = SimpleNamespace(
        _p=helpers["read_parameters"]({}.get), _mapped=symbol,
        _mapped_times={end - timedelta(minutes=i) for i in range(1, 6)},
        _range_times={start + timedelta(minutes=i) for i in range(15)},
        _range_start=start, _range_end=start + timedelta(minutes=15),
        _cutoff=start.replace(hour=11, minute=30), _day=start.date(), time=end,
        _range_high=5800, _range_low=5790, is_warming_up=False,
        _halted=False, _attempted=False, _blocked_day=None, _exit_reason=None,
        _signals_detected=0, _session_signals=0,
        _ema_end=None, _continuous_close=None, _day_equity=100_000,
        portfolio=SimpleNamespace(invested=False, total_portfolio_value=100_000),
        transactions=SimpleNamespace(get_open_orders=lambda: []),
        securities={symbol: SimpleNamespace(symbol_properties=SimpleNamespace(
            contract_multiplier=5, minimum_price_variation=0.25))},
        _ny_time=lambda value: value,
        _log=lambda event, **fields: logs.append((event, fields)),
        _skip=lambda reason: logs.append(("skip", {"reason": reason})),
        _submit_order=lambda *args: submitted.append(args),
    )
    bind_methods(state, methods, "_on_mapped_bar")
    bar = SimpleNamespace(time=end - timedelta(minutes=5), end_time=end, close=5801)
    return state, bar, logs, submitted


def test_basic_orb_does_not_access_ema(signal_case):
    class UnavailableEMA:
        def __getattr__(self, name):
            raise AssertionError("ORB básico no debe consultar EMA")

    state, bar, logs, submitted = signal_case
    state._ema = UnavailableEMA()
    state._on_mapped_bar(None, bar)
    assert len(submitted) == 1
    assert state._signals_detected == 1
    assert next(fields for event, fields in logs if event == "signal")["ema"] is None


@pytest.mark.parametrize("ready,synchronized", [(False, True), (True, False)])
def test_filtered_orb_requires_ready_synchronized_ema(signal_case, ready, synchronized):
    state, bar, logs, submitted = signal_case
    state._p["use_ema_filter"] = True
    state._ema = SimpleNamespace(is_ready=ready, current=SimpleNamespace(value=5700))
    state._ema_end = bar.end_time if synchronized else bar.end_time - timedelta(minutes=5)
    state._continuous_close = 5800
    state._on_mapped_bar(None, bar)
    assert not submitted
    assert state._signals_detected == 1
    assert ("skip", {"reason": "ema_not_ready_or_unsynchronized"}) in logs


def test_signal_counter_includes_breakouts_after_first_attempt(signal_case):
    state, bar, _, submitted = signal_case
    state._attempted = True
    state._on_mapped_bar(None, bar)
    assert state._signals_detected == 1
    assert not submitted


@pytest.mark.parametrize("offset", [-1, 1])
def test_delayed_or_future_five_minute_bar_cannot_signal(signal_case, offset):
    state, bar, _, submitted = signal_case
    state.time += timedelta(minutes=offset)
    state._on_mapped_bar(None, bar)
    assert not submitted
    assert state._signals_detected == 0


@pytest.mark.parametrize("offset,duration,expected", [(0, 1, True), (-1, 1, False),
                                                    (1, 1, False), (0, 5, False)])
def test_only_current_closed_minute_is_consumed(helpers, offset, duration, expected):
    now = datetime(2024, 10, 7, 9, 50)
    end = now + timedelta(minutes=offset)
    assert helpers["current_minute"](end - timedelta(minutes=duration), end, now) is expected


@pytest.mark.parametrize("direction,close,expected", [(1, 5809.75, False), (1, 5810, True),
    (1, 5811, True), (-1, 5810.25, False), (-1, 5810, True), (-1, 5809, True)])
def test_synthetic_target_uses_close_not_touch(helpers, direction, close, expected):
    assert helpers["target_reached"](close, 5810, direction) is expected
    assert not helpers["target_reached"](close, None, direction)


@pytest.mark.parametrize("day", [(2024, 1, 10), (2024, 7, 10), (2024, 3, 8),
                                (2024, 3, 11), (2024, 11, 1), (2024, 11, 4)])
def test_chicago_new_york_conversion_across_dst(methods, day):
    state = SimpleNamespace(_exchange_zone=ZoneInfo("America/Chicago"), _ny=ZoneInfo("America/New_York"))
    assert methods["_ny_time"](state, datetime(*day, 8, 30)) == datetime(*day, 9, 30)


def test_new_york_exchange_bars_are_not_shifted_again(methods):
    state = SimpleNamespace(_exchange_zone=ZoneInfo("America/New_York"), _ny=ZoneInfo("America/New_York"))
    stamp = datetime(2024, 10, 7, 9, 30)
    assert methods["_ny_time"](state, stamp) == stamp


class CancelTicket:
    """Entrada/salida controlada: no reproduce la cola ni el bróker de LEAN."""
    def __init__(self, order, accepted=True):
        self.order = order
        self.accepted = accepted
        self.calls = 0

    @property
    def status(self):
        return self.order.status

    def cancel(self):
        self.calls += 1
        if self.accepted:
            self.order.status = Status.CANCEL_PENDING
        return SimpleNamespace(is_success=self.accepted)


@pytest.fixture
def exit_case(methods):
    order = SimpleNamespace(id=1, tag="ORB|stop", status=Status.SUBMITTED)
    ticket = CancelTicket(order)
    orders, submitted, finished, logs = [order], [], [], []
    holding = SimpleNamespace(quantity=3)
    state = SimpleNamespace(
        _draining=False, _exit_reason="session_close_1555", _last_exit_state=None,
        _trade={"symbol": "MES"}, portfolio={"MES": holding},
        _order_roles={}, _submitting_role=None,
        _open_orders=lambda: orders,
        transactions=SimpleNamespace(get_order_ticket=lambda order_id: ticket),
        _submit_order=lambda *args: submitted.append(args),
        _finish_trade=lambda: finished.append(True),
        _log=lambda event, **fields: logs.append((event, fields)),
    )
    bind_methods(state, methods, "_drain_exit", "_order_role")
    return state, holding, orders, ticket, submitted, finished, logs


def test_close_waits_for_cancel_confirmation_and_uses_residual_position(exit_case):
    state, holding, orders, ticket, submitted, _, _ = exit_case
    state._drain_exit()
    state._drain_exit()
    assert ticket.calls == 1  # No reenvía una cancelación pendiente.
    assert not submitted
    assert orders[0].tag == "ORB|stop"
    holding.quantity = 1  # Un fill parcial mientras la cancelación estaba pendiente.
    orders.clear()  # La confirmación terminal la aporta el sistema externo al método.
    state._drain_exit()
    assert submitted == [("exit", "MES", -1)]


def test_stop_fill_during_cancellation_does_not_reverse_position(exit_case):
    state, holding, orders, _, submitted, finished, _ = exit_case
    state._drain_exit()
    holding.quantity = 0
    orders.clear()
    state._drain_exit()
    assert not submitted
    assert finished == [True]


def test_cancel_rejection_does_not_allow_parallel_market_exit(exit_case):
    state, _, _, ticket, submitted, _, logs = exit_case
    ticket.accepted = False
    state._drain_exit()
    state._drain_exit()
    assert ticket.calls == 2
    assert not submitted
    assert any(event == "cancel_error" for event, _ in logs)


def test_pending_partial_exit_is_not_duplicated(exit_case):
    state, holding, orders, _, submitted, _, _ = exit_case
    orders[0].tag = "ORB|exit"
    holding.quantity = 1
    state._drain_exit()
    assert not submitted


def test_1555_blocks_session_and_starts_cancellation(exit_case, methods):
    state, _, _, ticket, submitted, _, _ = exit_case
    state.time = datetime(2024, 10, 7, 15, 55)
    state.is_warming_up = False
    bind_methods(state, methods, "_request_exit", "_close_session")
    state._close_session()
    assert state._blocked_day == state.time.date()
    assert ticket.calls == 1
    assert not submitted


def test_order_identity_survives_tag_changes(exit_case):
    state, _, orders, _, _, _, _ = exit_case
    assert state._order_role(orders[0]) == "stop"
    orders[0].tag = "Mensaje de cancelación o actualización"
    assert state._order_role(orders[0]) == "stop"


def test_submission_identifies_reentrant_rejection_before_ticket_returns(methods):
    state = SimpleNamespace(_submitting_role=None, _order_roles={})
    bind_methods(state, methods, "_order_role", "_submit_order")

    def submit(symbol, quantity, **kwargs):
        order = SimpleNamespace(id=9, tag="Rechazo anterior al retorno del ticket")
        assert state._order_role(order) == "exit"
        return SimpleNamespace(order_id=9)

    state.market_order = submit
    state._submit_order("exit", "MES", -1)
    assert state._order_roles == {9: "exit"}
    assert state._submitting_role is None


def test_partial_entry_counts_one_entry_and_partial_stop_requests_exit(methods):
    orders = {1: SimpleNamespace(id=1, tag="ORB|entry"), 2: SimpleNamespace(id=2, tag="ORB|stop")}
    state = SimpleNamespace(
        _order_roles={}, _submitting_role=None,
        transactions=SimpleNamespace(get_order_by_id=orders.get),
        _fees=0, _entries=0, _session_entries=0, _slippage_estimate=0,
        _p={"slippage_ticks": 1}, _exit_reason=None,
        _trade={"fees": 0, "cashflow": 0, "multiplier": 5, "tick": 0.25,
                "entry_qty": 0, "entry_value": 0, "exit_qty": 0, "exit_value": 0},
        _log=lambda *args, **kwargs: None, _protect_position=lambda: None,
    )
    bind_methods(state, methods, "_order_role", "on_order_event")
    event = SimpleNamespace(order_id=1, symbol="MES", order_fee=SimpleNamespace(value=SimpleNamespace(amount=0.5)),
                            status=Status.SUBMITTED, fill_quantity=1, fill_price=5800, message="fill parcial")
    state.on_order_event(event)
    state.on_order_event(event)
    assert state._entries == state._session_entries == 1
    assert state._trade["entry_qty"] == 2
    event.order_id, event.fill_quantity = 2, -1
    state.on_order_event(event)
    assert state._exit_reason == "stop_loss"
    assert state._trade["exit_qty"] == 1


def test_live_and_paper_guard_is_preserved(methods):
    with pytest.raises(RuntimeError, match="solo backtesting"):
        methods["initialize"](SimpleNamespace(live_mode=True))


def test_rejected_exit_uses_identity_and_stops_after_three_rejections(methods):
    order = SimpleNamespace(id=8, tag="Texto de rechazo que sustituyó la etiqueta")
    state = SimpleNamespace(
        _order_roles={8: "exit"}, _submitting_role=None,
        transactions=SimpleNamespace(get_order_by_id=lambda order_id: order),
        _fees=0, _trade={"fees": 0}, _exit_failures=0, _halted=False,
        _log=lambda *args, **kwargs: None, _request_exit=lambda reason: None,
    )
    bind_methods(state, methods, "_order_role", "on_order_event")
    event = SimpleNamespace(order_id=8, symbol="MES", order_fee=SimpleNamespace(value=SimpleNamespace(amount=0)),
                            status=Status.INVALID, fill_quantity=0, fill_price=0, message="rechazo")
    state.on_order_event(event)
    state.on_order_event(event)
    with pytest.raises(RuntimeError, match="Tres rechazos"):
        state.on_order_event(event)
    assert state._halted


@pytest.mark.parametrize("missing,flat_range,expected_complete,expected_range", [
    (None, False, True, True), (100, False, False, True),
    (5, False, False, False), (None, True, True, False),
])
def test_session_counters_are_independent_and_recorded_once(methods, missing, flat_range,
                                                           expected_complete, expected_range):
    start = datetime(2024, 10, 7, 9, 30)
    stamps = {start + timedelta(minutes=i) for i in range(385) if i != missing}
    state = SimpleNamespace(
        _session_observed=True, _range_start=start, _range_end=start + timedelta(minutes=15),
        _range_times={stamp for stamp in stamps if stamp < start + timedelta(minutes=15)},
        _session_times=stamps, _range_high=5800, _range_low=5800 if flat_range else 5790,
        _session_mapping_changed=False, _day=start.date(),
        _sessions_seen=0, _sessions_complete=0, _sessions_valid_range=0,
        _session_signals=4, _session_entries=1, _log=lambda *args, **kwargs: None,
        _journal=methods["ResearchJournal"](),
    )
    methods["_record_session"](state)
    methods["_record_session"](state)
    assert state._sessions_seen == 1
    assert state._sessions_complete == int(expected_complete)
    assert state._sessions_valid_range == int(expected_range)


@pytest.mark.parametrize("ticks,points", [(0, 0.0), (1, 0.25), (2, 0.50)])
def test_fixed_tick_slippage_returns_price_points(helpers, ticks, points):
    asset = SimpleNamespace(symbol_properties=SimpleNamespace(minimum_price_variation=0.25))
    model = helpers["FixedTickSlippageModel"](ticks)
    assert model.get_slippage_approximation(asset, None) == points


def test_one_mes_tick_costs_one_dollar_twenty_five_per_contract(helpers):
    asset = SimpleNamespace(symbol_properties=SimpleNamespace(
        minimum_price_variation=0.25, contract_multiplier=5))
    points = helpers["FixedTickSlippageModel"](1).get_slippage_approximation(asset, None)
    assert points * asset.symbol_properties.contract_multiplier * 1 == 1.25


@pytest.mark.parametrize("price", [3000, 5800, 7000])
def test_tick_slippage_is_independent_of_mes_price(helpers, price):
    asset = SimpleNamespace(price=price, symbol_properties=SimpleNamespace(minimum_price_variation=0.25))
    assert helpers["FixedTickSlippageModel"](1).get_slippage_approximation(asset, None) == 0.25


@pytest.mark.parametrize("quantity", [1, -1, 3, -3])
def test_model_returns_unsigned_unit_price_offset_not_total_order_cost(helpers, quantity):
    asset = SimpleNamespace(symbol_properties=SimpleNamespace(minimum_price_variation=0.25))
    order = SimpleNamespace(quantity=quantity)
    assert helpers["FixedTickSlippageModel"](1).get_slippage_approximation(asset, order) == 0.25


@pytest.mark.parametrize("ticks", [-1, 1.5, True])
def test_slippage_model_rejects_invalid_tick_count(helpers, ticks):
    with pytest.raises(ValueError):
        helpers["FixedTickSlippageModel"](ticks)


def test_security_initializer_installs_parameterized_tick_model(helpers, methods):
    installed = []
    state = SimpleNamespace(_p={"slippage_ticks": 2})
    asset = SimpleNamespace(symbol_properties=SimpleNamespace(minimum_price_variation=0.25),
                            set_slippage_model=installed.append)
    methods["_initialize_security"](state, asset)
    assert isinstance(installed[0], helpers["FixedTickSlippageModel"])
    assert installed[0].get_slippage_approximation(asset, None) == 0.50


def test_filled_prices_already_include_slippage_and_estimate_is_not_deducted_again(methods):
    orders = {1: SimpleNamespace(id=1, tag="ORB|entry"), 2: SimpleNamespace(id=2, tag="ORB|exit")}
    logs = []
    state = SimpleNamespace(
        _order_roles={}, _submitting_role=None,
        transactions=SimpleNamespace(get_order_by_id=orders.get),
        _fees=0, _entries=0, _session_entries=0, _completed=0, _slippage_estimate=0,
        _p={"slippage_ticks": 1}, _exit_reason="target_close_1m",
        _trade={"symbol": "MES", "fees": 0, "cashflow": 0, "multiplier": 5, "tick": 0.25,
                "entry_qty": 0, "entry_value": 0, "exit_qty": 0, "exit_value": 0},
        _log=lambda event, **fields: logs.append((event, fields)), _protect_position=lambda: None,
    )
    bind_methods(state, methods, "_order_role", "on_order_event", "_finish_trade")
    # Entradas de prueba: precios YA ejecutados con 0,25 puntos adversos por lado.
    # Referencias sin slippage: compra 5800 y venta 5810. No ejecutamos un fill model.
    event = SimpleNamespace(order_id=1, symbol="MES", order_fee=SimpleNamespace(value=SimpleNamespace(amount=0.5)),
                            status=Status.FILLED, fill_quantity=1, fill_price=5800.25, message="")
    state.on_order_event(event)
    event.order_id, event.fill_quantity, event.fill_price = 2, -1, 5809.75
    state.on_order_event(event)
    state._finish_trade()
    state._finish_trade()  # No debe contabilizar el cierre dos veces.
    closed = next(fields for name, fields in logs if name == "trade_closed")
    assert state._slippage_estimate == 2.50  # Información, sin un nuevo cargo.
    assert closed["gross_usd"] == 47.50  # 50 USD teóricos menos 2,50 ya en los fills.
    assert closed["fees_usd"] == 1.00
    assert closed["net_usd"] == 46.50  # No 44 USD: eso descontaría slippage dos veces.
    assert state._journal.totals()["t"] == state._completed == 1


def test_2026_default_dates_and_minimal_logging(helpers):
    parameters = helpers["read_parameters"]({}.get)
    assert parameters["start_date"] == "2026-01-01"
    assert parameters["end_date"] == "2026-12-31"
    assert parameters["end_date_effective"] == "2026-11-16"
    assert parameters["log_level"] == "minimal"
    assert helpers["validate_effective_date"](parameters, datetime(2026, 11, 17).date()) == datetime(2026, 11, 16)


@pytest.mark.parametrize("parameters", [{"log_level": "debug"},
    {"end_date_effective": "2027-01-01"}, {"end_date_effective": "2025-12-31"}])
def test_invalid_logging_or_effective_dates(helpers, parameters):
    with pytest.raises(ValueError):
        helpers["read_parameters"](parameters.get)


@pytest.mark.parametrize("effective", ["2026-11-17", "2026-12-31"])
def test_current_or_future_effective_session_is_rejected(helpers, effective):
    parameters = helpers["read_parameters"]({"end_date_effective": effective}.get)
    with pytest.raises(ValueError, match="anterior"):
        helpers["validate_effective_date"](parameters, datetime(2026, 11, 17).date())


def test_full_year_requires_only_changing_effective_end_when_available(helpers):
    parameters = helpers["read_parameters"]({"end_date_effective": "2026-12-31"}.get)
    assert helpers["validate_effective_date"](parameters, datetime(2027, 1, 1).date()) == datetime(2026, 12, 31)


def test_logging_level_does_not_change_signal_decision(signal_case, methods):
    original, bar, _, _ = signal_case
    outcomes, output = [], {}
    for level in ("minimal", "verbose"):
        state = copy.copy(original)
        state._p = dict(original._p, log_level=level)
        submitted, lines = [], []
        state.log = lines.append
        state._submit_order = lambda *args: submitted.append(args)
        bind_methods(state, methods, "_log", "_on_mapped_bar")
        state._on_mapped_bar(None, bar)
        outcomes.append((submitted, state._trade, state._attempted, state._signals_detected))
        output[level] = lines
    assert outcomes[0] == outcomes[1]
    assert len(outcomes[0][0]) == 1
    assert not output["minimal"]
    assert {json.loads(line)["event"] for line in output["verbose"]} == {"breakout_detected", "signal"}


def test_monthly_journal_handles_fees_across_months_and_no_duplicate_emission(helpers):
    journal = helpers["ResearchJournal"]()
    january, february = datetime(2026, 1, 30), datetime(2026, 2, 2)
    journal.record_session(january, True, True)
    journal.record_session(february, False, False)
    journal.record_entry(january)
    journal.record_fee(january, 0.5)
    journal.record_fee(february, 0.5)
    journal.record_trade(february, 10, 1)
    january_rows = list(journal.pending_summaries("2026-02"))
    assert len(january_rows) == 1
    assert january_rows[0]["net"] == -0.5
    february_rows = list(journal.pending_summaries())
    assert len(february_rows) == 1
    assert february_rows[0]["net"] == 9.5
    assert not list(journal.pending_summaries())
    rows = january_rows + february_rows
    totals = journal.totals()
    for key in ("s", "dc", "rv", "e", "t", "w", "l", "g", "fees"):
        assert sum(row[key] for row in rows) == totals[key]
    assert sum(row["net"] for row in rows) == totals["g"] - totals["fees"] == 9


def test_journal_winning_losing_and_breakeven_classification(helpers):
    journal = helpers["ResearchJournal"]()
    day = datetime(2026, 1, 2)
    for gross in (5, -5, 1):
        journal.record_fee(day, 1)
        journal.record_trade(day, gross, 1)
    totals = journal.totals()
    assert (totals["t"], totals["w"], totals["l"]) == (3, 1, 1)
    assert totals["g"] - totals["fees"] == -2


def reporting_state(helpers, methods, level="minimal"):
    lines, errors = [], []
    state = SimpleNamespace(
        time=datetime(2026, 12, 31, 17),
        _p=helpers["read_parameters"]({"log_level": level, "end_date_effective": "2026-12-31"}.get),
        _journal=helpers["ResearchJournal"](), _trade=None, _halted=False,
        _anomalies={}, _anomalies_logged=0, _last_session_with_data="2026-12-31",
        _sessions_seen=0, _sessions_complete=0, _sessions_valid_range=0,
        _signals_detected=0, _entries=0, _completed=0, _fees=0, _slippage_estimate=0,
        _minute_bars=0, portfolio=SimpleNamespace(invested=False),
        _open_orders=lambda: [], _record_session=lambda: None,
        log=lines.append, error=errors.append,
    )
    bind_methods(state, methods, "_log", "_anomaly", "_flush_months", "on_end_of_algorithm")
    return state, lines, errors


def test_full_year_minimal_logs_fit_six_kb_including_prefix_allowance(helpers, methods):
    state, lines, errors = reporting_state(helpers, methods)
    state._log("parameters", version="0.1.3", slippage_model="fixed_ticks",
               exchange_time_zone="America/New_York", **state._p)
    # Escenario sintético de tamaño; no son resultados de mercado ni un backtest.
    for month in range(1, 13):
        day = datetime(2026, month, 2)
        for session in range(23):
            state._journal.record_session(day, True, True)
            state._journal.record_entry(day)
            state._journal.record_fee(day, 1)
            state._journal.record_trade(day, 225 if session % 2 else -150, 1)
            state._log("order", fill_price=5800, fill_quantity=1)
            state._log("session_summary", session_date=day)
        state.time = day.replace(day=28)
        state._flush_months()
    totals = state._journal.totals()
    state._sessions_seen, state._sessions_complete, state._sessions_valid_range = totals["s"], totals["dc"], totals["rv"]
    state._entries, state._completed, state._fees = totals["e"], totals["t"], totals["fees"]
    state._signals_detected, state._minute_bars = 5000, 400000
    state._slippage_estimate = 690.0
    state.on_end_of_algorithm()
    assert not errors
    records = [json.loads(line) for line in lines]
    assert len(records) == 14  # Inicio + 12 meses + resumen.
    assert {record["event"] for record in records} == {"parameters", "month_summary", "summary"}
    # Incluye 64 bytes por línea como margen para prefijos/terminadores de plataforma.
    json_bytes = sum(len(line.encode("utf-8")) for line in lines)
    bytes_with_margin = json_bytes + 64 * len(lines)
    print(f"\nSynthetic annual logs: {json_bytes} JSON bytes; {bytes_with_margin} with line allowance")
    assert bytes_with_margin < 6000
    final = records[-1]
    rows = [record for record in records if record["event"] == "month_summary"]
    assert sum(row["net"] for row in rows) == final["net_profit_usd"]
    assert sum(row["t"] for row in rows) == final["completed_trades"]
    assert sum(row["e"] for row in rows) == final["entries_executed"]
    assert final["valid"] and not final["invested"] and not final["unfinished_trade"]


def test_own_repeated_errors_are_bounded_and_counted_but_invalid_state_remains_visible(helpers, methods):
    state, lines, errors = reporting_state(helpers, methods)
    for _ in range(100):
        state._anomaly("cancel_error", "x" * 1000)
    assert len(errors) == 1
    assert state._anomalies["cancel_error"] == 100
    state._anomaly("stop_rejected")
    state._anomaly("entry_rejected")
    state.portfolio.invested = True
    state.on_end_of_algorithm()
    assert len(errors) == 4  # El estado final inválido no se oculta por el cupo.
    final = json.loads(lines[-1])
    assert not final["valid"] and final["invested"]
    assert final["anomalies"]["invalid_backtest"] == 1


def test_unfinished_trade_and_orders_are_reported_as_invalid(helpers, methods):
    state, lines, errors = reporting_state(helpers, methods)
    state._trade = {"symbol": "MES"}
    state._open_orders = lambda: [SimpleNamespace(id=1)]
    state.on_end_of_algorithm()
    final = json.loads(lines[-1])
    assert not final["valid"] and final["unfinished_trade"] and final["open_orders"] == 1
    assert errors


def test_session_without_minutes_is_never_complete(methods):
    state = SimpleNamespace(
        _session_observed=True, _day=datetime(2026, 1, 2).date(),
        _range_start=datetime(2026, 1, 2, 9, 30), _range_end=datetime(2026, 1, 2, 9, 45),
        _range_times=set(), _session_times=set(), _range_high=None, _range_low=None,
        _session_mapping_changed=False, _session_signals=0, _session_entries=0,
        _sessions_seen=0, _sessions_complete=0, _sessions_valid_range=0,
        _log=lambda *args, **kwargs: None,
    )
    bind_methods(state, methods, "_record_session")
    state._record_session()
    assert (state._sessions_seen, state._sessions_complete, state._sessions_valid_range) == (1, 0, 0)
    assert state._journal.totals()["dc"] == 0


def test_logging_levels_preserve_fills_accounting_and_final_summary(helpers, methods):
    summaries = []
    for level in ("minimal", "verbose"):
        state, lines, errors = reporting_state(helpers, methods, level)
        state.time = datetime(2026, 1, 2, 10)
        orders = {1: SimpleNamespace(id=1, tag="ORB|entry"), 2: SimpleNamespace(id=2, tag="ORB|exit")}
        state.transactions = SimpleNamespace(get_order_by_id=orders.get)
        state._order_roles, state._submitting_role, state._session_entries = {}, None, 0
        state._exit_reason = "target_close_1m"
        state._protect_position = lambda: None
        state._trade = dict(symbol="MES", fees=0, cashflow=0, multiplier=5, tick=0.25,
                            entry_qty=0, entry_value=0, exit_qty=0, exit_value=0)
        bind_methods(state, methods, "_order_role", "on_order_event", "_finish_trade")
        event = SimpleNamespace(order_id=1, symbol="MES", order_fee=SimpleNamespace(value=SimpleNamespace(amount=0.5)),
                                status=Status.FILLED, fill_quantity=1, fill_price=5800.25, message="")
        state.on_order_event(event)
        event.order_id, event.fill_quantity, event.fill_price = 2, -1, 5809.75
        state.on_order_event(event)
        state._finish_trade()
        state.on_end_of_algorithm()
        assert not errors
        summary = json.loads(lines[-1])
        summary.pop("time_ny", None)  # Metadato adicional de verbose, no resultado contable.
        summaries.append(summary)
    assert summaries[0] == summaries[1]
    assert summaries[0]["net_profit_usd"] == 46.5
    assert summaries[0]["winning_trades"] == summaries[0]["completed_trades"] == 1


def test_month_is_not_emitted_while_a_trade_is_pending(helpers, methods):
    state, lines, _ = reporting_state(helpers, methods)
    january = datetime(2026, 1, 30)
    state._journal.record_session(january, True, True)
    state.time = datetime(2026, 2, 2)
    state._trade = {"symbol": "MES"}
    state._flush_months()
    assert not lines
    state._journal.record_trade(january, 10, 0)
    state._trade = None
    state._flush_months()
    assert json.loads(lines[0])["g"] == 10
