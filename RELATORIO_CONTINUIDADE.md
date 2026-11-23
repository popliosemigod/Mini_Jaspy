# Relatório de continuidade — Robô ESP32-S3 com o Claude como cérebro

Última atualização: **2026-11-11**. Escrito no app Claude (aba Code) para o Claude Code no VS Code,
**em outra máquina**, continuar de onde parou. Repositório: <https://github.com/popliosemigod/Mini_Jaspy>
(**público**).

> ### ⚡ Primeiros passos na máquina nova
> 1. `git clone https://github.com/popliosemigod/Mini_Jaspy.git` num caminho **curto, sem acentos e
>    fora do OneDrive** (ex.: `C:\Mini_Jaspy`). Rode o **`instalar.bat`** (§11).
> 2. Crie `cam/src/wifi_redes.h` a partir de `cam/src/wifi_redes_exemplo.h` (senhas ficam fora do GitHub).
>    Opcional: o Wi-Fi só serve à página da câmera.
> 3. Se tiver as fotos de cadastro (não estão no GitHub, por privacidade), coloque em `fotos_cadastro/` e
>    rode `python ferramentas/converter_fotos.py fotos_cadastro cam/data`. Sem elas o build usa imagens
>    cinza e todo mundo vira "Creatura".
> 4. **Grave a placa** (`pio run -t upload` em `cam/`): o firmware com o **Wi-Fi próprio da placa** (§6.4)
>    foi compilado, mas **ainda não foi gravado** (a placa não estava no USB).
> 5. Histórico completo da conversa: `historico/conversa_legivel.md` (sem senhas).

---

## 1. Objetivo do projeto (o que o usuário pediu)

1. ESP32-S3 com câmera servindo uma **página web só com a imagem da câmera**. ✅
2. **Detecção de rostos** na placa (IA local). ✅
3. **Reconhecimento facial** de uma pessoa específica (fotos do usuário):
   o cadastrado aparece como **"Rapaz bonito e inteligente"** (caixa verde) e qualquer outra pessoa
   como **"Creatura"** (caixa vermelha). ✅
4. **Robô conversacional**: microfone **INMP441** (ouvidos), **MAX98357A** + alto-falante (boca),
   câmera (olhos), **2 servos** (pescoço) e o **Claude como cérebro**, usando a conta Claude do usuário
   num PC com internet. ✅ **funciona de ponta a ponta** (testado por autoteste acústico, §8)
5. Pedido mais recente: *"chegar num momento aleatório e falar, e ele responde logo em seguida"*,
   com componentes dormindo quando não são necessários e o microfone sempre ligado. ✅ (§3)

Idioma do usuário: português do Brasil. O robô fala pt-BR, em **volume baixo, mas audível** (pedido do usuário).

---

## 2. Estado atual (resumo honesto)

| Parte | Estado |
|---|---|
| Link PC ↔ placa **pelo cabo USB** (2 Mbaud, protocolo binário) | ✅ 0 quadros com erro nos testes |
| Microfone INMP441 | ✅ 16 k amostras/s, ruído ~135 RMS após filtro de 250 Hz (era ~1.200) |
| Alto-falante MAX98357A | ✅ Usuário ouviu o bip; volume 25% (`SPK_VOLUME`) |
| Autoteste acústico (alto-falante → mic) | ✅ Tom de 1 kHz detectado 37,7× acima do resto |
| Conversa completa (voz → Whisper → Claude → voz) | ✅ Autoteste: 5–6 de 6 frases entendidas, resposta em **~8–12 s** |
| Câmera dorme/acorda sob demanda | ✅ Acorda em 0,75 s; foto em 1,6 s se dormindo, 0,27 s se acordada |
| Reconhecimento facial | ✅ 11/11: dono 0,57–0,79 ao vivo, com o **quadro girado** (§13.2) |
| Rostos aprendidos pela câmera | 🟡 Gravado; comandos e prazo testados, **falta testar com uma pessoa nova** (§13.1) |
| Imagem da câmera | ✅ Clara. A câmera está **de lado** (~90°): o detector gira o quadro sozinho (§13.2) |
| Servos | 🟡 A placa comanda (pan 50→129, tilt 65→114 medidos na placa, 20°/s); **o dono não confirmou ter visto mexer** — conferir 5 V externo e GND comum |
| Wi-Fi | ✅ 11/11 entrou na rede `Jaspy` (−24 a −44 dBm). Não é necessário para o robô |
| **Wi-Fi próprio da placa** (rede aberta "Robo-ESP32") | 🟡 **Gravado** em 11/11, ainda não testado longe das redes conhecidas (§6.4) |
| Autoprogramação por voz | ✅ Rodou 2× de verdade (91 s e 125 s, só Python); fluxo de gravar com supervisor pronto (§13.4) |
| Voz | 🟡 Neural (Brian); **chiado** em investigação (§13.6) |
| Build sem fotos / sem senhas (repo público) | ✅ Compila nos dois casos (imagens cinza / `wifi_redes_exemplo.h`) |
| Disparos falsos do detector de voz | ⚠️ Pendência principal (§9.1) |

