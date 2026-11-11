"""Converte fotos (.jpeg) em .bin RGB565 big-endian 320x240 para cadastro facial embutido no firmware.
Uso: python ferramentas/converter_fotos.py fotos_cadastro cam/data   (precisa de Pillow)
Depois ajuste a lista board_build.embed_files em cam/platformio.ini e ENROLL_PHOTOS em cam/src/main.cpp."""
import sys, glob, os
from PIL import Image, ImageOps
src, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
fs = sorted(glob.glob(os.path.join(src, '*.jpeg')))
for i, f in enumerate(fs):
    im = ImageOps.exif_transpose(Image.open(f)).convert('RGB')
    im.thumbnail((320, 240), Image.LANCZOS)
    c = Image.new('RGB', (320, 240), (128, 128, 128))
    c.paste(im, ((320 - im.width) // 2, (240 - im.height) // 2))
    b = bytearray()
    for r, g, bl in c.getdata():
        v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (bl >> 3)
        b += bytes((v >> 8, v & 0xFF))  # big-endian, igual ao buffer da camera
    open(os.path.join(out, f'face{i}.bin'), 'wb').write(b)
    c.save(os.path.join(out, f'preview{i}.png'))
print(len(fs), 'fotos convertidas')
