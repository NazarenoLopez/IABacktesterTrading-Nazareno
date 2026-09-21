# -*- coding: utf-8 -*-
"""Descarga Yahoo Finance con curl_cffi, backoff y fallback a .data_cache."""
from __future__ import annotations

import os
import time
import contextlib
import io
from datetime import datetime

import pandas as pd
import yfinance as yf

CACHE_DIR = ".data_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

_YF_SESSION = None
_LAST_TICKER_TS = 0.0
_INTER_TICKER_SLEEP = 0.4
_BACKOFF = (2.0, 5.0, 10.0)


def _chrome_session():
    global _YF_SESSION
    if _YF_SESSION is not None:
        return _YF_SESSION
    try:
        from curl_cffi.requests import Session
        verify = os.environ.get("YF_SSL_VERIFY", "0").lower() in ("1", "true", "yes")
        _YF_SESSION = Session(impersonate="chrome", verify=verify)
    except Exception:
        _YF_SESSION = None
    return _YF_SESSION


def flatten_ohlc_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]
    if isinstance(df.index, pd.DatetimeIndex) and df.index.tz is not None:
        df.index = df.index.tz_convert(None)
    df.index.name = "Date"
    return df


def _pace():
    global _LAST_TICKER_TS
    now = time.time()
    wait = _INTER_TICKER_SLEEP - (now - _LAST_TICKER_TS)
    if wait > 0:
        time.sleep(wait)
    _LAST_TICKER_TS = time.time()


def _history_kwargs(start=None, period=None, interval="1d", end=None):
    kwargs = {"interval": interval, "auto_adjust": True, "timeout": 30}
    if period:
        kwargs["period"] = period
    else:
        if start:
            kwargs["start"] = start
        if end:
            kwargs["end"] = end
    return kwargs


def download_ticker(ticker, start=None, period=None, interval="1d", end=None):
    """Baja un ticker con sesión chrome y reintentos. DataFrame vacío si falla."""
    _pace()
    session = _chrome_session()
    df = pd.DataFrame()
    kwargs = _history_kwargs(start=start, period=period, interval=interval, end=end)
    buf = io.StringIO()
    for i, delay in enumerate(_BACKOFF):
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                tk = yf.Ticker(ticker, session=session) if session is not None else yf.Ticker(ticker)
                df = tk.history(**kwargs)
            df = flatten_ohlc_columns(df)
            if df is not None and not df.empty:
                return df
        except TypeError:
            try:
                with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                    df = yf.download(
                        ticker,
                        start=start,
                        end=end,
                        period=period,
                        interval=interval,
                        progress=False,
                        threads=False,
                        auto_adjust=True,
                    )
                df = flatten_ohlc_columns(df)
                if df is not None and not df.empty:
                    return df
            except Exception:
                pass
        except Exception:
            pass
        if i < len(_BACKOFF) - 1:
            time.sleep(delay)
    return flatten_ohlc_columns(df if df is not None else pd.DataFrame())


def download_tickers(tickers, period="1d", interval="1m"):
    """Varios tickers (p. ej. precios live). Un request batch lento, fallback uno a uno."""
    _pace()
    session = _chrome_session()
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            df = yf.download(
                list(tickers),
                period=period,
                interval=interval,
                progress=False,
                threads=False,
                auto_adjust=True,
                session=session,
            )
        if df is not None and not df.empty:
            return df
    except TypeError:
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                df = yf.download(
                    list(tickers),
                    period=period,
                    interval=interval,
                    progress=False,
                    threads=False,
                    auto_adjust=True,
                )
            if df is not None and not df.empty:
                return df
        except Exception:
            pass
    except Exception:
        pass

    closes = {}
    for t in tickers:
        one = download_ticker(t, period=period, interval=interval)
        if one is not None and not one.empty and "Close" in one.columns:
            closes[t] = one["Close"]
    if not closes:
        return pd.DataFrame()
    close_df = pd.concat(closes, axis=1)
    close_df.columns = list(closes.keys())
    return pd.concat({"Close": close_df}, axis=1)


def cache_path(ticker: str) -> str:
    return os.path.join(CACHE_DIR, f"{ticker}.csv")


def load_cache_csv(ticker: str) -> pd.DataFrame:
    path = cache_path(ticker)
    if not (os.path.exists(path) and os.path.getsize(path) > 100):
        return pd.DataFrame()
    try:
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        df.index.name = "Date"
        return flatten_ohlc_columns(df)
    except Exception:
        return pd.DataFrame()


def save_cache_csv(ticker: str, df: pd.DataFrame) -> None:
    if df is None or df.empty:
        return
    try:
        flatten_ohlc_columns(df).to_csv(cache_path(ticker))
    except Exception:
        pass


def fetch_with_cache(ticker, start=None, period=None, cache_expire_sec=3600, stale_ok=True):
    """
    Cache fresco si existe; si no, Yahoo; si Yahoo vacío, cache viejo.
    """
    path = cache_path(ticker)
    cache_valid = False
    if os.path.exists(path) and os.path.getsize(path) > 100:
        mod_time = os.path.getmtime(path)
        if 0 <= (time.time() - mod_time) < cache_expire_sec:
            cache_valid = True

    if cache_valid:
        cached = load_cache_csv(ticker)
        if not cached.empty:
            return cached

    df = download_ticker(ticker, start=start, period=period)
    if df is not None and not df.empty:
        save_cache_csv(ticker, df)
        return df

    stale = load_cache_csv(ticker)
    if stale_ok and not stale.empty:
        mtime = os.path.getmtime(path)
        when = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        print(f"[yf] {ticker}: Yahoo vacío/bloqueado; usando caché de {when}")
        return stale

    print(f"[yf] {ticker}: sin datos de Yahoo ni caché")
    return pd.DataFrame()
