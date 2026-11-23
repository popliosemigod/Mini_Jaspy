"""Link binario com a placa pelo cabo USB (CH343 na Freenove, USB nativo na XIAO) - ver cam/src/link.h.

Quadro: [0xA5][0x5A][tipo:1][tamanho:2 LE][dados][xor dos dados:1]
Placa -> PC: 'M' microfone, 'L' log, 'J' JPEG, 'F' JSON de rostos/estado, 'S' estatisticas
PC -> placa: 'B' inicio de fala, 'A' PCM do alto-falante, 'E' fim de fala, 'C' comando em texto
"""
import json, queue, threading, time

import serial
import serial.tools.list_ports

BAUD = 2000000  # no USB nativo da XIAO o baud nao importa
CH343_VID = 0x1A86   # Freenove ESP32-S3 CAM (USB-serial CH343)
ESPRESSIF_VID = 0x303A  # XIAO ESP32-S3 Sense (USB nativo da propria ESP32-S3)


def find_port():
    """A placa do robo no USB. Com varias, prefere a CH343; senao a primeira ESP32-S3 de USB nativo.
    Com mais de uma ESP32-S3 plugada (ex.: a cabeca do Jaspy do laboratorio) use --porta."""
    achadas = {CH343_VID: None, ESPRESSIF_VID: None}
    for p in serial.tools.list_ports.comports():
        if p.vid in achadas and achadas[p.vid] is None:
            achadas[p.vid] = p.device
    return achadas[CH343_VID] or achadas[ESPRESSIF_VID]


class UsbRobot:
    """Mesma interface do Robot (Wi-Fi) do robo.py, mas tudo pelo cabo USB."""

    def __init__(self, port=None, on_log=None):
        self.port = port or find_port()
        if not self.port:
            raise RuntimeError("placa nao encontrada em nenhuma porta USB (CH343 ou XIAO ESP32-S3)")
        s = serial.Serial()
        s.port, s.baudrate, s.timeout = self.port, BAUD, 0.1
        s.dtr = False; s.rts = False  # nao reinicia a placa ao abrir
        s.open()
        self.ser = s
        self.tx_lock = threading.Lock()
        self.on_log = on_log or (lambda t: None)
        self.mic_q = queue.Queue(maxsize=500)  # ~10 s
        self._mic_wanted = False
        self._jpeg = None; self._jpeg_ev = threading.Event()
        self._cap_lock = threading.Lock()  # conversa e janela da camera pedem foto: uma de cada vez
        self._faces = None; self._faces_ev = threading.Event()
        self._stats = None; self._stats_ev = threading.Event()
        self.bad_frames = 0
        threading.Thread(target=self._rx, daemon=True).start()
        threading.Thread(target=self._keepalive, daemon=True).start()
        self.host = f"USB {self.port}"

    # ---------------- baixo nivel ----------------
    def send(self, typ, data=b""):
        if isinstance(data, str):
            data = data.encode()
        x = 0
        for b in data:
            x ^= b
        frame = bytes([0xA5, 0x5A, ord(typ), len(data) & 0xFF, len(data) >> 8]) + data + bytes([x])
        with self.tx_lock:
            self.ser.write(frame)

    def cmd(self, text):
        self.send("C", text)

    def _rx(self):
        buf = bytearray()
        while True:
            try:
                d = self.ser.read(8192)
            except Exception:
                time.sleep(0.5); continue
            if not d:
                continue
            buf += d
            while True:
                i = buf.find(b"\xA5\x5A")
                if i < 0:
                    del buf[:-1]; break
                if i:
                    del buf[:i]
                if len(buf) < 5:
                    break
                typ = chr(buf[2]); n = buf[3] | (buf[4] << 8)
                if len(buf) < 6 + n:
                    break
                payload = bytes(buf[5:5 + n]); chk = buf[5 + n]
                x = 0
                for b in payload:
                    x ^= b
                if x != chk:
                    self.bad_frames += 1
                    del buf[:2]; continue
                del buf[:6 + n]
                self._dispatch(typ, payload)

    def _dispatch(self, typ, p):
        if typ == "M":
            if self._mic_wanted:
                try:
                    self.mic_q.put_nowait(p)
                except queue.Full:
                    pass
        elif typ == "L":
            self.on_log(p.decode("utf-8", "replace"))
        elif typ == "J":
            self._jpeg = p; self._jpeg_ev.set()
        elif typ == "F":
            try:
                self._faces = json.loads(p)
            except ValueError:
                self._faces = None
            self._faces_ev.set()
        elif typ == "S":
            try:
                self._stats = json.loads(p)
            except ValueError:
                self._stats = None
            self._stats_ev.set()

    def _keepalive(self):
        while True:
            if self._mic_wanted:
                try:
                    self.cmd("mic 1")
                except Exception:
                    pass
            time.sleep(1.5)

    # ---------------- interface do robo ----------------
    def status(self, timeout=2):
        self._faces_ev.clear(); self.cmd("faces")
        return self._faces if self._faces_ev.wait(timeout) else None

    def stats(self, timeout=2):
        self._stats_ev.clear(); self.cmd("stats")
        return self._stats if self._stats_ev.wait(timeout) else None

    def capture(self, timeout=7):
        with self._cap_lock:
            self._jpeg_ev.clear(); self.cmd("capture")
            if not self._jpeg_ev.wait(timeout):
                return None
            return self._jpeg or None

    def wake(self, ms=20000):
        self.cmd(f"wake {int(ms)}")

    def gesture(self, g):
        self.cmd(f"gesture {g}")

    def look(self, pan, tilt):
        self.cmd(f"servo {int(pan)} {int(tilt)}")

    def echo(self, on):
        self.cmd(f"echo {1 if on else 0}")

    def play(self, pcm: bytes):
        """Envia a fala em blocos de 20 ms, um pouco mais rapido que o tempo real."""
        PKT = 640
        self.send("B")
        t0 = time.time()
        for k, i in enumerate(range(0, len(pcm), PKT)):
            while k * 0.02 > (time.time() - t0) * 1.5 + 0.5:
                time.sleep(0.005)
            self.send("A", pcm[i:i + PKT])
        self.send("E")

    def wait_silence(self, max_wait):
        end = time.time() + max_wait
        time.sleep(0.4)
        while time.time() < end:
            st = self.status(1)
            if st is not None and not st.get("speaking"):
                return
            time.sleep(0.15)

    def mic_chunks(self):
        """Gerador de PCM do microfone (blocos de 20 ms)."""
        self._mic_wanted = True
        self.cmd("mic 1")
        while True:
            try:
                yield self.mic_q.get(timeout=3)
            except queue.Empty:
                raise ConnectionError("a placa nao esta enviando audio pelo USB")

    def mic_stop(self):
        self._mic_wanted = False
        self.cmd("mic 0")
        while not self.mic_q.empty():
            self.mic_q.get_nowait()
