from AlgorithmImports import *
from datetime import datetime, time, timedelta
from math import ceil, floor, isfinite
from zoneinfo import ZoneInfo
import json

def read_parameters(get_parameter):
    defaults = {'opening_range_minutes': '15', 'ema_period': '50', 'use_ema_filter': 'false', 'reward_risk': '1.5', 'contracts': '1', 'entry_cutoff': '11:30', 'max_trade_risk_usd': '150', 'max_daily_loss_usd': '200', 'slippage_ticks': '1', 'start_date': '2026-01-01', 'end_date': '2026-12-31', 'end_date_effective': '2026-11-16', 'log_level': 'minimal'}
    values = {}
    for key, default in defaults.items():
        raw = get_parameter(key)
        values[key] = default if raw is None or raw == '' else str(raw).strip()
    for key in ('opening_range_minutes', 'ema_period', 'contracts', 'slippage_ticks'):
        values[key] = int(values[key])
    for key in ('reward_risk', 'max_trade_risk_usd', 'max_daily_loss_usd'):
        values[key] = float(values[key])
        if not isfinite(values[key]) or values[key] <= 0:
            raise ValueError(f'{key} debe ser finito y positivo')
    if values['use_ema_filter'].lower() not in ('true', 'false'):
        raise ValueError('use_ema_filter debe ser true o false')
    values['use_ema_filter'] = values['use_ema_filter'].lower() == 'true'
    if values['log_level'] not in ('minimal', 'verbose'):
        raise ValueError('log_level debe ser minimal o verbose')
    cutoff = datetime.strptime(values['entry_cutoff'], '%H:%M').time()
    minutes = values['opening_range_minutes']
    if not 5 <= minutes <= 300:
        raise ValueError('opening_range_minutes debe estar entre 5 y 300')
    range_end = datetime(2000, 1, 1, 9, 30) + timedelta(minutes=minutes)
    if minutes < 5 or minutes % 5 or range_end.time() >= cutoff or (cutoff > time(15, 50)):
        raise ValueError('El rango debe ser múltiplo de 5 y terminar antes de entry_cutoff <= 15:50')
    if not 2 <= values['ema_period'] <= 500:
        raise ValueError('ema_period debe estar entre 2 y 500')
    if not 1 <= values['contracts'] <= 10 or not 0 <= values['slippage_ticks'] <= 20:
        raise ValueError('contracts: 1..10; slippage_ticks: 0..20')
    start = datetime.strptime(values['start_date'], '%Y-%m-%d')
    end = datetime.strptime(values['end_date'], '%Y-%m-%d')
    effective = datetime.strptime(values['end_date_effective'], '%Y-%m-%d')
    if not start <= effective <= end or start < datetime(2019, 5, 6):
        raise ValueError('Fechas incompatibles con el periodo de MES')
    return values

def validate_effective_date(parameters, today):
    effective = datetime.strptime(parameters['end_date_effective'], '%Y-%m-%d')
    if effective.date() >= today:
        raise ValueError('end_date_effective debe ser anterior a la fecha actual de Nueva York')
    return effective

def compact_json(payload):
    return json.dumps(payload, default=str, separators=(',', ':'), allow_nan=False)

class ResearchJournal:

    def __init__(self):
        self.months = {}
        self.emitted_months = set()

    def month(self, date):
        key = date.strftime('%Y-%m')
        if key not in self.months:
            self.months[key] = dict(s=0, dc=0, rv=0, e=0, t=0, w=0, l=0, g=0.0, fees=0.0)
        return self.months[key]

    def record_session(self, date, complete, valid_range):
        row = self.month(date)
        row['s'] += 1
        row['dc'] += int(complete)
        row['rv'] += int(valid_range)

    def record_entry(self, date):
        self.month(date)['e'] += 1

    def record_fee(self, date, fee):
        self.month(date)['fees'] += fee

    def record_trade(self, date, gross, trade_fees):
        row = self.month(date)
        row['t'] += 1
        row['w'] += int(gross - trade_fees > 0)
        row['l'] += int(gross - trade_fees < 0)
        row['g'] += gross

    def totals(self):
        return {key: sum((row[key] for row in self.months.values())) for key in ('s', 'dc', 'rv', 'e', 't', 'w', 'l', 'g', 'fees')}

    def pending_summaries(self, before=None):
        for month, row in sorted(self.months.items()):
            if month in self.emitted_months or (before is not None and month >= before):
                continue
            self.emitted_months.add(month)
            yield dict(m=month, **{key: round(value, 2) for key, value in row.items()}, net=round(row['g'] - row['fees'], 2))

