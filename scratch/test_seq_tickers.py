import yfinance as yf
import time

test_list = [
    "FI", "FISV", "MMC", "CVP", "CFLT", "BK", "AET", "DFS", "BLL", "BALL", "HES", "SQ", "BLOCK",
    "SUI-USD", "APT-USD", "MATIC-USD", "POL-USD", "UNI-USD", "PEPE-USD", "STX-USD", "GRT-USD", "FTM-USD", "S-USD"
]

print("Testing tickers sequentially with delay...")
for t in test_list:
    try:
        df = yf.download(t, period="5d", progress=False)
        status = f"OK ({len(df)} rows)" if not df.empty else "EMPTY/DELISTED"
    except Exception as e:
        status = f"ERROR: {e}"
    print(f"  {t:12s}: {status}")
    time.sleep(0.5)
