"""
Ponte PC <-> robo ESP32-S3.

  ouvidos : microfone INMP441 da placa (porta 82)  -> Whisper (local) -> texto
  olhos   : foto da camera da placa (/capture) + reconhecimento facial (/faces)
  cerebro : Claude Code (`claude -p`, usa a sua conta Claude logada neste PC)
  boca    : voz Microsoft Maria (Windows) -> alto-falante MAX98357A da placa (porta 83)
  pescoco : servos pan/tilt (/servo, /gesture)

Uso:
  .venv\\Scripts\\python robo.py                 # conversa por voz
  .venv\\Scripts\\python robo.py --texto         # digita no teclado em vez de falar
  .venv\\Scripts\\python robo.py --ip 10.140.67.103 --modelo sonnet --falar-no-pc
"""
import argparse, base64, collections, concurrent.futures, io, json, os, queue, re, socket
import subprocess, sys, tempfile, threading, time, urllib.request, wave

import numpy as np

RATE = 16000
HERE = os.path.dirname(os.path.abspath(__file__))

SYSTEM_PROMPT = """Voce e um pequeno robo de mesa simpatico, curioso e bem-humorado, que conversa em portugues do Brasil.
Seu corpo: uma camera (seus olhos), um microfone (seus ouvidos), um alto-falante (sua boca) e um pescoco com dois servos.

A cada mensagem voce recebe:
- o que a pessoa falou (transcrito automaticamente; pode ter pequenos erros, interprete com bom senso);
- uma foto atual da sua camera, ja com o reconhecimento facial desenhado:
  quadrado VERDE "Rapaz bonito e inteligente" = o seu dono, a pessoa que voce conhece;
  quadrado VERMELHO "Creatura" = alguem que voce nao conhece;
- um resumo do reconhecimento facial.

Chame o seu dono de "Rapaz bonito e inteligente" de vez em quando e trate pessoas desconhecidas, de brincadeira, por "Creatura".
Use a foto quando for relevante (o que a pessoa esta mostrando, onde ela esta etc.), sem descrever a imagem toda hora.

Responda SEMPRE e SOMENTE com um JSON valido, sem nada antes ou depois:
{"fala": "...", "gesto": "nenhum", "olhar": null}
- "fala": o que voce vai dizer em voz alta. Curto e natural (1 a 3 frases), sem emojis, sem markdown, sem listas.
- "gesto": um de "sim" (acenar com a cabeca), "nao" (balancar a cabeca), "curioso" (inclinar a cabeca), "centro" (olhar para frente) ou "nenhum".
- "olhar": null, ou {"pan": 20-160, "tilt": 50-130} para virar o pescoco para uma direcao (pan 90/tilt 90 = frente; pan maior = esquerda; tilt maior = baixo).
  Normalmente deixe null: o pescoco ja segue o rosto da pessoa sozinho.
"""

# frases que o Whisper costuma "inventar" em silencio/ruido
HALLUCINATIONS = ["amara.org", "legendas pela comunidade", "obrigado por assistir", "inscreva-se",
                  "legenda adriana", "sous-titres", "subtitles by"]


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ------------------------------------------------------------------ placa
class Robot:
    def __init__(self, host):
        self.host = host

    def get(self, path, timeout=3):
        with urllib.request.urlopen(f"http://{self.host}{path}", timeout=timeout) as r:
            return r.read()

    def status(self):
        try:
            return json.loads(self.get("/faces"))
        except Exception:
            return None

    def capture(self):
        try:
            return self.get("/capture", timeout=5)
        except Exception as e:
            log("[olhos] sem foto:", e)
            return None

    def gesture(self, g):
        try: self.get(f"/gesture?g={g}")
        except Exception: pass

    def look(self, pan, tilt):
        try: self.get(f"/servo?pan={int(pan)}&tilt={int(tilt)}")
        except Exception: pass

    def play(self, pcm: bytes):
        """Envia a fala por UDP (porta 83) em pacotes [seq][20 ms de PCM], num ritmo um pouco mais
        rapido que o tempo real; a placa monta um colchao de 300 ms antes de tocar."""
        PKT = 640
        END = (0xFFFFFFFF).to_bytes(4, "little")
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            t0 = time.time()
            for seq, i in enumerate(range(0, len(pcm), PKT)):
                while seq * 0.02 > (time.time() - t0) * 1.5 + 0.5:  # no maximo 0,5 s adiantado
                    time.sleep(0.005)
                s.sendto(seq.to_bytes(4, "little") + pcm[i:i + PKT], (self.host, 83))
            for _ in range(3):
                s.sendto(END, (self.host, 83))
                time.sleep(0.02)

    def wake(self, ms=20000):
        threading.Thread(target=lambda: self._try(f"/wake?ms={int(ms)}"), daemon=True).start()

    def echo(self, on):
        self._try(f"/config?echo={1 if on else 0}")

    def _try(self, path):
        try: self.get(path)
        except Exception: pass

    def mic_chunks(self):
        return MicUDP(self.host).chunks()

    def wait_silence(self, max_wait):
        """Espera a placa terminar de tocar (campo speaking do /faces)."""
        end = time.time() + max_wait
        time.sleep(0.4)
        while time.time() < end:
            st = self.status()
            if st is not None and not st.get("speaking"):
                return
            time.sleep(0.2)


