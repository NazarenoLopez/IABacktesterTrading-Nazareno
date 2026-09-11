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
def format_price_telegram(price):
    if price is None:
        return "$0.00"
    try:
        p = float(price)
        if p == 0:
            return "$0.00"
        abs_p = abs(p)
        if abs_p >= 100:
            return f"${p:,.2f}"
        elif abs_p >= 1:
            return f"${p:.2f}"
        elif abs_p >= 0.01:
            return f"${p:.4f}"
        elif abs_p >= 0.0001:
            return f"${p:.6f}"
        else:
            return f"${p:.8f}".rstrip('0').rstrip('.')
    except (ValueError, TypeError):
        return f"${price}"

def format_active_positions_message(scanner_data, top_n=10):
    if not scanner_data:
        return "⚠️ No hay datos del escáner disponible."

    ss11_list = scanner_data.get("ss11_signals", [])
    ais11_list = scanner_data.get("ais11_signals", [])

    ss11_active = []
    for item in ss11_list:
        met = item.get("metrics", {})
        if met.get("is_currently_in_position"):
            ss11_active.append({
                "ticker": item["ticker"],
                "category": item.get("category", "N/A"),
                "price": item["price"],
                "entry_price": met.get("entry_price", item["price"]),
                "pnl_pct": met.get("floating_pnl_pct", 0.0),
                "dist_sl": item.get("dist_sl_pct", 0.0),
                "signal": item.get("signal", "HOLD")
            })

    ais11_active = []
    for item in ais11_list:
        met = item.get("metrics", {})
        if met.get("is_currently_in_position"):
            ais11_active.append({
                "ticker": item["ticker"],
                "category": item.get("category", "N/A"),
                "price": item["price"],
                "entry_price": met.get("entry_price", item["price"]),
                "pnl_pct": met.get("floating_pnl_pct", 0.0),
                "ai_score": item.get("ai_score", 50.0),
                "signal": item.get("signal", "HOLD")
            })

    total_active = len(ss11_active) + len(ais11_active)
    if total_active == 0:
        return (
            "💼 <b>ESTADO DE POSICIONES ACTIVAS</b>\n\n"
            "ℹ️ Actualmente no hay posiciones abiertas en ninguna estrategia.\n"
            "El sistema se encuentra en liquidez esperando nuevas señales de compra."
        )

    msg = [f"💼 <b>POSICIONES ACTIVAS EN CARTERA ({total_active})</b>"]
    msg.append(f"<i>Actualizado: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</i>\n")

    if ss11_active:
        msg.append(f"<b>🟢 SS11 Macro Base Pura ({len(ss11_active)} activas - Top {min(len(ss11_active), top_n)}):</b>")
        for pos in ss11_active[:top_n]:
            pnl_icon = "🟢" if pos["pnl_pct"] >= 0 else "🔴"
            pnl_sign = "+" if pos["pnl_pct"] >= 0 else ""
            entry_p = format_price_telegram(pos['entry_price'])
            curr_p = format_price_telegram(pos['price'])
            msg.append(f" • <b>{pos['ticker']}</b> ({curr_p}) | Entr: {entry_p} | PnL: {pnl_icon} <b>{pnl_sign}{pos['pnl_pct']:.2f}%</b> | SL: <code>{pos['dist_sl']:+.1f}%</code>")
        msg.append("")

    if ais11_active:
        msg.append(f"<b>🧠 AIS11 Multi-IA GPU Master ({len(ais11_active)} activas - Top {min(len(ais11_active), top_n)}):</b>")
        for pos in ais11_active[:top_n]:
            pnl_icon = "🟢" if pos["pnl_pct"] >= 0 else "🔴"
            pnl_sign = "+" if pos["pnl_pct"] >= 0 else ""
            entry_p = format_price_telegram(pos['entry_price'])
            curr_p = format_price_telegram(pos['price'])
            msg.append(f" • <b>{pos['ticker']}</b> ({curr_p}) | Entr: {entry_p} | PnL: {pnl_icon} <b>{pnl_sign}{pos['pnl_pct']:.2f}%</b> | Score IA: <code>{pos['ai_score']:.1f}</code>")
        msg.append("")

    return "\n".join(msg)

