"""Hardware probing, auto tuning, and system validation."""

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class SystemSpecResult:
    passed: bool
    lines: tuple
    failures: tuple


@dataclass(frozen=True)
class ComputeProfile:
    device: str
    compute_type: str
    backend_label: str
    details: str


@dataclass(frozen=True)
class HardwareSnapshot:
    os_label: str
    python_label: str
    cpu_cores: int
    total_ram_gb: Optional[float]
    free_disk_gb: Optional[float]
    gpu_name: str
    storage_path: str


@dataclass(frozen=True)
class PerformanceProfile:
    name: str
    sample_rate: int
    chunk_size: int
    audio_queue_size: int
    partial_translation_delay_ms: int
    preload_secondary_model: bool
    max_cached_models: int
    status_text: str


class HardwareProbe:
    """Collects machine capabilities once so runtime tuning has stable inputs."""

    def probe(self) -> HardwareSnapshot:
        return HardwareSnapshot(
            os_label=platform.platform(),
            python_label=(
                f"{sys.version_info.major}.{sys.version_info.minor}."
                f"{sys.version_info.micro}"
            ),
            cpu_cores=os.cpu_count() or 0,
            total_ram_gb=self._total_ram_gb(),
            free_disk_gb=self._free_disk_gb(),
            gpu_name=self._detect_nvidia_gpu_name(),
            storage_path=str(Path.home()),
        )

    def _total_ram_gb(self) -> Optional[float]:
        ram_bytes = self._get_total_ram_bytes()
        if not ram_bytes:
            return None
        return ram_bytes / (1024**3)

    def _get_total_ram_bytes(self) -> Optional[int]:
        if sys.platform.startswith("win"):
            try:
                import ctypes

                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]

                status = MEMORYSTATUSEX()
                status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                    return int(status.ullTotalPhys)
            except Exception:
                return None

        try:
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            return int(pages * page_size)
        except Exception:
            return None

    def _free_disk_gb(self) -> Optional[float]:
        try:
            usage = shutil.disk_usage(Path.home())
            return usage.free / (1024**3)
        except Exception:
            return None

    def _detect_nvidia_gpu_name(self) -> str:
        if shutil.which("nvidia-smi") is None:
            return self._detect_cuda_dll()

        try:
            command = [
                "nvidia-smi",
                "--query-gpu=name",
                "--format=csv,noheader",
            ]
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=0.8,
                check=False,
            )
            if result.returncode == 0:
                lines = [line.strip() for line in (result.stdout or "").splitlines()]
                lines = [line for line in lines if line]
                if lines:
                    return lines[0]
        except Exception:
            pass

        return self._detect_cuda_dll()

    def _detect_cuda_dll(self) -> str:
        try:
            import ctypes

            ctypes.WinDLL("nvcuda.dll")
            return "NVIDIA CUDA Device"
        except Exception:
            return ""


class AutoTuner:
    """Chooses conservative runtime settings from CPU/RAM/GPU capacity."""

    def tune(self, hardware: HardwareSnapshot) -> PerformanceProfile:
        ram_gb = hardware.total_ram_gb or 0
        cores = hardware.cpu_cores or 0

        if ram_gb >= 24 and cores >= 8:
            return PerformanceProfile(
                name="high",
                sample_rate=16000,
                chunk_size=2048,
                audio_queue_size=4000,
                partial_translation_delay_ms=300,
                preload_secondary_model=True,
                max_cached_models=2,
                status_text="High profile: faster transcription and hot language switching.",
            )

        if ram_gb >= 12 and cores >= 4:
            return PerformanceProfile(
                name="mid",
                sample_rate=16000,
                chunk_size=4096,
                audio_queue_size=2000,
                partial_translation_delay_ms=450,
                preload_secondary_model=False,
                max_cached_models=1,
                status_text="Balanced profile: stable meeting transcription.",
            )

        return PerformanceProfile(
            name="low",
            sample_rate=16000,
            chunk_size=6144,
            audio_queue_size=1300,
            partial_translation_delay_ms=650,
            preload_secondary_model=False,
            max_cached_models=1,
            status_text="Low-resource profile: reduced UI churn and bounded memory.",
        )


