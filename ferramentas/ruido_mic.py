"""Mede o ruido do microfone com cada componente ligado/desligado (camera, Wi-Fi), pelo link USB.
Uso: ponte\\.venv\\Scripts\\python ferramentas/ruido_mic.py [porta]
Fique em silencio durante a medicao: o objetivo e medir o ruido eletrico/ambiente."""
import os, sys, time
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ponte"))
from link_usb import UsbRobot  # noqa: E402

r = UsbRobot(sys.argv[1] if len(sys.argv) > 1 else None)
gen = r.mic_chunks()


def measure(secs=4):
    while not r.mic_q.empty():
        r.mic_q.get_nowait()
    out = []; t = time.time()
    for c in gen:
        out.append(c)
        if time.time() - t > secs:
            break
    a = np.frombuffer(b"".join(out), dtype=np.int16).astype(np.float32)
    fr = a[: len(a) // 480 * 480].reshape(-1, 480).std(axis=1)
    X = np.abs(np.fft.rfft(a)); f = np.fft.rfftfreq(len(a), 1 / 16000)
    peaks = sorted(zip(X, f), reverse=True)[:3]
    return np.percentile(fr, 20), np.median(fr), [int(p[1]) for p in peaks]


CASES = [
    ("camera OFF, wifi ON ", "vision 0", "wifi 1"),
    ("camera ON,  wifi ON ", "vision 1", "wifi 1"),
    ("camera ON,  wifi OFF", "vision 1", "wifi 0"),
    ("camera OFF, wifi OFF", "vision 0", "wifi 0"),
]
res = {}
for rnd in range(2):
    for name, c1, c2 in CASES:
        r.cmd(c1); r.cmd(c2); time.sleep(5)
        p20, med, pk = measure()
        res.setdefault(name, []).append((p20, med))
        print(f"[{rnd + 1}] {name}: ruido p20 {p20:6.0f}  mediana {med:6.0f}  picos de frequencia {pk} Hz", flush=True)
print("\nRESUMO (ruido mediano, media das rodadas):")
for name, v in res.items():
    print(f"  {name}: {np.mean([m for _, m in v]):6.0f}")
r.cmd("vision 0"); r.cmd("wifi 1"); r.mic_stop()
