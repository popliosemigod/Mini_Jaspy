"""Supervisor do robo: roda o robo.py e cuida das gravacoes da autoprogramacao.

  python ponte/supervisor.py [opcoes do robo.py]

- robo.py sai com EXIT_GRAVAR (10): grava o firmware novo, espera a placa responder pelo USB e, se ela
  nao voltar, regrava o ultimo firmware bom e desfaz o commit. Depois volta o robo.
- robo.py sai com EXIT_REINICIAR (11): mudou so o Python; volta o robo. Se ele cair logo ao iniciar,
  desfaz o commit e volta a versao anterior.
- Qualquer outra saida (Ctrl+C, erro sem mudanca recente): encerra.
O que aconteceu fica em backup_placa/autoprogramacao_resultado.json, e o robo fala ao voltar.
"""
import json, os, shutil, subprocess, sys, time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from autoprogramacao import (CAM, FW_BOM, FW_BUILD, RAIZ, RESULTADO, EXIT_GRAVAR, EXIT_REINICIAR, _git)

QUEDA_RAPIDA_S = 40  # robo.py que morre antes disso depois de uma mudanca: a mudanca quebrou


def log(*a):
    print(time.strftime("%H:%M:%S"), "[supervisor]", *a, flush=True)


def resultado(fala, **extra):
    os.makedirs(os.path.dirname(RESULTADO), exist_ok=True)
    with open(RESULTADO, "w", encoding="utf-8") as f:
        json.dump({"fala": fala, **extra}, f, ensure_ascii=False)


def placa_respondeu(espera_s=90):
    """Abre o link USB e espera a placa responder (o boot leva ~20 s com o cadastro dos rostos)."""
    from link_usb import UsbRobot
    fim = time.time() + espera_s
    while time.time() < fim:
        try:
            r = UsbRobot()
            try:
                while time.time() < fim:
                    if r.stats(3):
                        return True
            finally:
                try:
                    r.ser.close()
                except Exception:
                    pass
        except Exception:
            time.sleep(2)
    return False


def esptool_python():
    """O Python do PlatformIO (tem o que o esptool precisa)."""
    pio = shutil.which("pio")
    if pio:
        py = os.path.join(os.path.dirname(pio), "python.exe")
        if os.path.exists(py):
            return py
    return sys.executable


def regrava_bom():
    core = os.environ.get("PLATFORMIO_CORE_DIR") or os.path.join(os.path.expanduser("~"), ".platformio")
    esptool = os.path.join(core, "packages", "tool-esptoolpy", "esptool.py")
    from link_usb import find_port
    porta = find_port()
    log(f"regravando o ultimo firmware bom em {porta}")
    r = subprocess.run([esptool_python(), esptool, "--chip", "esp32s3", "--port", porta, "--baud", "921600",
                        "write_flash", "0x10000", FW_BOM])
    if r.returncode == 0:
        shutil.copy2(FW_BOM, FW_BUILD)  # o build volta a ser o que esta na placa
    return r.returncode == 0


def desfaz_commit():
    msg = _git("log", "-1", "--format=%s")
    if msg.startswith("auto: ") and not msg.startswith("auto: base"):
        _git("reset", "-q", "--hard", "HEAD~1")
        log(f"commit desfeito: {msg}")


def grava():
    pedido = ""
    try:
        with open(RESULTADO, encoding="utf-8") as f:
            pedido = json.load(f).get("resumo", "")
    except (OSError, ValueError):
        pass
    log("gravando o firmware novo")
    up = subprocess.run(["pio", "run", "-t", "upload", "-d", CAM])
    if up.returncode == 0 and placa_respondeu():
        log("placa voltou com o firmware novo")
        resultado(f"Pronto, me reprogramei! {pedido} Estou de volta.")
        return
    log("a placa NAO voltou com o firmware novo")
    ok = os.path.exists(FW_BOM) and regrava_bom() and placa_respondeu()
    desfaz_commit()
    if ok:
        resultado("A mudanca nova deu problema na placa, entao voltei para a versao anterior. Estou bem.")
    else:
        resultado("Tive problema para gravar a mudanca e para voltar a versao anterior. Preciso de ajuda pelo computador.")


def main():
    robo = [sys.executable, os.path.join(AQUI, "robo.py"), *sys.argv[1:]]
    mudou_agora = False
    while True:
        t0 = time.time()
        codigo = subprocess.run(robo).returncode
        vida = time.time() - t0
        if codigo == EXIT_GRAVAR:
            grava()
            mudou_agora = True
        elif codigo == EXIT_REINICIAR:
            log("reiniciando o robo com o Python novo")
            resultado("Pronto, me reprogramei! Estou de volta.")
            mudou_agora = True
        elif codigo != 0 and mudou_agora and vida < QUEDA_RAPIDA_S:
            log(f"o robo caiu {vida:.0f} s depois de uma mudanca (codigo {codigo}): voltando a versao anterior")
            desfaz_commit()
            resultado("A mudanca nova me fez travar, entao voltei para a versao anterior.")
            mudou_agora = False
        else:
            break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