class MicUDP:
    """Recebe o microfone da placa por UDP (porta 82): manda HELLO a cada 1 s e recebe
    pacotes [seq uint32][PCM16]. Pacotes perdidos viram silencio (mantem o tempo do audio)."""

    def __init__(self, host):
        self.host = host
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("", 0))
        self.sock.settimeout(1.0)
        self.received = self.lost = 0

    def chunks(self):
        next_seq, last_hello, silent = None, 0.0, 0
        while True:
            if time.time() - last_hello > 1.0:
                self.sock.sendto(b"HELLO", (self.host, 82))
                last_hello = time.time()
            try:
                d, _ = self.sock.recvfrom(4096)
            except socket.timeout:
                silent += 1
                if silent > 5:
                    raise ConnectionError("a placa nao esta enviando audio")
                continue
            silent = 0
            if len(d) < 6:
                continue
            seq = int.from_bytes(d[:4], "little")
            pcm = d[4:]
            if next_seq is not None and seq < next_seq:
                if next_seq - seq > 100:  # placa reiniciou a contagem
                    next_seq = None
                else:
                    continue  # duplicado/atrasado
            if next_seq is not None and seq > next_seq:
                gap = min(seq - next_seq, 25)
                self.lost += gap
                yield bytes(len(pcm) * gap)
            self.received += 1
            next_seq = seq + 1
            yield pcm


def pc_network_hint():
    """Diz em qual rede Wi-Fi o PC esta (o erro mais comum e o PC voltar sozinho para outra rede)."""
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "(Get-NetConnectionProfile | Select -First 1 -Expand Name)"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        out = ""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80)); me = s.getsockname()[0]
    except Exception:
        me = "?"
    finally:
        s.close()
    return f"O PC esta na rede '{out or '?'}' com IP {me}."


def find_robot(ip=None):
    def ok(h):
        try:
            with urllib.request.urlopen(f"http://{h}/faces", timeout=1.5) as r:
                return "faces" in json.loads(r.read())
        except Exception:
            return False

    if ip:
        return ip if ok(ip) else None
    try:
        h = socket.gethostbyname("esp32cam.local")
        if ok(h):
            return h
    except Exception:
        pass
    # varre a rede local /24
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80)); me = s.getsockname()[0]
    except Exception:
        return None
    finally:
        s.close()
    base = me.rsplit(".", 1)[0]
    log(f"Procurando a placa na rede {base}.0/24 ...")

    def probe(i):
        h = f"{base}.{i}"
        try:
            with socket.create_connection((h, 80), timeout=0.4):
                pass
        except Exception:
            return None
        return h if ok(h) else None

    with concurrent.futures.ThreadPoolExecutor(64) as ex:
        for r in ex.map(probe, range(1, 255)):
            if r:
                return r
    return None


