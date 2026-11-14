"""Musica do Jaspy: acha um arquivo de audio numa pasta local e toca sem travar a conversa.

Onde ele procura (nessa ordem):
  - ponte/musicas/                 (fora do git: musica tem direito autoral e o repositorio e publico)
  - "MUSICAS" no ponte/maquina.json (uma pasta ou uma lista de pastas desta maquina)
  - a pasta Musicas do Windows (~/Music)
Formatos: mp3, flac, wav, ogg (decodificados pelo miniaudio, o mesmo da voz neural; sem ffmpeg).

Onde toca:
  - pela placa (link USB): PCM 16 kHz mono nos quadros 'B'/'A'/'E' de sempre, no ritmo do tempo real
    (no maximo ~1 s adiantado: a fila da placa tem 20 s e mandar mais rapido encheria e travaria o link);
  - pelo alto-falante do PC, se a placa nao puder (--falar-no-pc, transporte wifi ou sem placa).
Enquanto a musica toca, o eco da placa fica ligado (echo 1): o microfone continua ouvindo, para o dono
poder dizer "Jaspy, para a musica". Quando o robo fala, a musica pausa e volta depois.
"""
import json, os, re, threading, time, unicodedata

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
EXTS = (".mp3", ".flac", ".wav", ".ogg")
RATE = 16000
GANHO_PADRAO = 0.35   # a placa fica com volume 100 (pedido do dono): musica bem mais baixa que a voz
GANHO_MIN, GANHO_MAX = 0.05, 0.7


def pastas():
    p = [os.path.join(HERE, "musicas")]
    try:
        with open(os.path.join(HERE, "maquina.json"), encoding="utf-8") as f:
            m = json.load(f).get("MUSICAS")
        if isinstance(m, str):
            m = [m]
        if isinstance(m, list):
            p += [os.path.expandvars(os.path.expanduser(str(x))) for x in m]
    except (OSError, ValueError, AttributeError):
        pass
    p.append(os.path.join(os.path.expanduser("~"), "Music"))
    vistos, out = set(), []
    for x in p:
        k = os.path.normcase(os.path.abspath(x))
        if k not in vistos and os.path.isdir(x):
            vistos.add(k); out.append(x)
    return out


def _norm(s):
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("'", "").replace("&", " e ")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


_VAZIAS = {"a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "the", "musica", "cancao", "toca", "tocar",
           "toque", "bota", "coloca", "poe", "por", "favor", "pra", "para", "mim", "uma", "um", "som", "mp3"}


def listar(limite=2000):
    """[(caminho, nome legivel)] das musicas encontradas (o nome inclui a pasta do artista, se houver)."""
    out = []
    for raiz in pastas():
        for d, _, arqs in os.walk(raiz):
            for a in sorted(arqs):
                if a.lower().endswith(EXTS):
                    c = os.path.join(d, a)
                    rel = os.path.relpath(c, raiz)
                    out.append((c, os.path.splitext(rel)[0].replace(os.sep, " - ")))
                    if len(out) >= limite:
                        return out
    return out


def achar(pedido):
    """O arquivo que melhor combina com o pedido ("november rain guns n roses"), ou None."""
    import difflib
    q = [w for w in _norm(pedido).split() if w not in _VAZIAS]
    if not q:
        return None
    melhor, nota_melhor = None, 0.0
    for c, nome in listar():
        n = _norm(nome)
        palavras = set(n.split())
        acertos = sum(1 for w in q if w in palavras or (len(w) > 3 and w in n))
        nota = acertos / len(q) + 0.3 * difflib.SequenceMatcher(None, " ".join(q), n).ratio()
        if nota > nota_melhor:
            melhor, nota_melhor = c, nota
    # pelo menos metade das palavras do pedido no nome do arquivo (ou um nome muito parecido)
    return melhor if nota_melhor >= 0.5 else None


def nome_de(caminho):
    return os.path.splitext(os.path.basename(caminho))[0]


