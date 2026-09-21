# -*- coding: utf-8 -*-
"""
Diagnóstico live (Nazareno) vs estrategias originales (IABacktesterTrading).
Solo lectura + replay local. No modifica lógica de trading ni envía Telegram.
"""
import json
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ORIG = os.path.abspath(os.path.join(ROOT, "..", "IABacktesterTrading"))
sys.path.insert(0, ROOT)

from backtester import STRATEGY_INFO, TICKERS, generate_signals, run_simulation
from utils.tickers_universe import get_all_tickers, get_us_tickers, get_crypto_tickers
from utils.scanner_engine import (
    compute_ais11_score,
    evaluate_macro_crash_guard,
    load_ais11_params,
    get_ai_signals_age_days,
    simulate_strategy_trades,
    sigmoid_norm,
)

LIVE_STRATEGIES = {"SS11", "AIS11"}
AI_FILES = [
    "minirocket_gpu_signals.json",
    "timesfm_signals.json",
    "tspulse_signals.json",
    "minirocket_signals.json",
    "xgboost_stack_signals.json",
    "tspulse_multi_signals.json",
]


def _json_tickers(path):
    if not os.path.exists(path):
        return set(), 0
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return set(), 0
    nonempty = {k for k, v in data.items() if v}
    return nonempty, len(data)


def universe_audit():
    live = set(get_all_tickers())
    orig = set(TICKERS)
    us = set(get_us_tickers())
    crypto = set(get_crypto_tickers())
    overlap = sorted(orig & live)
    missing_in_live = sorted(orig - live)
    goog_mismatch = ("GOOG" in orig) and ("GOOGL" in live) and ("GOOG" not in live)
    return {
        "original_tickers": TICKERS,
        "original_count": len(orig),
        "live_count": len(live),
        "live_us": len(us),
        "live_crypto": len(crypto),
        "overlap": overlap,
        "overlap_count": len(overlap),
        "overlap_excluding_spy": [t for t in overlap if t != "SPY"],
        "original_missing_in_live": missing_in_live,
        "goog_vs_googl": goog_mismatch,
    }


def strategy_parity_table():
    rows = []
    for sid, info in STRATEGY_INFO.items():
        sl = info.get("stop_loss_pct")
        orig_strict = ((sid.startswith("SS") and sid != "SS11") or sid in ["AIS10", "AIS11"]) and sl is not None
        in_live = sid in LIVE_STRATEGIES
        live_status = "no existe en live"
        notes = []
        if sid == "SS11":
            live_status = "distinto"
            notes.append("live aplica is_strict_reentry=True; original lo excluye")
            notes.append("live omite crypto")
        elif sid == "AIS11":
            live_status = "distinto"
            notes.append("misma fórmula JSON 55/5 pero NO_AI si falta core IA")
            notes.append("universo 301 vs 18; fillna live != reindex original")
            notes.append("historia live 5y vs original 30y")
        rows.append({
            "id": sid,
            "type": info["type"],
            "name": info["name"],
            "stop_loss_pct": sl,
            "original_strict_sma20": bool(orig_strict),
            "live_status": live_status if not in_live or live_status != "no existe en live" else "en live",
            "notes": notes,
        })
        if in_live and sid not in ("SS11", "AIS11"):
            rows[-1]["live_status"] = "en live"
    return rows