**O que está gravado na placa hoje (11/11/2026):** o firmware do branch `autoprogramacao` (commit
`898273c`): Wi-Fi próprio, rostos aprendidos, quadro girado, pescoço lento, LittleFS montado só na hora.
Backup da flash anterior (16 MB, com as fotos) em `backup_placa/` — fora do git.

**Placa atual:** a placa conectada **não é a mesma de ontem** (mesmo modelo). A de hoje tem MAC
`c4:9e:7e:00:48:d8` e apareceu na **COM22** neste PC; a anterior tinha `…47:40` na COM21.

---

## 3. Arquitetura final e quem dorme / quem fica ligado

```
                     cabo USB (CH343, 2 Mbaud, quadros binários)
   PC (ponte/robo.py) ◄──────────────────────────────────────────► ESP32-S3 (cam/)
   ─────────────────                                               ──────────────
   detector de voz (VAD) ◄── 'M' microfone (sempre ligado) ─────── INMP441 + filtro 250 Hz
   ao detectar voz ───────── 'C' "wake 20000" ───────────────────► câmera ACORDA (0,75 s)
   Whisper small (pt)
   foto em paralelo ──────── 'C' "capture" ──────────────────────► 'J' JPEG + 'F' rostos
   Claude (claude -p persistente, conta do usuário)
   voz Maria (Windows) ───── 'B' / 'A' PCM / 'E' ────────────────► amplificador ACORDA, toca, DORME
                                                                   câmera DORME após 20 s sem uso
   Wi-Fi da placa: opcional (só para a página da câmera no navegador)
```

| Componente | Estado normal | Acorda quando | Por quê |
|---|---|---|---|
| **Microfone (I2S0)** | **Sempre ligado** | — | Precisa ouvir a qualquer momento |
| Câmera + IA de rosto | **Dormindo** (`esp_camera_deinit`, sem clock nem DMA) | Voz detectada, `capture`, stream aberto | Libera ~30 KB de RAM interna e CPU/PSRAM; acorda antes de a transcrição terminar |
| Amplificador (I2S1) | **Dormindo** (`i2s_stop`: sem clock, o MAX98357A entra em repouso) | Chega fala do PC | Sem chiado e menos consumo; 80 ms de silêncio ao acordar para não cortar a 1ª sílaba |
| Servos | Parados (sem servos ligados) | Gestos/rastreio | — |
| Wi-Fi | Ligado em segundo plano, **não bloqueia nada** | — | Só serve à página da câmera; pode ser desligado com o comando `wifi 0` |

Medições que embasaram as decisões (ver `ponte/testes/`):

- **O ruído do microfone não vem da câmera nem do Wi-Fi.** A mediana ficou entre 1.056 e 1.329 em todas
  as combinações; os picos eram de **120 Hz e 30 Hz**, zumbido da rede elétrica pela alimentação.
  Solução: passa-altas de 4ª ordem a 250 Hz, que levou o ruído para ~135.
- **Câmera ligada vs dormindo não melhorou o Wi-Fi** (perda de 25–52% nos dois casos): a causa é a rede (§7.2).

---

## 4. Hardware

- **Placa:** ESP32-S3 (QFN56) rev v0.2, 16 MB flash, 8 MB PSRAM OPI. Provavelmente uma
  **Freenove ESP32-S3 WROOM CAM**. USB-serial **CH343** (`VID 1A86 PID 55D3`). Neste PC apareceu na **COM22** (em outra máquina será outra; tudo detecta sozinho).
- **Câmera:** OV5640 (PID 0x5640), pinagem ESP32-S3-EYE: XCLK 15, SIOD 4, SIOC 5,
  D7..D0 = 16,17,18,12,10,8,9,11, VSYNC 6, HREF 7, PCLK 13.
- Pinos proibidos: os da câmera, 35–37 (PSRAM), 19/20 (USB), 43/44 (UART0 = link com o PC),
  0/3/45/46 (strapping), 2 e 48 (LEDs).

### 4.1 Ligações (montadas e funcionando, exceto servos)

