"""Supervisor do robo: deixa o robo.py sempre no ar e cuida das gravacoes da autoprogramacao.

  python  ponte/supervisor.py [opcoes do robo.py]     # com janela (ve o log ao vivo)
  pythonw ponte/supervisor.py [opcoes do robo.py]     # escondido (inicio automatico do Windows)

- Sem a placa no USB: espera ela ser plugada. Desplugou (robo.py sai com 3): espera voltar.
- Placa ainda no boot ou robo.py caiu: religa, esperando cada vez mais (5 s ate 60 s).
- robo.py sai com EXIT_GRAVAR (10): grava o firmware novo, confere o boot e, se a placa nao voltar,
  regrava o ultimo firmware bom e desfaz o commit. EXIT_REINICIAR (11): so religa (mudou o Python);
  se cair logo depois, desfaz o commit.
- Tudo vai para ponte/logs/robo_AAAA-MM-DD.log (conversa, placa, autoprogramacao, erros); 30 dias.
- Uma instancia so (trava numa porta local).
- Ambiente: poe o Claude Code no PATH (procura na extensao do VS Code) e le ponte/maquina.json
  (local, fora do git) para o que e desta maquina, ex.: {"PLATFORMIO_CORE_DIR": "C:\\\\pio-mini"}.
"""
import glob, json, os, re, shutil, socket, subprocess, sys, time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from autoprogramacao import (CAM, FW_BOM, FW_BUILD, RESULTADO, EXIT_GRAVAR, EXIT_REINICIAR, _git)

EXIT_DESPLUGOU = 3
QUEDA_RAPIDA_S = 40      # robo.py que morre antes disso depois de uma mudanca: a mudanca quebrou
LOGS = os.path.join(AQUI, "logs")
DIAS_DE_LOG = 30
TRAVA_PORTA = 48731      # uma instancia so
SEM_JANELA = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW: filhos sem janela pipocando


def _arquivo_log():
    os.makedirs(LOGS, exist_ok=True)
    return os.path.join(LOGS, time.strftime("robo_%Y-%m-%d.log"))


def escreve(linha):
    """Uma linha no log do dia (e na tela, se houver)."""
    try:
        with open(_arquivo_log(), "a", encoding="utf-8") as f:
            f.write(linha.rstrip("\n") + "\n")
    except OSError:
        pass
    try:
        print(linha.rstrip("\n"), flush=True)
    except Exception:
        pass  # pythonw: sem tela


def log(*a):
    escreve(time.strftime("%H:%M:%S") + " [supervisor] " + " ".join(str(x) for x in a))


def limpa_logs_velhos():
    limite = time.time() - DIAS_DE_LOG * 86400
    for f in glob.glob(os.path.join(LOGS, "robo_*.log")):
        try:
            if os.path.getmtime(f) < limite:
                os.remove(f)
        except OSError:
            pass


def prepara_ambiente():
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        with open(os.path.join(AQUI, "maquina.json"), encoding="utf-8") as f:
            env.update({k: str(v) for k, v in json.load(f).items()})
    except (OSError, ValueError):
        pass
    if not shutil.which("claude", path=env.get("PATH")):
        ext = os.path.join(os.path.expanduser("~"), ".vscode", "extensions")
        candidatos = glob.glob(os.path.join(ext, "anthropic.claude-code-*", "resources", "native-binary", "claude.exe"))

        def versao(p):  # ...\anthropic.claude-code-2.1.322-win32-x64\resources\native-binary\claude.exe
            pasta = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(p))))
            m = re.search(r"claude-code-(\d+(?:\.\d+)*)", pasta)
            return [int(x) for x in m.group(1).split(".")] if m else [0]
        if candidatos:
            env["PATH"] = os.path.dirname(max(candidatos, key=versao)) + os.pathsep + env.get("PATH", "")
            log(f"Claude Code da extensao do VS Code: {os.path.dirname(max(candidatos, key=versao))}")
        else:
            log("AVISO: comando 'claude' nao encontrado - o robo fica sem cerebro")
    pio = os.path.join(os.path.expanduser("~"), ".platformio", "penv", "Scripts")
    if os.path.isdir(pio) and pio not in env.get("PATH", ""):
        env["PATH"] = env["PATH"] + os.pathsep + pio
    return env


def python_com_console():
    """O robo.py roda no python.exe (nao no pythonw) com a janela escondida: assim powershell, claude e
    pio que ele abre herdam um console invisivel e nao pipocam janelas."""
    exe = sys.executable
    if exe.lower().endswith("pythonw.exe"):
        c = exe[:-len("pythonw.exe")] + "python.exe"
        if os.path.exists(c):
            return c
    return exe


