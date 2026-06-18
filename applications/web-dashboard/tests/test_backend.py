import os
import sqlite3
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

TEST_DIR = Path(__file__).resolve().parent
DB_FILE = TEST_DIR / "test_smartbin.sqlite3"
if DB_FILE.exists():
    DB_FILE.unlink()

os.environ["SMARTBIN_DB_PATH"] = str(DB_FILE)
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["TELEGRAM_CHAT_ID"] = ""
os.environ["MQTT_AUTO_START"] = "false"

import app as smartbin_app  # noqa: E402
from mqtt_client import SmartBinMQTTClient  # noqa: E402

import paho.mqtt.client as mqtt  # noqa: E402


def _firmware_telemetry_message(topic: str, *, oil: float, solid: float, ir: bool) -> mqtt.MQTTMessage:
    """Monta uma MQTTMessage identica a que o ESP32 publica em main.cpp.

    O firmware emite: {"nivel_oleo_pct":..,"nivel_solido_pct":..,"ir_cheio":bool,"device_ms":..}
    sem campo 'timestamp' (esse e adicionado pelo backend).
    """
    payload = (
        '{"nivel_oleo_pct":%.2f,"nivel_solido_pct":%.2f,"ir_cheio":%s,"device_ms":123456}'
        % (oil, solid, "true" if ir else "false")
    )
    msg = mqtt.MQTTMessage(topic=topic.encode("utf-8"))
    msg.payload = payload.encode("utf-8")
    return msg


class BackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = smartbin_app.app.test_client()

    def setUp(self):
        self._truncate_tables()
        smartbin_app.state.update(
            {
                "timestamp": None,
                "level_oil": 0.0,
                "level_solid": 0.0,
                "ir_full": False,
            }
        )
        smartbin_app.alert_lock["oleo"] = False
        smartbin_app.alert_lock["solido"] = False

    def _truncate_tables(self):
        conn = sqlite3.connect(DB_FILE)
        try:
            conn.execute("DELETE FROM telemetry")
            conn.execute("DELETE FROM discard_events")
            conn.execute("DELETE FROM alerts")
            conn.commit()
        finally:
            conn.close()

    def _count_rows(self, table_name: str) -> int:
        conn = sqlite3.connect(DB_FILE)
        try:
            row = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
            return int(row[0])
        finally:
            conn.close()

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["ok"])
        self.assertIn("timestamp", data)

    def test_state_updates_with_telemetry_payload(self):
        ts = datetime.now(timezone.utc).isoformat()
        smartbin_app.on_telemetry(
            {
                "timestamp": ts,
                "nivel_oleo_pct": 41.3,
                "nivel_solido_pct": 62.7,
                "ir_cheio": False,
            }
        )

        response = self.client.get("/api/state")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["timestamp"], ts)
        self.assertAlmostEqual(data["level_oil"], 41.3)
        self.assertAlmostEqual(data["level_solid"], 62.7)
        self.assertFalse(data["ir_full"])
        self.assertEqual(self._count_rows("telemetry"), 1)

    def test_solid_level_fallback_from_ir_sensor(self):
        ts = datetime.now(timezone.utc).isoformat()
        with patch("app.send_telegram_alert", return_value=None):
            smartbin_app.on_telemetry(
                {
                    "timestamp": ts,
                    "nivel_oleo_pct": 10,
                    "ir_cheio": True,
                }
            )
        data = self.client.get("/api/state").get_json()
        self.assertEqual(data["level_solid"], 100.0)
        self.assertTrue(data["ir_full"])

        with patch("app.send_telegram_alert", return_value=None):
            smartbin_app.on_telemetry(
                {
                    "timestamp": ts,
                    "nivel_oleo_pct": 10,
                    "ir_cheio": False,
                }
            )
        data = self.client.get("/api/state").get_json()
        self.assertEqual(data["level_solid"], 0.0)
        self.assertFalse(data["ir_full"])

    def test_discard_updates_stats(self):
        ts = datetime.now(timezone.utc).isoformat()
        smartbin_app.on_discard({"timestamp": ts, "tipo": "Óleo", "quantidade": 2})
        smartbin_app.on_discard({"timestamp": ts, "tipo": "solido", "quantidade": 3})

        response = self.client.get("/api/stats?days=7")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["total_oil_discards"], 2)
        self.assertEqual(data["total_solid_discards"], 3)
        self.assertAlmostEqual(data["total_liters_oil"], 1.0)
        self.assertAlmostEqual(data["total_kg_solid"], 0.6)
        self.assertEqual(len(data["labels"]), 7)
        self.assertEqual(self._count_rows("discard_events"), 2)

    def test_bootstrap_rearms_lock_when_bin_already_full(self):
        # Simula reinicio do processo com a lixeira ja cheia: o lock comeca
        # falso e o estado e restaurado do banco antes do bootstrap re-armar.
        ts = datetime.now(timezone.utc).isoformat()
        with patch("app.send_telegram_alert", return_value=None):
            smartbin_app.on_telemetry({"nivel_oleo_pct": 95, "nivel_solido_pct": 10, "ir_cheio": False})
            self.assertEqual(self._count_rows("alerts"), 1)

        # Estado de processo "reiniciado".
        smartbin_app.alert_lock["oleo"] = False
        smartbin_app.alert_lock["solido"] = False
        smartbin_app.bootstrap_state()
        self.assertTrue(smartbin_app.alert_lock["oleo"])

        # Novas leituras com a lixeira ainda cheia nao devem gerar novos alertas.
        with patch("app.send_telegram_alert", return_value=None):
            smartbin_app.on_telemetry({"nivel_oleo_pct": 96, "nivel_solido_pct": 10, "ir_cheio": False})
            smartbin_app.on_telemetry({"nivel_oleo_pct": 97, "nivel_solido_pct": 10, "ir_cheio": False})
        self.assertEqual(self._count_rows("alerts"), 1)

    def test_alert_threshold_lock_and_reset(self):
        with patch("app.send_telegram_alert", return_value=None):
            smartbin_app.on_telemetry({"nivel_oleo_pct": 90, "nivel_solido_pct": 20, "ir_cheio": False})
            smartbin_app.on_telemetry({"nivel_oleo_pct": 92, "nivel_solido_pct": 25, "ir_cheio": False})
            self.assertEqual(self._count_rows("alerts"), 1)

            smartbin_app.on_telemetry({"nivel_oleo_pct": 70, "nivel_solido_pct": 20, "ir_cheio": False})
            smartbin_app.on_telemetry({"nivel_oleo_pct": 91, "nivel_solido_pct": 20, "ir_cheio": False})
            self.assertEqual(self._count_rows("alerts"), 2)

        response = self.client.get("/api/alerts?limit=5")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(len(data["items"]), 2)
        self.assertEqual(data["items"][0]["compartment"], "oleo")