| Módulo | Pino | Ligar em |
|---|---|---|
| **INMP441** | VDD / GND / L/R | 3V3 / GND / GND |
| | SCK / WS / SD | **GPIO 41 / 42 / 1** |
| **MAX98357A** | VIN / GND | 5V / GND |
| | BCLK / LRC / DIN | **GPIO 47 / 21 / 14** |
| | GAIN, SD | sem ligação |
| **Servo pan** | sinal | **GPIO 38** |
| **Servo tilt** | sinal | **GPIO 39** |
| Servos | +5 V / GND | **fonte 5 V externa** com GND comum |

Pinos definidos em `cam/src/robo.h`. GPIO 38/39 são do slot SD (não use cartão SD).

---

## 5. Estrutura de pastas

Marcados com 🔒 = **fora do GitHub** (`.gitignore`), só existem na máquina local.

```
CLAUDE.md                     instruções para o Claude Code (lido automaticamente)
instalar.bat                  prepara uma máquina nova (venv, Whisper, verificações) - ver §11
LEIAME.md                     resumo para o usuário
RELATORIO_CONTINUIDADE.md     este arquivo
historico/
  conversa_legivel.md         a conversa inteira de desenvolvimento (sem senhas)
  conversa_completa_*.zip  🔒 transcript bruto exportado (tem e-mails, caminhos, senhas, imagens)
cam/                          firmware (PlatformIO)
  platformio.ini              porta detectada automaticamente; roda scripts/fotos_padrao.py antes do build
  scripts/fotos_padrao.py     cria imagens cinza em data/ se as fotos reais não existirem
  src/main.cpp                câmera (dorme/acorda), IA de rosto, cadastro, HTTP, Wi-Fi + rede própria, comandos USB
  src/wifi_redes_exemplo.h    modelo das redes Wi-Fi
  src/wifi_redes.h         🔒 redes e senhas reais (copiar do exemplo)
  src/robo.h / robo.cpp       microfone (+filtro), alto-falante (+sono), servos, UDP, estatísticas
  src/link.h / link.cpp       link binário USB com o PC
  data/face0..8.bin        🔒 fotos de cadastro (RGB565 BE 320x240) embutidas no firmware
ponte/
  robo.py                     o robô: ouvidos (VAD + Whisper), cérebro (Claude), boca (voz Maria)
  link_usb.py                 cliente do link USB (UsbRobot)
  .venv/                   🔒 Python + faster-whisper, numpy, pyserial (instalar.bat cria)
  modelos/                 🔒 Whisper small e base (baixados sozinhos)
  testes/                     logs dos 3 autotestes (gravações de áudio 🔒)
ferramentas/
  conversa_para_md.py         transcript exportado → Markdown legível, apagando as senhas do wifi_redes.h
  ler_serial.py               logs da placa pelo USB (decodifica os quadros)
  testar_usb.py               teste do link USB: foto, mic, autoteste acústico (bip → mic)
  ruido_mic.py                ruído do mic com câmera/Wi-Fi ligados ou desligados
  medir_rede.py               qualidade do Wi-Fi da placa (ping, perda UDP) por configuração
  testar_placa.py             teste pelo Wi-Fi (UDP/HTTP)
  testar_ponte_pc.py          TTS → Whisper → Claude sem a placa
  converter_fotos.py          fotos → .bin de cadastro
fotos_cadastro/           🔒 as 9 fotos originais
```

---

## 6. Firmware (`cam/`)

### 6.1 Compilar e gravar

```
cd cam
%USERPROFILE%\.platformio\penv\Scripts\pio.exe run -t upload
```

- `espressif32@6.10.0` = **Arduino-ESP32 2.0.17**. Não migrar para o core 3.x (I2S legado, LEDC e esp-dl mudam).
- **Feche o `robo.py` antes de gravar**, porque os dois usam a mesma porta.
- A porta é **detectada automaticamente** (as linhas `upload_port`/`monitor_port` estão comentadas
  no `platformio.ini`). Se houver mais de uma placa, descomente e ajuste.
  ⚠️ Não use `Set-Content` do PowerShell nesse arquivo: ele grava BOM e o PlatformIO para de ler.
- Logs: `ponte\.venv\Scripts\python ferramentas\ler_serial.py 40 --reset`. O monitor serial comum
  **não serve mais**: a UART fala binário a 2 Mbaud.
- O boot leva ~20 s (cadastro dos 18 rostos) até "Pronto! Link USB ativo".

### 6.2 Link USB (`link.h`)

Quadro: `[0xA5][0x5A][tipo][tamanho 2 B LE][dados][xor dos dados]`.

