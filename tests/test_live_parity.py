# -*- coding: utf-8 -*-
"""
Verifica paridad live vs backtester y anti-serrucho SMA.
Ejecutar desde la raíz del repo:
  python scripts/verify_live_parity.py
  python -m pytest tests/test_live_parity.py -q
"""

import os
import sys
import json
import tempfile
import unittest

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)

from utils.scanner_engine import (
    load_ais11_params,
    compute_ais11_score,
    simulate_strategy_trades,
)
from utils import telegram_bot


def _synthetic_ohlc(n=80, base=100.0):
    """Serie con cruce bajo/sobre SMA20 pero score estable en banda muerta."""
    rng = np.random.default_rng(42)
    closes = np.full(n, base, dtype=float)
    # Primera mitad alcista (entra), luego dip bajo SMA y recuperación
    for i in range(1, n):
        if i < 30:
            closes[i] = closes[i - 1] * 1.005
        elif i < 50:
            closes[i] = closes[i - 1] * 0.992  # baja ~bajo SMA
        else:
            closes[i] = closes[i - 1] * 1.004  # recupera
    opens = closes * (1.0 + rng.normal(0, 0.001, n))
    opens = np.maximum(opens, 0.01)
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    df = pd.DataFrame({"Open": opens, "Close": closes}, index=idx)
    df["SMA_20"] = df["Close"].rolling(20, min_periods=1).mean()
    df["ROC_3_NORM"] = 50.0
    df["AI_MINIROCKET_GPU"] = 50.0
    df["AI_TIMESFM"] = 50.0
    df["AI_TSPULSE"] = 50.0
    return df


class TestAis11Parity(unittest.TestCase):
    def test_params_load_from_json(self):
        p = load_ais11_params()
        self.assertEqual(p["entry_th"], 55)
        self.assertEqual(p["exit_th"], 5)
        self.assertEqual(len(p["indicators"]), 4)

    def test_no_whipsaw_on_sma_cross_with_mid_score(self):
        """
        Score fijo ~50 (entre exit 5 y entry 55):
        el live NUEVO no debe cerrar por cruzar SMA20.
        La lógica VIEJA (salida SMA*0.98) sí serrucharía.
        """
        df = _synthetic_ohlc()
        params = load_ais11_params()
        # Forzar score ~50 en toda la serie
        df["AI_MINIROCKET_GPU"] = 50.0
        df["AI_TIMESFM"] = 50.0
        df["AI_TSPULSE"] = 50.0
        df["ROC_3_NORM"] = 50.0
        score, has_ai = compute_ais11_score(df, params)
        self.assertTrue(has_ai)
        self.assertTrue(np.all((score > params["exit_th"]) & (score < params["entry_th"])))

        # Entrada forzada al inicio con score alto, luego score mid
        score_forced = score.copy()
        score_forced[:25] = 70.0  # entra
        # resto queda en 50 → no sale con exit_th=5

        macro = np.zeros(len(df), dtype=bool)
        long_new = (score_forced > params["entry_th"]) & (~macro)
        exit_new = macro | (score_forced < params["exit_th"])
        sig_new, met_new, trades_new = simulate_strategy_trades(
            df, long_new, exit_new, stop_loss_pct=-15.0, is_strict_reentry=True
        )

        # Viejo: sale si Close < SMA*0.98
        long_old = (score_forced >= 58.0) & (df["Close"].values > df["SMA_20"].values) & (~macro)
        exit_old = macro | (score_forced < 38.0) | (df["Close"].values < (df["SMA_20"].values * 0.98))
        sig_old, met_old, trades_old = simulate_strategy_trades(
            df, long_old, exit_old, stop_loss_pct=-15.0, is_strict_reentry=True
        )

        closed_new = [t for t in trades_new if not t["is_open"]]
        closed_old = [t for t in trades_old if not t["is_open"]]

        # Nueva lógica: tras entrar con score alto, score mid no cierra → 0 o 1 trade abierto, sin reopen
        self.assertLessEqual(len(closed_new), 1, "Nueva lógica no debería serruchar por SMA")
        # Vieja lógica típicamente cierra al menos una vez por dip SMA
        self.assertGreaterEqual(
            len(closed_old), 1,
            "La lógica vieja debería haber cerrado por SMA (control del test)"
        )

    def test_no_ai_flag(self):
        df = _synthetic_ohlc()
        df["AI_MINIROCKET_GPU"] = np.nan
        df["AI_TIMESFM"] = np.nan
        df["AI_TSPULSE"] = np.nan
        params = load_ais11_params()
        _, has_ai = compute_ais11_score(df, params)
        self.assertFalse(has_ai)


