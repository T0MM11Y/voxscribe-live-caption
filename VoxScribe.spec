# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Users\\t0mm11y\\AppData\\Local\\Programs\\Python\\Python311\\Lib\\site-packages\\customtkinter', 'customtkinter/')],
    hiddenimports=['soundcard', 'faster_whisper', 'ctranslate2', 'deep_translator'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'torchvision', 'torchaudio', 'transformers', 'tensorflow', 'onnxruntime', 'fsspec', 'sympy', 'networkx', 'pydantic', 'rich', 'huggingface_hub', 'vosk'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='VoxScribe',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
