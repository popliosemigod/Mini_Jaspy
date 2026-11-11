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

**Sozinho, sempre que plugar** (recomendado): rode uma vez

```
ponte\.venv\Scripts\python ferramentas\inicio_automatico.py
```

Daí em diante, a cada login do Windows o robô sobe escondido e espera a placa ser plugada; desplugou,
espera de novo; travou, religa. Tudo fica registrado em `ponte\logs\robo_AAAA-MM-DD.log`.
(`--tirar` desliga o início automático.)

**Na mão, vendo o log na tela:**

```
ponte\.venv\Scripts\python ponte\supervisor.py --logs-placa
```

Espere "Pronto! Pode falar" e fale normalmente. A resposta vem em ~4–9 s.

### Falando com ele

- **"Jaspy, …"**: o que vem depois do nome é uma ordem direta.
- **"Cala a boca"**, "fica quieto", "silêncio": ele acena e fica mudo até você chamar **"Jaspy"**.
- **"Jaspy, a partir de agora, quando eu disser X, faça Y"**: ele decora e repete sempre que ouvir X.
- **"Meu nome é Ana"** (com a Ana sozinha de frente para a câmera): ele aprende o rosto pela câmera.
- **"Jaspy, aprende a…"**: ele se reprograma (Claude Code), conta o que mudou e só grava depois de você
  dizer **"pode gravar"**.

Opções: `--texto` (digitar em vez de falar), `--modelo sonnet` (mais esperto, mais lento),
`--whisper base` (mais rápido, entende menos), `--logs-placa`, `--autoteste "frase 1|frase 2"`.

Volume do alto-falante: `SPK_VOLUME` em `cam/src/robo.h` (hoje 0.25 = baixo, mas audível).

Página da câmera (opcional): na rede conhecida, o endereço aparece ao iniciar o `robo.py`. Em
qualquer outro lugar, conecte o celular na rede **aberta "Robo-ESP32"** (a placa cria sozinha) e
abra `http://192.168.4.1/`.

Redes Wi-Fi da placa: copie `cam/src/wifi_redes_exemplo.h` para `cam/src/wifi_redes.h` e preencha.
Esse arquivo não vai para o GitHub.

Detalhes técnicos, medições e pendências: `RELATORIO_CONTINUIDADE.md`.
