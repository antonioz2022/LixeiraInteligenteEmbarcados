from typing import Optional

import requests


def send_telegram_alert(bot_token: str, chat_id: str, message: str) -> Optional[str]:
    if not bot_token or not chat_id:
        return "Telegram nao configurado"

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    try:
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
    except requests.RequestException as exc:
        return f"Falha ao enviar alerta Telegram: {exc}"
    return None
