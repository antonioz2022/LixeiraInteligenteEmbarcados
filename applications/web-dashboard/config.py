import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = int(os.getenv("APP_PORT", "5000"))
    app_secret: str = os.getenv("APP_SECRET", "smart-bin-secret")

    mqtt_host: str = os.getenv("MQTT_HOST", "localhost")
    mqtt_port: int = int(os.getenv("MQTT_PORT", "1883"))
    mqtt_username: str = os.getenv("MQTT_USERNAME", "")
    mqtt_password: str = os.getenv("MQTT_PASSWORD", "")
    mqtt_topic_base: str = os.getenv("MQTT_TOPIC_BASE", "smartbin")
    mqtt_auto_start: bool = _get_bool("MQTT_AUTO_START", True)

    alert_threshold: float = float(os.getenv("ALERT_THRESHOLD", "85"))
    alert_reset_threshold: float = float(os.getenv("ALERT_RESET_THRESHOLD", "80"))

    liters_per_oil_discard: float = float(os.getenv("LITERS_PER_OIL_DISCARD", "0.5"))
    kg_per_solid_discard: float = float(os.getenv("KG_PER_SOLID_DISCARD", "0.2"))

    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    debug: bool = _get_bool("FLASK_DEBUG", False)


settings = Settings()
