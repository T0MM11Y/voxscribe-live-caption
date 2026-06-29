import os
import shutil
import subprocess
import sys
from pathlib import Path


def build_exe():
    print("--- Starting Build Process ---")

    # 1. Install/Update requirements
    print("Checking dependencies...")
    libs = [
        "pyinstaller",
        "customtkinter",
        "soundcard",
        "numpy<2",
        "faster-whisper",
        "deep-translator",
    ]
    subprocess.run([sys.executable, "-m", "pip", "install"] + libs, check=True)

    # 2. Get library paths for assets and DLLs
    import customtkinter

    ctk_path = os.path.dirname(customtkinter.__file__)

    # 3. Build command
    cmd = [
        "pyinstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        f"--add-data={ctk_path};customtkinter/",
        "--name=VoxScribe",
        "--hidden-import=soundcard",
        "--hidden-import=faster_whisper",
        "--hidden-import=ctranslate2",
        "--hidden-import=deep_translator",
        "--exclude-module=torch",
        "--exclude-module=torchvision",
        "--exclude-module=torchaudio",
        "--exclude-module=transformers",
        "--exclude-module=tensorflow",
        "--exclude-module=onnxruntime",
        "--exclude-module=fsspec",
        "--exclude-module=sympy",
        "--exclude-module=networkx",
        "--exclude-module=pydantic",
        "--exclude-module=rich",
        "--exclude-module=huggingface_hub",
        "--exclude-module=vosk",
        "main.py",
    ]

    print(f"Running command: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

    print("\n--- Build Complete! ---")
    print("Your app is in the 'dist' folder as 'VoxScribe.exe'")


if __name__ == "__main__":
    build_exe()