| Direção | Tipo | Conteúdo |
|---|---|---|
| placa → PC | `M` | microfone, PCM16 mono 16 kHz, blocos de 20 ms (só enquanto o PC pede `mic 1`, renovado a cada 1,5 s) |
| placa → PC | `L` | log em texto (todo `LOGF` do firmware) |
| placa → PC | `J` / `F` / `S` | JPEG / JSON de rostos + `speaking` / JSON de estatísticas |
| PC → placa | `B` `A` `E` | início, PCM e fim de uma fala para o alto-falante |
| PC → placa | `C` | comandos: `mic 0/1`, `capture`, `faces`, `stats`, `wake <ms>`, `gesture <sim/nao/curioso/centro>`, `servo <pan> <tilt>`, `track 0/1`, `echo 0/1`, `vision 0/1`, `wifi 0/1` |

`echo 1` = o microfone **não** fica mudo enquanto o alto-falante toca (só para autoteste).

### 6.3 Outros pontos importantes do firmware

- **RAM interna é o recurso crítico** (~300 KB, dividida com Wi-Fi/lwIP). Um DMA de 64 KB no mic deixava
  só 6 KB livres e a rede parava de aceitar conexões. Hoje: DMA mic 6×256, alto-falante 6×256,
  buffers de áudio na **PSRAM** (`StreamBuffer`). Livre: ~73–88 KB com a câmera dormindo, ~38 KB acordada.
- Microfone: 32 bits, escolhe sozinho o canal L/R com sinal, `>>14`, **2 biquads passa-altas de 250 Hz**,
  depois `StreamBuffer` de 2 s → USB (`M`) e/ou UDP.
- Câmera: dorme 20 s após o último uso (`VISION_IDLE_MS`). `/capture` e `capture` esperam 3 quadros
  quando a câmera estava dormindo.
- Reconhecimento: `MATCH_THRESHOLD 0.55`, 18 IDs cadastrados na RAM a cada boot (9 fotos + espelhadas).
- Wi-Fi: `WiFiMulti` com **Wifi_2Solve** e **Ronaldo** (senhas em `cam/src/wifi_redes.h`, fora do GitHub), sem economia de
  energia e com potência máxima. **Não bloqueia o boot.**
- HTTP (porta 80) ainda existe para a página da câmera: `/`, `/faces`, `/capture`, `/servo`, `/gesture`,
  `/wake`, `/config?vision=&xclk=&echo=`, `/stats`; stream MJPEG na porta 81. Áudio por **UDP**
  (mic 82, alto-falante 83) para quem usar `--transporte wifi`.

### 6.4 Wi-Fi próprio da placa (modo reserva) — 🟡 compilado, NÃO gravado/testado

Pedido do usuário: em qualquer lugar (outra rede, sem as redes conhecidas), a página da câmera deve
continuar acessível. Implementado em `main.cpp` (`start_own_ap`, `stop_own_ap`, `loop()`):

- Se a placa ficar **30 s** sem nenhuma rede conhecida (`AP_AFTER_MS`), ela cria a rede **"Robo-ESP32"**,
  **aberta, sem senha** (pedido do usuário: "livre e fácil de entrar"). Página: **http://192.168.4.1/**.
- Modo `WIFI_AP_STA`: a cada **2 min** (`AP_STA_RETRY_MS`) ela ainda procura as redes conhecidas; se
  entrar numa, desliga a rede própria.
- O comando USB `stats` informa `ap`, `ap_rede`, `ap_ip`; o `robo.py` mostra no início como abrir a página.
- Para pôr senha: `AP_PASS` em `main.cpp` (mínimo 8 caracteres).
- **Testar depois de gravar:** sem `wifi_redes.h` (ou longe das redes), esperar ~50 s após o boot,
  conectar o celular em "Robo-ESP32" e abrir `http://192.168.4.1/`. Confirmar também que a busca
  periódica das redes conhecidas não derruba a página por muito tempo.

### 6.5 Segredos e repositório público

- Senhas Wi-Fi: `cam/src/wifi_redes.h` (🔒 `.gitignore`). Sem ele, o build usa `wifi_redes_exemplo.h`
  (sem redes), com um `#warning`, e a placa usa só a rede própria.
- Fotos de rosto: `fotos_cadastro/` e `cam/data/` (🔒). Sem elas, `scripts/fotos_padrao.py` gera imagens
  cinza, o cadastro fica vazio e o firmware trata "0 rostos cadastrados" (todos = "Creatura").
- **Nunca** comitar o `.zip` do transcript bruto nem gravações de áudio.

---

