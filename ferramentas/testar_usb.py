"""Teste do link USB com a placa: logs, estatisticas, foto, taxa do microfone e autoteste acustico
(toca um tom no alto-falante e verifica se o microfone ouviu - deixe o mic perto do alto-falante).
Uso: ponte\\.venv\\Scripts\\python ferramentas/testar_usb.py [porta] [--boot]
   --boot  reinicia a placa e mostra os logs do boot antes do teste"""
import os, sys, time
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ponte"))
from link_usb import UsbRobot  # noqa: E402

port = next((a for a in sys.argv[1:] if not a.startswith("-")), None)
r = UsbRobot(port, on_log=lambda t: print("  [placa]", t, flush=True))
print("porta:", r.port)
if "--boot" in sys.argv:
    r.ser.rts = True; time.sleep(0.1); r.ser.rts = False
    time.sleep(25)

print("stats:", r.stats())
t = time.time(); j = r.capture()
print(f"capture: {len(j) if j else 0} bytes em {time.time() - t:.2f}s (camera estava dormindo?)")
if j:
    open("capture_usb.jpg", "wb").write(j)
t = time.time(); j = r.capture()
print(f"capture 2: {len(j) if j else 0} bytes em {time.time() - t:.2f}s (camera acordada)")

# microfone 6 s
chunks = []; t0 = time.time()
for c in r.mic_chunks():
    chunks.append(c)
    if time.time() - t0 > 6:
        break
a = np.frombuffer(b"".join(chunks), dtype=np.int16).astype(np.float32)
print(f"mic: {len(a) / (time.time() - t0):.0f} amostras/s (esperado 16000), ruido rms {a.std():.0f}")

# autoteste acustico: tom de 1 kHz por 1 s, com o mic NAO mudo (eco)
r.echo(True); time.sleep(0.3)
while not r.mic_q.empty():
    r.mic_q.get_nowait()
tone = (np.sin(2 * np.pi * 1000 * np.arange(16000) / 16000) * 16000).astype(np.int16).tobytes()
rec = []; t0 = time.time()
r.play(tone)
for c in r.mic_chunks():
    rec.append(c)
    if time.time() - t0 > 2.5:
        break
r.echo(False)
x = np.frombuffer(b"".join(rec), dtype=np.int16).astype(np.float32)
f = np.fft.rfftfreq(len(x), 1 / 16000); X = np.abs(np.fft.rfft(x))
band = (f > 950) & (f < 1050); rest = (f > 300) & (f < 4000) & ~band
ratio = X[band].mean() / max(X[rest].mean(), 1e-9)
print(f"autoteste acustico: energia em 1 kHz {ratio:.1f}x acima do resto -> "
      f"{'MICROFONE OUVIU O ALTO-FALANTE' if ratio > 5 else 'nao detectado'}")
print("stats:", r.stats())
print("quadros com erro no link:", r.bad_frames)
r.mic_stop()
