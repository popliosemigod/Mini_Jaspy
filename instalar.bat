@echo off
chcp 65001 >nul
REM Prepara o projeto do robo numa maquina nova (Windows). Rode com dois cliques ou no terminal.
REM Detalhes: RELATORIO_CONTINUIDADE.md, secao "Levar para outra maquina".
cd /d "%~dp0"

echo === 1/4 Python ===
where python >nul 2>nul || (echo [ERRO] Python nao encontrado. Instale o Python 3.11+ em python.org ^(marque "Add to PATH"^) e rode de novo. & pause & exit /b 1)
python --version

echo === 2/4 Ambiente da ponte (ponte\.venv) ===
if exist ponte\.venv rmdir /s /q ponte\.venv
python -m venv ponte\.venv || (echo [ERRO] falha ao criar o venv & pause & exit /b 1)
ponte\.venv\Scripts\python -m pip install --upgrade pip
ponte\.venv\Scripts\python -m pip install faster-whisper numpy pyserial || (echo [ERRO] falha no pip install & pause & exit /b 1)

echo === 3/4 Baixando o modelo Whisper small (~480 MB, so na primeira vez) ===
ponte\.venv\Scripts\python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8', download_root=r'ponte\modelos'); print('Whisper OK')"

echo === 4/4 Verificacoes ===
where claude >nul 2>nul && (echo Claude Code: OK) || (echo [AVISO] comando 'claude' nao encontrado: instale o Claude Code e faca login - ele e o cerebro do robo.)
powershell -NoProfile -Command "Add-Type -AssemblyName System.Speech; $v=(New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices() | %% { $_.VoiceInfo.Name }; if ($v -match 'Maria') { 'Voz Microsoft Maria (pt-BR): OK' } else { '[AVISO] voz Microsoft Maria nao instalada: Configuracoes > Hora e idioma > Fala > adicionar Portugues (Brasil)' }"
where pio >nul 2>nul || if not exist "%USERPROFILE%\.platformio\penv\Scripts\pio.exe" echo [AVISO] PlatformIO nao encontrado: so e necessario para REGRAVAR a placa ^(instale a extensao PlatformIO IDE no VS Code^).
ponte\.venv\Scripts\python -c "import serial.tools.list_ports as l; p=[x.device for x in l.comports() if x.vid in (0x303A,0x2886,0x1A86)]; print('Placa (XIAO/Freenove) em: ' + (', '.join(p) if p else 'NAO ENCONTRADA - conecte o cabo USB'))"

echo.
echo Pronto! Para conversar com o robo:
echo    ponte\.venv\Scripts\python ponte\robo.py
pause
