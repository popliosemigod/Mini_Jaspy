"""Liga (ou desliga) o inicio automatico do robo com o Windows.

  ponte\\.venv\\Scripts\\python ferramentas\\inicio_automatico.py           # liga
  ponte\\.venv\\Scripts\\python ferramentas\\inicio_automatico.py --tirar   # desliga

Cria um atalho na pasta Inicializar do usuario: a cada login, o supervisor sobe ESCONDIDO (pythonw) e
fica esperando a placa ser plugada no USB; plugou, o robo comeca a ouvir. Desplugou, espera de novo.
Log de tudo em ponte\\logs\\robo_AAAA-MM-DD.log. Nao precisa de administrador.
"""
import os, subprocess, sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHONW = os.path.join(RAIZ, "ponte", ".venv", "Scripts", "pythonw.exe")
SUPERVISOR = os.path.join(RAIZ, "ponte", "supervisor.py")
INICIAR = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
ATALHO = os.path.join(INICIAR, "Mini_Jaspy robo.lnk")


def main():
    if "--tirar" in sys.argv:
        if os.path.exists(ATALHO):
            os.remove(ATALHO)
        print("inicio automatico desligado")
        return
    if not os.path.exists(PYTHONW):
        sys.exit(f"nao achei {PYTHONW}: rode o instalar.bat antes")
    ps = (f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{ATALHO}');"
          f"$s.TargetPath = '{PYTHONW}';"
          f"$s.Arguments = '\"{SUPERVISOR}\" --logs-placa';"
          f"$s.WorkingDirectory = '{RAIZ}';"
          f"$s.Description = 'Robo Mini_Jaspy: sobe escondido e espera a placa no USB';"
          f"$s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
    print(f"inicio automatico ligado: {ATALHO}")
    print("A cada login o robo sobe sozinho e espera a placa ser plugada. Log: ponte\\logs\\")


if __name__ == "__main__":
    main()
