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
    _infer_exit_reason,
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


class TestSs11StrictReentryDivergence(unittest.TestCase):
    """SS11 live debe reentrar como el original (sin SMA20 post-SL)."""

    def _ss11_sl_then_weak_recovery(self):
        n = 26
        closes = np.full(n, 100.0)
        opens = np.full(n, 100.0)
        # Entra al inicio. Cierre i=20 cae -16% → SL en i=21.
        # Quedan pocas barras a 84: SMA20 sigue ~98, live no reentra; original sí.
        closes[20] = 84.0
        opens[21] = 84.0
        for i in range(22, n):
            closes[i] = 84.0
            opens[i] = 84.0
        idx = pd.date_range("2024-01-01", periods=n, freq="B")
        df = pd.DataFrame({"Open": opens, "Close": closes}, index=idx)
        # SMA forzada por encima del piso: aísla el gate de reentrada (no el rolling).
        df["SMA_20"] = 200.0
        signals_long = np.ones(n, dtype=bool)   # SS11: ~macro
        signals_exit = np.zeros(n, dtype=bool)
        return df, signals_long, signals_exit

    def test_original_ss11_reenters_without_sma20(self):
        df, slong, sexit = self._ss11_sl_then_weak_recovery()
        sig, met, trades = simulate_strategy_trades(
            df, slong, sexit, stop_loss_pct=-15.0, is_strict_reentry=False
        )
        self.assertTrue(met["is_currently_in_position"], "SS11 original debe reentrar sin SMA20")
        self.assertIn(sig, ("HOLD", "BUY"))

    def test_live_ss11_matches_original_reentry(self):
        df, slong, sexit = self._ss11_sl_then_weak_recovery()
        sig, met, trades = simulate_strategy_trades(
            df, slong, sexit, stop_loss_pct=-15.0, is_strict_reentry=False
        )
        self.assertTrue(met["is_currently_in_position"], "SS11 live alineado: reentra sin SMA20")
        self.assertIn(sig, ("HOLD", "BUY"))
        closed_sl = [t for t in trades if (not t["is_open"]) and "Stop Loss" in str(t["reason"])]
        self.assertGreaterEqual(len(closed_sl), 1)

    def test_strict_true_still_blocks_below_sma(self):
        df, slong, sexit = self._ss11_sl_then_weak_recovery()
        sig, met, _ = simulate_strategy_trades(
            df, slong, sexit, stop_loss_pct=-15.0, is_strict_reentry=True
        )
        self.assertFalse(met["is_currently_in_position"])
        self.assertEqual(sig, "WAIT")


