# -*- coding: utf-8 -*-
"""
Bot de Telegram: cartera virtual SS11/AIS11 + comandos.

Push automático = solo transiciones reales de posición (COMPRA/VENTA CONFIRMADA).
Comandos de consulta = OPORTUNIDAD / CANDIDATO (nunca se confunden con compras).
"""

import os
import sys
import json
import time
import urllib.request
import threading
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
ENV_PATH = os.path.join(BASE_DIR, '.env')
CONFIG_PATH = os.path.join(BASE_DIR, 'data', 'telegram_config.json')
STATE_PATH = os.path.join(BASE_DIR, 'data', 'telegram_state.json')
HEALTH_PATH = os.path.join(BASE_DIR, 'data', 'telegram_health.json')

os.makedirs(os.path.join(BASE_DIR, 'data'), exist_ok=True)

# Cooldown solo anti-spam de re-alerta BUY tras un SELL (no bloquea estado real)
BUY_REALERT_COOLDOWN_SEC = int(os.environ.get("TELEGRAM_BUY_COOLDOWN_HOURS", "12")) * 3600
AI_STALE_DAYS = float(os.environ.get("AI_STALE_DAYS", "2"))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


def load_dotenv_file():
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
                    val = val.strip("'\"")
                    os.environ[key] = val
    except Exception as e:
        print(f"[Telegram Bot] Error al cargar .env: {e}")


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
            json.dump({
                "chat_id": chat_id,
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }, f, indent=2)
    except Exception as e:
        print(f"[Telegram Bot] Error al guardar chat_id: {e}")


def is_dry_run():
    return os.environ.get("TELEGRAM_DRY_RUN", "").strip().lower() in ("1", "true", "yes")


def send_telegram_message(text, chat_id=None, parse_mode="HTML"):
    if is_dry_run():
        print(f"[Telegram Bot][DRY_RUN] {text[:200]}...")
        return True

    token = get_bot_token()
    if not token:
        print("[Telegram Bot] Advertencia: TELEGRAM_BOT_TOKEN no está configurado.")
        return False

    target_chat = chat_id or get_saved_chat_id()
    if not target_chat:
        print("[Telegram Bot] Advertencia: No hay TELEGRAM_CHAT_ID. Envíe /start al bot.")
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


def _tv_url(ticker):
    tv_ticker = ticker.replace("-USD", "USD").replace("-", "")
    return f"https://www.tradingview.com/chart/?symbol={tv_ticker}"


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


def _load_scanner_cache():
    cache_file = os.path.join(BASE_DIR, "data", "live_scanner_cache.json")
    if os.path.exists(cache_file):
        with open(cache_file, "r", encoding="utf-8") as f:
            return json.load(f)
    from utils.scanner_engine import run_live_scanner
    return run_live_scanner()


