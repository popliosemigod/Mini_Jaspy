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
- O robô funciona **pelo cabo USB** (link binário a 2 Mbaud, `cam/src/link.h` + `ponte/link_usb.py`).
  O Wi-Fi é opcional, só para a página da câmera. Sem rede conhecida, a placa cria a rede **aberta**
  "Robo-ESP32" → http://192.168.4.1/ (gravado em 11/11, ainda não testado longe das redes, relatório §6.4).
- **O robô roda pelo `ponte/supervisor.py`** (nunca o `robo.py` direto em produção): ele religa, espera a placa,
  grava a autoprogramação e escreve **todo o log** em `ponte/logs/robo_AAAA-MM-DD.log`. Para mexer na placa,
  pare o supervisor antes (a porta é uma só). O que mudou em 11/11: relatório §13.
- Coisas desta máquina ficam em `ponte/maquina.json` (fora do git), ex.: `PLATFORMIO_CORE_DIR`.
- Firmware: `cam/` (PlatformIO, Arduino-ESP32 **2.0.17** via `espressif32@6.10.0`; não migrar para o core 3.x).
  Gravar: `pio run -t upload` dentro de `cam/` (PlatformIO detecta a porta). **Feche o robo.py antes**,
  porque a porta é uma só.
- Logs da placa: `ponte\.venv\Scripts\python ferramentas\ler_serial.py 40 --reset` (o monitor serial
  comum não entende o protocolo binário).
- Rodar o robô: `ponte\.venv\Scripts\python ponte\robo.py`. Autoteste sem ninguém por perto:
  `--autoteste "frase 1|frase 2"` (mic perto do alto-falante; ele vai se ouvir, é esperado).
- Pendências: chiado da voz (§13.6); servos (a placa comanda, falta ver mexer: 5 V e GND); aprender rosto de
  uma pessoa nova (§13.1); Wi-Fi próprio longe das redes; disparos falsos do detector de voz (§9.1).
- Não edite `platformio.ini` com `Set-Content` do PowerShell (grava BOM e quebra o PlatformIO).