def price_risk(entry, stop, quantity, multiplier):
    values = (entry, stop, quantity, multiplier)
    if not all((isfinite(float(value)) for value in values)) or quantity <= 0 or multiplier <= 0:
        raise ValueError('Datos de riesgo inválidos')
    return abs(entry - stop) * multiplier * quantity

def target_price(entry, stop, direction, reward_risk, tick):
    if direction not in (-1, 1) or tick <= 0 or reward_risk <= 0:
        raise ValueError('Dirección, tick o R/R inválidos')
    if direction * (entry - stop) <= 0:
        raise ValueError('El stop no está en el lado protector')
    target = entry + direction * abs(entry - stop) * reward_risk
    return (ceil(target / tick) if direction > 0 else floor(target / tick)) * tick

def complete_window(start, end, observed):
    expected = int((end - start).total_seconds() / 60)
    return expected > 0 and all((start + timedelta(minutes=i) in observed for i in range(expected)))

def exit_action(quantity, open_roles):
    if any((role != 'exit' for role in open_roles)):
        return 'cancel'
    if 'exit' in open_roles:
        return 'wait'
    return 'flatten' if quantity else 'done'

def current_minute(start, end, now):
    return end == now and end - start == timedelta(minutes=1)

def target_reached(close, target, direction):
    return target is not None and direction * (close - target) >= 0

