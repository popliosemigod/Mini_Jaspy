# Script de pre-compilacao do PlatformIO (extra_scripts = pre:scripts/fotos_padrao.py).
#
# O firmware embute as fotos de cadastro facial cam/data/face0..8.bin. Essas fotos sao de uma pessoa
# real e NAO vao para o GitHub (repositorio publico, ver .gitignore). Numa maquina sem elas, este
# script cria imagens neutras (cinza) para a compilacao funcionar: a placa sobe normalmente, mas sem
# ninguem cadastrado (todo rosto vira "Creatura").
#
# Para ter o reconhecimento de verdade: coloque as fotos em fotos_cadastro/ e rode
#   python ferramentas/converter_fotos.py fotos_cadastro cam/data
# (sobrescreve os arquivos cinza) e grave de novo.
import os

Import("env")  # noqa: F821  (fornecido pelo PlatformIO)

data_dir = os.path.join(env.subst("$PROJECT_DIR"), "data")  # noqa: F821
os.makedirs(data_dir, exist_ok=True)
SIZE = 320 * 240 * 2
GRAY = bytes([0x84, 0x10]) * (320 * 240)  # RGB565 big-endian ~ cinza medio
created = []
for i in range(9):
    p = os.path.join(data_dir, f"face{i}.bin")
    if not os.path.exists(p) or os.path.getsize(p) != SIZE:
        with open(p, "wb") as f:
            f.write(GRAY)
        created.append(os.path.basename(p))
if created:
    print("*" * 78)
    print("AVISO: fotos de cadastro facial ausentes -> criadas imagens cinza:", ", ".join(created))
    print("       O robo funciona, mas ninguem sera reconhecido (todos = 'Creatura').")
    print("       Veja cam/scripts/fotos_padrao.py para colocar as fotos reais.")
    print("*" * 78)
