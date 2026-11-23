"""Autoprogramacao: o robo muda o proprio codigo, pelo Claude Code, e so grava com confirmacao.

Fluxo (pedido por voz -> mudanca gravada):
  1. O cerebro devolve {"programar": "<o que mudar>"}.
  2. Programador.comeca(): retrato do codigo no git (branch local 'autoprogramacao'), guarda o
     firmware que esta na placa como "o ultimo bom" e abre uma sessao do Claude Code que so pode
     ler, editar e compilar - nunca gravar a placa, nunca mexer em pinagem, senhas ou fotos.
  3. Ao terminar, confere sozinho (compila o firmware, py_compile no Python) e deixa a mudanca
     PENDENTE: o robo conta o que fez e pergunta se pode gravar.
  4. "gravar"  -> commit "auto: <pedido>" e o robo.py sai com EXIT_GRAVAR / EXIT_REINICIAR;
                  o supervisor.py grava, confere o boot e, se a placa nao voltar, regrava o ultimo bom.
     "descartar" -> o codigo volta ao retrato.
Nada vai para o GitHub: o repositorio e publico; publicar e decisao do dono.
"""
import json, os, shutil, subprocess, sys, threading, time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAM = os.path.join(RAIZ, "cam")


def _placa_env():
    """Qual placa esta no robo: "esp32s3cam" (Freenove) ou "xiao" (XIAO Sense). Vem do PLACA_ENV do
    ponte/maquina.json (local, fora do git); sem ele, a Freenove."""
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "maquina.json"), encoding="utf-8") as f:
            v = str(json.load(f).get("PLACA_ENV", "")).strip()
        if v in ("esp32s3cam", "xiao"):
            return v
    except (OSError, ValueError):
        pass
    return "esp32s3cam"


PLACA_ENV = _placa_env()
FW_BUILD = os.path.join(CAM, ".pio", "build", PLACA_ENV, "firmware.bin")
BACKUP = os.path.join(RAIZ, "backup_placa")
FW_BOM = os.path.join(BACKUP, "firmware_bom.bin")
RESULTADO = os.path.join(BACKUP, "autoprogramacao_resultado.json")
BRANCH = "autoprogramacao"

EXIT_GRAVAR = 10     # supervisor: grava o firmware novo, confere o boot e volta o robo
EXIT_REINICIAR = 11  # supervisor: so reinicia o robo.py (mudou so o Python)

REGRAS = """Voce e o proprio robo Mini_Jaspy se reprogramando, a pedido do dono, dentro do repositorio dele.
Antes de mudar, leia o que precisar (CLAUDE.md, RELATORIO_CONTINUIDADE.md, cam/src, ponte/).

Regras que nao se quebram:
- A PINAGEM esta montada e nao muda: nao altere nenhum pino (robo.h, pinos da camera em main.cpp).
- Nao toque em cam/src/wifi_redes.h, fotos_cadastro/, cam/data/, backup_placa/, .git, nem em senhas.
- NUNCA grave a placa (nada de "pio run -t upload", esptool ou porta serial): quem grava e o supervisor,
  depois que o dono confirmar em voz alta.
- Firmware: mudou algo em cam/? compile com "pio run -d cam" e corrija ate compilar sem erro.
  A RAM interna e o recurso critico da placa (relatorio 6.3): buffers grandes vao na PSRAM.
- Python: mudou algo em ponte/? rode "python -m py_compile <arquivo>" em cada arquivo mudado.
- Comentarios em codigo embarcado: portugues sem acento. Mudanca pequena e focada no pedido.
- Nao faca commit nem push: o robo faz o commit depois da confirmacao.

Ao terminar, responda SOMENTE com um JSON, sem nada antes ou depois:
{"resumo_fala": "1 ou 2 frases curtas, faladas em primeira pessoa, do que voce mudou em si mesmo",
 "detalhes": "o que mudou, arquivo por arquivo", "compilou": true}
Se nao der para fazer com seguranca, nao mude nada e explique no resumo_fala."""

