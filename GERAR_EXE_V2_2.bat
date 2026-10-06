@echo off
setlocal
title Gerenciador de Automacoes V2.2 - Gerar EXE
cd /d "%~dp0"
echo ================================================
echo   GERENCIADOR DE AUTOMACOES V2.2
echo   COMPILADOR DO EXE
echo ================================================
where python >nul 2>&1
if errorlevel 1 (
    echo ERRO: Python nao foi encontrado.
    pause
    exit /b 1
)
echo [1/4] Verificando Python...
python --version
echo [2/4] Instalando dependencias...
python -m pip install -r requirements_v2_2.txt
if errorlevel 1 ( echo ERRO ao instalar dependencias. & pause & exit /b 1 )
echo [3/4] Limpando compilacao anterior...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
echo [4/4] Gerando EXE GUI...
python -m PyInstaller --clean --noconfirm GerenciadorAutomacoes_v2_2.spec
if errorlevel 1 ( echo ERRO ao gerar o EXE. & pause & exit /b 1 )
echo EXE gerado em %cd%\dist\GerenciadorAutomacoes_v2_2.exe
pause
