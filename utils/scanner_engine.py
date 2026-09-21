# -*- coding: utf-8 -*-
"""
Motor de Escáner en Tiempo Real y Generador de Señales Dual (SS11 & AIS11)
Aceleración mediante PyTorch CUDA Cores (NVIDIA GPU).

AIS11 live espeja el backtester original (data/ais11_com_params.json):
  score > entry_th entra; score < exit_th sale; SMA20 solo post Stop Loss.
Tickers sin señales IA no inventan score híbrido: quedan marcados NO_AI (no push).
"""

import os
import sys
import json
import time
import numpy as np
import pandas as pd
from datetime import datetime
from utils.yf_fetch import fetch_with_cache, flatten_ohlc_columns

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.tickers_universe import get_all_tickers, get_us_tickers, get_crypto_tickers, BENCHMARK_TICKER

CACHE_DIR = ".data_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

AIS11_PARAMS_PATH = "data/ais11_com_params.json"
AIS11_DEFAULT_PARAMS = {
    "indicators": ["AI_MINIROCKET_GPU", "AI_TIMESFM", "AI_TSPULSE", "ROC_3_NORM"],
    "weights": [5, 20, 65, 10],
    "entry_th": 55,
    "exit_th": 5,
}
AI_SIGNAL_FILES = [
    "data/minirocket_gpu_signals.json",
    "data/timesfm_signals.json",
    "data/tspulse_signals.json",
]


def load_ais11_params():
    """Carga umbrales/pesos AIS11 exactamente como el backtester."""
    try:
        with open(AIS11_PARAMS_PATH, "r", encoding="utf-8") as f:
            p = json.load(f)
        return {
            "indicators": list(p.get("indicators", AIS11_DEFAULT_PARAMS["indicators"])),
            "weights": list(p.get("weights", AIS11_DEFAULT_PARAMS["weights"])),
            "entry_th": float(p.get("entry_th", AIS11_DEFAULT_PARAMS["entry_th"])),
            "exit_th": float(p.get("exit_th", AIS11_DEFAULT_PARAMS["exit_th"])),
        }
    except Exception:
        return dict(AIS11_DEFAULT_PARAMS)


def get_ai_signals_age_days():
    """Edad en días del archivo de señales IA más reciente (None si no hay)."""
    newest = None
    for path in AI_SIGNAL_FILES:
        if os.path.exists(path):
            mtime = os.path.getmtime(path)
            if newest is None or mtime > newest:
                newest = mtime
    if newest is None:
        return None
    return (time.time() - newest) / 86400.0


def get_ai_signals_ages_by_file():
    """Edad en días por archivo core AIS11. None si el archivo no existe."""
    ages = {}
    now = time.time()
    for path in AI_SIGNAL_FILES:
        name = os.path.basename(path)
        if os.path.exists(path):
            ages[name] = round((now - os.path.getmtime(path)) / 86400.0, 2)
        else:
            ages[name] = None
    return ages


def compute_ais11_score(df, params):
    """
    Score ponderado idéntico a backtester.generate_signals para AIS11.
    Retorna (score_array, has_ai_core) donde has_ai_core exige al menos un modelo IA.
    """
    n = len(df)
    indicators = params["indicators"]
    weights = params["weights"]
    score = np.zeros(n, dtype=float)
    total_w = np.zeros(n, dtype=float)

    ai_core_inds = {"AI_MINIROCKET_GPU", "AI_TIMESFM", "AI_TSPULSE", "AI_MINIROCKET_BIN"}
    has_ai_core = False

    for idx, ind in enumerate(indicators):
        if ind not in df.columns:
            continue
        vals = df[ind].values.astype(float)
        valid = (~np.isnan(vals)).astype(float)
        if ind in ai_core_inds and valid.any():
            has_ai_core = True
        safe_vals = np.where(np.isnan(vals), 0.0, vals)
        w = float(weights[idx]) if idx < len(weights) else 0.0
        score += safe_vals * w
        total_w += valid * w

    valid_rows = total_w > 0
    score = np.where(valid_rows, score / total_w, 50.0)
    score = np.clip(np.nan_to_num(score, nan=50.0), 0.0, 100.0)
    return score, has_ai_core

