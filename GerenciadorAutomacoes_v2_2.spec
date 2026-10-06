# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []
for package in ["pyautogui", "pygetwindow", "pystray", "PIL", "cv2"]:
    try:
        d, b, h = collect_all(package)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

a = Analysis(["GerenciadorAutomacoes_v2_2.py"], pathex=[], binaries=binaries, datas=datas, hiddenimports=hiddenimports, hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="GerenciadorAutomacoes_v2_2", debug=False, bootloader_ignore_signals=False, strip=False, upx=True, console=False)