# ------------------------------------------------------------------ ouvidos
class Ears(threading.Thread):
    """Le o microfone da placa (USB ou UDP) e separa as frases por deteccao de voz.
    on_speech_start() e chamado assim que a voz comeca (o robo acorda a camera nessa hora)."""

    FRAME = 480  # 30 ms

    def __init__(self, robot, out_q, show_level=False, on_speech_start=None):
        super().__init__(daemon=True)
        self.robot, self.out_q, self.show_level = robot, out_q, show_level
        self.on_speech_start = on_speech_start or (lambda: None)
        self.muted_until = 0.0
        self.muted = False

    def mute(self, on):
        self.muted = on
        if not on:
            self.muted_until = time.time() + 0.4

    def run(self):
        while True:
            try:
                log(f"[ouvidos] ouvindo o microfone da placa ({self.robot.host})")
                self._listen(self.robot.mic_chunks())
            except Exception as e:
                log("[ouvidos] reconectando ao microfone:", e)
                time.sleep(2)

    def _listen(self, chunks):
        # Detector de voz por energia com ruido de fundo MEDIDO (o INMP441 com o ganho atual tem
        # ruido ~2000 de RMS; um valor fixo fazia o detector achar que havia fala o tempo todo).
        buf = b""
        calib = []                                  # primeiros ~0,6 s: mede o ruido
        noise = None
        hist = collections.deque(maxlen=200)        # ultimos 6 s de RMS (recalibracao)
        pre = collections.deque(maxlen=17)          # 500 ms antes da fala (nao corta a 1a silaba)
        speech, active, loud, quiet = [], False, 0, 0
        last_show = 0
        for data in chunks:
            buf += data
            while len(buf) >= self.FRAME * 2:
                fr = np.frombuffer(buf[: self.FRAME * 2], dtype=np.int16)
                buf = buf[self.FRAME * 2:]
                if self.muted or time.time() < self.muted_until:
                    speech, active, loud, quiet = [], False, 0, 0
                    pre.clear()
                    continue
                f32 = fr.astype(np.float32)
                rms = float(np.std(f32))  # sem o nivel medio (DC) do trecho
                if rms < 1.0:
                    continue  # silencio digital (pacote perdido / mic mudo): nao conta para o ruido
                hist.append(rms)
                if noise is None:
                    calib.append(rms)
                    if len(calib) >= 20:
                        noise = float(np.median(calib))
                        log(f"[ouvidos] ruido de fundo medido: {noise:.0f}")
                    continue
                if self.show_level and time.time() - last_show > 0.25:
                    last_show = time.time()
                    print(f"\r nivel {rms:7.0f}  ruido {noise:6.0f}  {'#' * min(60, int(rms / max(noise, 1) * 5))}     ",
                          end="", flush=True)
                start_thr = max(noise * 2.5, 150)
                stop_thr = max(noise * 1.7, 100)
                if not active:
                    noise = 0.98 * noise + 0.02 * min(rms, start_thr)  # acompanha o ambiente devagar
                    pre.append(fr)
                    loud = loud + 1 if rms > start_thr else 0
                    if loud >= 3:
                        active, speech, quiet = True, list(pre), 0
                        log(f"[ouvidos] voz detectada (nivel {rms:.0f}, ruido {noise:.0f})")
                        try:
                            self.on_speech_start()
                        except Exception:
                            pass
                else:
                    speech.append(fr)
                    quiet = quiet + 1 if rms < stop_thr else 0
                    dur = len(speech) * 0.03
                    if quiet >= 23 or dur > 12:  # 0,7 s de silencio ou 12 s de fala
                        if dur > 12:  # ficou "preso": provavelmente o ruido mudou -> recalibra
                            noise = max(float(np.percentile(hist, 20)), 50.0)
                            log(f"[ouvidos] recalibrando ruido de fundo: {noise:.0f}")
                        if dur - quiet * 0.03 >= 0.5:
                            self.out_q.put((np.concatenate(speech), time.time()))
                        active, speech, loud, quiet = False, [], 0, 0
                        pre.clear()


class Transcriber:
    def __init__(self, size):
        from faster_whisper import WhisperModel
        log(f"[ouvidos] carregando Whisper '{size}' (na primeira vez ele e baixado)...")
        self.model = WhisperModel(size, device="cpu", compute_type="int8", cpu_threads=4,
                                  download_root=os.path.join(HERE, "modelos"))
        log("[ouvidos] Whisper pronto")

    def __call__(self, pcm):
        a = pcm.astype(np.float32) / 32768.0
        peak = float(np.max(np.abs(a))) or 1.0
        a = a * (0.9 / peak)
        # temperatura fixa (sem re-decodificar) + sem timestamps + contexto generico: ~5 s no i5-1235U
        segs, _ = self.model.transcribe(a, language="pt", beam_size=1, vad_filter=False, temperature=0.0,
                                        without_timestamps=True, condition_on_previous_text=False,
                                        initial_prompt="Conversa informal em português do Brasil com um robô de mesa.")
        text = " ".join(s.text.strip() for s in segs if s.no_speech_prob < 0.6 and s.avg_logprob > -1.0).strip()
        if any(h in text.lower() for h in HALLUCINATIONS):
            return ""
        return text


