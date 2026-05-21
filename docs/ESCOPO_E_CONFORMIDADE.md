# Escopo, Conformidade e Plano de Testes

## 1) Escopo do Projeto

Projeto: **Sistema de Coleta com Lixeira Inteligente (IoT)**  
Objetivo: monitorar descarte de resíduos (óleo e sólido), coletar dados por sensores no ESP32 e disponibilizar acompanhamento em dashboard web em tempo real via MQTT.

Fluxo funcional definido:

1. Usuário interage com a lixeira.
2. Seleciona tipo de descarte por botão (`oleo` ou `solido`).
3. LED RGB fornece feedback local.
4. ESP32 mede status dos compartimentos (ultrassônico + infravermelho).
5. ESP32 publica dados no broker MQTT.
6. Dashboard exibe níveis, histórico e alertas.
7. Em cenário de cheio/quase cheio, sistema gera alerta (com suporte opcional a Telegram).

## 2) Componentes e Mapeamento de Pinos

Mapeamento consolidado no firmware:

- Ultrassônico `TRIG` -> `GPIO 5`
- Ultrassônico `ECHO` -> `GPIO 18`
- Sensor infravermelho -> `GPIO 19`
- Botão óleo -> `GPIO 4`
- Botão sólido -> `GPIO 13`
- LED RGB `R` -> `GPIO 25`
- LED RGB `G` -> `GPIO 26`
- LED RGB `B` -> `GPIO 27`

## 3) Contrato de Comunicação MQTT

Tópico base padrão: `smartbin`

- `smartbin/telemetry`
- `smartbin/discard`

Payload esperado para telemetria:

```json
{
  "timestamp": "2026-05-19T15:20:00Z",
  "nivel_oleo_pct": 42.5,
  "nivel_solido_pct": 63.7,
  "ir_cheio": false
}
```

Observação de compatibilidade: se o firmware enviar apenas `ir_cheio` para o compartimento sólido, o dashboard converte para nível simplificado (`100%` se cheio, `0%` caso contrário).

Payload esperado para evento de descarte:

```json
{
  "timestamp": "2026-05-19T15:21:05Z",
  "tipo": "oleo",
  "quantidade": 1
}
```

## 4) Conformidade com os Critérios da Disciplina

### 4.0 Datas e marcos (conforme texto recebido)

- Janela de acompanhamento: **12/05/2026 a 16/06/2026**
- Definição da ideia: **12/05/2026**
- Check Point: no material aparece **20/05/2026** e também **26/05/2026**  
  Ação recomendada: confirmar com o professor qual data vale oficialmente.
- Entrega de documentação (relatório + Git): **11/06/2026**
- Mostra TechDesign: **20/06/2026**

### Funcionamento do sistema (MQTT + coleta + dashboard)

- Implementado: ingestão MQTT no backend Flask.
- Implementado: persistência de telemetria e eventos em SQLite.
- Implementado: atualização em tempo real no dashboard com Socket.IO.
- Pendente de validação prática: publicação real do ESP32 no ambiente final.

### Dashboard (interface funcional em tempo real)

- Implementado: níveis de óleo/sólido.
- Implementado: histórico diário (últimos 7 dias).
- Implementado: alertas recentes.
- Implementado: estatísticas agregadas (litros de óleo e kg de sólido por fator configurável).

### GitHub/organização de repositório

Estrutura alinhada ao template solicitado:

- `/docs`
- `/applications`
- `/esp32-esp8266`
- `/schematics`

### Relatório técnico (MNR/ABNT2)

- Estrutura de apoio criada em `docs/`.
- Conteúdo final do relatório deve ser produzido pelo grupo, sem uso de IA para redação, conforme regra do professor.

## 5) Plano de Testes (Passo a Passo)

### 5.1 Pré-requisitos

1. Python 3.10+ instalado.
2. Broker Mosquitto ativo (`localhost:1883`) ou ajuste no `.env`.
3. Dependências instaladas em ambiente virtual.

### 5.2 Setup

```bash
cd "/Users/antonioalbuquerque/Documents/New project/applications/web-dashboard"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### 5.3 Teste de inicialização do backend

```bash
python app.py
```

Validações esperadas:

- Aplicação sobe em `http://localhost:5000`.
- Endpoint de saúde responde:

```bash
curl http://localhost:5000/health
```

### 5.4 Teste de dados simulados (sem ESP32)

Terminal 1:

```bash
python app.py
```

Terminal 2:

```bash
source .venv/bin/activate
python simulator_publish.py --host localhost --port 1883 --base-topic smartbin
```

Validações esperadas no dashboard:

1. Nível de óleo e sólido atualizando em tempo real.
2. Histórico de descartes preenchendo ao longo do tempo.
3. Alertas surgindo quando níveis simulados passam do limiar configurado.

### 5.5 Teste de APIs

```bash
curl http://localhost:5000/api/state
curl "http://localhost:5000/api/stats?days=7"
curl "http://localhost:5000/api/alerts?limit=10"
```

### 5.6 Teste de alerta Telegram (opcional)

Configurar no `.env`:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Depois reiniciar backend e executar simulação até atingir threshold.

## 6) Checklist de Uniformidade

- Linguagem de payload padronizada (`oleo`, `solido`, sem acento).
- Tópicos MQTT documentados e implementados de forma idêntica.
- Estrutura de pastas aderente ao template do professor.
- Mapeamento de pinos consolidado.
- Dashboard e backend com mesma semântica de dados.
- Alertas e histórico persistidos em banco.

## 7) Riscos e Pendências Reais (Transparência Técnica)

- Critério de IPv6: depende da configuração de rede/broker no ambiente final; software aceita host configurável, inclusive IPv6.
- Precisão de litros/kg: atualmente por fator estimado configurável (`.env`), pode evoluir para calibração real.
- Entrega “100% perfeita” depende da etapa final com hardware real, rede final e validação presencial no checkpoint.