# -------------------------------------------------------------------------
# Detección de Hardware (GPU NVIDIA CUDA)
# -------------------------------------------------------------------------
CUDA_AVAILABLE = False
GPU_DEVICE_NAME = "CPU (Sin GPU)"

try:
    import torch
    if torch.cuda.is_available():
        CUDA_AVAILABLE = True
        GPU_DEVICE_NAME = torch.cuda.get_device_name(0)
except Exception:
    pass

def get_hardware_status():
    return {
        "cuda_available": CUDA_AVAILABLE,
        "device_name": GPU_DEVICE_NAME,
        "torch_version": torch.__version__ if 'torch' in sys.modules else "N/A"
    }

def sigmoid_norm(x, scale=1.0):
    val = np.asarray(x, dtype=float)
    val = np.nan_to_num(val, nan=0.0)
    return 100.0 / (1.0 + np.exp(-val / scale))

def clean_nans(obj):
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return 0.0
        return obj
    elif isinstance(obj, (np.floating, np.integer)):
        val = float(obj)
        return 0.0 if np.isnan(val) or np.isinf(val) else val
    elif isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    elif isinstance(obj, dict):
        return {k: clean_nans(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_nans(v) for v in obj]
    return obj

def smart_round_price(val):
    if val is None or np.isnan(val) or np.isinf(val):
        return 0.0
    val = float(val)
    if val == 0.0:
        return 0.0
    abs_val = abs(val)
    if abs_val >= 100:
        return round(val, 2)
    elif abs_val >= 1:
        return round(val, 4)
    elif abs_val >= 0.0001:
        return round(val, 6)
    else:
        return round(val, 8)


# -------------------------------------------------------------------------
# Descarga y Caché de Datos de Mercado
# -------------------------------------------------------------------------
def fetch_ticker_data(tickers=None, cache_expire=1800):
    if tickers is None:
        tickers = get_all_tickers()

    data = {}
    
    # Pre-cargar modelos / predicciones de IA si existen
    minirocket_gpu_data = {}
    timesfm_data = {}
    tspulse_data = {}
    
    try:
        with open("data/minirocket_gpu_signals.json", "r", encoding="utf-8") as f:
            minirocket_gpu_data = json.load(f)
    except Exception: pass
    
    try:
        with open("data/timesfm_signals.json", "r", encoding="utf-8") as f:
            timesfm_data = json.load(f)
    except Exception: pass
    
    try:
        with open("data/tspulse_signals.json", "r", encoding="utf-8") as f:
            tspulse_data = json.load(f)
    except Exception: pass

    # Invalida caché si expira
    cache_expire_sec = float(os.environ.get("YF_CACHE_SECONDS", cache_expire))

    for ticker in tickers:
        cache_path = os.path.join(CACHE_DIR, f"{ticker}.csv")
        cache_valid = False
        
        if os.path.exists(cache_path) and os.path.getsize(cache_path) > 100:
            mod_time = os.path.getmtime(cache_path)
            if 0 <= (time.time() - mod_time) < cache_expire_sec:
                cache_valid = True

        df = pd.DataFrame()
        if cache_valid:
            try:
                df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
                df.index.name = "Date"
            except Exception:
                cache_valid = False

        if not cache_valid or df.empty:
            df = fetch_with_cache(
                ticker,
                period="5y",
                cache_expire_sec=cache_expire_sec,
                stale_ok=True,
            )
            df = flatten_ohlc_columns(df)

        if df.empty or len(df) < 30:
            continue

        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index, errors='coerce')
        df = df[df.index.notna()]
        if 'Close' in df.columns and 'Open' in df.columns:
            df = df[(df['Close'] > 0) & (df['Open'] > 0)]
        if len(df) < 30:
            continue

        # Indicadores Básicos de Tendencia y Momentum
        c = df['Close']
        df['SMA_20'] = c.rolling(20, min_periods=1).mean()
        df['SMA_50'] = c.rolling(50, min_periods=1).mean()
        df['SMA_200'] = c.rolling(200, min_periods=1).mean()

        roc3 = c.pct_change(3).fillna(0.0) * 100
        df['ROC_3_NORM'] = sigmoid_norm(roc3, 5.0)

        roc10 = c.pct_change(10).fillna(0.0) * 100
        df['ROC_10_NORM'] = sigmoid_norm(roc10, 10.0)

        # Paridad con backtester.fetch_data: reindex sin fillna inventado
        s_gpu = pd.Series(minirocket_gpu_data.get(ticker, {}))
        if not s_gpu.empty:
            s_gpu.index = pd.to_datetime(s_gpu.index)
        df['AI_MINIROCKET_GPU'] = s_gpu.reindex(df.index) * 100.0

        s_tfm = pd.Series(timesfm_data.get(ticker, {}))
        if not s_tfm.empty:
            s_tfm.index = pd.to_datetime(s_tfm.index)
        df['AI_TIMESFM'] = sigmoid_norm(s_tfm.reindex(df.index) * 100.0, 2.0)

        s_tsp = pd.Series(tspulse_data.get(ticker, {}))
        if not s_tsp.empty:
            s_tsp.index = pd.to_datetime(s_tsp.index)
        df['AI_TSPULSE'] = sigmoid_norm(s_tsp.reindex(df.index) * 100.0, 2.0)

        data[ticker] = df

    return data