class FirmwareIntegrationTests(unittest.TestCase):
    """Exercita o caminho real: payload do ESP32 -> parser MQTT -> app.

    Diferente de BackendTests (que chama on_telemetry direto), estes testes
    passam pelo SmartBinMQTTClient._on_message exatamente como em producao,
    garantindo que o JSON emitido pelo firmware nao gera notificacao repetida.
    """

    def setUp(self):
        conn = sqlite3.connect(DB_FILE)
        try:
            conn.execute("DELETE FROM telemetry")
            conn.execute("DELETE FROM discard_events")
            conn.execute("DELETE FROM alerts")
            conn.commit()
        finally:
            conn.close()
        smartbin_app.alert_lock["oleo"] = False
        smartbin_app.alert_lock["solido"] = False
        # Cliente MQTT real conectado aos callbacks reais do app, sem broker.
        self.mqtt = SmartBinMQTTClient(
            host="localhost",
            port=1883,
            topic_base="smartbin",
            username="",
            password="",
            on_telemetry=smartbin_app.on_telemetry,
            on_discard=smartbin_app.on_discard,
        )

    def _count_alerts(self) -> int:
        conn = sqlite3.connect(DB_FILE)
        try:
            return int(conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0])
        finally:
            conn.close()

    def _deliver(self, msg: mqtt.MQTTMessage) -> None:
        # Caminho identico ao recebimento real de uma mensagem do broker.
        self.mqtt._on_message(self.mqtt.client, None, msg)

    def test_firmware_full_bin_alerts_only_once_over_many_readings(self):
        # O ESP32 publica a cada 2s. Com a lixeira cheia, dezenas de leituras
        # iguais chegam; deve haver exatamente UM alerta.
        with patch("app.send_telegram_alert", return_value=None):
            for oil in (86.0, 88.5, 90.0, 91.2, 95.0, 99.9):
                self._deliver(
                    _firmware_telemetry_message(
                        "smartbin/telemetry", oil=oil, solid=10.0, ir=False
                    )
                )
        self.assertEqual(self._count_alerts(), 1)

    def test_firmware_ir_solid_full_alerts_only_once(self):
        # Compartimento solido cheio via sensor IR (nivel_solido = 100 fixo).
        with patch("app.send_telegram_alert", return_value=None):
            for _ in range(5):
                self._deliver(
                    _firmware_telemetry_message(
                        "smartbin/telemetry", oil=10.0, solid=100.0, ir=True
                    )
                )
        self.assertEqual(self._count_alerts(), 1)

    def test_retained_message_on_reconnect_does_not_realert(self):
        # Cenario real do bug: firmware publica com retained=true (main.cpp).
        # Lixeira enche -> 1 alerta. Dashboard reinicia: o lock zera, o broker
        # reentrega a mensagem retida. bootstrap_state() deve re-armar o lock
        # a partir do banco, entao a mensagem retida NAO gera novo alerta.
        with patch("app.send_telegram_alert", return_value=None):
            self._deliver(
                _firmware_telemetry_message(
                    "smartbin/telemetry", oil=97.0, solid=10.0, ir=False
                )
            )
        self.assertEqual(self._count_alerts(), 1)

        # Simula reinicio do processo do dashboard.
        smartbin_app.alert_lock["oleo"] = False
        smartbin_app.alert_lock["solido"] = False
        smartbin_app.bootstrap_state()

        # Broker reentrega a mensagem retida ao reconectar.
        with patch("app.send_telegram_alert", return_value=None):
            self._deliver(
                _firmware_telemetry_message(
                    "smartbin/telemetry", oil=97.0, solid=10.0, ir=False
                )
            )
        self.assertEqual(self._count_alerts(), 1)

    def test_emptying_then_refilling_alerts_again(self):
        # Histerese real: cheio -> coletado (esvazia) -> enche de novo = 2 alertas.
        with patch("app.send_telegram_alert", return_value=None):
            self._deliver(_firmware_telemetry_message("smartbin/telemetry", oil=95.0, solid=10.0, ir=False))
            self._deliver(_firmware_telemetry_message("smartbin/telemetry", oil=30.0, solid=10.0, ir=False))  # coleta
            self._deliver(_firmware_telemetry_message("smartbin/telemetry", oil=96.0, solid=10.0, ir=False))  # enche
        self.assertEqual(self._count_alerts(), 2)


if __name__ == "__main__":
    unittest.main()
