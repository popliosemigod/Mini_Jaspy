"""Teste dos perifericos da placa pela rede (PC precisa estar na mesma rede da placa).
Uso: ponte\\.venv\\Scripts\\python ferramentas/testar_placa.py <ip> [--sem-servos]

Verifica: /faces, /capture, taxa/perda/nivel do microfone (UDP 82, 10 s),
tom de 440 Hz no alto-falante (UDP 83) e movimentos dos servos."""
import json, os, sys, time, urllib.request
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ponte"))
from robo import MicUDP, Robot  # noqa: E402

H = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "192.168.15.137"
r = Robot(H)


def get(p, t=8):
    with urllib.request.urlopen(f"http://{H}{p}", timeout=t) as resp:
        return resp.read()


print("faces:", get("/faces").decode())
t = time.time(); j = get("/capture")
print(f"capture: {len(j)} bytes, jpeg={j[:2] == b'\xff\xd8'} ({time.time() - t:.2f}s)")
open("capture_teste.jpg", "wb").write(j)

# microfone: 10 s (fale perto do mic durante o teste)
mic = MicUDP(H)
buf = bytearray(); t = None
for c in mic.chunks():
    if t is None:
        t = time.time()
    buf += c
    if time.time() - t > 10:
        break
a = np.frombuffer(bytes(buf), dtype=np.int16)
el = time.time() - t
print(f"mic: {len(a) / el:.0f} amostras/s (esperado 16000), pacotes recebidos {mic.received}, perdidos {mic.lost} "
      f"({mic.lost * 100 / max(1, mic.received + mic.lost):.1f}%), rms={np.sqrt(np.mean(a.astype(float) ** 2)):.0f}, "
      f"min={a.min()} max={a.max()}")
np.save("mic_teste.npy", a)

# alto-falante: tom 440 Hz por 1,5 s
from robo import SPK_RATE  # noqa: E402
tone = (np.sin(2 * np.pi * 440 * np.arange(SPK_RATE * 3 // 2) / SPK_RATE) * 12000).astype(np.int16).tobytes()  # 1,5 s
t = time.time(); r.play(tone); r.wait_silence(5)
print(f"spk: tom de 1,5 s enviado e tocado em {time.time() - t:.1f}s (deve ouvir um bip)")

if "--sem-servos" not in sys.argv:
    for p in ["/servo?track=0", "/servo?pan=60&tilt=70", "/servo?pan=120&tilt=110", "/gesture?g=sim",
              "/gesture?g=nao", "/gesture?g=centro", "/servo?track=1"]:
        print(p, "->", get(p).decode()); time.sleep(1.5)
print("estado final:", get("/faces").decode())
