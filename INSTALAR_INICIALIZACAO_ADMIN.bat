@echo off
setlocal EnableExtensions
 title Gerenciador de Automacoes - Instalar Inicializacao Elevada
cd /d "%~dp0"

:: Solicita permissao de administrador quando necessario.
net session >nul 2>&1
if not "%errorlevel%"=="0" (
    echo Solicitando permissao de administrador...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b 0
)

set "TASK_NAME=GerenciadorAutomacoes_Inicializacao"
set "EXE_PATH=%~dp0dist\GerenciadorAutomacoes_v2_2.exe"
if not exist "%EXE_PATH%" set "EXE_PATH=%~dp0GerenciadorAutomacoes_v2_2.exe"
if not exist "%EXE_PATH%" (
    echo ERRO: EXE nao encontrado.
    echo Gere primeiro o EXE executando GERAR_EXE_V2_2.bat.
    pause
    exit /b 1
)

:: Remove uma versao anterior e cria uma unica tarefa no logon.
schtasks /Delete /TN "%TASK_NAME%" /F >nul 2>&1
schtasks /Create /TN "%TASK_NAME%" /TR "\"%EXE_PATH%\" --startup" /SC ONLOGON /DELAY 0000:30 /RL HIGHEST /F
if errorlevel 1 (
    echo ERRO: nao foi possivel criar a tarefa.
    pause
    exit /b 1
)

echo.
echo Tarefa criada com sucesso:
echo %TASK_NAME%
echo Executar como: administrador / nivel mais alto
echo Acionamento: ao fazer logon no Windows
echo Comando: "%EXE_PATH%" --startup
echo.
echo A fila sera controlada pelo proprio aplicativo.
pause