class TestTelegramStateMachine(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.state_path = os.path.join(self._tmpdir.name, "telegram_state.json")
        self._orig_state = telegram_bot.STATE_PATH
        telegram_bot.STATE_PATH = self.state_path
        os.environ["TELEGRAM_DRY_RUN"] = "1"

    def tearDown(self):
        telegram_bot.STATE_PATH = self._orig_state
        self._tmpdir.cleanup()
        os.environ.pop("TELEGRAM_DRY_RUN", None)

    def _scanner(self, ais_in_pos, ss_in_pos=False, ticker="MSFT"):
        return {
            "timestamp": "2026-09-14 12:00:00",
            "macro_guard": {"is_active": False, "days_remaining": 0, "message": "OK"},
            "ai_signals_age_days": 0.5,
            "ais11_params": {"entry_th": 55, "exit_th": 5},
            "summary": {},
            "ss11_signals": [{
                "ticker": ticker,
                "category": "US Stock",
                "price": 100.0,
                "signal": "HOLD" if ss_in_pos else "WAIT",
                "metrics": {
                    "is_currently_in_position": ss_in_pos,
                    "entry_price": 90.0 if ss_in_pos else None,
                    "floating_pnl_pct": 5.0,
                },
                "notify_eligible": True,
                "exit_reason": "Macro Crash Guard",
            }],
            "ais11_signals": [{
                "ticker": ticker,
                "category": "US Stock",
                "price": 100.0,
                "ai_score": 62.0,
                "signal": "HOLD" if ais_in_pos else "WAIT",
                "metrics": {
                    "is_currently_in_position": ais_in_pos,
                    "entry_price": 95.0 if ais_in_pos else None,
                    "floating_pnl_pct": 3.0,
                },
                "has_ai": True,
                "notify_eligible": True,
                "exit_reason": "Score bajo umbral de salida / Macro",
            }],
        }

    def test_baseline_no_spam(self):
        r = telegram_bot.check_and_notify_trades(self._scanner(ais_in_pos=True, ss_in_pos=True))
        self.assertTrue(r["initial"])
        self.assertEqual(r["buys"], 0)
        with open(self.state_path, encoding="utf-8") as f:
            st = json.load(f)
        self.assertIn("AIS11_MSFT", st)
        self.assertTrue(st["AIS11_MSFT"]["in_pos"])

    def test_buy_then_sell_transitions(self):
        telegram_bot.check_and_notify_trades(self._scanner(False, False))
        r_buy = telegram_bot.check_and_notify_trades(self._scanner(True, False))
        self.assertEqual(r_buy["buys"], 1)
        self.assertEqual(r_buy["sells"], 0)
        r_sell = telegram_bot.check_and_notify_trades(self._scanner(False, False))
        self.assertEqual(r_sell["sells"], 1)

    def test_no_limbo_on_hold(self):
        telegram_bot.check_and_notify_trades(self._scanner(False))
        telegram_bot.check_and_notify_trades(self._scanner(True))
        telegram_bot.check_and_notify_trades(self._scanner(True))
        with open(self.state_path, encoding="utf-8") as f:
            st = json.load(f)
        self.assertTrue(st["AIS11_MSFT"]["in_pos"])
        self.assertEqual(st["AIS11_MSFT"]["last_notified_action"], "BUY")

    def test_ss11_buy_sell_also_notified(self):
        telegram_bot.check_and_notify_trades(self._scanner(False, False))
        r = telegram_bot.check_and_notify_trades(self._scanner(False, True))
        self.assertEqual(r["buys"], 1)
        r2 = telegram_bot.check_and_notify_trades(self._scanner(False, False))
        self.assertEqual(r2["sells"], 1)

    def test_cooldown_suppresses_rebuy_alert(self):
        telegram_bot.check_and_notify_trades(self._scanner(False))
        telegram_bot.check_and_notify_trades(self._scanner(True))
        telegram_bot.check_and_notify_trades(self._scanner(False))
        # Recompra inmediata: estado in_pos=True pero alerta en cooldown
        r = telegram_bot.check_and_notify_trades(self._scanner(True))
        self.assertEqual(r["buys"], 0)
        with open(self.state_path, encoding="utf-8") as f:
            st = json.load(f)
        self.assertTrue(st["AIS11_MSFT"]["in_pos"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
