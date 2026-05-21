# Dashboard Web - Lixeira Inteligente

Aplicação responsável por:

- Assinar tópicos MQTT publicados pelo ESP32
- Armazenar telemetria e eventos em SQLite
- Exibir dashboard em tempo real
- Disparar alertas (incluindo Telegram opcional)

## Tópicos MQTT esperados

Base de tópico configurável em `.env` (`MQTT_TOPIC_BASE`, padrão `smartbin`):

- `smartbin/telemetry`
- `smartbin/discard`

`MQTT_AUTO_START=false` pode ser usado para executar testes sem tentar conectar no broker.

## Exemplo de payload

`smartbin/telemetry`

```json
{
  "timestamp": "2026-05-19T15:20:00Z",
  "nivel_oleo_pct": 42.5,
  "nivel_solido_pct": 63.7,
  "ir_cheio": false
}
```

Se `nivel_solido_pct` nao for enviado, o backend usa `ir_cheio` para exibir nivel simplificado do compartimento solido (`0%` ou `100%`).

`smartbin/discard`

```json
{
  "timestamp": "2026-05-19T15:21:05Z",
  "tipo": "oleo",
  "quantidade": 1
}
```

## Executando localmente

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

## Simular dados sem ESP32

Com broker MQTT ativo:

```bash
python simulator_publish.py --host localhost --port 1883 --base-topic smartbin
```

## Testes automáticos do backend (sem hardware)

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```
