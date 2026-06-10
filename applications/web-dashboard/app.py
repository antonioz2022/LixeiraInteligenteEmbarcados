from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO

from alerts import send_telegram_alert
from config import settings
from mqtt_client import SmartBinMQTTClient
from storage import get_latest_telemetry, get_recent_alerts, get_stats, init_db, insert_alert, insert_discard, insert_telemetry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
LOGGER = logging.getLogger("smartbin.app")

app = Flask(__name__)
app.config["SECRET_KEY"] = settings.app_secret
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

state: dict[str, Any] = {
    "timestamp": None,
    "level_oil": 0.0,
    "level_solid": 0.0,
    "ir_full": False,
}
alert_lock = {"oleo": False, "solido": False}
SOLID_LEVEL_KEYS = ("nivel_solido_pct", "nivel_solido", "solid_level_pct")


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _float(payload: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        if key in payload and payload[key] is not None:
            try:
                return float(payload[key])
            except (TypeError, ValueError):
                continue
    return default


def _bool(payload: dict[str, Any], *keys: str, default: bool = False) -> bool:
    for key in keys:
        if key in payload and payload[key] is not None:
            value = payload[key]
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return bool(value)
            if isinstance(value, str):
                return value.strip().lower() in {"1", "true", "yes", "on", "sim"}
    return default


def _normalize_type(raw: str) -> str:
    value = (raw or "").strip().lower()
    if value in {"oleo", "óleo"}:
        return "oleo"
    if value in {"solido", "sólido"}:
        return "solido"
    return "desconhecido"


def _has_any(payload: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return any(key in payload and payload[key] is not None for key in keys)


def _emit_alert(compartment: str, level: float, message: str) -> None:
    ts = iso_now()
    insert_alert(ts, compartment, level, message)
    socketio.emit(
        "alert",
        {
            "timestamp": ts,
            "compartment": compartment,
            "level": level,
            "message": message,
        },
    )
    error = send_telegram_alert(settings.telegram_bot_token, settings.telegram_chat_id, message)
    if error:
        LOGGER.warning(error)


def _evaluate_thresholds(level_oil: float, level_solid: float) -> None:
    if level_oil >= settings.alert_threshold and not alert_lock["oleo"]:
        alert_lock["oleo"] = True
        _emit_alert("oleo", level_oil, f"Alerta: compartimento de oleo em {level_oil:.1f}%")
    elif level_oil <= settings.alert_reset_threshold:
        alert_lock["oleo"] = False

    if level_solid >= settings.alert_threshold and not alert_lock["solido"]:
        alert_lock["solido"] = True
        _emit_alert("solido", level_solid, f"Alerta: compartimento de solido em {level_solid:.1f}%")
    elif level_solid <= settings.alert_reset_threshold:
        alert_lock["solido"] = False


def on_telemetry(payload: dict[str, Any]) -> None:
    level_oil = _float(payload, "nivel_oleo_pct", "nivel_oleo", "oil_level_pct")
    ir_full = _bool(payload, "ir_cheio", "infrared_full", "cheio_ir")
    if _has_any(payload, SOLID_LEVEL_KEYS):
        level_solid = _float(payload, *SOLID_LEVEL_KEYS)
    else:
        # Se o grupo optar por enviar apenas status do IR para o compartimento sólido,
        # convertemos para uma leitura de nível simplificada no dashboard.
        level_solid = 100.0 if ir_full else 0.0
    ts = payload.get("timestamp") or iso_now()

    state.update(
        {
            "timestamp": ts,
            "level_oil": round(level_oil, 2),
            "level_solid": round(level_solid, 2),
            "ir_full": ir_full,
        }
    )
    insert_telemetry(ts, level_oil, level_solid, ir_full, payload)
    _evaluate_thresholds(level_oil, level_solid)
    socketio.emit("telemetry", state)


def on_discard(payload: dict[str, Any]) -> None:
    waste_type = _normalize_type(str(payload.get("tipo") or payload.get("type") or "desconhecido"))
    qty_raw = _float(payload, "quantidade", "quantity", default=1)
    try:
        qty = max(int(qty_raw), 1)
    except (TypeError, ValueError):
        qty = 1
    ts = payload.get("timestamp") or iso_now()

    insert_discard(ts, waste_type, qty, payload)
    socketio.emit("discard", {"timestamp": ts, "waste_type": waste_type, "quantity": qty})
    socketio.emit("stats", _stats_payload(days=7))


def _stats_payload(days: int = 7) -> dict[str, Any]:
    data = get_stats(days=days)
    total_oil = data["total_oil_discards"]
    total_solid = data["total_solid_discards"]
    data["total_liters_oil"] = round(total_oil * settings.liters_per_oil_discard, 2)
    data["total_kg_solid"] = round(total_solid * settings.kg_per_solid_discard, 2)
    return data


def bootstrap_state() -> None:
    latest = get_latest_telemetry()
    if latest is None:
        return
    state.update(
        {
            "timestamp": latest["timestamp"],
            "level_oil": latest["level_oil"],
            "level_solid": latest["level_solid"],
            "ir_full": latest["ir_full"],
        }
    )


init_db()
bootstrap_state()

mqtt_client = SmartBinMQTTClient(
    host=settings.mqtt_host,
    port=settings.mqtt_port,
    topic_base=settings.mqtt_topic_base,
    username=settings.mqtt_username,
    password=settings.mqtt_password,
    on_telemetry=on_telemetry,
    on_discard=on_discard,
)

if settings.mqtt_auto_start:
    try:
        mqtt_client.start()
    except Exception:
        LOGGER.exception("Nao foi possivel iniciar cliente MQTT")
else:
    LOGGER.info("Inicializacao MQTT desativada por configuracao (MQTT_AUTO_START=false)")


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify({"ok": True, "timestamp": iso_now()})


@app.get("/api/state")
def api_state():
    return jsonify(state)


@app.get("/api/stats")
def api_stats():
    days = request.args.get("days", default=7, type=int)
    return jsonify(_stats_payload(days=days))


@app.get("/api/alerts")
def api_alerts():
    limit = request.args.get("limit", default=20, type=int)
    return jsonify({"items": get_recent_alerts(limit=max(1, min(limit, 200)))})


if __name__ == "__main__":
    socketio.run(
        app,
        host=settings.app_host,
        port=settings.app_port,
        debug=settings.debug,
        allow_unsafe_werkzeug=True,
    )
