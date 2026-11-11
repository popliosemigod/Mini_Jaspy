"""Teste da ponte no PC sem a placa: TTS (Maria) -> Whisper -> Claude com uma foto.
Uso: ponte\.venv\Scripts\python ferramentas/testar_ponte_pc.py ponte ferramentas/exemplo_capture.jpg"""
import sys, time, io, numpy as np
sys.path.insert(0, sys.argv[1])
import robo

t = time.time(); pcm, wf = robo.synthesize("Olá robô, quem você está vendo agora?")
print(f"TTS: {len(pcm)/32000:.1f}s de audio em {time.time()-t:.1f}s")
stt = robo.Transcriber("small")
t = time.time(); txt = stt(np.frombuffer(pcm, dtype=np.int16)); print(f"STT ({time.time()-t:.1f}s): {txt!r}")
jpg = open(sys.argv[2], "rb").read()
brain = robo.Brain("haiku")
faces = {"list": [{"name": "Rapaz bonito e inteligente", "sim": 0.81}]}
for q in [txt, "Faz que sim com a cabeça pra mim"]:
    t = time.time(); r = brain.ask(q, jpg, faces); print(f"CLAUDE ({time.time()-t:.1f}s):", r)
brain.proc.stdin.close()
