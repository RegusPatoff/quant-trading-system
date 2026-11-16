import json
from pathlib import Path

import pytest

from quant_trading.config import load_backtest_config


def test_load_backtest(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"mode": "backtest", "strategy": "smoke"}))
    config = load_backtest_config(path)
    assert (config.mode, config.strategy) == ("backtest", "smoke")


@pytest.mark.parametrize("mode", ["live", "paper", "", None])
def test_reject_unsupported_modes(tmp_path, mode):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"mode": mode, "strategy": "smoke"}))
    with pytest.raises(ValueError, match="solo se permite"):
        load_backtest_config(path)


@pytest.mark.parametrize("payload", [[], {}, {"mode": "backtest"},
    {"mode": "backtest", "strategy": "x", "extra": True},
    {"mode": "backtest", "strategy": " "},
    {"mode": "backtest", "strategy": 5}])
def test_reject_invalid_configuration(tmp_path, payload):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        load_backtest_config(path)


def test_repository_example():
    root = Path(__file__).resolve().parents[1]
    assert load_backtest_config(root / "config/backtest.example.json").mode == "backtest"