# ------------------------------------------------------------------ cerebro
class Brain:
    def __init__(self, model):
        self.model = model
        self.proc = None

    def _start(self):
        cmd = ["claude", "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
               "--tools", "", "--no-session-persistence", "--model", self.model, "--system-prompt", SYSTEM_PROMPT]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     text=True, encoding="utf-8", cwd=HERE)
        log(f"[cerebro] Claude ({self.model}) iniciado")

    def ask(self, heard, jpeg, faces):
        if self.proc is None or self.proc.poll() is not None:
            self._start()
        if faces and faces.get("list"):
            who = ", ".join(f"{f['name']} ({round(f['sim'] * 100)}%)" for f in faces["list"])
        else:
            who = "nenhum rosto visivel"
        send_photo = bool(jpeg) and is_visual(heard)
        text = f'A pessoa disse: "{heard}"\nReconhecimento facial agora: {who}.'
        if not send_photo:
            text += "\n(Sem foto nesta mensagem: a foto so vem quando a pergunta e sobre o que voce ve. " \
                    "Nao comente sobre a camera.)"
        content = []
        if send_photo:
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                        "data": base64.b64encode(jpeg).decode()}})
        content.append({"type": "text", "text": text})
        msg = {"type": "user", "message": {"role": "user", "content": content}}
        try:
            self.proc.stdin.write(json.dumps(msg) + "\n")
            self.proc.stdin.flush()
            for line in self.proc.stdout:
                try:
                    j = json.loads(line)
                except ValueError:
                    continue
                if j.get("type") == "result":
                    return parse_reply(j.get("result") or "")
        except Exception as e:
            log("[cerebro] erro:", e)
        self.proc = None  # reinicia na proxima
        return {"fala": "Desculpa, meu cerebro deu uma travada. Pode repetir?", "gesto": "nenhum", "olhar": None}


VISUAL_WORDS = ("ve", "vê", "ver", "vendo", "enxerg", "olha", "camera", "câmera", "quem", "rosto", "cara",
                "mostr", "segurando", "na mao", "na mão", "cor", "aqui", "isso", "isto", "foto", "imagem",
                "pareço", "pareco", "estou", "bonito", "roupa", "camisa", "oculos", "óculos", "cabelo", "luz")


def is_visual(text):
    t = " " + text.lower() + " "
    return any(w in t for w in VISUAL_WORDS)


def parse_reply(txt):
    m = re.search(r"\{.*\}", txt, re.S)
    if m:
        try:
            j = json.loads(m.group(0))
            if isinstance(j, dict) and j.get("fala") is not None:
                return j
        except ValueError:
            pass
    return {"fala": txt.strip(), "gesto": "nenhum", "olhar": None}


