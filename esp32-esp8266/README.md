# Firmware ESP32 (PlatformIO + Arduino)

Firmware para testar integração da lixeira inteligente com o dashboard web via MQTT.

## Mapeamento de pinos definido

- Ultrassônico `TRIG` -> `GPIO 5`
- Ultrassônico `ECHO` -> `GPIO 18` (via divisor 1k + 2k)
- Sensor infravermelho -> `GPIO 19`
- Botão óleo -> `GPIO 4`
- Botão sólido -> `GPIO 13`
- LED RGB `R` -> `GPIO 25`
- LED RGB `G` -> `GPIO 26`
- LED RGB `B` -> `GPIO 27`

## Segurança elétrica obrigatória

- HC-SR04 `VCC` em `5V/VIN`, `GND` comum.
- `ECHO` do HC-SR04 **nunca direto** no ESP32:
  - `ECHO -> 1kΩ -> nó -> GPIO18`
  - `nó -> 2kΩ -> GND`
- Sensor IR em `3V3` (para OUT compatível com GPIO 3.3V).

## Contrato MQTT com o dashboard

- `smartbin/telemetry`: nível de óleo, nível de sólido, status IR
- `smartbin/discard`: evento de descarte (tipo e quantidade)

## Como testar no PlatformIO

1. Copie credenciais:

```bash
cp include/secrets.example.h include/secrets.h
```

2. Edite `include/secrets.h` com:
- Wi-Fi
- IP do broker MQTT (seu PC/Raspberry)

3. Build/upload:

```bash
pio run -t upload
```

4. Monitor serial:

```bash
pio device monitor -b 115200
```

O firmware publica em:
- `smartbin/telemetry` a cada 2s
- `smartbin/discard` ao pressionar botões
