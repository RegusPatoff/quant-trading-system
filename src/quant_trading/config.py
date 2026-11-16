"""Validación de metadatos locales, sin conexiones externas."""

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class BacktestConfig:
    mode: str
    strategy: str


def load_backtest_config(path: Path) -> BacktestConfig:
    """Acepta únicamente backtest en esta fase del proyecto."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != {"mode", "strategy"}:
        raise ValueError("La configuración debe contener solo mode y strategy")
    if payload["mode"] != "backtest":
        raise ValueError("Fase 1A: solo se permite mode=backtest")
    strategy = payload["strategy"]
    if not isinstance(strategy, str) or not strategy.strip():
        raise ValueError("strategy debe ser un texto no vacío")
    return BacktestConfig(mode="backtest", strategy=strategy)