def ai_coverage():
    naz_dir = os.path.join(ROOT, "data")
    orig_dir = os.path.join(ORIG, "data")
    live = set(get_all_tickers())
    files = {}
    for name in AI_FILES:
        naz_p = os.path.join(naz_dir, name)
        orig_p = os.path.join(orig_dir, name)
        naz_t, naz_n = _json_tickers(naz_p)
        orig_t, orig_n = _json_tickers(orig_p)
        core = name in ("minirocket_gpu_signals.json", "timesfm_signals.json", "tspulse_signals.json")
        files[name] = {
            "exists_nazareno": os.path.exists(naz_p),
            "exists_original": os.path.exists(orig_p),
            "nazareno_tickers": sorted(naz_t),
            "original_tickers": sorted(orig_t),
            "nazareno_count": naz_n,
            "original_count": orig_n,
            "overlap_live_universe": sorted(orig_t & live) if core else [],
            "missing_in_live_universe": sorted(orig_t - live) if core else [],
            "live_without_this_file": (len(live) - len(orig_t & live)) if core and orig_t else None,
        }

    orig_gpu, _ = _json_tickers(os.path.join(orig_dir, "minirocket_gpu_signals.json"))
    orig_tfm, _ = _json_tickers(os.path.join(orig_dir, "timesfm_signals.json"))
    orig_tsp, _ = _json_tickers(os.path.join(orig_dir, "tspulse_signals.json"))
    any_core = orig_gpu | orig_tfm | orig_tsp
    ais11_usable = sorted(any_core & live)
    ais11_usable_ex_spy = [t for t in ais11_usable if t != "SPY"]

    return {
        "nazareno_ai_age_days": get_ai_signals_age_days(),
        "files": files,
        "original_any_ais11_core": sorted(any_core),
        "ais11_usable_in_live_universe": ais11_usable_ex_spy,
        "ais11_usable_count": len(ais11_usable_ex_spy),
        "live_ais11_candidates": len(live) - 1,
        "pct_live_with_original_ai": round(100.0 * len(ais11_usable_ex_spy) / max(1, len(live) - 1), 2),
        "note": "En Nazareno/Oracle los JSON están gitignored; sin generarlos AIS11 = NO_AI.",
    }


def pipeline_cpu_gpu():
    return {
        "timesfm": "corre en CPU (lento/OOM posible); no aborta",
        "tspulse_uni": "sys.exit(1) si no hay CUDA — AIS11 peso 65% queda vacío",
        "tspulse_multi": "sys.exit(1) si no hay CUDA; además no lo usa el backtester",
        "minirocket_bin": "CPU ok; solo 18 TICKERS; AIS11 no lo usa",
        "minirocket_gpu": "falla import tsai o queda en CPU; solo 18 TICKERS",
        "xgboost": "CPU ok; AIS11 no lo usa",
        "run_ai_update_background": "no aborta la cadena; igual escribe ai_last_updated.json",
        "setup_oracle": "instala torch CPU si no hay nvidia-smi; swap si RAM < 3.5GB",
    }


def telegram_cuts():
    return [
        {"cut": "Solo SS11+AIS11", "effect": "24 estrategias originales nunca pushean"},
        {"cut": "Solo transiciones in_pos", "effect": "BUY del scanner no es alerta; /ss11 y /ais11 son consulta"},
        {"cut": "initial_run / state vacío", "effect": "baseline 0 compras aunque haya 594 posiciones"},
        {"cut": "telegram_state ya hidratado", "effect": "sin flip de cartera → buys_queued=0 indefinidamente"},
        {"cut": "AIS11 NO_AI / notify_eligible=false", "effect": "excluido de la máquina de estados"},
        {"cut": "TELEGRAM_BUY_COOLDOWN_HOURS=12", "effect": "recompra post-SELL no alerta (estado sí se actualiza)"},
        {"cut": "TELEGRAM_DRY_RUN", "effect": "send retorna True sin HTTP"},
        {"cut": "token/chat vacíos", "effect": "warning y return False; 0 reintentos"},
        {"cut": "chat_id distinto al guardado", "effect": "comandos ignorados"},
        {"cut": "setup_oracle.sh pisa .env", "effect": "cada deploy reescribe solo TOKEN y CHAT_ID"},
        {"cut": "deploy reset origin/main", "effect": "push a fix/1 igual despliega main"},
    ]