# ------------------------------------------------------------------ boca
TTS_PS = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$t = [IO.File]::ReadAllText($args[0], [Text.Encoding]::UTF8)
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
try { $s.SelectVoice('Microsoft Maria Desktop') } catch {}
$s.Rate = [int]$args[2]
$f = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$s.SetOutputToWaveFile($args[1], $f)
$s.Speak($t)
$s.Dispose()
"""


def synthesize(text, rate=1):
    d = tempfile.mkdtemp(prefix="robo_tts_")
    tf, wf, pf = (os.path.join(d, n) for n in ("fala.txt", "fala.wav", "tts.ps1"))
    with open(tf, "w", encoding="utf-8") as f:
        f.write(text)
    with open(pf, "w", encoding="utf-8-sig") as f:
        f.write(TTS_PS)
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", pf, tf, wf, str(rate)],
                   check=True, capture_output=True)
    with wave.open(wf) as w:
        pcm = w.readframes(w.getnframes())
    return pcm, wf


def speak(robot, ears, text, volume, on_pc):
    if not text:
        return
    pcm, wf = synthesize(text)
    a = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) * volume
    pcm = np.clip(a, -32768, 32767).astype(np.int16).tobytes()
    dur = len(pcm) / 2 / RATE
    if ears: ears.mute(True)
    try:
        if on_pc or robot is None:
            import winsound
            winsound.PlaySound(wf, winsound.SND_FILENAME)
        else:
            robot.play(pcm)
            robot.wait_silence(dur + 3)
    except Exception as e:
        log("[boca] erro ao tocar:", e)
    finally:
        if ears: ears.mute(False)


# ------------------------------------------------------------------ principal
def look_and_gesture(robot, r):
    g = r.get("gesto") or "nenhum"
    if g != "nenhum":
        robot.gesture(g)
    o = r.get("olhar")
    if isinstance(o, dict) and "pan" in o and "tilt" in o:
        robot.look(o["pan"], o["tilt"])


def autotest_thread(robot, phrases, idle_ev, results):
    """Simula uma pessoa: toca cada frase no alto-falante da placa (o mic ao lado ouve) e espera o robo
    responder. Com eco ligado na placa o mic nao fica mudo enquanto o alto-falante toca."""
    time.sleep(3)
    robot.echo(True)
    for ph in phrases:
        idle_ev.wait(120)
        time.sleep(1.5)
        idle_ev.clear()
        log(f"[autoteste] tocando a frase: \"{ph}\"")
        pcm, _ = synthesize(ph)
        results.append({"frase": ph})
        robot.play(pcm)
        robot.wait_silence(len(pcm) / 2 / RATE + 3)
        if not idle_ev.wait(90):
            log("[autoteste] robo nao respondeu em 90 s")
            idle_ev.set()
    idle_ev.wait(120)
    robot.echo(False)
    log("[autoteste] FIM")
    results.append(None)


def high_priority():
    try:
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x80)  # HIGH
    except Exception:
        pass


def main():
    high_priority()
    ap = argparse.ArgumentParser(description="Robo ESP32-S3 com o Claude como cerebro")
    ap.add_argument("--transporte", default="usb", choices=["usb", "wifi"],
                    help="usb (padrao, cabo USB - recomendado) ou wifi (UDP/HTTP pela rede)")
    ap.add_argument("--porta", help="porta USB da placa (padrao: detecta o CH343)")
    ap.add_argument("--ip", help="IP da placa (so no transporte wifi; padrao: procura sozinho)")
    ap.add_argument("--modelo", default="haiku", help="modelo do Claude: haiku (rapido), sonnet, opus")
    ap.add_argument("--whisper", default="small", help="tamanho do Whisper: base, small, medium")
    ap.add_argument("--texto", action="store_true", help="digitar em vez de falar no microfone")
    ap.add_argument("--falar-no-pc", action="store_true", help="tocar a voz no alto-falante do PC")
    ap.add_argument("--volume", type=float, default=1.0,
                    help="ganho extra no PC (0.1 a 1.0); o volume base fica em SPK_VOLUME no firmware")
    ap.add_argument("--nivel", action="store_true", help="mostra o nivel do microfone (para calibrar)")
    ap.add_argument("--logs-placa", action="store_true", help="mostra os logs da placa (so USB)")
    ap.add_argument("--salvar-audio", action="store_true", help="salva cada fala ouvida em ponte/gravacoes/")
    ap.add_argument("--autoteste", help="frases separadas por | que o robo toca para si mesmo e responde")
    args = ap.parse_args()

    robot = None
    if args.transporte == "usb":
        try:
            from link_usb import UsbRobot
            robot = UsbRobot(args.porta, on_log=(lambda t: log("[placa]", t)) if args.logs_placa else None)
            st = robot.stats(3)
            if st is None:
                log(f"Porta {robot.port} aberta, mas a placa nao respondeu. Ela esta com o firmware novo?")
                sys.exit(1)
            log(f"Placa conectada pelo USB ({robot.port}). O robo funciona pelo cabo; o Wi-Fi so serve a pagina da camera.")
            if st.get("wifi"):
                log(f"  Pagina da camera: http://{st.get('ip')}/  (rede '{st.get('rede', '')}')")
            elif st.get("ap"):
                senha = st.get("ap_senha") or ""
                log(f"  Pagina da camera: conecte o celular na rede '{st.get('ap_rede')}' "
                    f"({'senha ' + repr(senha) if senha else 'aberta, sem senha'}) e abra http://{st.get('ap_ip')}/")
            else:
                log("  Pagina da camera: procurando rede Wi-Fi; se nao achar nenhuma conhecida em ~30 s, a placa "
                    "cria a rede propria aberta 'Robo-ESP32' (sem senha) -> http://192.168.4.1/")
        except SystemExit:
            raise
        except Exception as e:
            log("Nao consegui abrir a placa pelo USB:", e)
            log("  Feche outros programas usando a porta (monitor serial, PlatformIO) ou use --transporte wifi.")
            sys.exit(1)
    else:
        host = find_robot(args.ip)
        robot = Robot(host) if host else None
        if robot:
            log(f"Placa encontrada em http://{host}/")
        else:
            log("Placa NAO encontrada.")
            log("  " + pc_network_hint())
            log("  O PC precisa estar na MESMA rede Wi-Fi da placa (ou use o padrao: --transporte usb).")
            if not args.texto:
                sys.exit(1)
            log("Seguindo so com teclado + voz no PC (sem camera).")

    heard_q = queue.Queue()
    ears = None
    stt = None
    if not args.texto:
        stt = Transcriber(args.whisper)
        ears = Ears(robot, heard_q, args.nivel, on_speech_start=lambda: robot.wake(20000))
        ears.start()

    brain = Brain(args.modelo)
    brain._start()
    on_pc = args.falar_no_pc or robot is None

    idle_ev = threading.Event(); idle_ev.set()
    auto_results = []
    if args.autoteste and robot and not args.texto:
        threading.Thread(target=autotest_thread, daemon=True,
                         args=(robot, [p.strip() for p in args.autoteste.split("|") if p.strip()],
                               idle_ev, auto_results)).start()

    log("Pronto! " + ("Digite e aperte Enter (Ctrl+C sai)." if args.texto else "Pode falar (Ctrl+C sai)."))
    while True:
        seen = {}
        th = None
        try:
            if args.texto:
                heard = input("\nvoce> ").strip()
                t_end = time.time()
            else:
                while True:
                    try:
                        pcm, t_end = heard_q.get(timeout=1)
                        break
                    except queue.Empty:
                        if auto_results and auto_results[-1] is None:
                            raise KeyboardInterrupt
                idle_ev.clear()
                # foto e rostos em paralelo com a transcricao (a camera ja acordou quando a voz comecou)
                th = threading.Thread(target=lambda: seen.update(
                    jpeg=robot.capture() if robot else None, faces=robot.status() if robot else None))
                th.start()
                if args.salvar_audio:
                    os.makedirs(os.path.join(HERE, "gravacoes"), exist_ok=True)
                    with wave.open(os.path.join(HERE, "gravacoes", time.strftime("%H%M%S") + ".wav"), "wb") as w:
                        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(pcm.tobytes())
                t = time.time()
                heard = stt(pcm)
                if args.nivel: print()
                log(f"[ouvidos] ({time.time() - t:.1f}s) \"{heard}\"")
        except (KeyboardInterrupt, EOFError):
            break
        if not heard:
            idle_ev.set()
            continue
        if th is None:
            seen = {"jpeg": robot.capture() if robot else None, "faces": robot.status() if robot else None}
        else:
            th.join(10)
        t_stt = time.time()
        r = brain.ask(heard, seen.get("jpeg"), seen.get("faces"))
        t_brain = time.time()
        log(f"[cerebro] ({t_brain - t_stt:.1f}s) {json.dumps(r, ensure_ascii=False)}")
        if robot:
            look_and_gesture(robot, r)
        log(f"[tempo] fim da fala -> inicio da resposta: {time.time() - t_end:.1f}s "
            f"(ouvir+foto {t_stt - t_end:.1f}s, pensar {t_brain - t_stt:.1f}s)")
        if auto_results and auto_results[-1] is not None:
            auto_results[-1].update(ouviu=heard, resposta=r.get("fala", ""), latencia=round(time.time() - t_end, 1),
                                    foto=bool(seen.get("jpeg")))
        speak(robot, ears, r.get("fala", ""), args.volume, on_pc)
        idle_ev.set()

    if auto_results:
        log("[autoteste] RESULTADO:")
        for x in auto_results:
            if x:
                log(f"   frase: {x['frase']!r} | ouviu: {x.get('ouviu')!r} | latencia: {x.get('latencia')} s | "
                    f"foto: {x.get('foto')} | resposta: {x.get('resposta')!r}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
