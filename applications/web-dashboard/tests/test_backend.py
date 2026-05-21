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


if __name__ == "__main__":
    unittest.main()
