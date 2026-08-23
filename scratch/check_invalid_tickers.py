import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import yfinance as yf
from utils.tickers_universe import TOP_250_US_STOCKS, TOP_50_CRYPTOS, get_all_tickers
from concurrent.futures import ThreadPoolExecutor

all_tickers = get_all_tickers()
print(f"Total tickers: {len(all_tickers)}")

# Check duplicates
seen = {}
for idx, t in enumerate(TOP_250_US_STOCKS):
    if t in seen:
        print(f"Duplicate found in US STOCKS: {t} at index {idx} and {seen[t]}")
    seen[t] = idx

def test_ticker(ticker):
    try:
        df = yf.download(ticker, period="5d", progress=False)
        if df.empty or len(df) == 0:
            return (ticker, "EMPTY")
        return (ticker, "OK")
    except Exception as e:
        return (ticker, str(e))

print("Testing downloading in parallel...")
with ThreadPoolExecutor(max_workers=20) as executor:
    results = list(executor.map(test_ticker, all_tickers))

failed = [r for r in results if r[1] != "OK"]
print(f"\n--- FAILED TICKERS ({len(failed)}) ---")
for t, status in failed:
    print(f"  {t}: {status}")
