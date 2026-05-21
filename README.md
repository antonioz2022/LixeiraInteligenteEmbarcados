# Lixeira Inteligente IoT

Projeto da disciplina de Sistemas Embarcados com foco em coleta inteligente de resíduos (óleo e sólido), usando ESP32 + MQTT + Dashboard Web em tempo real.

## Estrutura

```text
.
├── README.md
├── docs
├── applications
│   └── web-dashboard
├── esp32-esp8266
└── schematics
```

## Objetivo

Monitorar níveis da lixeira e registrar descartes em tempo real:

- ESP32 coleta dados dos sensores e publica no MQTT.
- Dashboard exibe níveis, histórico diário e alertas.
- Alertas podem ser enviados para Telegram quando compartimento está quase cheio.

## Stack da aplicação web

- Backend: Python + Flask + Flask-SocketIO
- Broker: Mosquitto MQTT
- Banco: SQLite
- Frontend: HTML + CSS + JavaScript + Chart.js

## Como executar o dashboard

1. Acesse a pasta da aplicação:

```bash
cd applications/web-dashboard
```

2. Crie e ative ambiente virtual:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

3. Instale dependências:

```bash
pip install -r requirements.txt
```

4. Configure variáveis:

```bash
cp .env.example .env
```

5. Execute:

```bash
python app.py
```

6. Abra no navegador:

`http://localhost:5000`

## Entregáveis

- Código da aplicação em `applications/web-dashboard`
- Firmware/documentação ESP em `esp32-esp8266`
- Diagramas e esquemas em `schematics`
- Relatório e anexos em `docs`

## Escopo e conformidade

Documento completo de escopo, checklist e plano de testes:

- `docs/ESCOPO_E_CONFORMIDADE.md`
