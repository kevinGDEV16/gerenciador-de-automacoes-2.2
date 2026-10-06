@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Gerenciador de Automacoes - Limpar Tarefas do Windows
cd /d "%~dp0"

:: Solicita permissao de administrador quando necessario.
net session >nul 2>&1
if not "%errorlevel%"=="0" (
    echo Solicitando permissao de administrador...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b 0
)

echo ================================================
echo   LIMPEZA DE TAREFAS DO GERENCIADOR
echo ================================================
echo.
echo Serao removidas somente tarefas com estes prefixos:
echo   GerenciadorAutomacoes_
echo   AutoLogin2_
echo   AutoLogin_
echo Nenhuma outra tarefa do Windows sera alterada.
echo.

set "FOUND=0"
for /f "usebackq tokens=1 delims=," %%T in (`schtasks /Query /FO CSV /NH 2^>nul`) do (
    set "TASK_NAME=%%~T"
    echo !TASK_NAME! | findstr /I /B /C:"GerenciadorAutomacoes_" /C:"AutoLogin2_" /C:"AutoLogin_" >nul
    if not errorlevel 1 (
        set "FOUND=1"
        echo Removendo: !TASK_NAME!
        schtasks /Delete /TN "!TASK_NAME!" /F >nul 2>&1
        if errorlevel 1 (
            echo   ERRO ao remover !TASK_NAME!
        ) else (
            echo   Removida com sucesso.
        )
    )
)

if "%FOUND%"=="0" echo Nenhuma tarefa relacionada foi encontrada.
echo.
echo Limpeza concluida.
pause