FERRAMENTAS = ("Read,Edit,Write,Glob,Grep,Bash(pio run:*),Bash(python -m py_compile:*),"
               "Bash(git diff:*),Bash(git status:*)")


def _achar_claude():
    """Claude Code no PATH ou o da versao mais nova da extensao do VS Code (ver robo.achar_claude)."""
    import glob, re
    achado = shutil.which("claude")
    if achado:
        return achado
    ext = os.path.join(os.path.expanduser("~"), ".vscode", "extensions")
    cands = glob.glob(os.path.join(ext, "anthropic.claude-code-*", "resources", "native-binary", "claude.exe"))

    def versao(p):
        m = re.search(r"claude-code-(\d+(?:\.\d+)*)", p)
        return [int(x) for x in m.group(1).split(".")] if m else [0]
    return max(cands, key=versao) if cands else "claude"


def _git(*args, check=True):
    r = subprocess.run(["git", "-C", RAIZ, *args], capture_output=True, text=True, encoding="utf-8")
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip()


def _mudados(desde):
    """Arquivos mudados em relacao ao retrato (rastreados e novos)."""
    a = _git("diff", "--name-only", desde).splitlines()
    b = _git("ls-files", "--others", "--exclude-standard").splitlines()
    return sorted(set(x for x in a + b if x))


def ler_resultado():
    """Resultado da ultima gravacao, deixado pelo supervisor (e apagado ao ler)."""
    try:
        with open(RESULTADO, encoding="utf-8") as f:
            r = json.load(f)
        os.remove(RESULTADO)
        return r
    except (OSError, ValueError):
        return None


