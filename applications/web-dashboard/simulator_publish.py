import argparse
import json
import random
import time
from datetime import datetime, timezone

import paho.mqtt.publish as publish


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulador MQTT da lixeira inteligente")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--base-topic", default="smartbin")
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()

    oil = 20.0
    solid = 15.0
    print(f"Publicando em mqtt://{args.host}:{args.port} tópico base {args.base_topic}")

    while True:
        oil = min(100.0, oil + random.uniform(0.1, 2.0))
        solid = min(100.0, solid + random.uniform(0.2, 1.5))
        telemetry = {
            "timestamp": now_iso(),
            "nivel_oleo_pct": round(oil, 2),
            "nivel_solido_pct": round(solid, 2),
            "ir_cheio": solid >= 90,
        }
        publish.single(
            f"{args.base_topic}/telemetry",
            json.dumps(telemetry),
            hostname=args.host,
            port=args.port,
        )

        if random.random() < 0.35:
            discard = {
                "timestamp": now_iso(),
                "tipo": random.choice(["oleo", "solido"]),
                "quantidade": 1,
            }
            publish.single(
                f"{args.base_topic}/discard",
                json.dumps(discard),
                hostname=args.host,
                port=args.port,
            )

        print("telemetry:", telemetry)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