def synthetic_ss11_divergence():
    n = 26
    closes = np.full(n, 100.0)
    opens = np.full(n, 100.0)
    closes[20] = 84.0
    opens[21] = 84.0
    for i in range(22, n):
        closes[i] = 84.0
        opens[i] = 84.0
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    df = pd.DataFrame({"Open": opens, "Close": closes}, index=idx)
    df["SMA_20"] = 200.0
    slong = np.ones(n, dtype=bool)
    sexit = np.zeros(n, dtype=bool)
    sig_o, met_o, _ = simulate_strategy_trades(df, slong, sexit, -15.0, False)
    sig_l, met_l, _ = simulate_strategy_trades(df, slong, sexit, -15.0, True)
    return {
        "scenario": "SS11: SL -15% y recuperación débil bajo SMA20, macro off",
        "original_strict_false": {"signal": sig_o, "in_pos": met_o["is_currently_in_position"]},
        "live_strict_true": {"signal": sig_l, "in_pos": met_l["is_currently_in_position"]},
        "divergence": met_o["is_currently_in_position"] != met_l["is_currently_in_position"],
    }


def _align_ai_original(df, ticker, orig_data):
    """Alineación tipo backtester.fetch_data (sin fillna 0.5 / 0.0)."""
    gpu = orig_data["gpu"].get(ticker, {})
    tfm = orig_data["tfm"].get(ticker, {})
    tsp = orig_data["tsp"].get(ticker, {})
    s_gpu = pd.Series(gpu)
    if not s_gpu.empty:
        s_gpu.index = pd.to_datetime(s_gpu.index)
    df["AI_MINIROCKET_GPU"] = s_gpu.reindex(df.index) * 100.0
    s_tfm = pd.Series(tfm)
    if not s_tfm.empty:
        s_tfm.index = pd.to_datetime(s_tfm.index)
    df["AI_TIMESFM"] = sigmoid_norm(s_tfm.reindex(df.index) * 100.0, 2.0)
    s_tsp = pd.Series(tsp)
    if not s_tsp.empty:
        s_tsp.index = pd.to_datetime(s_tsp.index)
    df["AI_TSPULSE"] = sigmoid_norm(s_tsp.reindex(df.index) * 100.0, 2.0)
    roc3 = df["Close"].pct_change(3).fillna(0.0) * 100
    df["ROC_3_NORM"] = sigmoid_norm(roc3, 5.0)
    return df


def _align_ai_live(df, ticker, orig_data):
    """Alineación tipo scanner.fetch_ticker_data."""
    gpu = orig_data["gpu"].get(ticker, {})
    tfm = orig_data["tfm"].get(ticker, {})
    tsp = orig_data["tsp"].get(ticker, {})
    s_gpu = pd.Series(gpu)
    if not s_gpu.empty:
        s_gpu.index = pd.to_datetime(s_gpu.index)
        df["AI_MINIROCKET_GPU"] = s_gpu.reindex(df.index).ffill().fillna(0.5) * 100.0
    else:
        df["AI_MINIROCKET_GPU"] = np.nan
    s_tfm = pd.Series(tfm)
    if not s_tfm.empty:
        s_tfm.index = pd.to_datetime(s_tfm.index)
        aligned = s_tfm.reindex(df.index).ffill().fillna(0.0)
        df["AI_TIMESFM"] = sigmoid_norm(aligned * 100.0, 2.0)
    else:
        df["AI_TIMESFM"] = np.nan
    s_tsp = pd.Series(tsp)
    if not s_tsp.empty:
        s_tsp.index = pd.to_datetime(s_tsp.index)
        aligned = s_tsp.reindex(df.index).ffill().fillna(0.0)
        df["AI_TSPULSE"] = sigmoid_norm(aligned * 100.0, 2.0)
    else:
        df["AI_TSPULSE"] = np.nan
    roc3 = df["Close"].pct_change(3).fillna(0.0) * 100
    df["ROC_3_NORM"] = sigmoid_norm(roc3, 5.0)
    return df


def _signal_counts(items):
    counts = {}
    in_pos = 0
    no_ai = 0
    notify = 0
    sl_recovery = 0
    for it in items:
        sig = it.get("signal", "?")
        counts[sig] = counts.get(sig, 0) + 1
        if it.get("metrics", {}).get("is_currently_in_position"):
            in_pos += 1
        if it.get("metrics", {}).get("in_sl_recovery"):
            sl_recovery += 1
        if sig == "NO_AI" or not it.get("has_ai", True):
            no_ai += 1
        if it.get("notify_eligible"):
            notify += 1
    return {
        "n": len(items),
        "signals": counts,
        "in_position": in_pos,
        "in_sl_recovery": sl_recovery,
        "no_ai": no_ai,
        "notify_eligible": notify,
    }


