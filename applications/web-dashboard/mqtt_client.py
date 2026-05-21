import json
import logging
from typing import Callable

import paho.mqtt.client as mqtt

LOGGER = logging.getLogger(__name__)


class SmartBinMQTTClient:
    def __init__(
        self,
        host: str,
        port: int,
        topic_base: str,
        username: str,
        password: str,
        on_telemetry: Callable[[dict], None],
        on_discard: Callable[[dict], None],
    ) -> None:
        self.host = host
        self.port = port
        self.topic_base = topic_base.rstrip("/")
        self.on_telemetry = on_telemetry
        self.on_discard = on_discard

        self.client = mqtt.Client(client_id="smartbin-dashboard")
        if username:
            self.client.username_pw_set(username=username, password=password)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

    def start(self) -> None:
        LOGGER.info("Conectando ao broker MQTT em %s:%s", self.host, self.port)
        self.client.connect(self.host, self.port, keepalive=60)
        self.client.loop_start()

    def stop(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()

    def _on_connect(self, client: mqtt.Client, userdata, flags, rc) -> None:
        if rc != 0:
            LOGGER.error("Falha ao conectar MQTT (rc=%s)", rc)
            return
        LOGGER.info("Conectado ao MQTT. Inscrevendo topicos.")
        client.subscribe(f"{self.topic_base}/telemetry")
        client.subscribe(f"{self.topic_base}/discard")

    def _on_disconnect(self, client: mqtt.Client, userdata, rc) -> None:
        LOGGER.warning("MQTT desconectado (rc=%s)", rc)

    def _on_message(self, client: mqtt.Client, userdata, msg: mqtt.MQTTMessage) -> None:
        payload_raw = msg.payload.decode("utf-8", errors="ignore")
        try:
            payload = json.loads(payload_raw)
        except json.JSONDecodeError:
            LOGGER.warning("Payload JSON invalido em %s: %s", msg.topic, payload_raw)
            return

        try:
            if msg.topic.endswith("/telemetry"):
                self.on_telemetry(payload)
            elif msg.topic.endswith("/discard"):
                self.on_discard(payload)
        except Exception:
            LOGGER.exception("Erro ao processar payload MQTT (%s)", msg.topic)
