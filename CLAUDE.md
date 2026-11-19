# Robô ESP32-S3 + Claude (Mini_Jaspy)

**Máquina nova?** Siga os "Primeiros passos" no topo do **RELATORIO_CONTINUIDADE.md** (instalar.bat,
wifi_redes.h, fotos, gravar a placa).

Leia **RELATORIO_CONTINUIDADE.md** antes de qualquer coisa: lá estão o estado atual, a arquitetura,
o hardware, o protocolo USB, as medições, os problemas resolvidos e as pendências. A conversa inteira
de desenvolvimento está em `historico/conversa_legivel.md` (consulte quando precisar do porquê de algo).

- Fale com o usuário em **português do Brasil**.
- ⚠️ **O repositório GitHub é PÚBLICO** (github.com/popliosemigod/Mini_Jaspy). Nunca comite senhas
  (`cam/src/wifi_redes.h`), fotos de rosto (`fotos_cadastro/`, `cam/data/`), o transcript bruto
  (`historico/*.zip`) nem gravações de áudio: estão no `.gitignore` e devem continuar lá.
  Nada deste projeto vai para o OneDrive da TOSOLVE/2Solve (pedido do usuário).
- **Placa atual: XIAO ESP32-S3 Sense** (branch `xiao-sense`, relatório §0): câmera e microfone PDM
  embutidos, MAX98357A em D3/D4/D5, USB nativa. Compilado, **ainda não testado no hardware**.
  A montagem antiga (Freenove + INMP441) continua no ambiente `freenove_cam`.
- O robô funciona **pelo cabo USB** (link binário, `cam/src/link.h` + `ponte/link_usb.py`).
  O Wi-Fi é opcional, só para a página da câmera. Sem rede conhecida, a placa cria a rede **aberta**
  "Robo-ESP32" → http://192.168.4.1/ (relatório §6.4, não testado).
- Cérebro: **Sonnet** (padrão), resposta numa linha `G|fala` em estilo telegráfico (relatório §0.4).
- Firmware: `cam/` (PlatformIO, Arduino-ESP32 **2.0.17** via `espressif32@6.10.0`; não migrar para o core 3.x).
  Gravar: `pio run -t upload` (XIAO) ou `pio run -e freenove_cam -t upload` dentro de `cam/`.
  **Feche o robo.py antes**, porque a porta é uma só.
- Alto-falante em 22.050 Hz (`SPK_RATE` em `robo.h` = `SPK_RATE` em `robo.py`/`link_usb.py`: mudar junto).
- Logs da placa: `ponte\.venv\Scripts\python ferramentas\ler_serial.py 40 --reset` (o monitor serial
  comum não entende o protocolo binário).
- Rodar o robô: `ponte\.venv\Scripts\python ponte\robo.py`. Autoteste sem ninguém por perto:
  `--autoteste "frase 1|frase 2"` (mic perto do alto-falante; ele vai se ouvir, é esperado).
- Pendências: testar a XIAO (§0.5) e calibrar `MIC_GAIN`; gravar e testar o Wi-Fi próprio; disparos
  falsos do detector de voz (§9.1); servos (não ligados).
- Não edite `platformio.ini` com `Set-Content` do PowerShell (grava BOM e quebra o PlatformIO).
