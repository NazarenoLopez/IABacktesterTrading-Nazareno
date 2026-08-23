# -*- coding: utf-8 -*-
"""
Módulo Integrado de Bot de Telegram para Notificaciones de Trading y Comandos Interactivos.
Soporta:
- Carga de variables de entorno (.env)
- Notificaciones automáticas de señales de compra/venta y alertas de Stop Loss
- Comandos interactivos (/start, /posiciones, /actualizar, /scanner, /help)
- Guardado automático y persistente del Chat ID del usuario
"""

import os
import sys
import json
import time
import urllib.request
import urllib.parse
import threading
import traceback
from datetime import datetime

# Rutas de archivos de persistencia
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
ENV_PATH = os.path.join(BASE_DIR, '.env')
CONFIG_PATH = os.path.join(BASE_DIR, 'data', 'telegram_config.json')
STATE_PATH = os.path.join(BASE_DIR, 'data', 'telegram_state.json')

os.makedirs(os.path.join(BASE_DIR, 'data'), exist_ok=True)

# Configurar encoding UTF-8 para la consola de Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# -------------------------------------------------------------------------
# Carga de Variables de Entorno (.env)
# -------------------------------------------------------------------------
def load_dotenv_file():
    """Carga el archivo .env soportando delimitadores '=' y ':'."""
    if not os.path.exists(ENV_PATH):
        return

    try:
        with open(ENV_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                key, val = None, None
                if '=' in line:
                    parts = line.split('=', 1)
                    key, val = parts[0].strip(), parts[1].strip()
                elif ':' in line:
                    parts = line.split(':', 1)
                    key, val = parts[0].strip(), parts[1].strip()

                if key and val:
                    # Limpiar comillas si existen
                    val = val.strip("'\"")
                    os.environ[key] = val
    except Exception as e:
        print(f"[Telegram Bot] Error al cargar .env: {e}")

# Ejecución inicial de la carga de entorno
load_dotenv_file()

def get_bot_token():
    load_dotenv_file()
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()

def get_saved_chat_id():
    load_dotenv_file()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if chat_id:
        return chat_id
    
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                return str(cfg.get("chat_id", "")).strip()
        except Exception:
            pass
    return ""

def save_chat_id(chat_id):
    chat_id = str(chat_id).strip()
    if not chat_id:
        return
    
    os.environ["TELEGRAM_CHAT_ID"] = chat_id
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump({"chat_id": chat_id, "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}, f, indent=2)
    except Exception as e:
        print(f"[Telegram Bot] Error al guardar chat_id: {e}")

# -------------------------------------------------------------------------
# Envío de Mensajes a la API de Telegram
# -------------------------------------------------------------------------
def send_telegram_message(text, chat_id=None, parse_mode="HTML"):
    token = get_bot_token()
    if not token:
        print("[Telegram Bot] Advertencia: TELEGRAM_BOT_TOKEN no está configurado.")
        return False

    target_chat = chat_id or get_saved_chat_id()
    if not target_chat:
        print("[Telegram Bot] Advertencia: No hay TELEGRAM_CHAT_ID registrado aún. Envíe /start al bot para conectarlo.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": target_chat,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }

    try:
        data_encoded = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data_encoded, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            res_data = json.loads(resp.read().decode('utf-8'))
            return res_data.get("ok", False)
    except Exception as e:
        print(f"[Telegram Bot] Error enviando mensaje a Telegram: {e}")
        return False

# -------------------------------------------------------------------------
# Formateadores de Mensajes
# -------------------------------------------------------------------------
def format_active_positions_message(scanner_data):
    if not scanner_data:
        return "⚠️ No hay información del escáner disponible."

    ss11_list = scanner_data.get("ss11_signals", [])
    ais11_list = scanner_data.get("ais11_signals", [])

    active_positions = []

    # Extraer de SS11
    for item in ss11_list:
        met = item.get("metrics", {})
        if met.get("is_currently_in_position"):
            active_positions.append({
                "ticker": item["ticker"],
                "strategy": "SS11 (Macro)",
                "category": item.get("category", "N/A"),
                "price": item["price"],
                "entry_price": met.get("entry_price", item["price"]),
                "pnl_pct": met.get("floating_pnl_pct", 0.0),
                "dist_sl": item.get("dist_sl_pct", 0.0),
                "signal": item.get("signal", "HOLD")
            })

    # Extraer de AIS11
    for item in ais11_list:
        met = item.get("metrics", {})
        if met.get("is_currently_in_position"):
            active_positions.append({
                "ticker": item["ticker"],
                "strategy": "AIS11 (Multi-IA GPU)",
                "category": item.get("category", "N/A"),
                "price": item["price"],
                "entry_price": met.get("entry_price", item["price"]),
                "pnl_pct": met.get("floating_pnl_pct", 0.0),
                "ai_score": item.get("ai_score", 50.0),
                "signal": item.get("signal", "HOLD")
            })

    if not active_positions:
        return (
            "💼 <b>ESTADO DE POSICIONES ACTIVAS</b>\n\n"
            "ℹ️ Actualmente no hay posiciones abiertas en ninguna estrategia.\n"
            "El sistema se encuentra en liquidez esperando nuevas señales de compra."
        )

    msg = [f"💼 <b>POSICIONES ACTIVAS EN CARTERA ({len(active_positions)})</b>"]
    msg.append(f"<i>Actualizado: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</i>\n")

    for pos in active_positions:
        pnl_icon = "🟢" if pos["pnl_pct"] >= 0 else "🔴"
        pnl_sign = "+" if pos["pnl_pct"] >= 0 else ""
        
        entry_p = f"${pos['entry_price']:.2f}" if pos['entry_price'] > 1 else f"${pos['entry_price']:.4f}"
        curr_p = f"${pos['price']:.2f}" if pos['price'] > 1 else f"${pos['price']:.4f}"

        msg.append(f"📌 <b>{pos['ticker']}</b> | <i>{pos['strategy']}</i>")
        msg.append(f" • Entrada: {entry_p} ➔ Actual: {curr_p}")
        msg.append(f" • PnL Flotante: {pnl_icon} <b>{pnl_sign}{pos['pnl_pct']:.2f}%</b>")
        if "dist_sl" in pos:
            msg.append(f" • Distancia a SL (-15%): <code>{pos['dist_sl']:+.1f}%</code>")
        if "ai_score" in pos:
            msg.append(f" • Score IA: <code>{pos['ai_score']:.1f}/100</code>")
        msg.append(f" • Estado: <b>{pos['signal']}</b>\n")

    return "\n".join(msg)

def format_scanner_summary_message(scanner_data):
    if not scanner_data:
        return "⚠️ No hay datos del escáner disponible."

    mg = scanner_data.get("macro_guard", {})
    summary = scanner_data.get("summary", {})
    ss11_buys = [s for s in scanner_data.get("ss11_signals", []) if s.get("signal") == "BUY"]
    ais11_buys = [s for s in scanner_data.get("ais11_signals", []) if s.get("signal") == "BUY"]

    msg = ["⚡ <b>RESUMEN DEL ESCÁNER EN VIVO</b>"]
    msg.append(f"<i>Filtro Macro SPY:</i> {mg.get('message', 'N/A')}\n")
    msg.append(f"📊 Total Activos Escaneados: <b>{summary.get('total_scanned', 0)}</b>")
    msg.append(f"🚀 Señales BUY SS11: <b>{len(ss11_buys)}</b> | AIS11: <b>{len(ais11_buys)}</b>\n")

    if ss11_buys:
        msg.append("<b>🟢 OPORTUNIDADES BUY (SS11 Macro):</b>")
        for b in ss11_buys[:5]:
            msg.append(f" • <b>{b['ticker']}</b> (${b['price']}) ➔ Var 24h: {b['change_24h']:+.2f}%")
        msg.append("")

    if ais11_buys:
        msg.append("<b>🧠 OPORTUNIDADES BUY (AIS11 Multi-IA):</b>")
        for b in ais11_buys[:5]:
            msg.append(f" • <b>{b['ticker']}</b> (${b['price']}) ➔ Score IA: {b.get('ai_score', 50):.1f}")
        msg.append("")

    if not ss11_buys and not ais11_buys:
        msg.append("ℹ️ <i>Sin oportunidades de compra inmediatas. Mercado en espera.</i>")

    return "\n".join(msg)

# -------------------------------------------------------------------------
# Verificación y Alertas de Notificaciones de Trades
# -------------------------------------------------------------------------
def check_and_notify_trades(scanner_data):
    """Compara las señales actuales con el estado previo y envía alertas por Telegram si hay cambios."""
    if not scanner_data:
        return

    saved_state = {}
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, 'r', encoding='utf-8') as f:
                saved_state = json.load(f)
        except Exception:
            saved_state = {}

    current_state = {}
    notifications = []

    # Procesar SS11
    for item in scanner_data.get("ss11_signals", []):
        tk = item["ticker"]
        sig = item["signal"]
        met = item.get("metrics", {})
        in_pos = met.get("is_currently_in_position", False)
        
        key = f"SS11_{tk}"
        current_state[key] = {"signal": sig, "in_pos": in_pos}
        
        prev = saved_state.get(key, {})
        prev_sig = prev.get("signal")
        prev_in_pos = prev.get("in_pos", False)

        # Detectar Nueva Entrada (BUY)
        if sig == "BUY" and prev_sig != "BUY":
            notifications.append(
                f"🚀 <b>NUEVA SEÑAL DE ENTRADA (BUY)</b>\n"
                f"• <b>Activo:</b> {tk} ({item.get('category', 'N/A')})\n"
                f"• <b>Estrategia:</b> SS11 Macro Base Pura\n"
                f"• <b>Precio Actual:</b> ${item['price']}\n"
                f"• <b>Variación 24h:</b> {item['change_24h']:+.2f}%\n"
                f"• <b>Dist. Recup SMA20:</b> {item.get('dist_sma20_pct', 0.0):+.1f}%"
            )

        # Detectar Cierre de Posición / Salida (SELL)
        if prev_in_pos and not in_pos:
            notifications.append(
                f"🛑 <b>SALIDA / CIERRE DE POSICIÓN (SELL)</b>\n"
                f"• <b>Activo:</b> {tk}\n"
                f"• <b>Estrategia:</b> SS11 Macro Base Pura\n"
                f"• <b>Precio de Salida:</b> ${item['price']}\n"
                f"• <b>Motivo:</b> Cambio de señal a {sig} / Salida a Liquidez"
            )

    # Procesar AIS11
    for item in scanner_data.get("ais11_signals", []):
        tk = item["ticker"]
        sig = item["signal"]
        met = item.get("metrics", {})
        in_pos = met.get("is_currently_in_position", False)
        
        key = f"AIS11_{tk}"
        current_state[key] = {"signal": sig, "in_pos": in_pos}
        
        prev = saved_state.get(key, {})
        prev_sig = prev.get("signal")
        prev_in_pos = prev.get("in_pos", False)

        if sig == "BUY" and prev_sig != "BUY":
            notifications.append(
                f"🧠 <b>NUEVA SEÑAL DE ENTRADA MULTI-IA (BUY)</b>\n"
                f"• <b>Activo:</b> {tk} ({item.get('category', 'N/A')})\n"
                f"• <b>Estrategia:</b> AIS11 Multi-IA GPU Master\n"
                f"• <b>Precio Actual:</b> ${item['price']}\n"
                f"• <b>Score de IA:</b> <b>{item.get('ai_score', 50):.1f}/100</b>\n"
                f"• <b>Variación 24h:</b> {item['change_24h']:+.2f}%"
            )

        if prev_in_pos and not in_pos:
            notifications.append(
                f"🛑 <b>SALIDA DE POSICIÓN IA (SELL)</b>\n"
                f"• <b>Activo:</b> {tk}\n"
                f"• <b>Estrategia:</b> AIS11 Multi-IA GPU Master\n"
                f"• <b>Precio de Salida:</b> ${item['price']}\n"
                f"• <b>Score de IA Actual:</b> {item.get('ai_score', 50):.1f}/100"
            )

    # Guardar nuevo estado
    try:
        with open(STATE_PATH, 'w', encoding='utf-8') as f:
            json.dump(current_state, f, indent=2)
    except Exception:
        pass

    # Enviar notificaciones si hay novedades
    for notif in notifications:
        send_telegram_message(notif)

# -------------------------------------------------------------------------
# Bucle Listener Polling de Comandos de Telegram
# -------------------------------------------------------------------------
def start_telegram_bot_listener():
    token = get_bot_token()
    if not token:
        print("[Telegram Bot] Bot no iniciado: Falta TELEGRAM_BOT_TOKEN en .env")
        return

    print("[Telegram Bot] 🤖 Bot de Telegram activo y escuchando comandos...")
    offset = None

    while True:
        try:
            url = f"https://api.telegram.org/bot{token}/getUpdates?timeout=20"
            if offset:
                url += f"&offset={offset}"

            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=25) as resp:
                res = json.loads(resp.read().decode('utf-8'))
                if res.get("ok"):
                    updates = res.get("result", [])
                    for update in updates:
                        offset = update["update_id"] + 1
                        msg = update.get("message") or update.get("edited_message")
                        if not msg:
                            continue

                        chat = msg.get("chat", {})
                        chat_id = str(chat.get("id", "")).strip()
                        text = (msg.get("text") or "").strip()

                        if not chat_id or not text:
                            continue

                        saved_id = str(get_saved_chat_id()).strip()
                        if saved_id:
                            if chat_id != saved_id:
                                print(f"[Telegram Bot] ⛔ Acceso bloqueado para usuario no autorizado (Chat ID: {chat_id})")
                                continue
                        else:
                            save_chat_id(chat_id)

                        cmd = text.split()[0].lower()

                        if cmd == "/start":
                            welcome = (
                                "👋 <b>¡Bienvenido al Bot de IA Backtester Trading!</b>\n\n"
                                "✅ Tu Chat ID ha sido registrado exitosamente para recibir <b>alertas automáticas de trades</b>.\n\n"
                                "<b>Comandos disponibles:</b>\n"
                                "• /posiciones - Ver todas las posiciones activas en cartera\n"
                                "• /actualizar - Forzar actualización del escáner en tiempo real\n"
                                "• /scanner - Ver resumen del mercado y oportunidades BUY\n"
                                "• /help - Mostrar este menú de ayuda"
                            )
                            send_telegram_message(welcome, chat_id=chat_id)

                        elif cmd in ["/posiciones", "/activas"]:
                            send_telegram_message("⏳ Obteniendo posiciones activas del motor...", chat_id=chat_id)
                            try:
                                cache_file = os.path.join(BASE_DIR, "data", "live_scanner_cache.json")
                                scanner_data = None
                                if os.path.exists(cache_file):
                                    with open(cache_file, "r", encoding="utf-8") as f:
                                        scanner_data = json.load(f)
                                else:
                                    from utils.scanner_engine import run_live_scanner
                                    scanner_data = run_live_scanner()

                                reply = format_active_positions_message(scanner_data)
                                send_telegram_message(reply, chat_id=chat_id)
                            except Exception as e:
                                send_telegram_message(f"❌ Error al consultar posiciones: {e}", chat_id=chat_id)

                        elif cmd in ["/actualizar", "/scanner"]:
                            send_telegram_message("🔄 Ejecutando escáner en tiempo real...", chat_id=chat_id)
                            try:
                                from utils.scanner_engine import run_live_scanner
                                scanner_data = run_live_scanner()
                                
                                # Enviar resumen
                                summary_msg = format_scanner_summary_message(scanner_data)
                                send_telegram_message(summary_msg, chat_id=chat_id)
                                
                                # Enviar posiciones activas también
                                pos_msg = format_active_positions_message(scanner_data)
                                send_telegram_message(pos_msg, chat_id=chat_id)
                            except Exception as e:
                                send_telegram_message(f"❌ Error al actualizar el escáner: {e}", chat_id=chat_id)

                        elif cmd == "/help":
                            help_msg = (
                                "ℹ️ <b>AYUDA Y COMANDOS DEL BOT</b>\n\n"
                                "• /posiciones - Muestra las posiciones actualmente abiertas con sus PnL flotantes.\n"
                                "• /actualizar - Fuerza un escaneo en vivo de las cotizaciones y actualiza las señales.\n"
                                "• /scanner - Muestra el resumen de oportunidades BUY y filtro macro SPY.\n"
                                "• /start - Registra tu usuario para notificaciones."
                            )
                            send_telegram_message(help_msg, chat_id=chat_id)

        except Exception as e:
            # Silenciar desconexiones normales de red y reintentar
            time.sleep(5)

def launch_bot_background():
    """Inicia el bot de Telegram en un hilo en segundo plano."""
    t = threading.Thread(target=start_telegram_bot_listener, daemon=True)
    t.start()
    return t

if __name__ == "__main__":
    print("Probando bot de Telegram localmente...")
    token = get_bot_token()
    cid = get_saved_chat_id()
    print(f"Token configurado: {bool(token)}, Chat ID configurado: {cid or 'Ninguno (Esperando /start)'}")
    if token and cid:
        send_telegram_message("🤖 <b>Bot de Telegram iniciado correctamente.</b> Test de notificación OK.")
    
    # Iniciar listener interactivo
    start_telegram_bot_listener()