def format_scanner_summary_message(scanner_data, top_n=10):
    if not scanner_data:
        return "⚠️ No hay datos del escáner disponible."

    mg = scanner_data.get("macro_guard", {})
    summary = scanner_data.get("summary", {})
    ss11_buys = [s for s in scanner_data.get("ss11_signals", []) if s.get("signal") == "BUY"]
    ais11_buys = [s for s in scanner_data.get("ais11_signals", []) if s.get("signal") == "BUY"]

    msg = ["⚡ <b>RESUMEN DEL ESCÁNER EN VIVO (TOP 10 POR ESTRATEGIA)</b>"]
    msg.append(f"<i>Filtro Macro SPY:</i> {mg.get('message', 'N/A')}\n")
    msg.append(f"📊 Total Activos Escaneados: <b>{summary.get('total_scanned', 0)}</b>")
    msg.append(f"🚀 Oportunidades BUY ➔ SS11: <b>{len(ss11_buys)}</b> | AIS11 Multi-IA: <b>{len(ais11_buys)}</b>\n")

    if ss11_buys:
        msg.append(f"<b>🟢 TOP {min(len(ss11_buys), top_n)} OPORTUNIDADES BUY (SS11 Macro):</b>")
        for b in ss11_buys[:top_n]:
            msg.append(f" • <b>{b['ticker']}</b> ({format_price_telegram(b['price'])}) ➔ Var 24h: <b>{b['change_24h']:+.2f}%</b>")
        msg.append("")

    if ais11_buys:
        msg.append(f"<b>🧠 TOP {min(len(ais11_buys), top_n)} OPORTUNIDADES BUY (AIS11 Multi-IA):</b>")
        for b in ais11_buys[:top_n]:
            msg.append(f" • <b>{b['ticker']}</b> ({format_price_telegram(b['price'])}) ➔ Score IA: <b>{b.get('ai_score', 50):.1f}/100</b>")
        msg.append("")

    if not ss11_buys and not ais11_buys:
        msg.append("ℹ️ <i>Sin oportunidades de compra inmediatas. Mercado en espera.</i>")

    return "\n".join(msg)

def format_single_strategy_buys_message(scanner_data, strategy_code="SS11", top_n=15):
    if not scanner_data:
        return "⚠️ No hay datos del escáner disponible."

    mg = scanner_data.get("macro_guard", {})
    if strategy_code.upper() == "SS11":
        signals = [s for s in scanner_data.get("ss11_signals", []) if s.get("signal") == "BUY"]
        title = "🟢 <b>OPORTUNIDADES BUY — SS11 MACRO BASE PURA (Acciones & ETFs)</b>"
    else:
        signals = [s for s in scanner_data.get("ais11_signals", []) if s.get("signal") == "BUY"]
        title = "🧠 <b>OPORTUNIDADES BUY — AIS11 MULTI-IA GPU MASTER</b>"

    msg = [title]
    msg.append(f"<i>Filtro Macro SPY:</i> {mg.get('message', 'N/A')}")
    msg.append(f"📊 Oportunidades Detectadas: <b>{len(signals)}</b>\n")

    if not signals:
        msg.append("ℹ️ <i>Sin oportunidades de compra activas actualmente para esta estrategia.</i>")
        return "\n".join(msg)

    for item in signals[:top_n]:
        tk = item["ticker"]
        cat = item.get("category", "N/A")
        price = item["price"]
        p_str = format_price_telegram(price)
        var_24h = item.get("change_24h", 0.0)

        if strategy_code.upper() == "SS11":
            dist_sma20 = item.get("dist_sma20_pct", 0.0)
            msg.append(f" • <b>{tk}</b> ({cat}) | Precio: {p_str}")
            msg.append(f"   └ Var 24h: <code>{var_24h:+.2f}%</code> | Recup SMA20: <code>{dist_sma20:+.1f}%</code>\n")
        else:
            score = item.get("ai_score", 50.0)
            msg.append(f" • <b>{tk}</b> ({cat}) | Precio: {p_str}")
            msg.append(f"   └ Score IA: <b>{score:.1f}/100</b> | Var 24h: <code>{var_24h:+.2f}%</code>\n")

    return "\n".join(msg)