# -------------------------------------------------------------------------
# Cálculo del Filtro Macro Global SPY
# -------------------------------------------------------------------------
def evaluate_macro_crash_guard(spy_df):
    if spy_df is None or spy_df.empty:
        return np.zeros(0, dtype=bool), False, 0

    spy_close = spy_df['Close']
    spy_ret = (spy_close - spy_close.shift(1)) / spy_close.shift(1)

    n = len(spy_ret)
    macro_exit_mask = np.zeros(n, dtype=bool)

    days_out = 0
    for i in range(1, n):
        if spy_ret.iloc[i] < -0.042:
            days_out = 8
        if days_out > 0:
            macro_exit_mask[i] = True
            days_out -= 1

    is_currently_active = bool(macro_exit_mask[-1]) if n > 0 else False
    remaining_days = days_out if is_currently_active else 0

    return macro_exit_mask, is_currently_active, remaining_days

# -------------------------------------------------------------------------
# Simulación de Estrategia & Generador de Trades TradingView Style
# -------------------------------------------------------------------------
def simulate_strategy_trades(df, signals_long, signals_exit, stop_loss_pct=-15.0, is_strict_reentry=True, commission=0.004):
    n = len(df)
    closes = df['Close'].values
    opens  = df['Open'].values
    dates  = pd.to_datetime(df.index)

    def _fmt_d(d):
        if hasattr(d, 'strftime'):
            return d.strftime("%Y-%m-%d")
        return str(d)[:10]

    def _days_diff(d1, d2):
        try:
            return int((d1 - d2).days)
        except Exception:
            return 0

    initial_capital = 10000.0
    cash = initial_capital
    pos  = 0.0
    in_pos = False
    entry_price = 0.0
    entry_idx   = 0

    trades = []
    in_sl_recovery = False

    for i in range(1, n):
        hit_stop_loss = False
        if in_pos and stop_loss_pct is not None:
            current_loss = (closes[i-1] / entry_price - 1.0) * 100.0
            if current_loss <= stop_loss_pct:
                hit_stop_loss = True

        can_enter = False
        if not in_pos:
            if in_sl_recovery and is_strict_reentry:
                sma20 = df['SMA_20'].iloc[i-1]
                if closes[i-1] > sma20 and signals_long[i-1]:
                    can_enter = True
                    in_sl_recovery = False
            else:
                if signals_long[i-1]:
                    can_enter = True

        if can_enter and opens[i] > 0.0:
            pos = (cash * (1.0 - commission)) / opens[i]
            cash = 0.0
            in_pos = True
            entry_price = opens[i]
            entry_idx = i
        elif in_pos and (signals_exit[i-1] or hit_stop_loss):
            revenue = pos * opens[i] * (1.0 - commission)
            cost    = pos * entry_price / (1.0 - commission)
            pnl     = revenue - cost
            pct_ret = (revenue / cost - 1.0) * 100.0 if cost > 0 else 0.0
            trades.append({
                "entry_date":   _fmt_d(dates[entry_idx]),
                "entry_price":  smart_round_price(entry_price),
                "exit_date":    _fmt_d(dates[i]),
                "exit_price":   smart_round_price(opens[i]),
                "pct_return":   round(float(pct_ret), 2),
                "pnl":          round(float(pnl), 2),
                "reason":       "Stop Loss (umbral -15%)" if hit_stop_loss else "Salida de Estrategia",
                "duration_days": _days_diff(dates[i], dates[entry_idx]),
                "is_open": False
            })
            cash   = revenue
            pos    = 0.0
            in_pos = False

            if hit_stop_loss:
                in_sl_recovery = True

    # Evaluación de estado VIVO al final de la historia
    latest_close = closes[-1]
    latest_sma20 = df['SMA_20'].iloc[-1] if 'SMA_20' in df.columns else latest_close

    live_signal = "WAIT"
    floating_pnl_pct = 0.0
    floating_pnl_usd = 0.0

    if in_pos:
        cost = pos * entry_price / (1.0 - commission)
        current_val = pos * latest_close * (1.0 - commission)
        floating_pnl_usd = current_val - cost
        floating_pnl_pct = (current_val / cost - 1.0) * 100.0 if cost > 0 else 0.0

        tomorrow_hit_sl = False
        if stop_loss_pct is not None:
            if (latest_close / entry_price - 1.0) * 100.0 <= stop_loss_pct:
                tomorrow_hit_sl = True

        if signals_exit[-1] or tomorrow_hit_sl:
            live_signal = "SELL"
        elif entry_idx == (n - 1):
            live_signal = "BUY"
        else:
            live_signal = "HOLD"

        trades.append({
            "entry_date":   _fmt_d(dates[entry_idx]),
            "entry_price":  smart_round_price(entry_price),
            "exit_date":    "EN CURSO",
            "exit_price":   smart_round_price(latest_close),
            "pct_return":   round(float(floating_pnl_pct), 2),
            "pnl":          round(float(floating_pnl_usd), 2),
            "reason":       "Posición Activa",
            "duration_days": _days_diff(dates[-1], dates[entry_idx]),
            "is_open": True
        })
    else:
        can_enter = False
        if in_sl_recovery and is_strict_reentry:
            if latest_close > latest_sma20 and signals_long[-1]:
                can_enter = True
        else:
            if signals_long[-1]:
                can_enter = True

        if can_enter:
            live_signal = "BUY"
        else:
            live_signal = "WAIT"

    # Equidad Real y Métricas Consistentes
    current_val = pos * latest_close * (1.0 - commission) if in_pos else 0.0
    current_equity = cash + current_val
    net_profit_usd = current_equity - initial_capital
    total_return_pct = ((current_equity / initial_capital) - 1.0) * 100.0

    trade_eval = [t for t in trades if not t['is_open']]
    if in_pos and len(trades) > 0 and trades[-1]['is_open']:
        trade_eval.append(trades[-1])

    num_trades = len(trade_eval)
    wins = [t for t in trade_eval if t['pct_return'] > 0]
    win_rate = (len(wins) / num_trades * 100.0) if num_trades > 0 else 0.0

    gains = sum(t['pnl'] for t in trade_eval if t['pnl'] > 0)
    losses = sum(abs(t['pnl']) for t in trade_eval if t['pnl'] < 0)
    profit_factor = (gains / losses) if losses > 0 else (99.0 if gains > 0 else 1.0)

    metrics = {
        "trades_count": len([t for t in trades if not t['is_open']]),
        "win_rate": round(win_rate, 1),
        "profit_factor": round(profit_factor, 2),
        "net_profit_usd": round(net_profit_usd, 2),
        "total_return_pct": round(total_return_pct, 2),
        "current_equity": round(current_equity, 2),
        "is_currently_in_position": in_pos,
        "entry_price": smart_round_price(entry_price) if in_pos else None,
        "floating_pnl_pct": round(floating_pnl_pct, 2) if in_pos else 0.0,
        "in_sl_recovery": in_sl_recovery
    }

    return live_signal, metrics, trades