def analyze_live_cache():
    path = os.path.join(ROOT, "data", "live_scanner_cache.json")
    if not os.path.exists(path):
        return {"exists": False}
    with open(path, "r", encoding="utf-8") as f:
        cache = json.load(f)
    ss = cache.get("ss11_signals", [])
    ais = cache.get("ais11_signals", [])
    live = set(get_all_tickers())
    orig = set(TICKERS)
    overlap = [t for t in orig if t != "SPY" and t in live]

    def by_ticker(items):
        return {it["ticker"]: it for it in items}

    ss_map = by_ticker(ss)
    ais_map = by_ticker(ais)
    overlap_rows = []
    for t in overlap:
        ss_it = ss_map.get(t)
        ais_it = ais_map.get(t)
        overlap_rows.append({
            "ticker": t,
            "ss11_signal": None if not ss_it else ss_it.get("signal"),
            "ss11_in_pos": None if not ss_it else ss_it.get("metrics", {}).get("is_currently_in_position"),
            "ss11_sl_recovery": None if not ss_it else ss_it.get("metrics", {}).get("in_sl_recovery"),
            "ais11_signal": None if not ais_it else ais_it.get("signal"),
            "ais11_in_pos": None if not ais_it else ais_it.get("metrics", {}).get("is_currently_in_position"),
            "ais11_score": None if not ais_it else ais_it.get("ai_score"),
            "ais11_has_ai": None if not ais_it else ais_it.get("has_ai"),
        })

    wait_ss = [it["ticker"] for it in ss if it.get("signal") == "WAIT"]
    no_ai_ais = [it["ticker"] for it in ais if it.get("signal") == "NO_AI"]
    return {
        "exists": True,
        "timestamp": cache.get("timestamp"),
        "hardware": cache.get("hardware"),
        "ai_signals_age_days": cache.get("ai_signals_age_days"),
        "macro_guard": cache.get("macro_guard"),
        "summary": cache.get("summary"),
        "ss11": _signal_counts(ss),
        "ais11": _signal_counts(ais),
        "ss11_wait_tickers_sample": wait_ss[:20],
        "ss11_wait_count": len(wait_ss),
        "ais11_no_ai_count": len(no_ai_ais),
        "ais11_no_ai_pct": round(100.0 * len(no_ai_ais) / max(1, len(ais)), 2),
        "overlap_18_vs_cache": overlap_rows,
    }


def analyze_results_original_vs_naz():
    def load_signals(path):
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        out = {}
        for sid in ("SS11", "AIS11"):
            block = data.get(sid, {})
            out[sid] = {}
            for tk, met in block.items():
                if not isinstance(met, dict):
                    continue
                out[sid][tk] = {
                    "current_signal": met.get("current_signal"),
                    "is_open": met.get("is_open"),
                    "total_return": met.get("total_return"),
                }
        return out

    orig = load_signals(os.path.join(ORIG, "data", "results.json"))
    naz = load_signals(os.path.join(ROOT, "data", "results.json"))
    cmp_rows = []
    if orig and naz:
        for sid in ("SS11", "AIS11"):
            for tk in TICKERS:
                a = orig.get(sid, {}).get(tk)
                b = naz.get(sid, {}).get(tk)
                if not a and not b:
                    continue
                cmp_rows.append({
                    "strategy": sid,
                    "ticker": tk,
                    "original_signal": None if not a else a.get("current_signal"),
                    "nazareno_signal": None if not b else b.get("current_signal"),
                    "original_open": None if not a else a.get("is_open"),
                    "nazareno_open": None if not b else b.get("is_open"),
                    "mismatch": (None if not a else a.get("current_signal")) != (None if not b else b.get("current_signal")),
                })
    return {
        "original_exists": orig is not None,
        "nazareno_exists": naz is not None,
        "mismatches": sum(1 for r in cmp_rows if r.get("mismatch")),
        "rows": cmp_rows,
    }


