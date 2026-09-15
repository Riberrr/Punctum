"""Rozpoznawanie sprzetu, na ktorym dziala aplikacja.

Uzytkownik wybierajacy tor liczenia musi wiedziec, miedzy czym wybiera -
sama etykieta "GPU / procesor" nic nie mowi. Dlatego pokazujemy nazwy
handlowe, liczbe rdzeni i ilosc pamieci.

Kazdy odczyt jest osobno zabezpieczony. Rozpoznanie sprzetu to funkcja
informacyjna i nie ma prawa przeszkodzic w uruchomieniu programu, wiec
brak jakiegokolwiek zrodla konczy sie napisem "nieznany", a nie wyjatkiem.
"""

from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import dataclass, field


@dataclass
class CpuInfo:
    name: str = "nieznany"
    cores_logical: int = 0
    cores_physical: int = 0
    memory_gb: float = 0.0

    @property
    def summary(self) -> str:
        parts = [self.name]
        if self.cores_physical and self.cores_logical:
            parts.append(f"{self.cores_physical} rdzeni / {self.cores_logical} wątków")
        elif self.cores_logical:
            parts.append(f"{self.cores_logical} wątków")
        if self.memory_gb:
            parts.append(f"{self.memory_gb:.0f} GB RAM")
        return "  •  ".join(parts)


@dataclass
class GpuInfo:
    name: str = "niedostępna"
    vendor: str = ""
    driver: str = ""
    glsl: str = ""
    memory_mb: int = 0
    available: bool = False
    problem: str = ""

    @property
    def summary(self) -> str:
        if not self.available:
            return self.problem or "brak dostępnego kontekstu OpenGL"
        parts = [self.name]
        if self.memory_mb:
            parts.append(f"{self.memory_mb / 1024:.0f} GB pamięci")
        if self.driver:
            parts.append(f"OpenGL {self.driver.split(' ')[0]}")
        return "  •  ".join(parts)


@dataclass
class SystemInfo:
    cpu: CpuInfo = field(default_factory=CpuInfo)
    gpu: GpuInfo = field(default_factory=GpuInfo)
    system: str = ""
    python: str = ""


# ------------------------------------------------------------------ procesor


def _cpu_name_windows() -> str:
    try:
        import winreg

        path = r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
            return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
    except Exception:
        return ""


def _cpu_name_linux() -> str:
    try:
        with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return ""


def _cpu_name_macos() -> str:
    try:
        output = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True, text=True, timeout=3, check=False,
        )
        return output.stdout.strip()
    except Exception:
        return ""


def _physical_cores() -> int:
    """Rdzenie fizyczne - istotne, bo watki logiczne nie daja pelnej wydajnosci."""
    if platform.system() == "Windows":
        try:
            output = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-CimInstance Win32_Processor | "
                 "Measure-Object -Property NumberOfCores -Sum).Sum"],
                capture_output=True, text=True, timeout=8, check=False,
            )
            return int(output.stdout.strip())
        except Exception:
            return 0
    try:
        with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as handle:
            ids = {line.split(":")[1].strip() for line in handle if line.startswith("core id")}
        return len(ids)
    except Exception:
        return 0


def _memory_gb() -> float:
    if platform.system() == "Windows":
        try:
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.dwLength = ctypes.sizeof(MemoryStatus)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return status.ullTotalPhys / (1024**3)
        except Exception:
            return 0.0
    try:
        with open("/proc/meminfo", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if line.startswith("MemTotal"):
                    return int(line.split()[1]) / (1024**2)
    except Exception:
        pass
    return 0.0


def detect_cpu() -> CpuInfo:
    system = platform.system()
    name = (
        _cpu_name_windows() if system == "Windows"
        else _cpu_name_macos() if system == "Darwin"
        else _cpu_name_linux()
    )
    return CpuInfo(
        name=name or platform.processor() or "nieznany",
        cores_logical=os.cpu_count() or 0,
        cores_physical=_physical_cores(),
        memory_gb=_memory_gb(),
    )


# ------------------------------------------------------------ calosc systemu


_CACHE: SystemInfo | None = None


def detect_system(gpu: GpuInfo | None = None) -> SystemInfo:
    return SystemInfo(
        cpu=detect_cpu(),
        gpu=gpu or GpuInfo(),
        system=f"{platform.system()} {platform.release()}",
        python=platform.python_version(),
    )


def system_info(gpu: GpuInfo | None = None, refresh: bool = False) -> SystemInfo:
    """Rozpoznanie sprzetu z pamiecia podreczna.

    Odczyt liczby rdzeni fizycznych na Windows uruchamia PowerShell, co potrafi
    zajac sekunde. Robimy to raz i trzymamy wynik - inaczej otwarcie okna
    ustawien zawieszaloby interfejs.
    """
    global _CACHE
    if _CACHE is None or refresh:
        _CACHE = detect_system(gpu)
    elif gpu is not None:
        _CACHE.gpu = gpu  # dane karty moga dojsc pozniej niz reszta
    return _CACHE
