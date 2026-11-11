"""O Jaspy apresenta um seminario: os slides em tela cheia no PC e ele falando, slide por slide.

  ponte\\.venv\\Scripts\\python ferramentas\\apresentar.py --pdf "C:\\...\\apresentacao.pdf"
  ponte\\.venv\\Scripts\\python ferramentas\\apresentar.py                    # slides ja convertidos

Roteiro em apresentacao/roteiro.json (editavel): cada slide tem trechos {"gesto", "fala"}. As falas sao
geradas ANTES de comecar (voz neural; sem internet, a Maria) e guardadas em apresentacao/audio/, entao a
apresentacao nao espera a rede. Teclas: seta para a direita = proximo slide, Esc = encerrar.

O robo precisa estar com a porta USB livre: pare o supervisor antes. Com --conversar-depois, ao terminar
o robo volta sozinho em modo conversa (supervisor escondido) para o debate.

Imagens dos slides e audios ficam fora do git (apresentacao/slides, apresentacao/audio).
"""
import argparse, hashlib, io, json, os, queue, subprocess, sys, threading, time, wave

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PONTE = os.path.join(RAIZ, "ponte")
PASTA = os.path.join(RAIZ, "apresentacao")
sys.path.insert(0, PONTE)


def log(*a):
    print(time.strftime("%H:%M:%S"), "[apresentacao]", *a, flush=True)


# ------------------------------------------------------------------ slides
def converte_pdf(pdf, saida, recorte, giro):
    """PDF -> slideN.png. O PDF do seminario veio impresso do navegador: slide deitado numa folha em pe,
    com cabecalho e rodape; recorte (pt) tira a moldura e giro poe em paisagem."""
    import pymupdf
    from PIL import Image
    os.makedirs(saida, exist_ok=True)
    doc = pymupdf.open(pdf)
    for i, pg in enumerate(doc):
        clip = pymupdf.Rect(*recorte) if recorte else None
        pix = pg.get_pixmap(dpi=220, clip=clip)
        im = Image.open(io.BytesIO(pix.tobytes("png")))
        if giro:
            im = im.rotate(giro, expand=True)
        im.save(os.path.join(saida, f"slide{i + 1}.png"))
    log(f"{doc.page_count} slides convertidos em {saida}")


# ------------------------------------------------------------------ falas
def prepara_falas(roteiro, pasta_audio, voz):
    """Gera (ou reaproveita) o PCM de cada trecho. Chave = voz + texto: mudou o texto, gera de novo."""
    import robo
    os.makedirs(pasta_audio, exist_ok=True)
    wav = os.path.join(pasta_audio, "_tmp.wav")

    def chave(v, texto):
        # "v2": a primeira versao do cache guardou falas da Maria marcadas como voz neural
        return os.path.join(pasta_audio, hashlib.sha1(("v2|" + v + "|" + texto).encode("utf-8")).hexdigest()[:16] + ".pcm")

    total = sum(len(s["trechos"]) for s in roteiro["slides"])
    feitos, na_maria = 0, 0
    for s in roteiro["slides"]:
        for tr in s["trechos"]:
            texto = tr["fala"]
            arq = chave(voz, texto) if voz else None
            if arq and not os.path.exists(arq):
                # sem pressa aqui (nao e ao vivo): 2 tentativas de 20 s - na rede UVV a voz neural responde,
                # mas devagar, e o timeout de 8 s da conversa jogava tudo na Maria (11/11/2026)
                robo.VOZ = voz
                for _ in range(2):
                    try:
                        pcm = robo._neural(texto, wav, timeout=20)
                        with open(arq, "wb") as f:
                            f.write(pcm)
                        break
                    except Exception:
                        pass
            if not arq or not os.path.exists(arq):
                arq = chave("", texto)  # Maria: o cache marca a voz que foi usada de verdade
                if not os.path.exists(arq):
                    robo.VOZ = ""
                    pcm, _ = robo.synthesize(texto)
                    with open(arq, "wb") as f:
                        f.write(pcm)
                na_maria += 1
            tr["_pcm"] = arq
            feitos += 1
            print(f"\r  falas prontas: {feitos}/{total} (na Maria: {na_maria})", end="", flush=True)
    print()
    log(f"voz: {voz or 'Maria'}" + (f" ({na_maria} trecho(s) na Maria, a neural nao respondeu)" if na_maria and voz else ""))
    dur = sum(os.path.getsize(tr["_pcm"]) / 32000 for s in roteiro["slides"] for tr in s["trechos"])
    log(f"{total} trechos, {dur / 60:.1f} min de fala")


def no_pico(pcm, pico=0.95):
    """Volume no maximo (pedido do dono): o PCM sobe ate 95% da escala no pico."""
    import numpy as np
    a = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    m = float(np.abs(a).max()) if a.size else 0.0
    return (a * (pico * 32767.0 / m)).astype(np.int16).tobytes() if m > 0 else pcm