def format_candidates_message(scanner_data, top_n=6):
    if not scanner_data:
        return "⚠️ No hay datos del escáner disponible."

    ais11_waits = [s for s in scanner_data.get("ais11_signals", []) if s.get("signal") == "WAIT"]
    ais11_waits.sort(key=lambda x: -x.get("ai_score", 0.0))

    msg = ["⏳ <b>TOP PRÓXIMOS CANDIDATOS (EN ESPERA - WAIT)</b>"]
    msg.append("<i>Activos con mayor Score de IA listos para próxima entrada:</i>\n")

    if not ais11_waits:
        msg.append("ℹ️ <i>Sin candidatos en espera disponibles.</i>")
        return "\n".join(msg)

    for idx, item in enumerate(ais11_waits[:top_n], 1):
        tk = item["ticker"]
        cat = item.get("category", "N/A")
        price = item["price"]
        p_str = format_price_telegram(price)
        score = item.get("ai_score", 50.0)
        var_24h = item.get("change_24h", 0.0)

        msg.append(f" • <b>Candidato #{idx}: {tk}</b> ({cat}) | Precio: {p_str}")
        msg.append(f"   └ Score IA: <b>{score:.1f}/100</b> | Var 24h: <code>{var_24h:+.2f}%</code>\n")

    return "\n".join(msg)

