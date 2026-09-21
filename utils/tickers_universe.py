# -*- coding: utf-8 -*-
"""
Universo de Activos:
- Top 250 Empresas de EE.UU. + extras del laboratorio (QQQ, GOOG, GLD, ...)
- Top 50 Criptomonedas por Capitalización de Mercado (Crypto USD Pairs)
- Benchmark Macro: SPY
"""
import os

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

# Símbolos del laboratorio (backtester.TICKERS) que no están en el top 250.
LAB_UNIVERSE_EXTRAS = ["QQQ", "DIA", "IWM", "GOOG", "GLD", "IVE", "EWZ", "PBR"]


def get_us_tickers():
    tickers = list(TOP_250_US_STOCKS)
    for t in LAB_UNIVERSE_EXTRAS:
        if t not in tickers:
            tickers.append(t)
    return tickers


def get_live_us_ai_tickers():
    """Universo para generar TimesFM/TSPulse/MiniRocket GPU: US + lab, sin crypto."""
    tickers = [BENCHMARK_TICKER]
    for t in get_us_tickers():
        if t not in tickers:
            tickers.append(t)
    return tickers


def live_us_start_date():
    """Horizonte 5y alineado al scanner live."""
    from datetime import datetime, timedelta
    return (datetime.today() - timedelta(days=365 * 5 + 7)).strftime("%Y-%m-%d")


def resolve_ai_fetch_args():
    """
    AI_TICKERS=live_us → universo US 5y.
    Default / lab → None, None (fetch_data usa los 18 desde 1996).
    """
    mode = os.environ.get("AI_TICKERS", "lab").strip().lower()
    if mode in ("live_us", "live-us", "us"):
        return get_live_us_ai_tickers(), live_us_start_date()
    return None, None

def get_crypto_tickers():
    return list(TOP_50_CRYPTOS)

def get_all_tickers():
    tickers = [BENCHMARK_TICKER]
    for t in get_us_tickers():
        if t not in tickers:
            tickers.append(t)
    for t in TOP_50_CRYPTOS:
        if t not in tickers:
            tickers.append(t)
    return tickers

def get_universe_summary():
    us = get_us_tickers()
    return {
        "benchmark": BENCHMARK_TICKER,
        "us_count": len(us),
        "crypto_count": len(TOP_50_CRYPTOS),
        "lab_extras": list(LAB_UNIVERSE_EXTRAS),
        "live_us_ai_count": len(get_live_us_ai_tickers()),
        "total_count": len(get_all_tickers())
    }

if __name__ == "__main__":
    summary = get_universe_summary()
    print(f"Universo cargado correctamente: {summary['total_count']} activos ({summary['us_count']} US, {summary['crypto_count']} Crypto)")
