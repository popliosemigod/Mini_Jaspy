"""Mostra os logs da placa pelo cabo USB (o firmware fala um protocolo binario a 2 Mbaud, ver cam/src/link.h).
Uso: ponte\\.venv\\Scripts\\python ferramentas/ler_serial.py [segundos=40] [porta] [--reset]
   --reset  reinicia a placa antes (para ver o boot completo)
Feche o robo.py antes: so um programa pode usar a porta por vez."""
import os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ponte"))
from link_usb import UsbRobot  # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith("-")]
secs = float(args[0]) if args else 40
port = args[1] if len(args) > 1 else None
r = UsbRobot(port, on_log=lambda t: print(time.strftime("%H:%M:%S"), t, flush=True))
print("porta:", r.port)
if "--reset" in sys.argv:
    r.ser.rts = True; time.sleep(0.1); r.ser.rts = False
time.sleep(secs)
print("estatisticas:", r.stats())