class Programador:
    def __init__(self, modelo="opus", log=print, anunciar=None):
        self.modelo = modelo
        self.log = log
        self.anunciar = anunciar or (lambda texto: None)
        self.estado = "livre"   # livre | programando | pendente
        self.pedido = ""
        self.inicio = 0.0
        self.retrato = ""
        self.resumo = ""
        self.firmware_mudou = False
        self.python_mudou = False

    # ---- o que o cerebro precisa saber a cada mensagem
    def contexto(self):
        if self.estado == "programando":
            return (f"Voce esta se reprogramando agora (pedido: \"{self.pedido}\", ha "
                    f"{int((time.time() - self.inicio) / 60)} min). Ainda nao terminou.")
        if self.estado == "pendente":
            return (f"Voce terminou de se reprogramar: {self.resumo} A mudanca ESPERA CONFIRMACAO. "
                    "Se a pessoa autorizar gravar, coloque \"gravar\": true; se recusar, \"descartar\": true.")
        return ""

    # ---- 1. comecar
    def comeca(self, pedido):
        if self.estado != "livre":
            self.log(f"[autoprog] ignorado (estado {self.estado}): {pedido}")
            return False
        self.estado, self.pedido, self.inicio = "programando", pedido.strip(), time.time()
        threading.Thread(target=self._trabalha, daemon=True).start()
        return True

    def _prepara_git(self):
        if _git("rev-parse", "--abbrev-ref", "HEAD") != BRANCH:
            existe = _git("branch", "--list", BRANCH)
            _git("checkout", BRANCH) if existe else _git("checkout", "-b", BRANCH)
        if _git("status", "--porcelain"):
            _git("add", "-A")
            _git("commit", "-q", "-m", f"auto: base antes de '{self.pedido[:60]}'")
        self.retrato = _git("rev-parse", "HEAD")

    def _trabalha(self):
        try:
            self._prepara_git()
            os.makedirs(BACKUP, exist_ok=True)
            if os.path.exists(FW_BUILD):
                shutil.copy2(FW_BUILD, FW_BOM)  # o firmware que esta na placa agora: o ultimo bom
            self.log(f"[autoprog] programando ({self.modelo}): {self.pedido}")
            cmd = [_achar_claude(), "-p", f"Pedido do dono: {self.pedido}", "--model", self.modelo,
                   "--permission-mode", "acceptEdits", "--allowedTools", FERRAMENTAS,
                   "--append-system-prompt", REGRAS, "--output-format", "json", "--no-session-persistence"]
            r = subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", timeout=1800)
            texto = ""
            try:
                texto = json.loads(r.stdout).get("result", "")
            except ValueError:
                texto = r.stdout
            relato = {}
            try:
                relato = json.loads(texto[texto.index("{"):texto.rindex("}") + 1])
            except ValueError:
                pass
            mudados = _mudados(self.retrato)
            self.firmware_mudou = any(m.startswith("cam/") for m in mudados)
            self.python_mudou = any(m.startswith("ponte/") and m.endswith(".py") for m in mudados)
            self.log(f"[autoprog] sessao terminou em {int(time.time() - self.inicio)} s; mudou: {mudados or 'nada'}")
            if not mudados:
                self._volta("")
                self.anunciar(relato.get("resumo_fala") or "Tentei me reprogramar, mas nao mudei nada.")
                return
            erro = self._confere(mudados)
            if erro:
                self.log(f"[autoprog] conferencia falhou: {erro}")
                self._volta("")
                self.anunciar(f"Tentei me reprogramar, mas {erro}. Desfiz a mudanca.")
                return
            self.resumo = relato.get("resumo_fala") or f"mudei {len(mudados)} arquivos."
            self.estado = "pendente"
            self.log(f"[autoprog] pendente: {self.resumo} | {relato.get('detalhes', '')}")
            self.anunciar(f"Terminei. {self.resumo} Compilou certinho. Posso gravar em mim?")
        except Exception as e:
            self.log(f"[autoprog] erro: {e}")
            try:
                self._volta("")
            except Exception:
                pass
            self.anunciar("Deu um problema enquanto eu me reprogramava. Deixei tudo como estava.")

    def _confere(self, mudados):
        """Nao confia so no relato da sessao: compila e confere o Python de novo."""
        proibidos = ("cam/src/wifi_redes.h", "fotos_cadastro/", "cam/data/", "backup_placa/")
        if any(m.startswith(p) for m in mudados for p in proibidos):
            return "mexi num arquivo proibido"
        if self.firmware_mudou:
            r = subprocess.run(["pio", "run", "-d", CAM, "-e", PLACA_ENV], capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=1200)
            if r.returncode != 0:
                return "o firmware nao compilou"
        for m in mudados:
            if m.endswith(".py") and os.path.exists(os.path.join(RAIZ, m)):
                r = subprocess.run([sys.executable, "-m", "py_compile", os.path.join(RAIZ, m)],
                                   capture_output=True, text=True)
                if r.returncode != 0:
                    return f"o arquivo {m} tem erro"
        return ""

    def _volta(self, _):
        if self.retrato:
            _git("reset", "-q", "--hard", self.retrato)
            _git("clean", "-q", "-fd")
        self.estado, self.pedido, self.resumo = "livre", "", ""

    # ---- 4. a resposta do dono
    def gravar(self):
        """Commit da mudanca e o codigo de saida para o supervisor (None se nao ha nada pendente)."""
        if self.estado != "pendente":
            return None
        _git("add", "-A")
        _git("commit", "-q", "-m", f"auto: {self.pedido[:70]}")
        self.log(f"[autoprog] gravando: {self.pedido}")
        with open(RESULTADO, "w", encoding="utf-8") as f:
            json.dump({"pedido": self.pedido, "resumo": self.resumo, "firmware": self.firmware_mudou}, f)
        return EXIT_GRAVAR if self.firmware_mudou else EXIT_REINICIAR

    def descartar(self):
        if self.estado != "pendente":
            return False
        self.log(f"[autoprog] descartado: {self.pedido}")
        self._volta("")
        return True