def _save_health(payload):
    try:
        with open(HEALTH_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except Exception:
        pass


def format_active_positions_message(scanner_data, top_n=15):
    if not scanner_data:
        return "⚠️ No hay datos del escáner disponible."

    ss11_active = []
    for item in scanner_data.get("ss11_signals", []):
        met = item.get("metrics", {})
        if met.get("is_currently_in_position"):
            ss11_active.append({
                "ticker": item["ticker"],
                "price": item["price"],
                "entry_price": met.get("entry_price", item["price"]),
                "pnl_pct": met.get("floating_pnl_pct", 0.0),
                "dist_sl": item.get("dist_sl_pct", 0.0),
                "signal": item.get("signal", "HOLD"),
            })

    ais11_active = []
    for item in scanner_data.get("ais11_signals", []):
        met = item.get("metrics", {})
        if met.get("is_currently_in_position") and item.get("notify_eligible", item.get("has_ai", True)):
            ais11_active.append({
                "ticker": item["ticker"],
                "price": item["price"],
                "entry_price": met.get("entry_price", item["price"]),
                "pnl_pct": met.get("floating_pnl_pct", 0.0),
                "ai_score": item.get("ai_score", 50.0),
                "signal": item.get("signal", "HOLD"),
            })

    total_active = len(ss11_active) + len(ais11_active)
    if total_active == 0:
        return (
            "💼 <b>CARTERA VIRTUAL — POSICIONES ABIERTAS</b>\n\n"
            "ℹ️ No hay posiciones abiertas en SS11 ni AIS11.\n"
            "<i>Esto es lo que el sistema considera COMPRADO ahora.</i>"
        )

    msg = [
        f"💼 <b>CARTERA VIRTUAL — POSICIONES ABIERTAS ({total_active})</b>",
        f"<i>Actualizado: {scanner_data.get('timestamp', datetime.now().strftime('%d/%m/%Y %H:%M:%S'))}</i>",
        "<i>Estas son compras confirmadas (HOLD). No confundir con /oportunidades.</i>\n",
    ]

    if ss11_active:
        msg.append(f"<b>🟢 SS11 Macro ({len(ss11_active)} abiertas — mostrando {min(len(ss11_active), top_n)}):</b>")
        for pos in ss11_active[:top_n]:
            pnl_icon = "🟢" if pos["pnl_pct"] >= 0 else "🔴"
            msg.append(
                f" • <b>{pos['ticker']}</b> | {format_price_telegram(pos['price'])} | "
                f"Entr: {format_price_telegram(pos['entry_price'])} | "
                f"PnL: {pnl_icon} <b>{pos['pnl_pct']:+.2f}%</b> | {pos['signal']}"
            )
        msg.append("")

    if ais11_active:
        msg.append(f"<b>🧠 AIS11 Multi-IA ({len(ais11_active)} abiertas — mostrando {min(len(ais11_active), top_n)}):</b>")
        for pos in ais11_active[:top_n]:
            pnl_icon = "🟢" if pos["pnl_pct"] >= 0 else "🔴"
            msg.append(
                f" • <b>{pos['ticker']}</b> | {format_price_telegram(pos['price'])} | "
                f"Entr: {format_price_telegram(pos['entry_price'])} | "
                f"PnL: {pnl_icon} <b>{pos['pnl_pct']:+.2f}%</b> | Score: <code>{pos['ai_score']}</code>"
            )
        msg.append("")

    return "\n".join(msg)


def format_portfolio_message(scanner_data):
    """Resumen compacto de cartera (alias /cartera)."""
    return format_active_positions_message(scanner_data, top_n=20)


def format_scanner_summary_message(scanner_data, top_n=10):
    if not scanner_data:
        return "⚠️ No hay datos del escáner disponible."

    mg = scanner_data.get("macro_guard", {})
    summary = scanner_data.get("summary", {})
    ss11_buys = [s for s in scanner_data.get("ss11_signals", []) if s.get("signal") == "BUY"]
    ais11_buys = [
        s for s in scanner_data.get("ais11_signals", [])
        if s.get("signal") == "BUY" and s.get("notify_eligible", s.get("has_ai", True))
    ]

    msg = [
        "📋 <b>OPORTUNIDADES (consulta — NO son compras ejecutadas)</b>",
        f"<i>Filtro Macro SPY:</i> {mg.get('message', 'N/A')}",
        f"📊 Escaneados: <b>{summary.get('total_scanned', 0)}</b> | "
        f"Con IA: <b>{summary.get('with_ai', 0)}</b> | "
        f"En cartera SS11/AIS11: <b>{summary.get('ss11_in_position', 0)}</b>/"
        f"<b>{summary.get('ais11_in_position', 0)}</b>\n",
        f"🔎 Señales BUY (posible entrada): SS11 <b>{len(ss11_buys)}</b> | AIS11 <b>{len(ais11_buys)}</b>\n",
    ]

    if ss11_buys:
        msg.append(f"<b>🟢 TOP OPORTUNIDADES SS11 (no confundir con cartera):</b>")
        for b in ss11_buys[:top_n]:
            msg.append(
                f" • <b>{b['ticker']}</b> ({format_price_telegram(b['price'])}) "
                f"Var24h: <b>{b['change_24h']:+.2f}%</b>"
            )
        msg.append("")

    if ais11_buys:
        msg.append(f"<b>🧠 TOP OPORTUNIDADES AIS11 (no confundir con cartera):</b>")
        for b in ais11_buys[:top_n]:
            msg.append(
                f" • <b>{b['ticker']}</b> ({format_price_telegram(b['price'])}) "
                f"Score: <b>{b.get('ai_score', 50):.1f}</b>"
            )
        msg.append("")

    if not ss11_buys and not ais11_buys:
        msg.append("ℹ️ <i>Sin oportunidades BUY ahora. Revisá /posiciones para lo ya comprado.</i>")

    msg.append("\n💡 Push automático = solo COMPRA/VENTA CONFIRMADA. Usá /posiciones para cartera.")
    return "\n".join(msg)


def format_single_strategy_buys_message(scanner_data, strategy_code="SS11", top_n=15):
    if not scanner_data:
        return "⚠️ No hay datos del escáner disponible."

    mg = scanner_data.get("macro_guard", {})
    if strategy_code.upper() == "SS11":
        signals = [s for s in scanner_data.get("ss11_signals", []) if s.get("signal") == "BUY"]
        title = "🟢 <b>OPORTUNIDADES — SS11</b>\n<i>Consulta: NO son compras confirmadas. Ver /posiciones.</i>"
    else:
        signals = [
            s for s in scanner_data.get("ais11_signals", [])
            if s.get("signal") == "BUY" and s.get("notify_eligible", s.get("has_ai", True))
        ]
        title = "🧠 <b>OPORTUNIDADES — AIS11</b>\n<i>Consulta: NO son compras confirmadas. Ver /posiciones.</i>"

    msg = [title, f"<i>Filtro Macro:</i> {mg.get('message', 'N/A')}", f"Detectadas: <b>{len(signals)}</b>\n"]
    if not signals:
        msg.append("ℹ️ <i>Sin oportunidades BUY para esta estrategia.</i>")
        return "\n".join(msg)

    for item in signals[:top_n]:
        p_str = format_price_telegram(item["price"])
        if strategy_code.upper() == "SS11":
            msg.append(
                f" • <b>{item['ticker']}</b> | {p_str} | "
                f"Var24h <code>{item.get('change_24h', 0):+.2f}%</code>"
            )
        else:
            msg.append(
                f" • <b>{item['ticker']}</b> | {p_str} | "
                f"Score <b>{item.get('ai_score', 50):.1f}</b>"
            )
    return "\n".join(msg)


def format_candidates_message(scanner_data, top_n=6):
    if not scanner_data:
        return "⚠️ No hay datos del escáner disponible."

    ais11_waits = [
        s for s in scanner_data.get("ais11_signals", [])
        if s.get("signal") == "WAIT" and s.get("notify_eligible", s.get("has_ai", True))
    ]
    ais11_waits.sort(key=lambda x: -(x.get("ai_score") or 0.0))

    params = scanner_data.get("ais11_params") or {}
    entry_th = params.get("entry_th", 55)

    msg = [
        "⏳ <b>CANDIDATOS (WAIT — aún no comprados)</b>",
        f"<i>Cerca de entrada AIS11 (score &gt; {entry_th}). No son compras.</i>\n",
    ]
    if not ais11_waits:
        msg.append("ℹ️ <i>Sin candidatos en espera.</i>")
        return "\n".join(msg)

    for idx, item in enumerate(ais11_waits[:top_n], 1):
        msg.append(
            f" • <b>#{idx} {item['ticker']}</b> | {format_price_telegram(item['price'])} | "
            f"Score <b>{item.get('ai_score', 0):.1f}</b>"
        )
    return "\n".join(msg)


def format_health_message(scanner_data=None):
    token_ok = bool(get_bot_token())
    chat_ok = bool(get_saved_chat_id())
    ai_age = None
    last_scan = "N/A"
    macro = "N/A"
    params_txt = "N/A"
    summary = {}

    try:
        from utils.scanner_engine import get_ai_signals_age_days
        ai_age = get_ai_signals_age_days()
    except Exception:
        pass

    if scanner_data is None:
        cache_file = os.path.join(BASE_DIR, "data", "live_scanner_cache.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    scanner_data = json.load(f)
            except Exception:
                scanner_data = None

    if scanner_data:
        last_scan = scanner_data.get("timestamp", "N/A")
        macro = scanner_data.get("macro_guard", {}).get("message", "N/A")
        p = scanner_data.get("ais11_params") or {}
        if p:
            params_txt = f"entry={p.get('entry_th')} / exit={p.get('exit_th')}"
        summary = scanner_data.get("summary") or {}
        if scanner_data.get("ai_signals_age_days") is not None:
            ai_age = scanner_data.get("ai_signals_age_days")

    stale = ai_age is not None and ai_age > AI_STALE_DAYS
    age_txt = "desconocida" if ai_age is None else f"{ai_age:.1f} días"
    stale_line = "⚠️ Señales IA DESACTUALIZADAS" if stale else "✅ Señales IA OK"

    return "\n".join([
        "🩺 <b>SALUD DEL MONITOR</b>",
        f"• Token Telegram: {'✅' if token_ok else '❌'}",
        f"• Chat ID: {'✅' if chat_ok else '❌'}",
        f"• Dry-run: {'ON' if is_dry_run() else 'OFF'}",
        f"• Último escaneo: <code>{last_scan}</code>",
        f"• AIS11 params: <code>{params_txt}</code>",
        f"• Edad señales IA: <b>{age_txt}</b> — {stale_line}",
        f"• Macro: {macro}",
        f"• Cartera SS11/AIS11: <b>{summary.get('ss11_in_position', '?')}</b> / "
        f"<b>{summary.get('ais11_in_position', '?')}</b>",
        f"• Con IA / sin IA: <b>{summary.get('with_ai', '?')}</b> / "
        f"<b>{summary.get('without_ai', '?')}</b>",
    ])


def _format_buy_card(alert):
    entry_p = alert["entry_price"]
    sl_price = entry_p * 0.85
    tv_url = _tv_url(alert["ticker"])
    strat = alert["strategy"]
    score_line = ""
    if strat == "AIS11" and alert.get("ai_score") is not None:
        score_line = f"• <b>Score IA:</b> <code>{alert['ai_score']:.1f}/100</code>\n"

    return (
        f"🟢 <b>COMPRA CONFIRMADA — {strat}</b>\n\n"
        f"• <b>Activo:</b> <a href=\"{tv_url}\">{alert['ticker']}</a> ({alert['category']})\n"
        f"{score_line}"
        f"• <b>Precio entrada:</b> <code>{format_price_telegram(entry_p)}</code>\n"
        f"• <b>Stop Loss (-15%):</b> <code>{format_price_telegram(sl_price)}</code>\n"
        f"• <b>Estado:</b> queda <b>COMPRADA</b> hasta VENTA CONFIRMADA\n\n"
        f"📊 <a href=\"{tv_url}\">TradingView</a>"
    )


def _format_sell_card(alert):
    curr_p = alert["price"]
    ent_p = alert.get("entry_price") or curr_p
    ret_pct = ((curr_p / ent_p) - 1.0) * 100.0 if ent_p else 0.0
    emoji_ret = "🟢" if ret_pct >= 0 else "🔴"
    tv_url = _tv_url(alert["ticker"])
    reason = alert.get("exit_reason") or "Salida de Estrategia"
    score_line = ""
    if alert.get("strategy") == "AIS11" and alert.get("ai_score") is not None:
        score_line = f"• <b>Score IA:</b> <code>{alert['ai_score']:.1f}/100</code>\n"

    return (
        f"🔴 <b>VENTA CONFIRMADA — {alert['strategy']}</b>\n\n"
        f"• <b>Activo:</b> <a href=\"{tv_url}\">{alert['ticker']}</a> ({alert['category']})\n"
        f"• <b>Precio salida:</b> <code>{format_price_telegram(curr_p)}</code>\n"
        f"• <b>Resultado:</b> {emoji_ret} <b>{ret_pct:+.2f}%</b>\n"
        f"{score_line}"
        f"• <b>Motivo:</b> {reason}\n\n"
        f"📊 <a href=\"{tv_url}\">TradingView</a>"
    )


def _process_strategy_transitions(items, strategy, saved_state, current_time, is_initial_run):
    """
    Detecta solo cambios de is_currently_in_position.
    Siempre persiste estado (sin limbos). Cooldown solo suprime re-alerta BUY tras SELL.
    """
    buy_alerts = []
    sell_alerts = []
    current_state = {}

    for item in items:
        if strategy == "AIS11" and not item.get("notify_eligible", item.get("has_ai", False)):
            continue
        if item.get("signal") == "NO_AI":
            continue

        tk = item["ticker"]
        met = item.get("metrics", {})
        in_pos = bool(met.get("is_currently_in_position", False))
        key = f"{strategy}_{tk}"
        prev = saved_state.get(key) or {}

        base = {
            "signal": item.get("signal", "WAIT"),
            "in_pos": in_pos,
            "last_price": item.get("price", 0.0),
            "entry_price": met.get("entry_price"),
            "ai_score": item.get("ai_score"),
            "strategy": strategy,
        }

        if is_initial_run or not prev:
            current_state[key] = {
                **base,
                "last_notified_action": "BUY" if in_pos else "WAIT",
                "last_alert_time": current_time if in_pos else 0,
                "last_sell_time": 0,
            }
            continue

        prev_in_pos = bool(prev.get("in_pos", False))
        last_alert_time = float(prev.get("last_alert_time", 0) or 0)
        last_sell_time = float(prev.get("last_sell_time", 0) or 0)
        prev_action = prev.get("last_notified_action", "WAIT")

        # Fuente de verdad: posición, no el label BUY del día
        is_buy_transition = in_pos and not prev_in_pos
        is_sell_transition = (not in_pos) and prev_in_pos

        if is_buy_transition:
            suppress = (current_time - last_sell_time) < BUY_REALERT_COOLDOWN_SEC if last_sell_time else False
            current_state[key] = {
                **base,
                "last_notified_action": "BUY",
                "last_alert_time": current_time,
                "last_sell_time": last_sell_time,
            }
            if not suppress:
                buy_alerts.append({
                    "ticker": tk,
                    "category": item.get("category", "N/A"),
                    "entry_price": met.get("entry_price") or item.get("price", 0.0),
                    "price": item.get("price", 0.0),
                    "ai_score": item.get("ai_score"),
                    "strategy": strategy,
                })
            else:
                print(f"[Telegram Bot] BUY {strategy} {tk} en cartera pero alerta en cooldown post-SELL")

        elif is_sell_transition:
            current_state[key] = {
                **base,
                "last_notified_action": "SELL",
                "last_alert_time": current_time,
                "last_sell_time": current_time,
            }
            sell_alerts.append({
                "ticker": tk,
                "category": item.get("category", "N/A"),
                "price": item.get("price", 0.0),
                "entry_price": prev.get("entry_price") or prev.get("last_price") or item.get("price", 0.0),
                "ai_score": item.get("ai_score"),
                "strategy": strategy,
                "exit_reason": item.get("exit_reason") or "Salida de Estrategia",
            })
        else:
            current_state[key] = {
                **base,
                "last_notified_action": prev_action,
                "last_alert_time": last_alert_time,
                "last_sell_time": last_sell_time,
            }

    return buy_alerts, sell_alerts, current_state


def check_and_notify_trades(scanner_data):
    """
    Push solo por transiciones de cartera (in_pos).
    SS11 + AIS11. Sin quality gates que contradigan la estrategia.
    """
    if not scanner_data:
        return {"buys": 0, "sells": 0, "initial": False}

    saved_state = {}
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, 'r', encoding='utf-8') as f:
                saved_state = json.load(f)
        except Exception as e:
            print(f"[Telegram Bot] Error al leer {STATE_PATH}: {e}")
            saved_state = {}

    # Migración: estado vacío o solo macro → baseline sin spam
    position_keys = [k for k in saved_state.keys() if not k.startswith("__")]
    is_initial_run = len(position_keys) == 0
    current_time = time.time()

    # Macro
    macro_guard = scanner_data.get("macro_guard", {})
    is_macro_active = bool(macro_guard.get("is_active", False))
    days_rem = macro_guard.get("days_remaining", 0)
    prev_macro_active = bool(saved_state.get("__macro_crash_active", False))

    if is_macro_active and not prev_macro_active:
        send_telegram_message(
            "🚨 <b>ALERTA MACRO SISTÉMICA</b>\n\n"
            "SPY &lt; −4.2% en 24h. Filtro Macro activo → salida a liquidez recomendada.\n"
            f"Enfriamiento estimado: <b>{days_rem} días</b>."
        )
        saved_state["__macro_crash_active"] = True
    elif not is_macro_active and prev_macro_active:
        send_telegram_message(
            "🟢 <b>FIN ALERTA MACRO</b>\n\n"
            "Mercado estabilizado. Se reactivan entradas según SS11/AIS11."
        )
        saved_state["__macro_crash_active"] = False

    # Aviso IA stale (como máximo 1 vez cada 12h)
    ai_age = scanner_data.get("ai_signals_age_days")
    last_stale_warn = float(saved_state.get("__last_ai_stale_warn", 0) or 0)
    if ai_age is not None and ai_age > AI_STALE_DAYS and (current_time - last_stale_warn) > 12 * 3600:
        send_telegram_message(
            f"⚠️ <b>Señales IA desactualizadas</b> (~{ai_age:.1f} días).\n"
            "AIS11 puede degradarse hasta el próximo update. Usá /salud."
        )
        saved_state["__last_ai_stale_warn"] = current_time

    buy_alerts = []
    sell_alerts = []
    current_state = {}

    b1, s1, st1 = _process_strategy_transitions(
        scanner_data.get("ss11_signals", []), "SS11", saved_state, current_time, is_initial_run
    )
    b2, s2, st2 = _process_strategy_transitions(
        scanner_data.get("ais11_signals", []), "AIS11", saved_state, current_time, is_initial_run
    )
    buy_alerts.extend(b1 + b2)
    sell_alerts.extend(s1 + s2)
    current_state.update(st1)
    current_state.update(st2)

    saved_state.update(current_state)
    saved_state["__last_scan"] = scanner_data.get("timestamp")
    saved_state["__updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        with open(STATE_PATH, 'w', encoding='utf-8') as f:
            json.dump(saved_state, f, indent=2)
    except Exception as e:
        print(f"[Telegram Bot] Error al persistir estado: {e}")

    _save_health({
        "updated_at": saved_state["__updated_at"],
        "last_scan": saved_state.get("__last_scan"),
        "buys_queued": len(buy_alerts),
        "sells_queued": len(sell_alerts),
        "initial_run": is_initial_run,
        "positions_tracked": len(position_keys) if not is_initial_run else len(current_state),
    })

    if is_initial_run:
        send_telegram_message(
            "🤖 <b>Monitor de cartera inicializado</b>\n\n"
            f"✅ Baseline de <b>{len(current_state)}</b> activos (sin spam de compras ya abiertas).\n"
            "🟢 Push = <b>COMPRA CONFIRMADA</b> / 🔴 <b>VENTA CONFIRMADA</b> (SS11 + AIS11).\n"
            "📋 /posiciones = lo comprado | /ss11 /ais11 = oportunidades (consulta).\n"
            "🩺 /salud = estado del sistema."
        )
        print(f"[Telegram Bot] Baseline inicial: {len(current_state)} claves")
        return {"buys": 0, "sells": 0, "initial": True}

    total_alerts = len(buy_alerts) + len(sell_alerts)
    print(
        f"[Telegram Bot] Transiciones: BUY={len(buy_alerts)} SELL={len(sell_alerts)} "
        f"(tracked={len(current_state)})"
    )
    if total_alerts == 0:
        return {"buys": 0, "sells": 0, "initial": False}

    if total_alerts <= 4:
        for b in buy_alerts:
            send_telegram_message(_format_buy_card(b))
        for s in sell_alerts:
            send_telegram_message(_format_sell_card(s))
    else:
        lines = [
            f"🔔 <b>REPORTE DE CARTERA</b> ({datetime.now().strftime('%H:%M:%S')})",
            f"<i>{total_alerts} cambios de posición (no son listas de oportunidades):</i>\n",
        ]
        if buy_alerts:
            lines.append(f"🟢 <b>COMPRAS CONFIRMADAS ({len(buy_alerts)}):</b>")
            for b in buy_alerts:
                score = f" score={b['ai_score']:.1f}" if b.get("ai_score") is not None else ""
                lines.append(
                    f"• <b>{b['strategy']}</b> {b['ticker']} @ "
                    f"{format_price_telegram(b['entry_price'])}{score}"
                )
            lines.append("")
        if sell_alerts:
            lines.append(f"🔴 <b>VENTAS CONFIRMADAS ({len(sell_alerts)}):</b>")
            for s in sell_alerts:
                lines.append(
                    f"• <b>{s['strategy']}</b> {s['ticker']} @ "
                    f"{format_price_telegram(s['price'])} ({s.get('exit_reason', '')})"
                )
        send_telegram_message("\n".join(lines))

    return {"buys": len(buy_alerts), "sells": len(sell_alerts), "initial": False}


HELP_TEXT = (
    "ℹ️ <b>COMANDOS</b>\n\n"
    "<b>Cartera (lo comprado):</b>\n"
    "• /posiciones o /cartera — posiciones abiertas SS11/AIS11\n\n"
    "<b>Consulta (NO son compras):</b>\n"
    "• /oportunidades o /top10 — posibles entradas BUY\n"
    "• /ss11 — oportunidades SS11\n"
    "• /ais11 — oportunidades AIS11\n"
    "• /candidatos — WAIT cerca de entrada\n\n"
    "<b>Sistema:</b>\n"
    "• /salud — token, IA, último scan, params\n"
    "• /actualizar — forzar escaneo + resumen\n"
    "• /start — registrar chat para push\n\n"
    "Push automático = solo COMPRA/VENTA CONFIRMADA."
)


def start_telegram_bot_listener():
    token = get_bot_token()
    if not token:
        print("[Telegram Bot] Bot no iniciado: Falta TELEGRAM_BOT_TOKEN en .env")
        return

    print("[Telegram Bot] Bot activo (cartera SS11/AIS11)...")
    offset = None

    while True:
        try:
            url = f"https://api.telegram.org/bot{token}/getUpdates?timeout=20"
            if offset:
                url += f"&offset={offset}"

            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=25) as resp:
                res = json.loads(resp.read().decode('utf-8'))
                if not res.get("ok"):
                    continue
                for update in res.get("result", []):
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
                            print(f"[Telegram Bot] Acceso bloqueado Chat ID: {chat_id}")
                            continue
                    else:
                        save_chat_id(chat_id)

                    cmd = text.split()[0].lower().split("@")[0]

                    if cmd in ("/start", "/help"):
                        if cmd == "/start":
                            send_telegram_message(
                                "👋 <b>Monitor de cartera SS11 + AIS11</b>\n\n"
                                "Chat registrado para push de COMPRA/VENTA CONFIRMADA.\n\n"
                                + HELP_TEXT,
                                chat_id=chat_id,
                            )
                        else:
                            send_telegram_message(HELP_TEXT, chat_id=chat_id)

                    elif cmd in ("/posiciones", "/activas", "/cartera"):
                        send_telegram_message("⏳ Leyendo cartera virtual...", chat_id=chat_id)
                        try:
                            send_telegram_message(
                                format_portfolio_message(_load_scanner_cache()),
                                chat_id=chat_id,
                            )
                        except Exception as e:
                            send_telegram_message(f"❌ Error: {e}", chat_id=chat_id)

                    elif cmd in ("/candidatos", "/proximos", "/watchlist", "/candidato"):
                        try:
                            send_telegram_message(
                                format_candidates_message(_load_scanner_cache(), top_n=6),
                                chat_id=chat_id,
                            )
                        except Exception as e:
                            send_telegram_message(f"❌ Error: {e}", chat_id=chat_id)

                    elif cmd in ("/top10", "/top", "/oportunidades", "/scanner"):
                        try:
                            send_telegram_message(
                                format_scanner_summary_message(_load_scanner_cache(), top_n=10),
                                chat_id=chat_id,
                            )
                        except Exception as e:
                            send_telegram_message(f"❌ Error: {e}", chat_id=chat_id)

                    elif cmd in ("/ss11", "/macro"):
                        try:
                            send_telegram_message(
                                format_single_strategy_buys_message(
                                    _load_scanner_cache(), strategy_code="SS11", top_n=15
                                ),
                                chat_id=chat_id,
                            )
                        except Exception as e:
                            send_telegram_message(f"❌ Error: {e}", chat_id=chat_id)

                    elif cmd in ("/ais11", "/ia"):
                        try:
                            send_telegram_message(
                                format_single_strategy_buys_message(
                                    _load_scanner_cache(), strategy_code="AIS11", top_n=15
                                ),
                                chat_id=chat_id,
                            )
                        except Exception as e:
                            send_telegram_message(f"❌ Error: {e}", chat_id=chat_id)

                    elif cmd in ("/salud", "/health", "/status"):
                        try:
                            send_telegram_message(format_health_message(), chat_id=chat_id)
                        except Exception as e:
                            send_telegram_message(f"❌ Error: {e}", chat_id=chat_id)

                    elif cmd in ("/actualizar", "/refresh"):
                        send_telegram_message("🔄 Escaneando mercado...", chat_id=chat_id)
                        try:
                            from utils.scanner_engine import run_live_scanner
                            scanner_data = run_live_scanner()
                            send_telegram_message(
                                format_scanner_summary_message(scanner_data, top_n=10),
                                chat_id=chat_id,
                            )
                            send_telegram_message(
                                format_active_positions_message(scanner_data, top_n=10),
                                chat_id=chat_id,
                            )
                            send_telegram_message(format_health_message(scanner_data), chat_id=chat_id)
                        except Exception as e:
                            send_telegram_message(f"❌ Error: {e}", chat_id=chat_id)

        except Exception:
            time.sleep(5)


def launch_bot_background():
    t = threading.Thread(target=start_telegram_bot_listener, daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    print("Probando bot de Telegram localmente...")
    token = get_bot_token()
    cid = get_saved_chat_id()
    print(f"Token: {bool(token)}, Chat ID: {cid or 'Ninguno'}")
    if token and cid and not is_dry_run():
        send_telegram_message("🤖 <b>Bot OK</b> — test de notificación.")
    start_telegram_bot_listener()
