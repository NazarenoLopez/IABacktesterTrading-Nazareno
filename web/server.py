import http.server
import socketserver
import urllib.parse
import json
import traceback
import sys
import os
import io
import contextlib
import shutil
from datetime import datetime
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import backtester
import threading

PORT = 8000
IS_LOADING = True

AI_STATUS = {
    "is_running": False,
    "current_step": 0,
    "total_steps": 6,
    "step_name": "",
    "error": None
}

def run_ai_update_background():
    global AI_STATUS
    AI_STATUS["is_running"] = True
    AI_STATUS["error"] = None
    AI_STATUS["current_step"] = 0

    steps = [
        ("models/precalculate_timesfm.py", "[1/6] Google TimesFM (Oráculo Principal)"),
        ("models/finetune_tspulse.py", "[2/6] IBM TSPulse Univariate"),
        ("models/finetune_tspulse_multi.py", "[3/6] IBM TSPulse Multivariate"),
        ("models/train_minirocket.py", "[4/6] MiniRocket Clasificación"),
        ("models/train_minirocket_gpu.py", "[5/6] MiniRocketPlus GPU Probabilidades"),
        ("models/train_xgboost_stack.py", "[6/6] XGBoost Stack Ensamble")
    ]

    py_cmd = shutil.which("uv")
    if py_cmd:
        base_cmd = [py_cmd, "run", "python"]
    else:
        base_cmd = [sys.executable]

    env = os.environ.copy()
    env["YF_CACHE_SECONDS"] = "3600"

    try:
        import subprocess
        for idx, (script, desc) in enumerate(steps, 1):
            AI_STATUS["current_step"] = idx
            AI_STATUS["step_name"] = desc
            print(f"\n[AI Background Update] {desc}...")
            res = subprocess.run(base_cmd + [script], env=env)
            if res.returncode != 0:
                print(f"[AI Background Update] Advertencia en {script} (Código {res.returncode})")
        
        AI_STATUS["step_name"] = "Regenerando rankings y backtests finales..."
        import importlib
        importlib.reload(backtester)
        result_dict = backtester.run_all(commission=0.004)
        with open("data/results.json", "w", encoding="utf-8") as f:
            json.dump(result_dict, f, indent=2, ensure_ascii=False)

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open("data/ai_last_updated.json", "w", encoding="utf-8") as f:
                json.dump({"last_updated": now_str}, f, indent=2)
        except Exception: pass
            
    except Exception as e:
        AI_STATUS["error"] = str(e)
        traceback.print_exc()
    finally:
        AI_STATUS["is_running"] = False
        AI_STATUS["step_name"] = "Completado"

LIVE_PRICES_CACHE = {}

def update_live_prices_loop():
    global LIVE_PRICES_CACHE
    import time
    import yfinance as yf
    import pandas as pd
    from backtester import TICKERS

    while True:
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                df = yf.download(TICKERS, period="1d", interval="1m", progress=False)
            if not df.empty:
                prices = {}
                if isinstance(df.columns, pd.MultiIndex):
                    if 'Close' in df.columns:
                        close_df = df['Close']
                        valid_df = close_df.dropna(how='all')
                        if not valid_df.empty:
                            last_row = valid_df.iloc[-1]
                            for tk in TICKERS:
                                if tk in last_row and pd.notna(last_row[tk]):
                                    prices[tk] = float(last_row[tk])
                else:
                    if 'Close' in df.columns:
                        valid_s = df['Close'].dropna()
                        if not valid_s.empty:
                            last_val = valid_s.iloc[-1]
                            if pd.notna(last_val):
                                for tk in TICKERS:
                                    prices[tk] = float(last_val)
                if prices:
                    LIVE_PRICES_CACHE = prices
        except Exception:
            pass
        time.sleep(15)

class APIHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        super().end_headers()

    def do_POST(self):
        parsed_path = urllib.parse.urlparse(self.path)
        if parsed_path.path == '/api/update-ai':
            if not AI_STATUS["is_running"]:
                threading.Thread(target=run_ai_update_background, daemon=True).start()
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "started", "is_running": True}).encode('utf-8'))
            return
        self.send_error(404)

    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        
        if parsed_path.path in ('', '/'):
            self.send_response(302)
            self.send_header('Location', '/web/')
            self.end_headers()
            return

        if parsed_path.path == '/api/ai-status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            last_ai_date = None
            if os.path.exists("data/xgboost_stack_signals.json"):
                try:
                    with open("data/xgboost_stack_signals.json", "r") as f:
                        d = json.load(f)
                        spy_dates = list(d.get("SPY", {}).keys())
                        if spy_dates:
                            last_ai_date = sorted(spy_dates)[-1][:10]
                except Exception:
                    pass
            
            last_market_date = None
            if os.path.exists(".data_cache/SPY.csv"):
                try:
                    import pandas as pd
                    df_spy = pd.read_csv(".data_cache/SPY.csv")
                    dates = df_spy.iloc[:, 0].dropna()
                    if not dates.empty:
                        last_market_date = str(dates.iloc[-1])[:10]
                except Exception:
                    pass
                    
            status_code = "up_to_date"
            if AI_STATUS["is_running"]:
                status_code = "running"
            elif last_ai_date and last_market_date and last_ai_date < last_market_date:
                status_code = "outdated"
                
            last_updated_time = None
            if os.path.exists("data/ai_last_updated.json"):
                try:
                    with open("data/ai_last_updated.json", "r") as f:
                        last_updated_time = json.load(f).get("last_updated")
                except Exception: pass
            
            if not last_updated_time:
                for target_file in ["data/xgboost_stack_signals.json", "data/minirocket_gpu_signals.json", "data/results.json"]:
                    if os.path.exists(target_file):
                        mtime = os.path.getmtime(target_file)
                        last_updated_time = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                        break

            res = {
                "status": status_code,
                "is_running": AI_STATUS["is_running"],
                "step": AI_STATUS["current_step"],
                "total": AI_STATUS["total_steps"],
                "step_name": AI_STATUS["step_name"],
                "last_ai_date": last_ai_date or "Desconocido",
                "latest_market_date": last_market_date or "Desconocido",
                "last_updated_time": last_updated_time or "Desconocido",
                "error": AI_STATUS["error"]
            }
            self.wfile.write(json.dumps(res).encode('utf-8'))
            return

        # API Endpoint
        if parsed_path.path == '/api/status':
            global IS_LOADING
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"loading": IS_LOADING}).encode('utf-8'))
            return

        if parsed_path.path == '/api/recalculate':
            qs = urllib.parse.parse_qs(parsed_path.query)
            comm_str = qs.get('commission', ['0.0'])[0]
            try:
                # User enters percentage e.g. 0.4, we need decimal 0.004
                comm_pct = float(comm_str)
                comm_decimal = comm_pct / 100.0
            except ValueError:
                comm_decimal = 0.004
                
            start_date = qs.get('start_date', [None])[0]
            end_date = qs.get('end_date', [None])[0]
            
            try:
                print(f"Server received request to recalculate with commission: {comm_pct}%, start: {start_date}, end: {end_date}")
                import importlib
                importlib.reload(backtester)
                result_dict = backtester.run_all(commission=comm_decimal, start_date=start_date, end_date=end_date)
                
                # Also save to results.json to keep it updated for future static loads
                with open("data/results.json", "w", encoding="utf-8") as f:
                    json.dump(result_dict, f, indent=2, ensure_ascii=False)
                    
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result_dict).encode('utf-8'))
            except Exception as e:
                print("Error during recalculation:")
                traceback.print_exc()
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return
            
        if parsed_path.path == '/api/live-prices':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(LIVE_PRICES_CACHE).encode('utf-8'))
            return

        if parsed_path.path == '/api/live-scanner':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            try:
                from utils.scanner_engine import run_live_scanner
                cache_file = "data/live_scanner_cache.json"
                qs = urllib.parse.parse_qs(parsed_path.query)
                force_refresh = qs.get('refresh', ['false'])[0].lower() == 'true'

                scanner_res = None
                if not force_refresh and os.path.exists(cache_file):
                    try:
                        with open(cache_file, "r", encoding="utf-8") as f:
                            scanner_res = json.load(f)
                    except Exception: pass

                if scanner_res is None or force_refresh:
                    scanner_res = run_live_scanner()

                from utils.scanner_engine import clean_nans
                scanner_res = clean_nans(scanner_res)

                self.wfile.write(json.dumps(scanner_res, ensure_ascii=False).encode('utf-8'))
            except Exception as e:
                print("Error in /api/live-scanner:")
                traceback.print_exc()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return

        if parsed_path.path == '/api/hardware':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            try:
                from utils.scanner_engine import get_hardware_status
                self.wfile.write(json.dumps(get_hardware_status()).encode('utf-8'))
            except Exception as e:
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return

        if parsed_path.path == '/api/universe':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            try:
                from utils.tickers_universe import get_universe_summary
                self.wfile.write(json.dumps(get_universe_summary()).encode('utf-8'))
            except Exception as e:
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return

        if parsed_path.path == '/api/active-positions':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            try:
                cache_file = "data/live_scanner_cache.json"
                scanner_res = None
                if os.path.exists(cache_file):
                    with open(cache_file, "r", encoding="utf-8") as f:
                        scanner_res = json.load(f)
                else:
                    from utils.scanner_engine import run_live_scanner
                    scanner_res = run_live_scanner()

                actives = []
                for strat_key in ["ss11_signals", "ais11_signals"]:
                    strat_label = "SS11 (Macro)" if strat_key == "ss11_signals" else "AIS11 (Multi-IA)"
                    for item in scanner_res.get(strat_key, []):
                        met = item.get("metrics", {})
                        if met.get("is_currently_in_position"):
                            actives.append({
                                "ticker": item["ticker"],
                                "strategy": strat_label,
                                "category": item.get("category", "N/A"),
                                "price": item["price"],
                                "entry_price": met.get("entry_price", item["price"]),
                                "pnl_pct": met.get("floating_pnl_pct", 0.0),
                                "dist_sl": item.get("dist_sl_pct", 0.0),
                                "dist_sma20": item.get("dist_sma20_pct", 0.0),
                                "signal": item.get("signal", "HOLD"),
                                "recent_trades": item.get("recent_trades", [])
                            })
                self.wfile.write(json.dumps({"positions": actives, "count": len(actives)}, ensure_ascii=False).encode('utf-8'))
            except Exception as e:
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return

        # Serve static files normally
        super().do_GET()