def toca_no_pc(pcm_arq):
    import winsound
    wav = pcm_arq[:-4] + ".wav"
    if not os.path.exists(wav):
        with open(pcm_arq, "rb") as f, wave.open(wav, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(f.read())
    winsound.PlaySound(wav, winsound.SND_FILENAME)


# ------------------------------------------------------------------ apresentacao
def main():
    ap = argparse.ArgumentParser(description="O Jaspy apresenta os slides")
    ap.add_argument("--pdf", help="PDF dos slides (converte para apresentacao/slides)")
    ap.add_argument("--recorte", default="95,61,501,782",
                    help="retangulo do slide na pagina, em pt (x0,y0,x1,y1); vazio = pagina inteira")
    ap.add_argument("--giro", type=int, default=-90, help="graus para girar cada slide (0 = nao gira)")
    ap.add_argument("--roteiro", default=os.path.join(PASTA, "roteiro.json"))
    ap.add_argument("--voz", default="en-US-BrianMultilingualNeural", help="voz neural (vazio = Maria)")
    ap.add_argument("--falar-no-pc", action="store_true", help="voz no alto-falante do PC, sem o robo")
    ap.add_argument("--conversar-depois", action="store_true", help="no fim, liga o robo em modo conversa")
    ap.add_argument("--pausa", type=float, default=0.8, help="segundos entre um trecho e outro")
    ap.add_argument("--volume", type=int, default=100, help="volume do alto-falante na placa, 0 a 100")
    ap.add_argument("--so-preparar", action="store_true", help="so converte os slides e gera as falas")
    args = ap.parse_args()

    slides_dir = os.path.join(PASTA, "slides")
    if args.pdf:
        rec = [float(x) for x in args.recorte.split(",")] if args.recorte else None
        converte_pdf(args.pdf, slides_dir, rec, args.giro)
    with open(args.roteiro, encoding="utf-8") as f:
        roteiro = json.load(f)
    imagens = {s["slide"]: os.path.join(slides_dir, f"slide{s['slide']}.png") for s in roteiro["slides"]}
    faltam = [p for p in imagens.values() if not os.path.exists(p)]
    if faltam:
        sys.exit(f"faltam slides: {faltam} (rode com --pdf)")

    log("preparando as falas (so na primeira vez demora)...")
    prepara_falas(roteiro, os.path.join(PASTA, "audio"), args.voz)
    if args.so_preparar:
        log("pronto para apresentar")
        return

    robot = None
    if not args.falar_no_pc:
        from link_usb import UsbRobot
        try:
            robot = UsbRobot()
        except Exception as e:
            sys.exit(f"nao abri a placa pelo USB ({e}). O supervisor/robo.py esta rodando? Pare-o antes.")
        if not robot.stats(3):
            sys.exit("a placa nao respondeu pelo USB")
        for c in ("wifi 0", "servovel 10 20", "track 1", f"volume {args.volume}"):
            robot.cmd(c)
        log(f"robo pronto em {robot.port}")

    # ---- janela em tela cheia (Tk no fio principal; a fala num fio separado)
    import tkinter as tk
    from PIL import Image, ImageTk
    janela = tk.Tk()
    janela.title("Jaspy apresenta")
    janela.configure(bg="black")
    janela.attributes("-fullscreen", True)
    janela.config(cursor="none")
    W, H = janela.winfo_screenwidth(), janela.winfo_screenheight()
    rotulo = tk.Label(janela, bg="black", bd=0)
    rotulo.pack(expand=True, fill="both")
    fotos = {}
    for n, p in imagens.items():
        im = Image.open(p)
        e = min(W / im.width, H / im.height)
        fotos[n] = ImageTk.PhotoImage(im.resize((int(im.width * e), int(im.height * e)), Image.LANCZOS))

    pedidos = queue.Queue()
    pular = threading.Event()
    parar = threading.Event()

    def mostra(n):
        rotulo.configure(image=fotos[n])

    def processa_pedidos():
        while not pedidos.empty():
            tipo, valor = pedidos.get()
            if tipo == "slide":
                mostra(valor)
            elif tipo == "fim":
                janela.destroy()
                return
        janela.after(50, processa_pedidos)

    janela.bind("<Escape>", lambda e: (parar.set(), pedidos.put(("fim", None))))
    janela.bind("<Right>", lambda e: pular.set())
    janela.bind("<space>", lambda e: pular.set())

    def fala(tr):
        if robot:
            if tr.get("gesto") and tr["gesto"] != "nenhum":
                robot.gesture(tr["gesto"])
            with open(tr["_pcm"], "rb") as f:
                pcm = f.read()
            pcm = no_pico(pcm)
            robot.play(pcm)
            robot.wait_silence(len(pcm) / 32000 + 3)
        else:
            toca_no_pc(tr["_pcm"])

    def apresenta():
        time.sleep(1.5)  # a janela abre
        inicio = time.time()
        for s in roteiro["slides"]:
            if parar.is_set():
                return
            pular.clear()
            pedidos.put(("slide", s["slide"]))
            log(f"slide {s['slide']}")
            time.sleep(0.6)
            for tr in s["trechos"]:
                if parar.is_set() or pular.is_set():
                    break
                log(f"  [{tr.get('gesto', '-')}] {tr['fala'][:70]}...")
                fala(tr)
                time.sleep(args.pausa)
        log(f"fim da apresentacao ({(time.time() - inicio) / 60:.1f} min)")
        if args.conversar_depois and robot:
            try:
                robot.ser.close()
            except Exception:
                pass
            pyw = os.path.join(PONTE, ".venv", "Scripts", "pythonw.exe")
            subprocess.Popen([pyw, os.path.join(PONTE, "supervisor.py"), "--logs-placa"], cwd=RAIZ)
            log("robo em modo conversa para o debate (supervisor escondido); Esc fecha os slides")

    pedidos.put(("slide", roteiro["slides"][0]["slide"]))
    threading.Thread(target=apresenta, daemon=True).start()
    janela.after(50, processa_pedidos)
    janela.mainloop()


if __name__ == "__main__":
    main()
