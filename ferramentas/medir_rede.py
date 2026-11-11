"""Compara a qualidade do link Wi-Fi da placa em diferentes configuracoes (camera ligada/dormindo, clock).
Uso: ponte\\.venv\\Scripts\\python ferramentas/medir_rede.py <ip> [rodadas=2]

Para cada configuracao: ping (latencia/perda), microfone UDP (pacotes perdidos em 10 s) e tempo do /capture."""
import json, os, re, statistics, subprocess, sys, threading, time, urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ponte"))
from robo import MicUDP  # noqa: E402

H = sys.argv[1] if len(sys.argv) > 1 else "192.168.15.137"
ROUNDS = int(sys.argv[2]) if len(sys.argv) > 2 else 2

CONFIGS = [
    ("camera LIGADA, xclk 20 MHz", "vision=1&xclk=20"),
    ("camera DORMINDO", "vision=0&xclk=20"),
    ("camera LIGADA, xclk 10 MHz", "vision=1&xclk=10"),
]


def get(p, t=8):
    with urllib.request.urlopen(f"http://{H}{p}", timeout=t) as r:
        return r.read()


def ping(n=20):
    out = subprocess.run(["ping", "-n", str(n), "-l", "600", "-w", "1500", H], capture_output=True, text=True,
                         encoding="cp850", errors="replace").stdout
    times = [int(x) for x in re.findall(r"(?:tempo|time)[=<](\d+)ms", out)]
    lost = n - len(times)
    return lost, times


def mic(secs=10):
    m = MicUDP(H)
    t = time.time()
    try:
        for _ in m.chunks():
            if time.time() - t > secs:
                break
    except Exception as e:
        return None, str(e)
    tot = m.received + m.lost
    return (m.lost * 100 / tot if tot else 100.0), f"{m.received} recebidos / {m.lost} perdidos"


def capture_times(k=3):
    ts = []
    for _ in range(k):
        t = time.time()
        try:
            get("/capture", 10); ts.append(time.time() - t)
        except Exception:
            ts.append(None)
        time.sleep(0.3)
    return ts


results = {}
for rnd in range(ROUNDS):
    for name, q in CONFIGS:
        try:
            get(f"/config?{q}")
        except Exception as e:
            print(name, "-> /config falhou:", e); continue
        time.sleep(4)  # deixa estabilizar (camera ligar/desligar)
        # ping e mic ao mesmo tempo (o mic gera o trafego real do robo)
        res = {}
        th = threading.Thread(target=lambda: res.update(mic=mic(10)))
        th.start()
        lost, times = ping(20)
        th.join()
        mloss, mdesc = res["mic"]
        st = json.loads(get("/stats"))
        caps = capture_times(3) if "vision=1" in q else ["(dormindo)"]
        r = results.setdefault(name, [])
        r.append({"ping_perda": lost * 5, "ping_med": statistics.median(times) if times else None,
                  "ping_max": max(times) if times else None, "mic_perda": mloss, "rssi": st["rssi"]})
        print(f"[{rnd + 1}] {name:28s} ping perda {lost * 5:3d}%  mediana {r[-1]['ping_med']} ms  max {r[-1]['ping_max']} ms"
              f" | mic perda {mloss if mloss is None else round(mloss, 1)}% ({mdesc}) | capture {caps} | rssi {st['rssi']}",
              flush=True)

print("\nRESUMO (media das rodadas):")
for name, rs in results.items():
    def avg(k):
        v = [x[k] for x in rs if x[k] is not None]
        return round(sum(v) / len(v), 1) if v else None
    print(f"  {name:28s} ping perda {avg('ping_perda')}%  ping mediana {avg('ping_med')} ms  ping max {avg('ping_max')} ms"
          f"  mic perda {avg('mic_perda')}%")
get("/config?vision=0&xclk=20")