class Musica:
    """Um tocador so: tocar() troca a musica, parar() para, pausa()/retoma() abrem espaco para a fala."""

    def __init__(self, robot, no_pc, ganho=GANHO_PADRAO, log=print):
        self.robot = robot
        # pela placa so pelo link USB (o UsbRobot tem send/cmd); senao, no alto-falante do PC
        self.na_placa = (not no_pc) and robot is not None and hasattr(robot, "send")
        self.ganho = min(max(float(ganho), GANHO_MIN), GANHO_MAX)
        self.log = log
        self.atual = None              # caminho da musica tocando
        self._parar = threading.Event()
        self._pausa = threading.Event()
        self._pausado = threading.Event()  # o tocador confirmou que parou de mandar audio
        self._th = None
        self._lk = threading.Lock()

    @property
    def tocando(self):
        return self._th is not None and self._th.is_alive()

    def tocar(self, caminho):
        with self._lk:
            self._para_thread()
            self._parar.clear(); self._pausa.clear(); self._pausado.clear()
            self.atual = caminho
            alvo = self._na_placa if self.na_placa else self._no_pc
            self._th = threading.Thread(target=self._roda, args=(alvo, caminho), daemon=True)
            self._th.start()
        self.log(f"[musica] tocando \"{nome_de(caminho)}\" ({'placa' if self.na_placa else 'PC'}, "
                 f"volume {round(self.ganho * 100)}%)")

    def parar(self):
        with self._lk:
            tinha = self.tocando
            self._para_thread()
            self.atual = None
        if tinha:
            self.log("[musica] parada")
        return tinha

    def volume(self, delta):
        self.ganho = min(max(self.ganho + delta, GANHO_MIN), GANHO_MAX)
        self.log(f"[musica] volume {round(self.ganho * 100)}%")

    def pausa(self):
        """Antes de o robo falar: para de mandar audio e corta o que estava na fila da placa."""
        if not self.tocando:
            return False
        self._pausado.clear()
        self._pausa.set()
        self._pausado.wait(1.5)
        return True

    def retoma(self):
        self._pausa.clear()

    # ---------------- por dentro ----------------
    def _para_thread(self):
        if self._th is not None and self._th.is_alive():
            self._parar.set(); self._pausa.clear()
            self._th.join(3)
        self._th = None

    def _roda(self, alvo, caminho):
        try:
            alvo(caminho)
        except Exception as e:
            self.log(f"[musica] erro ao tocar \"{nome_de(caminho)}\": {e}")
        finally:
            if self.na_placa:
                try:
                    if self._parar.is_set():
                        self.robot.send("B"); self.robot.send("E")  # B zera a fila da placa, E encerra
                    self.robot.cmd("echo 0")                         # mic volta a ficar mudo quando o robo fala
                except Exception:
                    pass
            if not self._parar.is_set():
                self.log(f"[musica] fim de \"{nome_de(caminho)}\"")

    def _aplica(self, amostras):
        a = np.frombuffer(amostras, dtype=np.int16).astype(np.float32) * self.ganho
        return np.clip(a, -32768, 32767).astype(np.int16)

    def _na_placa(self, caminho):
        import miniaudio
        PKT = 320  # 20 ms a 16 kHz
        src = miniaudio.stream_file(caminho, output_format=miniaudio.SampleFormat.SIGNED16, nchannels=1,
                                    sample_rate=RATE, frames_to_read=PKT)
        r = self.robot
        r.cmd("echo 1")  # mic aberto durante a musica: o dono consegue mandar parar
        r.send("B")
        t0, k = time.time(), 0
        for bloco in src:
            if self._parar.is_set():
                return
            if self._pausa.is_set():
                r.send("B"); r.send("E")        # corta na hora o que estava na fila da placa
                self._pausado.set()
                while self._pausa.is_set() and not self._parar.is_set():
                    time.sleep(0.05)
                if self._parar.is_set():
                    return
                r.cmd("echo 1")                 # a fala pode ter deixado o eco como estava; garante
                r.send("B")
                t0, k = time.time(), 0
            # ritmo do tempo real, no maximo 1 s adiantado (fila da placa: 20 s)
            while k * 0.02 > (time.time() - t0) + 1.0:
                if self._parar.is_set() or self._pausa.is_set():
                    break
                time.sleep(0.01)
            r.send("A", self._aplica(bloco).tobytes())
            k += 1
        r.send("E")
        # espera a placa tocar o que ficou na fila (ate ~1 s), sem atropelar a proxima fala
        fim = time.time() + 1.5
        while time.time() < fim and not self._parar.is_set():
            if self._pausa.is_set():   # o robo quer falar: o resto da fila e so o finalzinho da musica
                self._pausado.set()
                return
            time.sleep(0.05)

    def _no_pc(self, caminho):
        import miniaudio
        sr, ch = 44100, 2
        src = miniaudio.stream_file(caminho, output_format=miniaudio.SampleFormat.SIGNED16, nchannels=ch,
                                    sample_rate=sr, frames_to_read=1024)
        acabou = threading.Event()

        def gerador():
            pedidos = yield b""
            while True:
                if self._parar.is_set():
                    acabou.set(); return
                if self._pausa.is_set():
                    self._pausado.set()
                    pedidos = yield bytes(pedidos * ch * 2)
                    continue
                try:
                    bloco = src.send(pedidos)
                except StopIteration:
                    acabou.set(); return
                pedidos = yield self._aplica(bloco).tobytes()

        g = gerador(); next(g)
        dev = miniaudio.PlaybackDevice(output_format=miniaudio.SampleFormat.SIGNED16, nchannels=ch, sample_rate=sr)
        try:
            dev.start(g)
            while not acabou.is_set() and not self._parar.is_set():
                time.sleep(0.1)
            time.sleep(0.3)
        finally:
            dev.close()