class MesOpeningRangeBreakout(QCAlgorithm):

    def initialize(self):
        if self.live_mode:
            raise RuntimeError('MES ORB research: solo backtesting; paper/live no autorizados')
        self._p = read_parameters(self.get_parameter)
        start = datetime.strptime(self._p['start_date'], '%Y-%m-%d')
        end = validate_effective_date(self._p, datetime.now(ZoneInfo('America/New_York')).date())
        self._journal = ResearchJournal()
        self._anomalies = {}
        self._anomalies_logged = 0
        self._last_session_with_data = None
        self.set_start_date(start.year, start.month, start.day)
        self.set_end_date(end.year, end.month, end.day)
        self.set_time_zone(TimeZones.NEW_YORK)
        self.set_cash(100000)
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.add_security_initializer(self._initialize_security)
        self._future = self.add_future(Futures.Indices.MICRO_SP_500_E_MINI, Resolution.MINUTE, fill_forward=False, extended_market_hours=True, data_mapping_mode=DataMappingMode.OPEN_INTEREST, data_normalization_mode=DataNormalizationMode.BACKWARDS_RATIO, contract_depth_offset=0)
        self._future.set_filter(0, 90)
        self._ny = ZoneInfo('America/New_York')
        self._exchange_zone = ZoneInfo(str(self._future.exchange.time_zone))
        self._ema = ExponentialMovingAverage(self._p['ema_period'])
        self._ema_end = None
        self._continuous_close = None
        self._continuous_times = set()
        self._mapped_times = set()
        self._continuous_consolidator = TradeBarConsolidator(timedelta(minutes=5))
        self._continuous_consolidator.data_consolidated += self._on_continuous_bar
        self._mapped_consolidator = None
        self._mapped = None
        self._day = None
        self._blocked_day = None
        self._halted = False
        self._attempted = False
        self._trade = None
        self._stop_ticket = None
        self._submitting_stop = False
        self._exit_reason = None
        self._draining = False
        self._last_exit_state = None
        self._completed = 0
        self._entries = 0
        self._fees = 0.0
        self._slippage_estimate = 0.0
        self._exit_failures = 0
        self._order_roles = {}
        self._submitting_role = None
        self._minute_bars = 0
        self._sessions_seen = 0
        self._sessions_complete = 0
        self._sessions_valid_range = 0
        self._signals_detected = 0
        self._session_observed = False
        self._range_times = set()
        self._range_high = None
        self._range_low = None
        self._reasons = set()
        self.schedule.on(self.date_rules.every_day(), self.time_rules.at(15, 55), self._close_session)
        self.set_warm_up(timedelta(days=7))
        self._log('parameters', version='0.1.3', slippage_model='fixed_ticks', exchange_time_zone=str(self._exchange_zone), **self._p)

    def _log(self, event, **fields):
        if self._p['log_level'] == 'minimal' and event not in ('parameters', 'month_summary', 'summary'):
            return
        payload = {'mode': 'backtest', 'event': event, **fields}
        if self._p['log_level'] == 'verbose':
            payload['time_ny'] = str(self.time)
        self.log(compact_json(payload))

    def _anomaly(self, reason, message=''):
        count = self._anomalies.get(reason, 0) + 1
        self._anomalies[reason] = count
        if self._p['log_level'] == 'verbose' or reason == 'invalid_backtest' or (count == 1 and self._anomalies_logged < 3):
            self._anomalies_logged += 1
            self.error(compact_json(dict(event='anomaly', reason=reason, time_ny=str(self.time), message=str(message) if self._p['log_level'] == 'verbose' else str(message)[:160])))

    def _flush_months(self, final=False):
        if self._trade is not None and (not final):
            return
        before = None if final else self.time.strftime('%Y-%m')
        for row in self._journal.pending_summaries(before):
            self._log('month_summary', **row)

    def _skip(self, reason):
        if reason not in self._reasons and (not self.is_warming_up):
            self._reasons.add(reason)
            self._log('skip', reason=reason)

    def _initialize_security(self, security):
        security.set_slippage_model(FixedTickSlippageModel(self._p['slippage_ticks']))

    def _ny_time(self, value):
        return value.replace(tzinfo=self._exchange_zone).astimezone(self._ny).replace(tzinfo=None)

    def _new_day(self):
        if self._day == self.time.date():
            return
        self._record_session()
        if self._trade is not None or self.transactions.get_open_orders():
            self._halted = True
            self._anomaly('overnight_invariant_breach')
            self._request_exit('overnight_invariant_breach')
        self._day = self.time.date()
        self._day_equity = float(self.portfolio.total_portfolio_value)
        self._attempted = False
        self._range_times = set()
        self._range_high = self._range_low = None
        self._reasons = set()
        self._session_times = set()
        self._session_observed = False
        self._session_mapping_changed = False
        self._session_signals = 0
        self._session_entries = 0
        self._range_start = datetime.combine(self._day, time(9, 30))
        self._range_end = self._range_start + timedelta(minutes=self._p['opening_range_minutes'])
        self._cutoff = datetime.combine(self._day, datetime.strptime(self._p['entry_cutoff'], '%H:%M').time())

    def _record_session(self):
        if not self._session_observed:
            return
        range_complete = complete_window(self._range_start, self._range_end, self._range_times)
        range_valid = range_complete and self._range_high is not None and (self._range_low is not None) and (self._range_high > self._range_low) and (not self._session_mapping_changed)
        session_end = datetime.combine(self._day, time(15, 55))
        data_complete = complete_window(self._range_start, session_end, self._session_times) and (not self._session_mapping_changed)
        self._sessions_seen += 1
        self._sessions_complete += int(data_complete)
        self._sessions_valid_range += int(range_valid)
        self._journal.record_session(self._day, data_complete, range_valid)
        if self._session_times:
            self._last_session_with_data = str(self._day)
        self._log('session_summary', session_date=self._day, data_complete=data_complete, observed_minutes=len(self._session_times), expected_minutes=385, range_complete=range_complete, range_valid=range_valid, mapping_changed=self._session_mapping_changed, signals_detected=self._session_signals, entries_executed=self._session_entries)
        self._session_observed = False

    def _change_contract(self, symbol):
        previous = self._mapped
        if previous is not None:
            self._session_mapping_changed = True
            self._blocked_day = self.time.date()
            if not self.is_warming_up:
                self._request_exit('rollover')
            self._ema.reset()
            self._ema_end = None
            self._continuous_close = None
            self._continuous_times.clear()
            self._continuous_consolidator.dispose()
            self._continuous_consolidator = TradeBarConsolidator(timedelta(minutes=5))
            self._continuous_consolidator.data_consolidated += self._on_continuous_bar
        if self._mapped_consolidator is not None:
            self._mapped_consolidator.dispose()
        self.add_future_contract(symbol, Resolution.MINUTE, fill_forward=False, extended_market_hours=True)
        self._mapped = symbol
        self._mapped_times.clear()
        self._range_times.clear()
        self._range_high = self._range_low = None
        self._mapped_consolidator = TradeBarConsolidator(timedelta(minutes=5))
        self._mapped_consolidator.data_consolidated += self._on_mapped_bar
        self._log('mapping', old=previous, new=symbol, skip_session=previous is not None)

    def on_data(self, data: Slice):
        self._new_day()
        mapped = self._future.mapped
        if mapped is not None and mapped != Symbol.EMPTY and (mapped != self._mapped):
            self._change_contract(mapped)
        continuous = data.bars.get(self._future.symbol)
        if continuous is not None and (not continuous.is_fill_forward) and current_minute(self._ny_time(continuous.time), self._ny_time(continuous.end_time), self.time):
            self._continuous_times.add(continuous.time)
            self._continuous_consolidator.update(continuous)
            self._continuous_consolidator.scan(continuous.end_time)
        if self.is_warming_up:
            return
        if self.time.weekday() < 5:
            self._session_observed = True
        if self.time.time() >= time(15, 55):
            self._close_session()
        loss = self._day_equity - float(self.portfolio.total_portfolio_value)
        if loss >= self._p['max_daily_loss_usd']:
            self._blocked_day = self._day
            self._request_exit('daily_loss')
        bar = data.bars.get(self._mapped) if self._mapped is not None else None
        if bar is not None and (not current_minute(self._ny_time(bar.time), self._ny_time(bar.end_time), self.time)):
            self._skip('mapped_bar_timestamp_mismatch')
            bar = None
        if bar is not None and (not bar.is_fill_forward):
            self._minute_bars += 1
            local_start = self._ny_time(bar.time)
            local_end = self._ny_time(bar.end_time)
            if self._range_start <= local_start < datetime.combine(self._day, time(15, 55)):
                self._session_times.add(local_start)
            if self._range_start <= local_start < self._range_end:
                self._range_times.add(local_start)
                high, low = (float(bar.high), float(bar.low))
                self._range_high = high if self._range_high is None else max(self._range_high, high)
                self._range_low = low if self._range_low is None else min(self._range_low, low)
            self._mapped_times.add(bar.time)
            self._mapped_consolidator.update(bar)
            self._mapped_consolidator.scan(bar.end_time)
            if self._trade and self._exit_reason is None and (self._trade['target'] is not None):
                trade = self._trade
                if trade['symbol'] == bar.symbol and target_reached(float(bar.close), trade['target'], trade['direction']):
                    self._log('target_trigger', bar_end=local_end, close=float(bar.close), target=trade['target'], direction=trade['direction'])
                    self._request_exit('target_close_1m')
        if self._exit_reason is not None:
            self._drain_exit()
        self._flush_months()

    def _on_continuous_bar(self, sender, bar):
        valid = complete_window(bar.time, bar.end_time, self._continuous_times)
        self._continuous_times = {stamp for stamp in self._continuous_times if stamp >= bar.end_time}
        if valid:
            self._ema.update(bar.end_time, bar.close)
            self._ema_end = self._ny_time(bar.end_time)
            self._continuous_close = float(bar.close)

    def _on_mapped_bar(self, sender, bar):
        valid = complete_window(bar.time, bar.end_time, self._mapped_times)
        self._mapped_times = {stamp for stamp in self._mapped_times if stamp >= bar.end_time}
        end = self._ny_time(bar.end_time)
        if self.is_warming_up or not valid or (not self._range_end < end < self._cutoff):
            return
        if end != self.time:
            self._skip('delayed_signal_bar')
            return
        if not complete_window(self._range_start, self._range_end, self._range_times):
            self._skip('incomplete_opening_range')
            return
        if self._range_high <= self._range_low:
            self._skip('empty_opening_range')
            return
        if self._mapped.id.date.date() <= self._day + timedelta(days=1):
            self._skip('near_expiry')
            return
        close = float(bar.close)
        direction = 1 if close > self._range_high else -1 if close < self._range_low else 0
        if not direction:
            return
        self._signals_detected += 1
        self._session_signals += 1
        self._log('breakout_detected', bar_end=end, direction=direction, close=close)
        if self._halted or self._attempted or self._blocked_day == self._day or self._exit_reason:
            return
        if self.portfolio.invested or self.transactions.get_open_orders():
            return
        ema_value = None
        if self._p['use_ema_filter']:
            if not self._ema.is_ready or self._ema_end != end or self._continuous_close is None:
                self._skip('ema_not_ready_or_unsynchronized')
                return
            ema_value = float(self._ema.current.value)
            if direction * (self._continuous_close - ema_value) <= 0:
                self._skip('ema_filter')
                return
        security = self.securities[self._mapped]
        multiplier = float(security.symbol_properties.contract_multiplier)
        tick = float(security.symbol_properties.minimum_price_variation)
        if multiplier != 5 or tick != 0.25:
            raise RuntimeError('Metadatos MES inesperados: se esperan 5 USD/punto y tick 0.25')
        stop = self._range_low if direction == 1 else self._range_high
        expected_entry = close + direction * tick * self._p['slippage_ticks']
        risk = price_risk(expected_entry, stop, self._p['contracts'], multiplier)
        range_risk = price_risk(self._range_high, self._range_low, 1, multiplier)
        if range_risk > self._p['max_trade_risk_usd'] or risk > self._p['max_trade_risk_usd']:
            self._skip('trade_risk_limit')
            return
        if self._day_equity - float(self.portfolio.total_portfolio_value) + risk >= self._p['max_daily_loss_usd']:
            self._skip('daily_risk_budget')
            return
        self._attempted = True
        self._trade = {'symbol': self._mapped, 'direction': direction, 'stop': stop, 'target': None, 'multiplier': multiplier, 'tick': tick, 'cashflow': 0.0, 'fees': 0.0, 'entry_qty': 0, 'entry_value': 0.0, 'exit_qty': 0, 'exit_value': 0.0}
        self._stop_ticket = None
        self._log('signal', symbol=self._mapped, bar_end=end, close=close, stop=stop, range_high=self._range_high, range_low=self._range_low, ema=ema_value, continuous_close=self._continuous_close if self._p['use_ema_filter'] else None, direction=direction, estimated_price_risk_usd=risk)
        self._submit_order('entry', self._mapped, direction * self._p['contracts'])

    def _order_role(self, order):
        if order.id not in self._order_roles:
            role = order.tag.split('|')[-1]
            if role not in ('entry', 'stop', 'exit'):
                role = self._submitting_role or 'unknown'
            self._order_roles[order.id] = role
        return self._order_roles[order.id]

    def _submit_order(self, role, symbol, quantity, stop=None):
        previous = self._submitting_role
        self._submitting_role = role
        try:
            if role == 'stop':
                ticket = self.stop_market_order(symbol, quantity, stop, tag='ORB|stop')
            else:
                ticket = self.market_order(symbol, quantity, asynchronous=True, tag=f'ORB|{role}')
            self._order_roles[ticket.order_id] = role
            return ticket
        finally:
            self._submitting_role = previous

    def _open_orders(self):
        return self.transactions.get_open_orders()

    def _request_exit(self, reason):
        if self._trade is None and (not self._open_orders()):
            return
        if self._exit_reason is None:
            self._exit_reason = reason
            self._log('exit_requested', reason=reason, open_orders=len(self._open_orders()))
            if reason in ('fill_beyond_stop', 'fill_risk_exceeded', 'stop_update_failed', 'stop_rejected'):
                self._anomaly(reason)

    def _close_session(self):
        if not self.is_warming_up:
            self._blocked_day = self.time.date()
            self._request_exit('session_close_1555')
            self._drain_exit()

    def _drain_exit(self):
        if self._draining or self._exit_reason is None:
            return
        self._draining = True
        try:
            orders = self._open_orders()
            quantity = int(self.portfolio[self._trade['symbol']].quantity) if self._trade else 0
            roles = [self._order_role(order) for order in orders]
            action = exit_action(quantity, roles)
            state = (action, quantity, tuple(((order.id, str(order.status)) for order in orders)))
            if state != self._last_exit_state:
                self._last_exit_state = state
                self._log('exit_state', action=action, position_quantity=quantity, open_order_ids=[order.id for order in orders], roles=roles)
            if action == 'cancel':
                for order in orders:
                    if self._order_role(order) == 'exit':
                        continue
                    ticket = self.transactions.get_order_ticket(order.id)
                    if ticket.status != OrderStatus.CANCEL_PENDING:
                        response = ticket.cancel()
                        self._log('cancel_requested', order_id=order.id, role=self._order_role(order), accepted=response.is_success, reason=self._exit_reason)
                        if not response.is_success:
                            self._log('cancel_error', order_id=order.id, response=str(response))
                            self._anomaly('cancel_error', response)
            elif action == 'flatten':
                self._log('exit_submitted', symbol=self._trade['symbol'], quantity=-quantity, reason=self._exit_reason, open_orders=0)
                self._submit_order('exit', self._trade['symbol'], -quantity)
            elif action == 'done':
                self._finish_trade()
        finally:
            self._draining = False

    def _protect_position(self):
        if self._exit_reason or self._submitting_stop or self._trade is None:
            return
        trade = self._trade
        quantity = int(self.portfolio[trade['symbol']].quantity)
        if not quantity:
            return
        average = trade['entry_value'] / trade['entry_qty']
        if trade['direction'] * (average - trade['stop']) <= 0:
            self._request_exit('fill_beyond_stop')
            return
        trade['target'] = target_price(average, trade['stop'], trade['direction'], self._p['reward_risk'], trade['tick'])
        self._submitting_stop = True
        try:
            if self._stop_ticket is None:
                self._stop_ticket = self._submit_order('stop', trade['symbol'], -quantity, trade['stop'])
                if self._stop_ticket.status == OrderStatus.INVALID:
                    self._request_exit('stop_rejected')
            elif not self._stop_ticket.status.is_closed():
                desired = int(self._stop_ticket.quantity_filled) - quantity
                if int(self._stop_ticket.quantity) != desired:
                    response = self._stop_ticket.update_quantity(desired)
                    if not response.is_success:
                        self._request_exit('stop_update_failed')
        finally:
            self._submitting_stop = False
        actual_risk = price_risk(average, trade['stop'], abs(quantity), trade['multiplier'])
        if actual_risk > self._p['max_trade_risk_usd']:
            self._request_exit('fill_risk_exceeded')
        self._log('protection', quantity=quantity, average_entry=average, stop=trade['stop'], target=trade['target'], price_risk_usd=actual_risk)

    def on_order_event(self, event: OrderEvent):
        order = self.transactions.get_order_by_id(event.order_id)
        if order is None:
            return
        role = self._order_role(order)
        fee = float(event.order_fee.value.amount)
        self._fees += fee
        if fee:
            self._journal.record_fee(self.time, fee)
        self._log('order', order_id=event.order_id, symbol=event.symbol, role=role, status=str(event.status), fill_quantity=event.fill_quantity, fill_price=event.fill_price, fee_usd=fee, message=event.message)
        trade = self._trade
        if trade is None:
            return
        trade['fees'] += fee
        if event.fill_quantity:
            qty, price = (int(event.fill_quantity), float(event.fill_price))
            trade['cashflow'] -= qty * price * trade['multiplier']
            self._slippage_estimate += abs(qty) * trade['tick'] * self._p['slippage_ticks'] * trade['multiplier']
            if role == 'entry':
                if trade['entry_qty'] == 0:
                    self._entries += 1
                    self._session_entries += 1
                    self._journal.record_entry(self.time)
                trade['entry_qty'] += abs(qty)
                trade['entry_value'] += abs(qty) * price
                self._protect_position()
            else:
                trade['exit_qty'] += abs(qty)
                trade['exit_value'] += abs(qty) * price
                trade['last_exit_time'] = self.time
                if role == 'stop':
                    self._exit_reason = 'stop_loss'
        if event.status == OrderStatus.INVALID:
            self._halted = True
            self._anomaly(f'{role}_rejected', event.message)
            self._request_exit(f'{role}_rejected')
            if role == 'exit':
                self._exit_failures += 1
                if self._exit_failures >= 3:
                    raise RuntimeError('Tres rechazos de cierre: backtest inválido; revisar margen y órdenes')
        elif event.status == OrderStatus.CANCELED and role in ('entry', 'stop') and (self._exit_reason is None):
            self._anomaly(f'{role}_unexpected_cancel')
            self._request_exit(f'{role}_unexpected_cancel')

    def _finish_trade(self):
        trade = self._trade
        if trade and trade['entry_qty']:
            self._completed += 1
            gross = trade['cashflow']
            self._journal.record_trade(trade.get('last_exit_time', self.time), gross, trade['fees'])
            self._log('trade_closed', trade_number=self._completed, symbol=trade['symbol'], entry_quantity=trade['entry_qty'], exit_quantity=trade['exit_qty'], average_entry=trade['entry_value'] / trade['entry_qty'], average_exit=trade['exit_value'] / trade['exit_qty'] if trade['exit_qty'] else None, gross_usd=gross, fees_usd=trade['fees'], net_usd=gross - trade['fees'], reason=self._exit_reason)
        self._trade = None
        self._stop_ticket = None
        self._exit_reason = None
        self._last_exit_state = None

    def on_end_of_algorithm(self):
        self._record_session()
        self._flush_months(final=True)
        totals = self._journal.totals()
        consistent = totals['s'] == self._sessions_seen and totals['dc'] == self._sessions_complete and (totals['rv'] == self._sessions_valid_range) and (totals['e'] == self._entries) and (totals['t'] == self._completed) and (abs(totals['fees'] - self._fees) < 1e-08)
        if not consistent:
            self._anomaly('journal_mismatch')
        invalid = bool(self.portfolio.invested or self._open_orders() or self._trade is not None or self._halted or (not consistent))
        if invalid:
            self._anomaly('invalid_backtest', 'Estado residual o ejecución bloqueada; no aceptar resultados')
        self._log('summary', version='0.1.3', start_date=self._p['start_date'], end_date_effective=self._p['end_date_effective'], end_date_requested=self._p['end_date'], last_session_with_data=self._last_session_with_data, result_source='internal_journal', valid=not invalid, journal_consistent=consistent, entries=self._entries, completed_trades=self._completed, sessions_seen=self._sessions_seen, sessions_with_complete_data=self._sessions_complete, sessions_with_valid_range=self._sessions_valid_range, signals_detected=self._signals_detected, entries_executed=self._entries, winning_trades=totals['w'], losing_trades=totals['l'], gross_profit_usd=round(totals['g'], 2), net_profit_usd=round(totals['g'] - totals['fees'], 2), fees_usd=round(self._fees, 2), modeled_slippage_estimate_usd=round(self._slippage_estimate, 2), slippage_estimate_is_informational=True, anomalies=self._anomalies, mapped_minute_bars=self._minute_bars, open_orders=len(self._open_orders()), invested=self.portfolio.invested, unfinished_trade=self._trade is not None)

class FixedTickSlippageModel:

    def __init__(self, slippage_ticks: int):
        if isinstance(slippage_ticks, bool) or not isinstance(slippage_ticks, int) or slippage_ticks < 0:
            raise ValueError('slippage_ticks debe ser un entero no negativo')
        self._slippage_ticks = slippage_ticks

    def get_slippage_approximation(self, asset, order) -> float:
        tick_size = float(asset.symbol_properties.minimum_price_variation)
        if not isfinite(tick_size) or tick_size <= 0:
            raise ValueError('El instrumento debe tener un tick finito y positivo')
        return tick_size * self._slippage_ticks
