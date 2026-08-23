import sys
import os
import io
import contextlib
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import yfinance as yf
from utils.tickers_universe import TOP_250_US_STOCKS, TOP_50_CRYPTOS

# Replacements for outdated/delisted/changed tickers
replacements = {
    "FI": "FISV",      # Fiserv yfinance symbol is FISV
    "BLL": "BALL",     # Ball Corp symbol changed to BALL
    "AET": "COR",      # Cencora
    "CVP": "APP",      # AppLovin Corp
    "HES": "VRTX",     # Vertex Pharmaceuticals
    "DFS": "SYF",      # Synchrony Financial
}

clean_us = []
for t in TOP_250_US_STOCKS:
    t_fixed = replacements.get(t, t)
    if t_fixed not in clean_us:
        clean_us.append(t_fixed)

print(f"Cleaned US count: {len(clean_us)}")

failed_us = []
for idx, t in enumerate(clean_us):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            df = yf.download(t, period="5d", progress=False)
            empty = df.empty
        except Exception:
            empty = True
    if empty:
        failed_us.append((t, buf.getvalue().strip()))
    if (idx + 1) % 25 == 0:
        print(f"  Processed {idx+1}/{len(clean_us)} US stocks... (Failed so far: {len(failed_us)})", flush=True)

print(f"\nFailed US stocks ({len(failed_us)}):")
for t, msg in failed_us:
    print(f"  {t}: {msg[:100]}")

clean_crypto = []
for t in TOP_50_CRYPTOS:
    if t not in clean_crypto:
        clean_crypto.append(t)

failed_crypto = []
for idx, t in enumerate(clean_crypto):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            df = yf.download(t, period="5d", progress=False)
            empty = df.empty
        except Exception:
            empty = True
    if empty:
        failed_crypto.append((t, buf.getvalue().strip()))

print(f"\nFailed Crypto ({len(failed_crypto)}):")
for t, msg in failed_crypto:
    print(f"  {t}: {msg[:100]}")