## 7. Problemas encontrados e como foram resolvidos

1. **Erro "recorrente" de conexão ao IP da placa:** o PC estava na rede Wifi_2Solve e a placa no hotspot
   Ronaldo. O Windows bloqueia `netsh wlan connect` sem permissão de Localização.
   A placa passou a usar várias redes (WiFiMulti).
2. **A rede Wifi_2Solve é ruim para a ESP32**, mesmo com sinal de -52 dBm: 25–75% de perda de ping,
   latência de 100 ms a 1 s, enquanto o PC fala com o roteador em 11 ms. Causa provável: **canal 6 de
   2,4 GHz congestionado** (4 redes da 2Solve no mesmo canal); o PC deve estar em 5 GHz, que a ESP32
   não tem. Tentativas: TCP → UDP, retry de envio, Wi-Fi sem economia de energia, câmera dormindo,
   XCLK 10 MHz. Melhorou, mas não resolveu. **Solução definitiva: link pelo cabo USB.**
3. **Falta de RAM interna** travava a rede (ver §6.3).
4. **Deriva DC e zumbido no microfone** (oscilação de ±10.000 e 120 Hz) faziam o detector de voz ver
   "fala" o tempo todo e mandar 15 s de ruído para o Whisper (67 s de processamento). Resolvido com o
   filtro de 250 Hz e o detector com ruído medido e recalibração.
5. **Whisper lento e instável** no i5-1235U (2 núcleos P + 8 E, CPU 68% ocupada por VS Code, Edge e
   OneDrive). Resolvido em parte: prioridade **alta** do processo, 4 threads (12 era pior), temperatura
   fixa, sem timestamps e contexto genérico em pt-BR → **~4–6 s**. Benchmark nas gravações: small é bem
   mais preciso que base ("Olá, Robô" vs "Vamos por tudo bem"); base leva ~2–3 s.
6. **Câmera escura:** a imagem está quase toda preta mesmo após 8 s acordada. Confira fisicamente se há
   algo na frente da lente e a orientação (`ferramentas/exemplo_capture.jpg` é de ontem, quando funcionava).
7. **Local do projeto:** `C:\Users\Henrique\robo_esp32` (caminho curto, **fora do OneDrive**). A pedido
   do usuário, **nada deste projeto deve ficar no OneDrive da TOSOLVE/2Solve**; ele foi retirado de lá em
   2026-11-10 (a pasta "Relatório de estágio" do OneDrive tem outros projetos do usuário, que não fazem
   parte deste). O venv foi recriado aqui e funciona. `vad_filter` do Whisper continua desligado
   (onnxruntime não foi testado).

---

## 8. Resultados dos autotestes de conversa (`ponte/testes/autoteste*.log`)

Método: com o microfone ao lado do alto-falante, `robo.py --autoteste "f1|f2|..."` toca cada frase
com a voz Maria **pelo alto-falante da placa** (como se fosse uma pessoa), e o robô ouve, transcreve,
pergunta ao Claude e responde em voz.

| Rodada | Ouviu certo | Tempo fim da fala → resposta | Observação |
|---|---|---|---|
| 1 | 2 de 4 + 1 parcial | 8,9–10,9 s | início cortado; 1 frase não detectada |
| 2 (pré-roll 500 ms, amplificador aquecendo) | **6 de 6** (2 com erro leve) | 10–27 s | Whisper lento (12 threads) |
| 3 (Whisper ajustado, frases novas) | 5 de 6 | **7,6–12 s** | disparos falsos: o robô ouviu e respondeu a própria voz (§9.1) |

Exemplo real: "Qual é a capital do Brasil?" → *"A capital do Brasil é Brasília, Rapaz bonito e
inteligente…"* + gesto "sim". Tempo típico: **~5 s ouvir + ~3,5 s pensar (Haiku) ≈ 8–9 s**.

---

## 9. Pendências (em ordem de prioridade)

