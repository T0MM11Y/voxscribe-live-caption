
"""Optional runtime dependency detection and install hints."""

DEPENDENCIES_OK = True
MISSING_DEPS = []

try:
    import customtkinter as ctk
except ImportError:
    ctk = None
    DEPENDENCIES_OK = False
    MISSING_DEPS.append("customtkinter")

try:
    import soundcard as sc
except ImportError:
    sc = None
    DEPENDENCIES_OK = False
    MISSING_DEPS.append("soundcard")

try:
    import numpy as np
except ImportError:
    np = None
    DEPENDENCIES_OK = False
    MISSING_DEPS.append("numpy")

try:
    import faster_whisper
except ImportError:
    faster_whisper = None
    DEPENDENCIES_OK = False
    MISSING_DEPS.append("faster-whisper")

try:
    from deep_translator import GoogleTranslator
except ImportError:
    GoogleTranslator = None
    DEPENDENCIES_OK = False
    MISSING_DEPS.append("deep-translator")

try:
    import opencc
except ImportError:
    opencc = None
    DEPENDENCIES_OK = False
    MISSING_DEPS.append("opencc-python-reimplemented")

DEPENDENCY_INSTALL_TARGETS = {
    "numpy": "numpy<2",
}


def dependency_install_target(dep: str) -> str:
    return DEPENDENCY_INSTALL_TARGETS.get(dep, dep)


def dependency_install_command() -> str:
    return " ".join(dependency_install_target(dep) for dep in MISSING_DEPS)
