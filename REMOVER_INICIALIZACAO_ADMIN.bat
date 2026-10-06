@echo off
setlocal
 title Gerenciador de Automacoes - Remover Inicializacao
cd /d "%~dp0"
net session >nul 2>&1
if not "%errorlevel%"=="0" (
    echo Solicitando permissao de administrador...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b 0
)
set "TASK_NAME=GerenciadorAutomacoes_Inicializacao"
schtasks /Delete /TN "%TASK_NAME%" /F
if errorlevel 1 echo A tarefa nao foi encontrada ou ja foi removida.
if not errorlevel 1 echo Tarefa removida com sucesso.
pause
