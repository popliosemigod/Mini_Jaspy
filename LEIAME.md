# Robô ESP32-S3 com o Claude como cérebro

## Placa: XIAO ESP32-S3 Sense (padrão)

A câmera e o microfone (PDM) já vêm **embutidos** na placa de expansão Sense: não precisam de fios.
Só o amplificador (e, se quiser, os servos) são ligados.

### Ligações

| Módulo | Pino do módulo | Ligar em (XIAO) | Componente no caminho |
|---|---|---|---|
| **MAX98357A** | VIN | **5V** | C1 10 µF + C2 100 nF + C3 470 µF entre VIN e GND, colados no módulo |
| | GND | GND | — |
| | DIN | **D3** (GPIO 4) | R2 **33 Ω** em série |
| | BCLK | **D4** (GPIO 5) | R3 **33 Ω** em série |
| | LRC | **D5** (GPIO 6) | R4 **33 Ω** em série |
| | GAIN | — | R1 **100 kΩ** do GAIN para o **VIN** (ganho 3 dB) |
| | SD | sem ligação | (o módulo já tem o resistor que liga o amplificador) |
| | + / − | alto-falante 4–8 Ω | fios curtos e trançados; **nunca** ligar o − no GND |
| Servo pan (opcional) | sinal | **D0** (GPIO 1) | — |
| Servo tilt (opcional) | sinal | **D1** (GPIO 2) | — |
| Servos | + / − | **fonte 5 V externa**, GND em comum | 470–1000 µF perto dos servos |

### Lista de componentes para o som

| Ref. | Valor | Tipo | Para quê |
|---|---|---|---|
| R1 | **100 kΩ** | resistor 1/4 W | GAIN → VIN: ganho analógico de 3 dB (era 9 dB). O volume vem do digital (`SPK_VOLUME 0.5`), que usa o dobro da resolução: **menos chiado** no mesmo volume baixo |
| R2, R3, R4 | **33 Ω** (22–47 Ω servem) | resistor 1/4 W | em série nos sinais I2S, perto da XIAO: amortecem reflexões e ruído de alta frequência |
| C1 | **10 µF** | cerâmico X5R/X7R, ≥10 V | desacoplamento do VIN, colado nos pinos do MAX98357A |
| C2 | **100 nF** | cerâmico | ruído de alta frequência da alimentação |
| C3 | **470 µF** (mín. 220 µF) | eletrolítico ≥10 V | reserva de corrente para os picos do classe D: menos distorção e menos ruído chegando à XIAO |
| FB1 (opcional) | ferrite 600 Ω @100 MHz, ≥1 A | em série no 5 V do amplificador | isola o chaveamento do amplificador do microfone e da câmera |

⚠️ Se você **não** colocar o R1 (GAIN solto = 9 dB), mude `SPK_VOLUME` para `0.25f` em `cam/src/robo.h`,
senão o som fica o dobro mais alto.

Deixe o alto-falante **longe do microfone da placa Sense** e virado para o lado oposto (senão o robô se ouve).

Montagem antiga (Freenove + INMP441): ver `RELATORIO_CONTINUIDADE.md` §4.1. Gravar com `pio run -e freenove_cam -t upload`.

## Rodar

O robô conversa com o PC **pelo cabo USB**: não precisa de hotspot nem de Wi-Fi.

1. Deixe a placa ligada ao PC pelo USB.
2. Na pasta `ponte`:

```
.venv\Scripts\python robo.py
```

3. Espere "Pronto! Pode falar" e fale normalmente. O cérebro é o **Sonnet**, respondendo em estilo
   telegráfico ("Brasília capital. Fácil.") para ser rápido: ~4 s para pensar, ~6 palavras por resposta.

Opções: `--texto` (digitar em vez de falar), `--modelo haiku` (mais rápido, menos esperto),
`--whisper base` (mais rápido, entende menos), `--logs-placa`, `--autoteste "frase 1|frase 2"`.

Volume do alto-falante: `SPK_VOLUME` em `cam/src/robo.h` (0.5 com o R1 de 100 kΩ = baixo, mas audível).

Página da câmera (opcional): na rede conhecida, o endereço aparece ao iniciar o `robo.py`. Em
qualquer outro lugar, conecte o celular na rede **aberta "Robo-ESP32"** (a placa cria sozinha) e
abra `http://192.168.4.1/`.

Redes Wi-Fi da placa: copie `cam/src/wifi_redes_exemplo.h` para `cam/src/wifi_redes.h` e preencha.
Esse arquivo não vai para o GitHub.

Detalhes técnicos, medições e pendências: `RELATORIO_CONTINUIDADE.md`.