### 9.1 Disparos falsos do detector de voz (o robô ouvindo a si mesmo)
No autoteste 3, as frases sem sentido do final ("A gente pode não quantificar o que a gente processa",
"A automática é expurviada"…) eram **o robô ouvindo a própria voz e respondendo**: o usuário confirmou
que ninguém falou. Motivo: no autoteste a placa fica com `echo 1` (mic não fica mudo enquanto o
alto-falante toca), e o mic estava colado no alto-falante; o fim da fala e o eco do ambiente passavam do
mudo de 0,4 s do PC. No uso normal (`echo 0`) a placa também deixa o mic mudo durante a fala + 0,3 s, o
que diminui o problema, mas com mic e alto-falante muito próximos ele ainda pode ocorrer. Esses trechos
viram "" ou frases sem sentido no Whisper e ocupam ~5 s cada, atrasando a próxima fala real.
O usuário pediu para **não corrigir agora** (foi causado pela posição do mic). Quando for tratar:
- afastar o microfone do alto-falante (ou virá-los em direções opostas);
- aumentar o tempo de mudo após o robô falar (hoje 0,4 s no PC + 0,3 s na placa) para ~1 s;
- descartar trechos com menos de ~0,8 s de voz efetiva;
- reativar o VAD Silero do faster-whisper (`pip install onnxruntime`, `vad_filter=True`);
- **palavra de ativação** ("Robô, …") ou responder só quando o rosto do dono estiver na câmera;
- descartar transcrições com `avg_logprob` baixo (já existe o filtro; dá para endurecer).

### 9.2 Câmera escura
Ver §7.6. Depois de resolver, testar "o que você está vendo?" com uma pessoa na frente.

### 9.3 Servos
Ligar os servos (fonte 5 V externa), testar `gesture`, `servo`, rastreio e sinais `PAN_DIR`/`TILT_DIR`.

### 9.4 Latência
Hoje ~8–12 s. Próximos passos: começar a transcrever enquanto a pessoa ainda fala (streaming), sintetizar
e tocar a 1ª frase da resposta enquanto o resto é gerado, `--whisper base` se a precisão bastar, e
reiniciar o processo do Claude a cada N turnos (o contexto cresce indefinidamente).

### 9.5 Reconhecimento ao vivo
Testar com outra pessoa (deve ser "Creatura") e ajustar `MATCH_THRESHOLD`.

---

## 10. Como rodar

```
cd ponte
.venv\Scripts\python robo.py                     # conversa por voz, pelo cabo USB (padrão)
.venv\Scripts\python robo.py --logs-placa        # mostra também os logs da placa
.venv\Scripts\python robo.py --texto             # digitar em vez de falar
.venv\Scripts\python robo.py --modelo sonnet     # mais esperto, mais lento
.venv\Scripts\python robo.py --whisper base      # transcrição mais rápida, menos precisa
.venv\Scripts\python robo.py --salvar-audio      # grava as falas ouvidas em ponte/gravacoes/
.venv\Scripts\python robo.py --autoteste "Oi robô|Que horas são?"   # robô testa a si mesmo
.venv\Scripts\python robo.py --transporte wifi --ip 192.168.15.137  # pelo Wi-Fi (não recomendado)
```

Para recriar o ambiente Python, se a pasta for movida de novo:

```
cd ponte
rmdir /s /q .venv
python -m venv .venv
.venv\Scripts\python -m pip install faster-whisper numpy pyserial
```

Página da câmera (opcional): na rede conhecida, o IP aparece no `robo.py` ao iniciar (no escritório foi
`http://192.168.15.137/`). Em qualquer outro lugar: rede aberta **"Robo-ESP32"** → `http://192.168.4.1/` (§6.4).

---

## 11. Levar para outra máquina

O projeto vai continuar numa **outra máquina** (VS Code + Claude Code), pelo GitHub:

```
git clone https://github.com/popliosemigod/Mini_Jaspy.git C:\Mini_Jaspy
```

- O repositório é **público**: senhas, fotos de rosto, transcript bruto e áudios ficam fora (§6.5).
  Se precisar deles, leve por um meio pessoal. **Não use o OneDrive da TOSOLVE/2Solve** (pedido do usuário).
- Clone num caminho **curto, sem acentos e fora do OneDrive**: caminhos longos já quebraram bibliotecas
  Python neste projeto.
- Ao terminar mudanças: `git add -A && git commit && git push`; na outra máquina, `git pull`.
  Antes de comitar, confira que nenhuma senha entrou (`git diff --cached | findstr /i senha`).

Pré-requisitos da máquina nova:

| Item | Para quê | Obrigatório? |
|---|---|---|
| **Windows** | a voz usa o System.Speech do Windows | sim (em outro SO, trocar o TTS em `synthesize()`) |
| Voz **Microsoft Maria (pt-BR)** | a fala do robô | sim (Configurações → Hora e idioma → Fala → adicionar Português (Brasil)) |
| **Python 3.11+** no PATH | a ponte | sim (foi testado com 3.14.6) |
| **Claude Code** instalado e logado (`claude` no PATH) | o cérebro (`claude -p`) | sim |
| Driver **CH343** (USB-serial da placa) | enxergar a placa | normalmente o Windows instala sozinho |
| **PlatformIO** (extensão do VS Code) | só para **regravar** o firmware | só se for mexer no firmware |
| Internet | Claude + 1º download do Whisper (~480 MB) | sim |