class TestTelegramStateMachine(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.state_path = os.path.join(self._tmpdir.name, "telegram_state.json")
        self._orig_state = telegram_bot.STATE_PATH
        self._orig_health = telegram_bot.HEALTH_PATH
        telegram_bot.STATE_PATH = self.state_path
        telegram_bot.HEALTH_PATH = os.path.join(self._tmpdir.name, "telegram_health.json")
        os.environ["TELEGRAM_DRY_RUN"] = "1"

    def tearDown(self):
        telegram_bot.STATE_PATH = self._orig_state
        telegram_bot.HEALTH_PATH = self._orig_health
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

    def test_sell_card_uses_trade_pnl_not_latest_close(self):
        """Resultado debe venir del trade (fill), no de latest_close vs entry."""
        card = telegram_bot._format_sell_card({
            "ticker": "VICI",
            "category": "US Stock",
            "strategy": "SS11",
            "price": 24.76,          # exit fill
            "entry_price": 22.80,
            "pct_return": 8.63,      # P&L real del trade
            "exit_reason": "Stop Loss (umbral -15%, fill al open)",
        })
        self.assertIn("+8.63%", card)
        self.assertIn("Stop Loss (umbral -15%, fill al open)", card)
        self.assertIn("Precio entrada", card)
        # No debe recalcular con un close distinto: si ignorara pct_return
        # y usara price/entry distintos, el % cambiaría.
        card_mismatch = telegram_bot._format_sell_card({
            "ticker": "VICI",
            "category": "US Stock",
            "strategy": "SS11",
            "price": 30.0,           # latest_close recuperado
            "entry_price": 22.80,
            "pct_return": -14.50,    # fill real ~SL
            "exit_reason": "Stop Loss (umbral -15%, fill al open)",
        })
        self.assertIn("-14.50%", card_mismatch)
        self.assertNotIn("+31.", card_mismatch)

    def test_sell_transition_prefers_recent_trade_fill(self):
        telegram_bot.check_and_notify_trades(self._scanner(False, False, ticker="VICI"))
        telegram_bot.check_and_notify_trades(self._scanner(False, True, ticker="VICI"))
        scanner = self._scanner(False, False, ticker="VICI")
        scanner["ss11_signals"][0]["price"] = 30.0  # latest_close (engañoso)
        scanner["ss11_signals"][0]["exit_reason"] = "Stop Loss (umbral -15%, fill al open)"
        scanner["ss11_signals"][0]["recent_trades"] = [{
            "entry_price": 22.80,
            "exit_price": 24.76,
            "pct_return": 8.63,
            "reason": "Stop Loss (umbral -15%)",
            "is_open": False,
        }]
        # Capturar alertas formateadas vía dry-run + espía
        sent = []
        orig = telegram_bot.send_telegram_message

        def _spy(msg, *a, **k):
            sent.append(msg)
            return orig(msg, *a, **k)

        telegram_bot.send_telegram_message = _spy
        try:
            r = telegram_bot.check_and_notify_trades(scanner)
        finally:
            telegram_bot.send_telegram_message = orig
        self.assertEqual(r["sells"], 1)
        self.assertTrue(any("+8.63%" in m for m in sent))
        self.assertTrue(any("24.76" in m for m in sent))
        self.assertFalse(any("+31." in m for m in sent))

    def test_no_ai_never_notifies(self):
        telegram_bot.check_and_notify_trades(self._scanner(False, False))
        scanner = self._scanner(True, False)
        scanner["ais11_signals"][0]["signal"] = "NO_AI"
        scanner["ais11_signals"][0]["notify_eligible"] = False
        scanner["ais11_signals"][0]["has_ai"] = False
        scanner["ais11_signals"][0]["ai_score"] = None
        r = telegram_bot.check_and_notify_trades(scanner)
        self.assertEqual(r["buys"], 0)
        self.assertEqual(r["sells"], 0)

    def test_no_ai_drops_ghost_state(self):
        telegram_bot.check_and_notify_trades(self._scanner(True, False))
        with open(self.state_path, encoding="utf-8") as f:
            st = json.load(f)
        self.assertIn("AIS11_MSFT", st)
        scanner = self._scanner(True, False)
        scanner["ais11_signals"][0]["signal"] = "NO_AI"
        scanner["ais11_signals"][0]["notify_eligible"] = False
        scanner["ais11_signals"][0]["has_ai"] = False
        telegram_bot.check_and_notify_trades(scanner)
        with open(self.state_path, encoding="utf-8") as f:
            st = json.load(f)
        self.assertNotIn("AIS11_MSFT", st)


class TestStopLossReasonClarity(unittest.TestCase):
    def test_infer_exit_reason_clarifies_sl_fill(self):
        item = {
            "signal": "WAIT",
            "recent_trades": [{
                "reason": "Stop Loss (umbral -15%)",
                "pct_return": 8.63,
                "is_open": False,
            }],
        }
        self.assertEqual(
            _infer_exit_reason(item, is_macro_active=False),
            "Stop Loss (umbral -15%, fill al open)",
        )

    def test_sl_gap_up_can_be_green_with_sl_label(self):
        """SL dispara por cierre -15%, fill al open puede quedar en verde."""
        n = 40
        closes = np.full(n, 100.0)
        opens = np.full(n, 100.0)
        # Entra en i=10 (señal en i=9)
        # Cierre i=20 cae a 84 → dispara SL; open i=21 sube a 108
        closes[20] = 84.0
        opens[21] = 108.0
        idx = pd.date_range("2024-01-01", periods=n, freq="B")
        df = pd.DataFrame({"Open": opens, "Close": closes}, index=idx)
        df["SMA_20"] = df["Close"].rolling(20, min_periods=1).mean()

        signals_long = np.zeros(n, dtype=bool)
        signals_long[9] = True
        signals_exit = np.zeros(n, dtype=bool)

        _, _, trades = simulate_strategy_trades(
            df, signals_long, signals_exit, stop_loss_pct=-15.0, is_strict_reentry=False
        )
        closed = [t for t in trades if not t["is_open"]]
        self.assertGreaterEqual(len(closed), 1)
        sl = [t for t in closed if "Stop Loss" in str(t["reason"])]
        self.assertEqual(len(sl), 1)
        self.assertGreater(sl[0]["pct_return"], 0.0)
        self.assertIn("umbral -15%", sl[0]["reason"])


class TestAiPipelineAndUniverse(unittest.TestCase):
    def test_evaluate_cores_write_only_if_all_ok(self):
        from utils.ai_pipeline import evaluate_ais11_cores
        ok, _ = evaluate_ais11_cores({
            "models/precalculate_timesfm.py": "ok",
            "models/finetune_tspulse.py": "ok",
            "models/train_minirocket_gpu.py": "ok",
        })
        self.assertTrue(ok)
        ok2, msg = evaluate_ais11_cores({
            "models/precalculate_timesfm.py": "skipped",
            "models/finetune_tspulse.py": "skipped",
            "models/train_minirocket_gpu.py": "skipped",
        })
        self.assertFalse(ok2)
        self.assertIn("GPU", msg)
        ok3, msg3 = evaluate_ais11_cores({
            "models/precalculate_timesfm.py": "ok",
            "models/finetune_tspulse.py": "failed",
            "models/train_minirocket_gpu.py": "ok",
        })
        self.assertFalse(ok3)
        self.assertIn("tspulse", msg3)

    def test_skip_gpu_scripts_without_cuda(self):
        from utils.ai_pipeline import should_skip_gpu_script
        self.assertTrue(should_skip_gpu_script("models/finetune_tspulse.py", has_cuda=False))
        self.assertFalse(should_skip_gpu_script("models/finetune_tspulse.py", has_cuda=True))
        self.assertFalse(should_skip_gpu_script("models/train_minirocket.py", has_cuda=False))

    def test_lab_extras_in_us_universe(self):
        from utils.tickers_universe import (
            LAB_UNIVERSE_EXTRAS,
            get_all_tickers,
            get_live_us_ai_tickers,
            get_us_tickers,
        )
        us = get_us_tickers()
        all_tk = get_all_tickers()
        for t in LAB_UNIVERSE_EXTRAS:
            self.assertIn(t, us)
            self.assertIn(t, all_tk)
        ai = get_live_us_ai_tickers()
        self.assertIn("SPY", ai)
        self.assertIn("GOOG", ai)
        self.assertNotIn("BTC-USD", ai)

    def test_fetch_data_accepts_tickers_and_start(self):
        import inspect
        from backtester import fetch_data
        params = inspect.signature(fetch_data).parameters
        self.assertIn("tickers", params)
        self.assertIn("start_date", params)


if __name__ == "__main__":
    unittest.main(verbosity=2)