def roda(cmd, env):
    """Roda um processo mandando a saida (stdout+stderr) para o log, linha a linha."""
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                         errors="replace", env=env, creationflags=SEM_JANELA)
    for linha in p.stdout:
        escreve(linha)
    return p.wait()


def placa_no_usb():
    from link_usb import find_port
    return find_port()


def espera_placa():
    if placa_no_usb():
        return
    log("esperando a placa ser plugada no USB...")
    while not placa_no_usb():
        time.sleep(2)
    log(f"placa plugada em {placa_no_usb()}; esperando o boot")
    time.sleep(8)


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
    pio = shutil.which("pio")
    if pio:
        py = os.path.join(os.path.dirname(pio), "python.exe")
        if os.path.exists(py):
            return py
    return python_com_console()


def regrava_bom(env):
    core = env.get("PLATFORMIO_CORE_DIR") or os.path.join(os.path.expanduser("~"), ".platformio")
    esptool = os.path.join(core, "packages", "tool-esptoolpy", "esptool.py")
    porta = placa_no_usb()
    log(f"regravando o ultimo firmware bom em {porta}")
    ok = roda([esptool_python(), esptool, "--chip", "esp32s3", "--port", porta, "--baud", "921600",
               "write_flash", "0x10000", FW_BOM], env) == 0
    if ok:
        shutil.copy2(FW_BOM, FW_BUILD)  # o build volta a ser o que esta na placa
    return ok


def desfaz_commit():
    msg = _git("log", "-1", "--format=%s")
    if msg.startswith("auto: ") and not msg.startswith("auto: base"):
        _git("reset", "-q", "--hard", "HEAD~1")
        log(f"commit desfeito: {msg}")


def grava(env):
    resumo = ""
    try:
        with open(RESULTADO, encoding="utf-8") as f:
            resumo = json.load(f).get("resumo", "")
    except (OSError, ValueError):
        pass
    log("gravando o firmware novo")
    pio = shutil.which("pio", path=env.get("PATH")) or "pio"
    if roda([pio, "run", "-t", "upload", "-d", CAM], env) == 0 and placa_respondeu():
        log("placa voltou com o firmware novo")
        resultado(f"Pronto, me reprogramei! {resumo} Estou de volta.")
        return
    log("a placa NAO voltou com o firmware novo")
    ok = os.path.exists(FW_BOM) and regrava_bom(env) and placa_respondeu()
    desfaz_commit()
    if ok:
        resultado("A mudanca nova deu problema na placa, entao voltei para a versao anterior. Estou bem.")
    else:
        resultado("Tive problema para gravar a mudanca e para voltar a versao anterior. Preciso de ajuda pelo computador.")


def main():
    trava = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        trava.bind(("127.0.0.1", TRAVA_PORTA))
    except OSError:
        log("ja existe um supervisor rodando; saindo")
        return
    limpa_logs_velhos()
    env = prepara_ambiente()
    robo = [python_com_console(), "-u", os.path.join(AQUI, "robo.py"), *sys.argv[1:]]
    log(f"inicio: {' '.join(robo)}")
    mudou_agora = False
    espera = 5
    while True:
        espera_placa()
        t0 = time.time()
        codigo = roda(robo, env)
        vida = time.time() - t0
        log(f"robo.py saiu com {codigo} depois de {vida:.0f} s")
        if codigo == 0:
            break  # Ctrl+C / saida pedida
        if codigo == EXIT_GRAVAR:
            grava(env)
            mudou_agora, espera = True, 5
        elif codigo == EXIT_REINICIAR:
            log("religando o robo com o Python novo")
            resultado("Pronto, me reprogramei! Estou de volta.")
            mudou_agora, espera = True, 5
        elif codigo == EXIT_DESPLUGOU:
            mudou_agora, espera = False, 5
        elif mudou_agora and vida < QUEDA_RAPIDA_S:
            log("o robo caiu logo depois de uma mudanca: voltando a versao anterior")
            desfaz_commit()
            resultado("A mudanca nova me fez travar, entao voltei para a versao anterior.")
            mudou_agora = False
        else:
            mudou_agora = False
            log(f"religando em {espera} s")
            time.sleep(espera)
            espera = min(60, espera * 2) if vida < 60 else 5


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log(f"ERRO no supervisor: {e!r}")
        raise