def analyze_telegram_state():
    path = os.path.join(ROOT, "data", "telegram_state.json")
    if not os.path.exists(path):
        return {"exists": False}
    with open(path, "r", encoding="utf-8") as f:
        st = json.load(f)
    keys = [k for k in st if not k.startswith("__")]
    ss = [k for k in keys if k.startswith("SS11_")]
    ais = [k for k in keys if k.startswith("AIS11_")]
    ss_in = sum(1 for k in ss if st[k].get("in_pos"))
    ais_in = sum(1 for k in ais if st[k].get("in_pos"))
    return {
        "exists": True,
        "updated_at": st.get("__updated_at"),
        "last_scan": st.get("__last_scan"),
        "macro_crash_active": st.get("__macro_crash_active"),
        "keys": len(keys),
        "ss11_keys": len(ss),
        "ais11_keys": len(ais),
        "ss11_in_pos": ss_in,
        "ais11_in_pos": ais_in,
    }


def replay_common_tickers():
    orig_dir = os.path.join(ORIG, "data")
    orig_data = {"gpu": {}, "tfm": {}, "tsp": {}}
    mapping = {
        "gpu": "minirocket_gpu_signals.json",
        "tfm": "timesfm_signals.json",
        "tsp": "tspulse_signals.json",
    }
    for key, name in mapping.items():
        path = os.path.join(orig_dir, name)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                orig_data[key] = json.load(f)

    overlap = [t for t in TICKERS if t in set(get_all_tickers()) and t != "SPY"]
    params = load_ais11_params()
    rows = []
    downloaded = 0
    try:
        import yfinance as yf
    except Exception as e:
        return {"error": f"yfinance no disponible: {e}", "rows": []}

    spy = None
    try:
        spy = yf.download("SPY", period="5y", progress=False)
        if isinstance(spy.columns, pd.MultiIndex):
            spy.columns = [c[0] for c in spy.columns]
    except Exception:
        spy = None

    for ticker in overlap:
        try:
            df = yf.download(ticker, period="5y", progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[0] for c in df.columns]
            if df.empty or len(df) < 40:
                rows.append({"ticker": ticker, "error": "sin datos OHLC"})
                continue
            downloaded += 1
            df = df[(df["Close"] > 0) & (df["Open"] > 0)].copy()
            df["SMA_20"] = df["Close"].rolling(20, min_periods=1).mean()

            if spy is not None and not spy.empty:
                macro_mask, is_macro, _ = evaluate_macro_crash_guard(spy)
                spy_series = pd.Series(macro_mask, index=spy.index)
                macro_aligned = spy_series.reindex(df.index).ffill().fillna(False).values
            else:
                macro_aligned = np.zeros(len(df), dtype=bool)
                is_macro = False

            # SS11 original vs live
            ss_long = ~macro_aligned
            ss_exit = macro_aligned
            sig_ss_o, met_ss_o, _ = simulate_strategy_trades(df, ss_long, ss_exit, -15.0, False)
            sig_ss_l, met_ss_l, _ = simulate_strategy_trades(df, ss_long, ss_exit, -15.0, True)

            df_o = _align_ai_original(df.copy(), ticker, orig_data)
            df_l = _align_ai_live(df.copy(), ticker, orig_data)
            score_o, has_o = compute_ais11_score(df_o, params)
            score_l, has_l = compute_ais11_score(df_l, params)

            if spy is not None and not spy.empty:
                spy_idx = spy.index
                spy_ret = spy["Close"].pct_change()
            else:
                spy_idx = df_o.index
                spy_ret = df_o["Close"].pct_change()
            ls_o, es_o = generate_signals(
                df_o, ticker, spy_idx, spy_ret,
                STRATEGY_INFO["AIS11"], commission=0.004,
            )

            strict = (df_o["Close"] > df_o["SMA_20"]).values
            _, _, sig_bt = run_simulation(
                ls_o, es_o, df_o["Open"].values, df_o["Close"].values, df_o.index,
                commission=0.004, stop_loss_pct=-15.0, signals_strict=strict,
            )
            # last in_pos from simulation: BUY/HOLD => in
            bt_in = sig_bt in ("BUY", "HOLD")

            ai_wants_in = score_l > params["entry_th"]
            ai_wants_out = score_l < params["exit_th"]
            ais_long = ai_wants_in & (~macro_aligned)
            ais_exit = macro_aligned | ai_wants_out
            sig_ais_l, met_ais_l, _ = simulate_strategy_trades(df_l, ais_long, ais_exit, -15.0, True)

            last_o = float(score_o[-1]) if len(score_o) else None
            last_l = float(score_l[-1]) if len(score_l) else None
            rows.append({
                "ticker": ticker,
                "bars": int(len(df)),
                "macro_active": bool(is_macro),
                "ss11_original": {"signal": sig_ss_o, "in_pos": met_ss_o["is_currently_in_position"]},
                "ss11_live": {"signal": sig_ss_l, "in_pos": met_ss_l["is_currently_in_position"]},
                "ss11_in_pos_mismatch": met_ss_o["is_currently_in_position"] != met_ss_l["is_currently_in_position"],
                "ais11_has_ai_original_align": bool(has_o),
                "ais11_has_ai_live_align": bool(has_l),
                "ais11_score_original_last": None if last_o is None else round(last_o, 2),
                "ais11_score_live_last": None if last_l is None else round(last_l, 2),
                "ais11_score_abs_diff": None if last_o is None or last_l is None else round(abs(last_o - last_l), 3),
                "ais11_backtester_signal": sig_bt,
                "ais11_live_signal": sig_ais_l,
                "ais11_in_pos_mismatch": bt_in != met_ais_l["is_currently_in_position"],
            })
        except Exception as e:
            rows.append({"ticker": ticker, "error": str(e)})

    mismatches_ss = sum(1 for r in rows if r.get("ss11_in_pos_mismatch"))
    mismatches_ais = sum(1 for r in rows if r.get("ais11_in_pos_mismatch"))
    return {
        "downloaded": downloaded,
        "tickers_attempted": overlap,
        "ss11_in_pos_mismatches": mismatches_ss,
        "ais11_in_pos_mismatches": mismatches_ais,
        "rows": rows,
    }