# -------------------------------------------------------------------------
# Ejecución del Escáner Completo
# -------------------------------------------------------------------------
def _last_closed_trade(item):
    """Último trade cerrado de recent_trades (si existe)."""
    recent = item.get("recent_trades") or []
    closed = [t for t in recent if not t.get("is_open")]
    return closed[-1] if closed else None


def _infer_exit_reason(item, is_macro_active):
    """Motivo legible de salida a partir de trades recientes / macro / score."""
    last = _last_closed_trade(item)
    if last:
        reason = last.get("reason") or "Salida de Estrategia"
        if "Stop Loss" in str(reason):
            # El -15% es el umbral sobre el cierre previo; el fill es al open siguiente.
            return "Stop Loss (umbral -15%, fill al open)"
        if is_macro_active:
            return "Macro Crash Guard"
        return reason
    if is_macro_active:
        return "Macro Crash Guard"
    if item.get("signal") == "SELL":
        return "Score bajo umbral de salida / Macro"
    return "Salida de Estrategia"


def run_live_scanner(tickers=None):
    if tickers is None:
        tickers = get_all_tickers()

    us_list = get_us_tickers()
    crypto_list = get_crypto_tickers()
    ais11_params = load_ais11_params()
    entry_th = ais11_params["entry_th"]
    exit_th = ais11_params["exit_th"]

    t0 = time.time()
    data_map = fetch_ticker_data(tickers)

    spy_df = data_map.get(BENCHMARK_TICKER)
    if spy_df is None and os.path.exists(".data_cache/SPY.csv"):
        spy_df = pd.read_csv(".data_cache/SPY.csv", index_col=0, parse_dates=True)

    macro_mask, is_macro_active, days_remaining = evaluate_macro_crash_guard(spy_df)
    ai_age_days = get_ai_signals_age_days()

    results = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "hardware": get_hardware_status(),
        "ais11_params": {
            "entry_th": entry_th,
            "exit_th": exit_th,
            "indicators": ais11_params["indicators"],
            "weights": ais11_params["weights"],
        },
        "ai_signals_age_days": None if ai_age_days is None else round(ai_age_days, 2),
        "macro_guard": {
            "is_active": is_macro_active,
            "days_remaining": days_remaining,
            "benchmark": BENCHMARK_TICKER,
            "message": "🚨 CRASH SISTÉMICO ACTIVO - Salida a Liquidez" if is_macro_active else "🟢 Mercado Seguro - Macro Filtro OK"
        },
        "ss11_signals": [],
        "ais11_signals": [],
        "summary": {
            "total_scanned": 0,
            "with_ai": 0,
            "without_ai": 0,
            "ss11_buys": 0,
            "ss11_holds": 0,
            "ss11_in_position": 0,
            "ss11_sl_recovery": 0,
            "ais11_buys": 0,
            "ais11_holds": 0,
            "ais11_in_position": 0,
        }
    }

    for ticker, df in data_map.items():
        if ticker == BENCHMARK_TICKER:
            continue

        n = len(df)
        if n < 30:
            continue

        category = "Crypto" if ticker in crypto_list else ("US Stock" if ticker in us_list else "Otro")
        latest_close = float(df['Close'].iloc[-1])
        prev_close = float(df['Close'].iloc[-2]) if n > 1 else latest_close
        change_24h = ((latest_close - prev_close) / prev_close) * 100.0
        latest_sma20 = float(df['SMA_20'].iloc[-1]) if 'SMA_20' in df.columns and pd.notna(df['SMA_20'].iloc[-1]) else latest_close

        if spy_df is not None and not spy_df.empty:
            spy_series = pd.Series(macro_mask, index=spy_df.index)
            macro_aligned = spy_series.reindex(df.index).ffill().fillna(False).values
        else:
            macro_aligned = np.zeros(n, dtype=bool)

        # -----------------------------------------------------------------
        # 1. SS11 (Macro Base Pura) — acciones/ETFs
        # -----------------------------------------------------------------
        if category != "Crypto":
            ss11_long = ~macro_aligned
            ss11_exit = macro_aligned

            ss11_sig, ss11_met, ss11_trades = simulate_strategy_trades(
                df, ss11_long, ss11_exit, stop_loss_pct=-15.0, is_strict_reentry=False
            )

            dist_sl = -15.0
            if ss11_met['is_currently_in_position'] and ss11_met.get('entry_price') and ss11_met['entry_price'] > 0:
                dist_sl = ((latest_close / ss11_met['entry_price']) - 1.0) * 100.0 - (-15.0)

            dist_sma20 = ((latest_close / latest_sma20) - 1.0) * 100.0
            ss11_item = {
                "ticker": ticker,
                "category": category,
                "price": smart_round_price(latest_close),
                "change_24h": round(change_24h, 2),
                "signal": ss11_sig,
                "metrics": ss11_met,
                "dist_sl_pct": round(dist_sl, 2),
                "dist_sma20_pct": round(dist_sma20, 2),
                "recent_trades": ss11_trades[-5:],
                "notify_eligible": True,
                "strategy": "SS11",
            }
            ss11_item["exit_reason"] = _infer_exit_reason(ss11_item, is_macro_active)
            results["ss11_signals"].append(ss11_item)

            if ss11_sig == "BUY":
                results["summary"]["ss11_buys"] += 1
            elif ss11_sig == "HOLD":
                results["summary"]["ss11_holds"] += 1
            if ss11_met.get("is_currently_in_position"):
                results["summary"]["ss11_in_position"] += 1
            if ss11_met.get("in_sl_recovery"):
                results["summary"]["ss11_sl_recovery"] += 1

        # -----------------------------------------------------------------
        # 2. AIS11 — espejo exacto del backtester (params JSON)
        # -----------------------------------------------------------------
        score, has_ai = compute_ais11_score(df, ais11_params)
        latest_score = float(score[-1]) if n > 0 else 50.0
        dist_sma20_ais = ((latest_close / latest_sma20) - 1.0) * 100.0

        if not has_ai:
            # Sin modelos IA: no inventar score; no operar / no push
            results["ais11_signals"].append({
                "ticker": ticker,
                "category": category,
                "price": smart_round_price(latest_close),
                "change_24h": round(change_24h, 2),
                "ai_score": None,
                "signal": "NO_AI",
                "metrics": {
                    "trades_count": 0,
                    "win_rate": 0.0,
                    "profit_factor": 1.0,
                    "net_profit_usd": 0.0,
                    "total_return_pct": 0.0,
                    "current_equity": 10000.0,
                    "is_currently_in_position": False,
                    "entry_price": None,
                    "floating_pnl_pct": 0.0,
                    "in_sl_recovery": False,
                },
                "dist_sl_pct": -15.0,
                "dist_sma20_pct": round(dist_sma20_ais, 2),
                "recent_trades": [],
                "has_ai": False,
                "notify_eligible": False,
                "strategy": "AIS11",
                "exit_reason": None,
            })
            results["summary"]["without_ai"] += 1
            results["summary"]["total_scanned"] += 1
            continue

        # Paridad con backtester: score > entry_th / score < exit_th (+ macro)
        ai_wants_in = score > entry_th
        ai_wants_out = score < exit_th
        ais11_long = ai_wants_in & (~macro_aligned)
        ais11_exit = macro_aligned | ai_wants_out

        ais11_sig, ais11_met, ais11_trades = simulate_strategy_trades(
            df, ais11_long, ais11_exit, stop_loss_pct=-15.0, is_strict_reentry=True
        )

        dist_sl_ais = -15.0
        if ais11_met['is_currently_in_position'] and ais11_met.get('entry_price') and ais11_met['entry_price'] > 0:
            dist_sl_ais = ((latest_close / ais11_met['entry_price']) - 1.0) * 100.0 - (-15.0)

        ais11_item = {
            "ticker": ticker,
            "category": category,
            "price": smart_round_price(latest_close),
            "change_24h": round(change_24h, 2),
            "ai_score": round(latest_score, 1),
            "signal": ais11_sig,
            "metrics": ais11_met,
            "dist_sl_pct": round(dist_sl_ais, 2),
            "dist_sma20_pct": round(dist_sma20_ais, 2),
            "recent_trades": ais11_trades[-5:],
            "has_ai": True,
            "notify_eligible": True,
            "strategy": "AIS11",
            "entry_th": entry_th,
            "exit_th": exit_th,
        }
        ais11_item["exit_reason"] = _infer_exit_reason(ais11_item, is_macro_active)
        results["ais11_signals"].append(ais11_item)

        if ais11_sig == "BUY":
            results["summary"]["ais11_buys"] += 1
        elif ais11_sig == "HOLD":
            results["summary"]["ais11_holds"] += 1
        if ais11_met.get("is_currently_in_position"):
            results["summary"]["ais11_in_position"] += 1
        results["summary"]["with_ai"] += 1
        results["summary"]["total_scanned"] += 1

    sm0 = results["summary"]
    ais_n = sm0["with_ai"] + sm0["without_ai"]
    sm0["ais11_no_ai_pct"] = round(100.0 * sm0["without_ai"] / ais_n, 2) if ais_n else 0.0
    results["ai_file_ages"] = get_ai_signals_ages_by_file()

    priority = {"BUY": 0, "HOLD": 1, "WAIT": 2, "SELL": 3, "NO_AI": 4}
    results["ss11_signals"].sort(key=lambda x: (priority.get(x["signal"], 99), -x["change_24h"]))
    results["ais11_signals"].sort(
        key=lambda x: (priority.get(x["signal"], 99), -(x.get("ai_score") or 0.0))
    )

    results = clean_nans(results)
    elapsed = time.time() - t0
    results["scan_elapsed_sec"] = round(elapsed, 2)

    try:
        with open("data/live_scanner_cache.json", "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Scanner Engine] Error al persistir caché del escáner: {e}")

    sm = results["summary"]
    print(
        f"[Scanner Engine] Escaneo {elapsed:.1f}s | scanned={sm['total_scanned']} "
        f"with_ai={sm['with_ai']} no_ai={sm['without_ai']} | "
        f"SS11 in_pos={sm['ss11_in_position']} buys={sm['ss11_buys']} | "
        f"AIS11 in_pos={sm['ais11_in_position']} buys={sm['ais11_buys']} | "
        f"entry/exit={entry_th}/{exit_th} | ai_age_days={results.get('ai_signals_age_days')}"
    )

    try:
        from utils.telegram_bot import check_and_notify_trades
        check_and_notify_trades(results)
    except Exception as e:
        print(f"[Scanner Engine] Advertencia al notificar por Telegram: {e}")

    return results

if __name__ == "__main__":
    print(f"Probando escáner en vivo con hardware: {get_hardware_status()}")
    res = run_live_scanner()
    print(f"Escaneo completado. Scanned: {res['summary']['total_scanned']}, SS11 Buys: {res['summary']['ss11_buys']}, AIS11 Buys: {res['summary']['ais11_buys']}, AIS11 Holds: {res['summary']['ais11_holds']}")