Passo a passo:

1. Clonar o repositório e ligar a placa no USB.
2. Rodar **`instalar.bat`** (cria `ponte\.venv`, instala faster-whisper/numpy/pyserial, baixa o Whisper
   small e verifica Claude, voz Maria, PlatformIO e a porta da placa).
3. Abrir a **pasta raiz** no VS Code e, no Claude Code, mandar: *"Leia o RELATORIO_CONTINUIDADE.md e o
   CLAUDE.md, me resuma o estado do projeto e as pendências."*
4. Testar: `ponte\.venv\Scripts\python ponte\robo.py`.

A placa já está gravada com um firmware que **funciona para conversar**, mas **sem** o Wi-Fi próprio
(§6.4): grave de novo para tê-lo. A porta COM vai ser outra na máquina nova: o `robo.py` acha a placa sozinho (pelo CH343), e o `platformio.ini` está sem
porta fixa (detecção automática). A primeira compilação na máquina nova baixa o toolchain ESP32
(~1 GB) e leva alguns minutos.

## 13. O que mudou em 11/11/2026 (máquina do laboratório Jaspy, `C:\Mini_Jaspy`)

Branch local `autoprogramacao` (não publicado). Firmware compilado com o PlatformIO **isolado** em
`C:\pio-mini` (`ponte/maquina.json`): o Arduino 2.0.17 deste projeto tem o mesmo nome de pacote do
Arduino 3.x de outros projetos da máquina e o sobrescreveria.

### 13.1 Rostos aprendidos pela câmera
Quem aparece como "Creatura" diz o nome ("meu nome é Ana") → o cérebro manda `"aprender": "Ana"` →
a placa tira **5 amostras** (só com **um** rosto no quadro, largura ≥ 50 px, prazo 30 s). Depois, a cada
30 s em que reconhece a pessoa com certeza média (0,60–0,80), junta mais uma (até 15 por pessoa): aprende
aos poucos. Amostras (vetor de 512 números) na **PSRAM** e em `/rostos.bin` (LittleFS na partição spiffs,
sobrevive a desligar e a regravar). Comandos USB: `aprender <nome>`, `esquecer <nome>`, `pessoas`.
**Lição:** com o LittleFS montado o tempo todo, o maior bloco de RAM interna caiu de 35,8 para 30,7 KB e a
câmera não acordava mais (`esp_camera_init 0xffffffff`). Agora monta, lê/grava e desmonta (34,8 KB).

### 13.2 Quadro girado
O detector só acha rosto **em pé**, e a câmera está **de lado** (~90°): nada era achado. Sem rosto por
3 quadros, o próximo é girado 90° para um lado, depois para o outro; achou, fica nele. O pescoço segue no
quadro da câmera (ponto desgirado). Medido: "rosto achado com o quadro girado anti-horário", dono
0,57–0,79. Se a câmera for montada em pé, nada muda (o modo normal é tentado primeiro).

### 13.3 Pescoço, hora
Pescoço: 20°/s seguindo o rosto e 45°/s nos gestos (eram 125 e 300), freando ao chegar; passos dos gestos
de 800 ms. O cérebro recebe a data **e a hora**. `stats` traz `pan`, `tilt` e `ram_maior_bloco` ao vivo.

### 13.4 Autoprogramação por voz
"Jaspy, aprende a…" → `"programar": "<pedido>"` → `ponte/autoprogramacao.py` abre uma sessão do Claude Code
(Opus) que **só lê, edita e compila** (nada de gravar a placa, pinagem, senhas ou fotos) → o robô confere
(recompila / py_compile) e pergunta "Posso gravar em mim?". Só grava com **palavra explícita**
("pode gravar"; um "não tá bom" solto já descartou uma mudança por engano) → `supervisor.py` grava, espera
a placa responder e, se não voltar, regrava `backup_placa/firmware_bom.bin` e desfaz o commit. Cada mudança
aceita vira o commit `auto: <pedido>`.

### 13.5 Nome, silêncio e comandos ensinados (decididos no `robo.py`, sem o Claude)
- **"Jaspy, …"**: o que vem depois do nome é ordem direta; só "Jaspy" → "Pode falar" e espera 12 s.
- **Silêncio oficial**: "cala a boca", "fica quieto", "silêncio", "para de falar", "psiu"… → acena e fica
  **mudo de verdade** (nem chama o Claude, anúncios esperam) até ouvir **"Jaspy"**.
