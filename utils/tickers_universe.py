# -*- coding: utf-8 -*-
"""
Universo de Activos (300 Tickers):
- Top 250 Empresas de EE.UU. por Capitalización Bursátil (US Stocks & Large Caps)
- Top 50 Criptomonedas por Capitalización de Mercado (Crypto USD Pairs)
- Benchmark Macro: SPY
"""

TOP_250_US_STOCKS = [
    # Megacaps & Tech
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "BRK-B", "LLY", "AVGO",
    "JPM", "UNH", "V", "XOM", "MA", "PG", "COST", "JNJ", "HD", "MRK",
    "WMT", "NFLX", "BAC", "ABBV", "CRM", "CVX", "AMD", "ORCL", "KO", "PEP",
    "ADBE", "CSCO", "ACN", "TMO", "MCD", "IBM", "CAT", "GE", "QCOM", "PFE",
    "WFC", "INTC", "DHR", "INTU", "NOW", "AMAT", "DIS", "TXN", "MS", "PM",
    "VZ", "AXP", "SPGI", "COP", "RTX", "UBER", "ISRG", "AMGN", "LOW", "BKNG",
    "NKE", "HON", "GS", "PGR", "UNP", "SYK", "TJX", "T", "LRCX", "SCHW",
    "VRTX", "BLK", "ETN", "C", "MU", "PANW", "REGN", "LMT", "BSX", "BA",
    "ADP", "DE", "PLTR", "FISV", "CB", "MDLZ", "CI", "ADI", "KLAC", "GILD",
    "BMY", "MMC", "SBUX", "SNPS", "APP", "CDNS", "WM", "EOG", "HCA", "SLB",
    "CRWD", "SHW", "TT", "APH", "ORLY", "MO", "PH", "MCK", "NXPI", "CMG",
    "SO", "ITW", "DUK", "FCX", "CTAS", "AON", "TDG", "MAR", "CL", "CEG",
    "EMR", "PNC", "MSI", "USB", "ECL", "RSG", "CVS", "BDX", "ROP", "APTV",
    "COF", "HUM", "MCO", "AJG", "HLT", "CFLT", "AZO", "GM", "F", "DXCM",
    "MET", "ROST", "TRV", "FDX", "NOC", "PCAR", "WELL", "PSA", "AIG", "O",
    "IDXX", "KMB", "TGT", "PAYX", "MCHP", "OXY", "CCI", "DLR", "ALL", "FAST",
    "BK", "MPC", "WMB", "STZ", "GIS", "D", "KMI", "VLO", "IQV", "ADM",
    "GLW", "GEV", "CPRT", "SYY", "COR", "CTVA", "HAL", "AEP", "PRU", "KR",
    "SYF", "GWW", "YUM", "DD", "BKR", "NUE", "ED", "XEL", "OTIS", "VMC",
    "FANG", "ACGL", "MLM", "EXC", "LULU", "EIX", "BALL", "MTB", "VICI", "ANET",
    "EBAY", "ROK", "WEC", "HPQ", "FTNT", "KEYS", "RMD", "CSX", "AWK", "HIG", "WST",
    "STT", "ODFL", "WTW", "GPN", "DOV", "GEHC", "DVN", "FITB", "EFX", "URI",
    "CHD", "EL", "DAL", "UAL", "AAL", "LUV", "COIN", "HOOD", "PYPL", "SQ",
    "SHOP", "SE", "SNOW", "NET", "DDOG", "MDB", "ZS", "SMCI", "ARM", "DELL",
    "RBLX", "TWLO", "U", "PATH", "PLUG", "ENPH", "SEDG", "RIVN", "LCID", "NU"
]

TOP_50_CRYPTOS = [
    "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD", "DOGE-USD", "ADA-USD",
    "AVAX-USD", "LINK-USD", "SHIB-USD", "SUI-USD", "NEAR-USD", "APT-USD", "MATIC-USD",
    "LTC-USD", "UNI-USD", "ICP-USD", "BCH-USD", "FET-USD", "RENDER-USD", "PEPE-USD",
    "ETC-USD", "XLM-USD", "STX-USD", "FIL-USD", "INJ-USD", "AAVE-USD", "TIA-USD",
    "ARB-USD", "OP-USD", "WIF-USD", "BONK-USD", "FLOKI-USD", "GRT-USD", "THETA-USD",
    "FTM-USD", "RUNE-USD", "SAND-USD", "MANA-USD", "AXS-USD", "ALGO-USD", "FLOW-USD",
    "EOS-USD", "XTZ-USD", "NEO-USD", "KAVA-USD", "MINA-USD", "QNT-USD", "JUP-USD", "SEI-USD"
]

BENCHMARK_TICKER = "SPY"

def get_us_tickers():
    return list(TOP_250_US_STOCKS)

def get_crypto_tickers():
    return list(TOP_50_CRYPTOS)

def get_all_tickers():
    tickers = [BENCHMARK_TICKER]
    for t in TOP_250_US_STOCKS:
        if t not in tickers:
            tickers.append(t)
    for t in TOP_50_CRYPTOS:
        if t not in tickers:
            tickers.append(t)
    return tickers

def get_universe_summary():
    return {
        "benchmark": BENCHMARK_TICKER,
        "us_count": len(TOP_250_US_STOCKS),
        "crypto_count": len(TOP_50_CRYPTOS),
        "total_count": len(get_all_tickers())
    }

if __name__ == "__main__":
    summary = get_universe_summary()
    print(f"Universo cargado correctamente: {summary['total_count']} activos ({summary['us_count']} US, {summary['crypto_count']} Crypto)")
