# Mini_Jaspy na XIAO ESP32-S3 Sense — pinagem e ligação

Troca da Freenove ESP32-S3 CAM pela **Seeed XIAO ESP32-S3 Sense**. Os números abaixo são GPIO; entre
parênteses, o nome impresso na placa. A fonte única dos pinos no código é [`src/placa.h`](src/placa.h).

> **Estado (23/11/2026): gravada e ensaiada pelo USB, com um limite conhecido no enlace** (ver "Ensaio
> de 23/11"). Os três ambientes compilam (`xiao`, `xiao_tusb` e `esp32s3cam`, o de antes).

## Ensaio de 23/11 (XIAO nova, MAC `94:A9:90:DF:61:58`, gravada pelo USB)

| O que | Resultado medido |
| --- | --- |
| Boot, reconhecimento de rosto (autoteste) | ✅ 0,61 / 0,92 / 0,58, **idêntico à Freenove** |
| Câmera | ✅ sensor **OV3660** (`0x3660`, não a OV2640), acorda em **372 ms** (Freenove: 745). Imagem muito esverdeada nos primeiros quadros: conferir o balanço de branco |
| Microfone PDM | ✅ ~15,7 mil amostras/s; ruído médio **145** em silêncio (INMP441: 114). Ganho `MIC_GANHO_PDM=4` ainda **não calibrado com voz** |
| Comandos PC → placa, servo | ✅ `servo 60 90` levou o `pan` a 60; o `servodiag` e os GPIO4/5 **não foram medidos** nesta placa |
| Link, respostas curtas | ✅ 30 de 30 `stats` respondidos em < 0,1 s (a 5 comandos/s) **depois** de mandar cada quadro numa escrita só |
| Link sob carga (microfone + fotos) | ⚠️ **2 de 8 fotos perdidas, 33 quadros corrompidos** no USB-Serial-JTAG (HWCDC) |
| Alto-falante, servos movendo, energia | ⛔ não ensaiados (sem MAX98357A/servos ligados nesta placa) |

**Por que o HWCDC perde bytes:** lendo `HWCDC.cpp`, a interrupção que esvazia o buffer escreve 64 bytes no FIFO
do hardware sem conferir se cabe, enquanto cada `Serial.write` também mexe no FIFO; com o FIFO parcialmente
cheio, o excesso some **no meio** do quadro. Mandar o quadro inteiro numa escrita (feito) reduziu muito, não
zerou. **TinyUSB** (`pio run -e xiao_tusb`) não perde (0 erros em 57 s), **mas não regrava sozinho**: o reset por
DTR/RTS e o toque de 1200 baud deixaram a placa parada, e só um replugue a recuperou. Como a autoprogramação
precisa gravar sozinha, o padrão ficou o HWCDC. Saídas: aceitar a perda (o robô já tolera foto sem resposta),
gravar o TinyUSB com BOOT apertado, ou ligar um **adaptador USB-UART** nos pinos D6/D7 (como a Freenove).

## O que já vem na placa (nada a ligar)

| Função | Pinos | Observação |
| --- | --- | --- |
| Câmera (OV2640, na placa de expansão Sense) | XCLK 10 · SIOD 40 · SIOC 39 · VSYNC 38 · HREF 47 · PCLK 13 · Y2–Y9 = 15, 17, 18, 16, 14, 12, 11, 48 | os mesmos da cabeça do Jaspy do laboratório |
| Microfone PDM | CLK **42** · DATA **41** | no S3 só o I2S0 faz PDM; o amplificador fica no I2S1 |

## O que você liga

| Módulo | Fio | Vai em |
| --- | --- | --- |
| **MAX98357A** (alto-falante) | BCLK | **GPIO1** (D0) |
| | LRC | **GPIO2** (D1) |
| | DIN | **GPIO3** (D2) |
| | VIN / GND | 5 V / GND (veja "Energia") |
| **Servo 1** (pescoço) | sinal | **GPIO4** (D3) |
| **Servo 2** (pescoço) | sinal | **GPIO5** (D4) |
| Servos | + / − | fonte 5 V externa, **GND em comum** com a placa |

**Por que os servos mudaram de pino:** na Freenove eram GPIO38 e 39, que na XIAO são da câmera.
GPIO4 e 5 estão livres e não têm papel no boot. **Evite** D6/D7 (GPIO43/44, UART0: o log de boot sai por
ali) e D8/D9/D10 (GPIO7/8/9, o SD da expansão). Os dois canais PWM são independentes: servem tanto para
pan + tilt quanto para dois servos no mesmo eixo (nesse caso, mova os dois juntos no código).

## O que mudou no firmware

| Ponto | Freenove | XIAO |
| --- | --- | --- |
| Microfone | INMP441, I2S padrão 32 bits | PDM embutido, 16 bits; o código lê os 2 canais e escolhe o que tem sinal. Ganho inicial `MIC_GANHO_PDM = 4` (**medir e ajustar**) |
| Link com o PC | UART0 a 2 Mbaud pelo chip CH343 | USB nativo (`ARDUINO_USB_CDC_ON_BOOT=1`); o baud não importa. A porta é `303A:1001`; o PC reconhece as duas (`find_port`) |
| Flash | 16 MB | 8 MB, com tabela própria (`partitions_xiao_8MB.csv`): 6 MB para o programa, 1,9 MB para os rostos aprendidos. A tabela padrão de 8 MB só dá 3,2 MB e o firmware tem 4,4 MB |
| Câmera | OV5640 | OV2640 (a imagem pode vir com outra orientação; o detector já tenta o quadro girado) |

## Gravar (primeira vez)

```
$env:PLATFORMIO_CORE_DIR = "C:\pio-mini"
cd C:\Mini_Jaspy\cam
pio run -e xiao -t upload
```

Na primeira gravação, com a XIAO ainda sem este firmware: **segure BOOT, plugue o USB** (ou aperte RESET
com BOOT apertado) e solte. Depois disso grava sozinho. Para o supervisor usar a XIAO, ponha
`"PLACA_ENV": "xiao"` no `ponte/maquina.json` (local, fora do git). **Se houver outra ESP32-S3 plugada
(a cabeça do Jaspy), passe `--porta COMx` ao robô:** as duas têm o mesmo identificador USB.

## Energia (o ponto que já derrubou a Freenove)

A Freenove reiniciava quando o alto-falante começava a falar com o volume no máximo. A XIAO também se
alimenta só pelo USB-C. Faça: **MAX98357A com 5 V próprio** (GND em comum com a placa), servos em fonte
própria, capacitor de 470–1000 µF no 5 V do amplificador, e o USB numa porta direto do PC.

## Roteiro do ensaio (na bancada)

| # | Passo | Previsto |
| --- | --- | --- |
| 1 | Gravar (`-e xiao`), abrir o robô | log: `Sensor PID: 0x2642` (OV2640), `Pronto! Link USB ativo` |
| 2 | Falar perto | `[mic] lidas ~16000 amostras/s`; `voz detectada` com nível >> ruído; se o nível ficar baixo, subir `MIC_GANHO_PDM` |
| 3 | Resposta falada | alto-falante toca; a placa não reinicia |
| 4 | `servo 60 90`, `servo 120 90`, `servodiag` | pescoço vai; `diag` mostra 5–10% nos GPIO4 e 5 |
| 5 | Câmera acorda e dorme | `acordou em ~745 ms`, sem `Falha na camera` repetida |