if __name__ == "__main__":
    # Cargar variables de entorno de .env
    try:
        from utils.telegram_bot import load_dotenv_file, launch_bot_background
        load_dotenv_file()
        launch_bot_background()
    except Exception as e:
        print(f"[Server] Advertencia al iniciar bot de Telegram: {e}")

    def load_data_thread():
        global IS_LOADING
        print("Pre-loading Yahoo Finance data into memory cache...")
        try:
            backtester.run_all(commission=0.004)
            print("\nData loaded.")
        except Exception as e:
            print(f"\nError loading data: {e}")
            traceback.print_exc()
        IS_LOADING = False

    def run_auto_scanner_loop():
        import time
        from utils.scanner_engine import run_live_scanner
        print("[Auto-Scanner] Bucle de actualización automática cada 60 segundos iniciado.")
        while True:
            try:
                # Runs scanner and updates live_scanner_cache.json
                run_live_scanner()
            except Exception as e:
                print(f"[Auto-Scanner] Advertencia en escáner automático: {e}")
            time.sleep(60)

    def run_daily_timer_loop():
        import time
        print("[Timer-Scheduler] Temporizador de IA iniciado: primer ejecución en 18 horas, luego cada 24 horas.")
        time.sleep(18 * 3600)
        while True:
            try:
                if not AI_STATUS["is_running"]:
                    print("\n[Timer-Scheduler] ⏰ Iniciando actualización automática de IA (intervalo 24hs)...")
                    threading.Thread(target=run_ai_update_background, daemon=True).start()
            except Exception as e:
                print(f"[Timer-Scheduler] Advertencia en temporizador: {e}")
            time.sleep(24 * 3600)

    # Start data loading & auto-scanner in background
    threading.Thread(target=load_data_thread, daemon=True).start()
    threading.Thread(target=update_live_prices_loop, daemon=True).start()
    threading.Thread(target=run_auto_scanner_loop, daemon=True).start()
    threading.Thread(target=run_daily_timer_loop, daemon=True).start()
    
    try:
        with http.server.ThreadingHTTPServer(("", PORT), APIHandler) as httpd:
            print(f"Serving at port {PORT}. Web Dashboard available at http://localhost:{PORT}")
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[Server] Servidor detenido por el usuario.")

