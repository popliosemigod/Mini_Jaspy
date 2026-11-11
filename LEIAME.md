# Robô ESP32-S3 com o Claude como cérebro

## Ligações

| Módulo | Pino do módulo | Ligar em |
|---|---|---|
| **INMP441** (microfone) | VDD | 3V3 |
| | GND | GND |
| | L/R | GND |
| | SCK | GPIO 41 |
| | WS | GPIO 42 |
| | SD | GPIO 1 |
| **MAX98357A** (amplificador) | VIN | 5V |
| | GND | GND |
| | BCLK | GPIO 47 |
| | LRC | GPIO 21 |
| | DIN | GPIO 14 |
| | GAIN / SD | sem ligação |
| | + / − | alto-falante 4–8 Ω |
| **Servo pan** (esquerda/direita) | sinal (laranja) | GPIO 38 |
| **Servo tilt** (cima/baixo) | sinal (laranja) | GPIO 39 |
| Servos | + (vermelho) / − (marrom) | **fonte 5 V externa**, com GND em comum com a placa |

Os servos puxam picos de corrente que podem reiniciar a ESP32 se forem alimentados pela USB. Se for usar o 5V da placa
mesmo assim, coloque um capacitor de 470–1000 µF entre 5V e GND perto dos servos.

Se o pescoço seguir o rosto para o lado errado, troque `PAN_DIR`/`TILT_DIR` em `cam/src/robo.h`.

## Rodar

O robô conversa com o PC **pelo cabo USB**: não precisa de hotspot nem de Wi-Fi.

1. Deixe a placa ligada ao PC pelo USB.
2. Na pasta `ponte`:

```
.venv\Scripts\python robo.py
```

3. Espere "Pronto! Pode falar" e fale normalmente. A resposta vem em ~8–12 s.

Opções: `--texto` (digitar em vez de falar), `--modelo sonnet` (mais esperto, mais lento),
`--whisper base` (mais rápido, entende menos), `--logs-placa`, `--autoteste "frase 1|frase 2"`.

Volume do alto-falante: `SPK_VOLUME` em `cam/src/robo.h` (hoje 0.25 = baixo, mas audível).

Página da câmera (opcional): na rede conhecida, o endereço aparece ao iniciar o `robo.py`. Em
qualquer outro lugar, conecte o celular na rede **aberta "Robo-ESP32"** (a placa cria sozinha) e
abra `http://192.168.4.1/`.

Redes Wi-Fi da placa: copie `cam/src/wifi_redes_exemplo.h` para `cam/src/wifi_redes.h` e preencha.
Esse arquivo não vai para o GitHub.

Detalhes técnicos, medições e pendências: `RELATORIO_CONTINUIDADE.md`.