class ComputeModeDetector:
    """Detects the best available compute backend for runtime workloads."""

    def __init__(
        self,
        hardware: Optional[HardwareSnapshot] = None,
        performance_profile: Optional[PerformanceProfile] = None,
    ):
        self.hardware = hardware
        self.performance_profile = performance_profile

    def detect(self) -> ComputeProfile:
        gpu_name = (
            self.hardware.gpu_name if self.hardware else self._detect_nvidia_gpu_name()
        )
        if gpu_name:
            return ComputeProfile(
                device="cuda",
                compute_type="int8",
                backend_label="CUDA INT8",
                details=self._details(f"NVIDIA GPU detected: {gpu_name}"),
            )

        return ComputeProfile(
            device="cpu",
            compute_type="default",
            backend_label="CPU",
            details=self._details("No NVIDIA GPU detected. Using CPU backend."),
        )

    def _details(self, backend_text: str) -> str:
        if not self.performance_profile:
            return backend_text
        return f"{backend_text} {self.performance_profile.status_text}"

    def _detect_nvidia_gpu_name(self) -> str:
        if shutil.which("nvidia-smi") is None:
            return self._detect_cuda_dll()

        try:
            command = [
                "nvidia-smi",
                "--query-gpu=name",
                "--format=csv,noheader",
            ]
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=0.8,
                check=False,
            )
            if result.returncode == 0:
                lines = [line.strip() for line in (result.stdout or "").splitlines()]
                lines = [line for line in lines if line]
                if lines:
                    return lines[0]
        except Exception:
            pass

        return self._detect_cuda_dll()

    def _detect_cuda_dll(self) -> str:
        try:
            import ctypes

            ctypes.WinDLL("nvcuda.dll")
            return "NVIDIA CUDA Device"
        except Exception:
            return ""


class SystemSpecChecker:
    """Checks local machine requirements before dependency/model startup work."""

    MIN_PYTHON = (3, 10)
    MIN_CPU_CORES = 2
    MIN_RAM_GB = 8
    MIN_DISK_FREE_GB = 6

    def __init__(self, compute_profile: Optional[ComputeProfile] = None):
        self.compute_profile = compute_profile

    def run(self) -> SystemSpecResult:
        lines = []
        failures = []

        def add_result(name: str, passed: bool, value: str, requirement: str):
            status = "OK" if passed else "FAILED"
            lines.append(f"[{status}] {name}: {value} | Required: {requirement}")
            if not passed:
                failures.append(f"{name}: {value} | Required: {requirement}")

        is_windows = sys.platform.startswith("win")
        add_result(
            "Operating System",
            is_windows,
            platform.platform(),
            "Windows with WASAPI loopback support",
        )

        python_version = sys.version_info
        add_result(
            "Python",
            python_version >= self.MIN_PYTHON,
            f"{python_version.major}.{python_version.minor}.{python_version.micro}",
            f"{self.MIN_PYTHON[0]}.{self.MIN_PYTHON[1]}+",
        )

        cpu_cores = os.cpu_count() or 0
        add_result(
            "CPU Cores",
            cpu_cores >= self.MIN_CPU_CORES,
            str(cpu_cores or "Unknown"),
            f"{self.MIN_CPU_CORES}+ logical cores",
        )

        ram_bytes = self._get_total_ram_bytes()
        if ram_bytes:
            ram_gb = ram_bytes / (1024**3)
            add_result(
                "System RAM",
                ram_gb >= self.MIN_RAM_GB,
                f"{ram_gb:.1f} GB",
                f"{self.MIN_RAM_GB}+ GB",
            )
        else:
            lines.append(
                f"[WARN] System RAM: Unknown | Required: {self.MIN_RAM_GB}+ GB"
            )

        disk_free_gb = self._get_free_disk_gb()
        if disk_free_gb is not None:
            add_result(
                "Free Disk Space",
                disk_free_gb >= self.MIN_DISK_FREE_GB,
                f"{disk_free_gb:.1f} GB",
                f"{self.MIN_DISK_FREE_GB}+ GB for Whisper model download",
            )
        else:
            lines.append(
                "[WARN] Free Disk Space: Unknown | Required: "
                f"{self.MIN_DISK_FREE_GB}+ GB"
            )

        if self.compute_profile is not None:
            lines.append(
                "[INFO] Compute Backend: "
                f"{self.compute_profile.backend_label} | Policy: NVIDIA GPU -> CUDA INT8, otherwise CPU"
            )
            lines.append(f"[INFO] Compute Detail: {self.compute_profile.details}")

        return SystemSpecResult(
            passed=not failures,
            lines=tuple(lines),
            failures=tuple(failures),
        )

    def _get_total_ram_bytes(self) -> Optional[int]:
        if sys.platform.startswith("win"):
            try:
                import ctypes

                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]

                status = MEMORYSTATUSEX()
                status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                    return int(status.ullTotalPhys)
            except Exception:
                return None

        try:
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            return int(pages * page_size)
        except Exception:
            return None

    def _get_free_disk_gb(self) -> Optional[float]:
        try:
            usage = shutil.disk_usage(Path.home())
            return usage.free / (1024**3)
        except Exception:
            return None