# -------------------------------------------------------------------------
# Verificación y Alertas de Notificaciones de Trades
# -------------------------------------------------------------------------
def check_and_notify_trades(scanner_data):
    """
    Compara las señales actuales con el estado previo y envía alertas por Telegram.
    Compuerta de Calidad Institucional (Quality Gate):
    1. Cero alertas de compras ciegas de SS11 (SS11 es Buy&Hold pasivo de benchmark).
    2. Señales de Compra exclusivas de AIS11 con Score >= 58.0 y confirmación sobre SMA20.
    3. Exclusión de activos con historial perdedor crónico (evita altcoins y activos destructivos).
    4. Cooldown Anti-Whipsaw de 12 horas por ticker para eliminar el serrucho intradía.
    5. Macro Crash Guard de SPY para alertas de emergencia a liquidez sistémica.
    6. Formato accionable con Target (+30%), Stop Loss (-15%) y enlace directo a TradingView.
    """
    if not scanner_data:
        return

    saved_state = {}
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, 'r', encoding='utf-8') as f:
                saved_state = json.load(f)
        except Exception as e:
            print(f"[Telegram Bot] Error al leer {STATE_PATH}: {e}")
            saved_state = {}

    is_initial_run = (len(saved_state) == 0)
    current_time = time.time()
    COOLDOWN_SECONDS = 12 * 3600  # 12 horas entre alertas del mismo ticker

    # -------------------------------------------------------------------------
    # 1. Monitoreo del Macro Crash Guard (SPY)
    # -------------------------------------------------------------------------
    macro_guard = scanner_data.get("macro_guard", {})
    is_macro_active = bool(macro_guard.get("is_active", False))
    days_rem = macro_guard.get("days_remaining", 0)
    prev_macro_active = bool(saved_state.get("__macro_crash_active", False))

    if is_macro_active and not prev_macro_active:
        macro_alert = (
            "🚨 <b>ALERTA DE EMERGENCIA MACRO SISTÉMICA</b> 🚨\n\n"
            "⚠️ <b>El índice SPY ha colapsado más de -4.2% en 24 horas.</b>\n"
            "🛡️ <b>Filtro Macro Activado:</b> Se recomienda salida inmediata a liquidez (Cash 100%) para proteger el capital.\n"
            f"⏱️ Período estimado de enfriamiento: <b>{days_rem} días</b>."
        )
        send_telegram_message(macro_alert)
        saved_state["__macro_crash_active"] = True
    elif not is_macro_active and prev_macro_active:
        macro_recovery = (
            "🟢 <b>FIN DE ALERTA MACRO SISTÉMICA</b> 🟢\n\n"
            "✅ El mercado ha estabilizado la volatilidad macro.\n"
            "📈 Se reactiva la búsqueda de nuevas oportunidades de compra."
        )
        send_telegram_message(macro_recovery)
        saved_state["__macro_crash_active"] = False

    # -------------------------------------------------------------------------
    # 2. Compuerta de Calidad de Señales AIS11 (Multi-IA & Momentum Élite)
    # -------------------------------------------------------------------------
    current_state = {}
    buy_alerts = []
    sell_alerts = []

    ais_signals = scanner_data.get("ais11_signals", [])

    for item in ais_signals:
        tk = item["ticker"]
        sig = item.get("signal", "WAIT")
        met = item.get("metrics", {})
        in_pos = bool(met.get("is_currently_in_position", False))
        category = item.get("category", "N/A")
        price = item.get("price", 0.0)
        entry_p = met.get("entry_price") or price
        ai_score = item.get("ai_score", 50.0)
        dist_sma20 = item.get("dist_sma20_pct", 0.0)
        win_rate = met.get("win_rate", 0.0)
        trades_count = met.get("trades_count", 0)
        net_profit = met.get("net_profit_usd", 0.0)

        key = f"AIS11_{tk}"
        prev = saved_state.get(key, {})

        # Estado inicial base sin spam retroactivo
        if prev is None or is_initial_run or not prev:
            current_state[key] = {
                "signal": sig,
                "in_pos": in_pos,
                "last_notified_action": "BUY" if in_pos else "WAIT",
                "last_alert_time": current_time if in_pos else 0,
                "last_price": price
            }
            continue

        prev_in_pos = bool(prev.get("in_pos", False))
        prev_action = prev.get("last_notified_action", "WAIT")
        last_alert_time = prev.get("last_alert_time", 0)

        is_buy_transition = (in_pos or sig == "BUY") and (not prev_in_pos) and (prev_action != "BUY")
        is_sell_transition = prev_in_pos and (not in_pos) and (prev_action == "BUY")

        # COMPUERTA DE CALIDAD PARA COMPRA:
        if is_buy_transition:
            # 1. Anti-Whipsaw Cooldown
            if (current_time - last_alert_time) < COOLDOWN_SECONDS:
                continue

            # 2. Convicción mínima de IA / Momentum
            if ai_score < 58.0:
                continue

            # 3. Filtro de tendencia: no comprar en caída libre bajo la SMA20
            if dist_sma20 < -1.5:
                continue

            # 4. Filtro de historial negativo crónico (descarta altcoins destructoras)
            if trades_count >= 5 and win_rate < 35.0 and net_profit < -1500.0:
                continue

            # Pasa todas las compuertas: SEÑAL VERÍDICA CONFIRMADA
            buy_alerts.append({
                "ticker": tk,
                "category": category,
                "entry_price": entry_p,
                "price": price,
                "ai_score": ai_score,
                "win_rate": win_rate,
                "trades_count": trades_count,
                "dist_sma20": dist_sma20
            })
            current_state[key] = {
                "signal": sig,
                "in_pos": True,
                "last_notified_action": "BUY",
                "last_alert_time": current_time,
                "last_price": price
            }

        elif is_sell_transition:
            # Salida de una posición previamente alertada con BUY
            sell_alerts.append({
                "ticker": tk,
                "category": category,
                "price": price,
                "ai_score": ai_score,
                "entry_price": prev.get("last_price", price)
            })
            current_state[key] = {
                "signal": sig,
                "in_pos": False,
                "last_notified_action": "SELL",
                "last_alert_time": current_time,
                "last_price": price
            }
        else:
            current_state[key] = {
                "signal": sig,
                "in_pos": in_pos,
                "last_notified_action": prev_action,
                "last_alert_time": last_alert_time,
                "last_price": price
            }

    # Preservar historial completo actualizando de forma aditiva
    saved_state.update(current_state)
    try:
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        with open(STATE_PATH, 'w', encoding='utf-8') as f:
            json.dump(saved_state, f, indent=2)
    except Exception as e:
        print(f"[Telegram Bot] Error al persistir estado en {STATE_PATH}: {e}")

    # Si fue la primera inicialización, confirmar vinculación sin spamear
    if is_initial_run and current_state:
        init_msg = (
            "🤖 <b>Monitor de Señales Institucional Inicializado</b>\n\n"
            f"✅ Se calibró el estado base de <b>{len(current_state)}</b> activos.\n"
            "🛡️ <b>Compuerta de Calidad Activada:</b> Solo se emitirán señales de alta convicción (Score >= 58, confirmación de tendencia y control anti-serrucho).\n"
            "🔔 Notificaciones activas en tiempo real."
        )
        send_telegram_message(init_msg)
        return

    total_alerts = len(buy_alerts) + len(sell_alerts)
    if total_alerts == 0:
        return

    # Despacho de Alertas Formateadas con TradingView Links
    if total_alerts <= 3:
        for b in buy_alerts:
            entry_p = b["entry_price"]
            curr_p = b["price"]
            sl_price = entry_p * 0.85  # -15% Stop Loss
            tp_price = entry_p * 1.30  # +30% Target estimado (R:R 1:2)

            tv_ticker = b["ticker"].replace("-USD", "USD").replace("-", "")
            tv_url = f"https://www.tradingview.com/chart/?symbol={tv_ticker}"

            card = (
                "🎯 <b>NUEVA SEÑAL VERÍDICA MULTI-IA (BUY)</b>\n\n"
                f"• <b>Activo:</b> <b><a href=\"{tv_url}\">{b['ticker']}</a></b> ({b['category']})\n"
                "• <b>Estrategia:</b> AIS11 Multi-IA High Convicción\n"
                f"• <b>Score IA / Momentum:</b> <b>{b['ai_score']:.1f}/100</b> 🔥\n"
                f"• <b>Precio de Entrada:</b> <code>{format_price_telegram(entry_p)}</code>\n"
                f"• <b>Stop Loss (-15%):</b> <code>{format_price_telegram(sl_price)}</code>\n"
                f"• <b>Objetivo Estimado (+30%):</b> <code>{format_price_telegram(tp_price)}</code>\n"
                f"• <b>Win Rate Histórico:</b> <code>{b['win_rate']:.1f}%</code> ({b['trades_count']} trades)\n\n"
                f"📊 <a href=\"{tv_url}\">Abrir Gráfico en TradingView</a>"
            )
            send_telegram_message(card)

        for s in sell_alerts:
            curr_p = s["price"]
            ent_p = s.get("entry_price", curr_p)
            ret_pct = ((curr_p / ent_p) - 1.0) * 100.0 if ent_p > 0 else 0.0
            emoji_ret = "🟢" if ret_pct >= 0 else "🔴"

            tv_ticker = s["ticker"].replace("-USD", "USD").replace("-", "")
            tv_url = f"https://www.tradingview.com/chart/?symbol={tv_ticker}"

            card = (
                "🛑 <b>CIERRE DE POSICIÓN / TOMA DE BENEFICIOS (SELL)</b>\n\n"
                f"• <b>Activo:</b> <b><a href=\"{tv_url}\">{s['ticker']}</a></b> ({s['category']})\n"
                f"• <b>Precio de Salida:</b> <code>{format_price_telegram(curr_p)}</code>\n"
                f"• <b>Resultado Estimado:</b> {emoji_ret} <b>{ret_pct:+.2f}%</b>\n"
                f"• <b>Score IA Actual:</b> <code>{s['ai_score']:.1f}/100</code>\n"
                "• <b>Motivo:</b> Debilidad del Momentum / Salida Estratégica\n\n"
                f"📊 <a href=\"{tv_url}\">Ver Gráfico en TradingView</a>"
            )
            send_telegram_message(card)
    else:
        # Modo Digest / Resumen cuando ocurren múltiples movimientos simultáneos
        now_str = datetime.now().strftime("%H:%M:%S")
        lines = [
            f"🔔 <b>REPORTE DE SEÑALES CONFIRMADAS ({now_str})</b>",
            f"<i>Se detectaron {total_alerts} movimientos de alta convicción:</i>\n"
        ]
        if buy_alerts:
            lines.append(f"🟢 <b>Nuevas Compras ({len(buy_alerts)}):</b>")
            for b in buy_alerts:
                lines.append(
                    f"• <b>{b['ticker']}</b> ➔ Ent: <code>{format_price_telegram(b['entry_price'])}</code> "
                    f"(Score: <b>{b['ai_score']:.1f}</b> | SL: <code>{format_price_telegram(b['entry_price'] * 0.85)}</code>)"
                )
            lines.append("")

        if sell_alerts:
            lines.append(f"🔴 <b>Salidas / Cierres ({len(sell_alerts)}):</b>")
            for s in sell_alerts:
                lines.append(
                    f"• <b>{s['ticker']}</b> ➔ Salida: <code>{format_price_telegram(s['price'])}</code> "
                    f"(Score: <code>{s['ai_score']:.1f}</code>)"
                )

        digest_msg = "\n".join(lines)
        send_telegram_message(digest_msg)


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
                                "• /posiciones - Ver posiciones activas agrupadas por estrategia\n"
                                "• /candidatos - Ver Top Próximos Candidatos en Espera (WAIT)\n"
                                "• /top10 - Ver Top 10 mejores oportunidades BUY de ambas estrategias\n"
                                "• /ss11 - Ver oportunidades BUY de la estrategia SS11 Macro únicamente\n"
                                "• /ais11 - Ver oportunidades BUY de la estrategia AIS11 Multi-IA únicamente\n"
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

                                reply = format_active_positions_message(scanner_data, top_n=10)
                                send_telegram_message(reply, chat_id=chat_id)
                            except Exception as e:
                                send_telegram_message(f"❌ Error al consultar posiciones: {e}", chat_id=chat_id)

                        elif cmd in ["/candidatos", "/proximos", "/watchlist", "/candidato"]:
                            send_telegram_message("⏳ Consultando Top Próximos Candidatos en Espera...", chat_id=chat_id)
                            try:
                                cache_file = os.path.join(BASE_DIR, "data", "live_scanner_cache.json")
                                scanner_data = None
                                if os.path.exists(cache_file):
                                    with open(cache_file, "r", encoding="utf-8") as f:
                                        scanner_data = json.load(f)
                                else:
                                    from utils.scanner_engine import run_live_scanner
                                    scanner_data = run_live_scanner()

                                reply = format_candidates_message(scanner_data, top_n=6)
                                send_telegram_message(reply, chat_id=chat_id)
                            except Exception as e:
                                send_telegram_message(f"❌ Error al consultar candidatos: {e}", chat_id=chat_id)

                        elif cmd in ["/top10", "/top", "/oportunidades"]:
                            send_telegram_message("🔍 Consultando Top 10 oportunidades por estrategia...", chat_id=chat_id)
                            try:
                                cache_file = os.path.join(BASE_DIR, "data", "live_scanner_cache.json")
                                scanner_data = None
                                if os.path.exists(cache_file):
                                    with open(cache_file, "r", encoding="utf-8") as f:
                                        scanner_data = json.load(f)
                                else:
                                    from utils.scanner_engine import run_live_scanner
                                    scanner_data = run_live_scanner()

                                summary_msg = format_scanner_summary_message(scanner_data, top_n=10)
                                send_telegram_message(summary_msg, chat_id=chat_id)
                            except Exception as e:
                                send_telegram_message(f"❌ Error al consultar Top 10: {e}", chat_id=chat_id)

                        elif cmd in ["/ss11", "/macro"]:
                            send_telegram_message("🟢 Consultando oportunidades BUY para SS11 Macro...", chat_id=chat_id)
                            try:
                                cache_file = os.path.join(BASE_DIR, "data", "live_scanner_cache.json")
                                scanner_data = None
                                if os.path.exists(cache_file):
                                    with open(cache_file, "r", encoding="utf-8") as f:
                                        scanner_data = json.load(f)
                                else:
                                    from utils.scanner_engine import run_live_scanner
                                    scanner_data = run_live_scanner()

                                msg_ss11 = format_single_strategy_buys_message(scanner_data, strategy_code="SS11", top_n=15)
                                send_telegram_message(msg_ss11, chat_id=chat_id)
                            except Exception as e:
                                send_telegram_message(f"❌ Error al consultar SS11: {e}", chat_id=chat_id)

                        elif cmd in ["/ais11", "/ia"]:
                            send_telegram_message("🧠 Consultando oportunidades BUY para AIS11 Multi-IA...", chat_id=chat_id)
                            try:
                                cache_file = os.path.join(BASE_DIR, "data", "live_scanner_cache.json")
                                scanner_data = None
                                if os.path.exists(cache_file):
                                    with open(cache_file, "r", encoding="utf-8") as f:
                                        scanner_data = json.load(f)
                                else:
                                    from utils.scanner_engine import run_live_scanner
                                    scanner_data = run_live_scanner()

                                msg_ais11 = format_single_strategy_buys_message(scanner_data, strategy_code="AIS11", top_n=15)
                                send_telegram_message(msg_ais11, chat_id=chat_id)
                            except Exception as e:
                                send_telegram_message(f"❌ Error al consultar AIS11: {e}", chat_id=chat_id)

                        elif cmd in ["/actualizar", "/scanner"]:
                            send_telegram_message("🔄 Ejecutando escáner en tiempo real...", chat_id=chat_id)
                            try:
                                from utils.scanner_engine import run_live_scanner
                                scanner_data = run_live_scanner()
                                
                                # Enviar resumen
                                summary_msg = format_scanner_summary_message(scanner_data, top_n=10)
                                send_telegram_message(summary_msg, chat_id=chat_id)
                                
                                # Enviar posiciones activas también
                                pos_msg = format_active_positions_message(scanner_data, top_n=10)
                                send_telegram_message(pos_msg, chat_id=chat_id)
                            except Exception as e:
                                send_telegram_message(f"❌ Error al actualizar el escáner: {e}", chat_id=chat_id)

                        elif cmd == "/help":
                            help_msg = (
                                "ℹ️ <b>AYUDA Y COMANDOS DEL BOT</b>\n\n"
                                "• /posiciones - Posiciones abiertas en cartera por estrategia.\n"
                                "• /top10 - Top 10 oportunidades BUY de cada estrategia juntas.\n"
                                "• /ss11 - Ver oportunidades BUY exclusivamente de SS11 Macro.\n"
                                "• /ais11 - Ver oportunidades BUY exclusivamente de AIS11 Multi-IA.\n"
                                "• /actualizar - Fuerza un escaneo en vivo de todo el mercado.\n"
                                "• /scanner - Resumen del escáner en vivo y estado macro SPY.\n"
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