- **Comandos ensinados**: "Jaspy, a partir de agora, quando eu disser X, faça Y" → `ponte/comandos.json`
  (local, fora do git), lembrado a cada mensagem; "esquece o comando X" apaga.

### 13.6 Voz e chiado (em aberto)
Voz neural do edge-tts (`en-US-BrianMultilingualNeural`, escolhida de ouvido; `--voz` troca; sem internet
volta para a Maria). O dono ouve **chiado** com qualquer voz → está no caminho do som, não na voz. Teste de
11/11 pelo USB (Wi-Fi ligado/desligado × volume normal/dobrado) **sem resposta ainda**: se o Wi-Fi desligado
limpar, o rádio puxa corrente do 5 V do MAX98357A (separar a alimentação ou desligar o Wi-Fi ao falar); se
o volume dobrado limpar, subir `SPK_VOLUME` (hoje 0,25).

### 13.7 Funcionar sozinho, com log de tudo
`ponte/supervisor.py`: espera a placa ser plugada, religa o robô se cair (5→60 s), trata desplugar
(`robo.py` sai com 3), grava as mudanças da autoprogramação, acha o Claude Code na extensão do VS Code e
**grava tudo** em `ponte/logs/robo_AAAA-MM-DD.log` (30 dias). Uma instância só.
- Com janela: `rodar_robo.bat` (local) ou `ponte\.venv\Scripts\python ponte\supervisor.py --logs-placa`.
- **Início automático** a cada login (escondido): `ponte\.venv\Scripts\python ferramentas\inicio_automatico.py`
  (`--tirar` desliga). Tem de ser rodado pelo dono (cria atalho na pasta Inicializar).

### 13.8 O Jaspy apresenta seminário (11/11/2026, ✅ apresentado)
`ferramentas/apresentar.py` + `apresentacao/roteiro.json`: slides em tela cheia no PC, o Jaspy fala cada slide
pelo alto-falante (com gestos) e passa sozinho ao terminar; no fim, `--conversar-depois` liga o robô para o
debate. Falas geradas antes (voz neural, 2 tentativas de 20 s por trecho; Maria só no que falhar), cache em
`apresentacao/audio/`. Imagens dos slides em `apresentacao/slides/` (fora do git: fotos de bancada).
**Resultado:** seminário "Do Protótipo ao Chão de Fábrica" apresentado inteiro, 6 slides, 26 trechos,
**5,8 min**, e o dono aprovou ("foi perfeito"). Volume no máximo (comando `volume 0-100` na placa).

### 13.9 Troca da placa para a XIAO ESP32-S3 Sense (23/11/2026, 🟡 gravada e ensaiada; enlace com perda sob carga)
Pedido do dono: trocar o microcontrolador pela XIAO Sense (câmera e microfone na placa), mantendo **dois
servos** no pescoço. Segundo ambiente `xiao` em `cam/platformio.ini` (o `esp32s3cam` continua o padrão até
a XIAO ser validada); pinos em `cam/src/placa.h`; ligação, diferenças e roteiro de ensaio em
[`cam/PINAGEM_XIAO.md`](cam/PINAGEM_XIAO.md). Pontos que mudam: microfone **PDM** (GPIO41/42), USB **nativo**
(`303A:1001`, o PC reconhece as duas), flash de 8 MB com tabela própria (a padrão não comporta os 4,4 MB),
servos em **GPIO4/5** (38/39 são da câmera). A autoprogramação e o supervisor passam `-e` por
`PLACA_ENV` (`ponte/maquina.json`). **Medido** (ensaio em [`cam/PINAGEM_XIAO.md`](cam/PINAGEM_XIAO.md)): câmera OV3660
(acorda em 372 ms), microfone PDM e comandos ok; o USB-Serial-JTAG (HWCDC) perde bytes sob carga e o TinyUSB
(`-e xiao_tusb`) não regrava sozinho. **Pendente na bancada:** alto-falante, servos, energia, ganho do microfone
com voz, e escolher entre aceitar a perda, TinyUSB com BOOT apertado ou um adaptador USB-UART em D6/D7.

## 12. Cadastro facial com outras fotos

1. Fotos `.jpeg` em `fotos_cadastro/`.
2. `python ferramentas/converter_fotos.py fotos_cadastro cam/data` (Python do sistema, que tem Pillow).
3. Se mudar a quantidade: ajustar `board_build.embed_files` (`platformio.ini`) e `FACE_SYM`/`ENROLL_PHOTOS`/`N_TEST` (`main.cpp`).
4. Gravar e conferir nos logs: "foto N: OK / espelhada: OK".