def main():
    report = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "backtester_py_identical": True,
        "ais11_params": load_ais11_params(),
        "universe": universe_audit(),
        "strategies": strategy_parity_table(),
        "ai_coverage": ai_coverage(),
        "pipeline_cpu_gpu": pipeline_cpu_gpu(),
        "telegram_cuts": telegram_cuts(),
        "synthetic_ss11": synthetic_ss11_divergence(),
        "live_cache": analyze_live_cache(),
        "telegram_state": analyze_telegram_state(),
        "results_compare": analyze_results_original_vs_naz(),
        "replay_yfinance": replay_common_tickers(),
    }
    out = os.path.join(ROOT, "data", "diagnosis_live_vs_original.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    cache = report["live_cache"]
    print(json.dumps({
        "wrote": out,
        "overlap": report["universe"]["overlap"],
        "ais11_usable_from_orig_json": report["ai_coverage"]["ais11_usable_count"],
        "pct_live_with_orig_ai": report["ai_coverage"]["pct_live_with_original_ai"],
        "nazareno_ai_age": report["ai_coverage"]["nazareno_ai_age_days"],
        "ss11_synthetic_divergence": report["synthetic_ss11"]["divergence"],
        "cache_ts": cache.get("timestamp"),
        "cache_ss11": cache.get("ss11"),
        "cache_ais11": cache.get("ais11"),
        "cache_ais11_no_ai_pct": cache.get("ais11_no_ai_pct"),
        "telegram_state": report["telegram_state"],
        "results_mismatches": report["results_compare"].get("mismatches"),
        "replay_downloaded": report["replay_yfinance"].get("downloaded"),
    }, indent=2, ensure_ascii=False))
    return report


if __name__ == "__main__":
    main()
