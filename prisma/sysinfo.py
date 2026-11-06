"""Informações do sistema e utilidades do Windows (somente leitura)."""
from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import winreg
from ctypes import wintypes

HKLM = winreg.HKEY_LOCAL_MACHINE
HKCU = winreg.HKEY_CURRENT_USER


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin(args: list[str]) -> bool:
    """Reabre o programa pedindo elevação (UAC). Retorna True se o novo processo abriu."""
    exe = sys.executable
    if getattr(sys, "frozen", False):
        params = subprocess.list2cmdline(args)
    else:
        params = subprocess.list2cmdline([os.path.abspath(sys.argv[0]), *args])
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
    return rc > 32


def set_app_id(app_id: str) -> None:
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


def _reg(root, path: str, name: str, default=None):
    try:
        with winreg.OpenKey(root, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return default


def windows_info() -> tuple[str, str, int]:
    cv = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
    try:
        build = int(_reg(HKLM, cv, "CurrentBuild", "0") or 0)
    except ValueError:
        build = 0
    display = _reg(HKLM, cv, "DisplayVersion", "") or ""
    edition = _reg(HKLM, cv, "EditionID", "") or ""
    ed = {
        "Professional": "Pro", "Core": "Home", "CoreSingleLanguage": "Home", "CoreCountrySpecific": "Home",
        "Enterprise": "Enterprise", "Education": "Education", "ProfessionalWorkstation": "Pro Workstation",
    }.get(edition, edition)
    name = "Windows 11" if build >= 22000 else "Windows 10"
    return f"{name} {ed}".strip(), display, build


class _MemStatus(ctypes.Structure):
    _fields_ = [
        ("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def memory() -> tuple[float, int]:
    """(RAM total em GB, % em uso)."""
    st = _MemStatus()
    st.dwLength = ctypes.sizeof(_MemStatus)
    try:
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
        return st.ullTotalPhys / (1024 ** 3), int(st.dwMemoryLoad)
    except Exception:
        return 0.0, 0


def winget_available() -> bool:
    if shutil.which("winget"):
        return True
    local = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WindowsApps", "winget.exe")
    return os.path.exists(local)


_UNINSTALL = [
    (HKLM, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    (HKLM, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    (HKCU, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
]


def installed_names() -> set[str]:
    names: set[str] = set()
    for root, path in _UNINSTALL:
        try:
            with winreg.OpenKey(root, path) as k:
                for i in range(winreg.QueryInfoKey(k)[0]):
                    try:
                        sub = winreg.EnumKey(k, i)
                        with winreg.OpenKey(k, sub) as s:
                            names.add(str(winreg.QueryValueEx(s, "DisplayName")[0]).strip())
                    except OSError:
                        continue
        except OSError:
            continue
    return names


def appx_installed(prefix: str) -> bool:
    path = r"Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\Repository\Packages"
    try:
        with winreg.OpenKey(HKCU, path) as k:
            for i in range(winreg.QueryInfoKey(k)[0]):
                if winreg.EnumKey(k, i).startswith(prefix):
                    return True
    except OSError:
        pass
    return False


def installed_apps() -> set[str]:
    """IDs das tarefas de instalação cujos apps já estão no PC."""
    names = installed_names()
    found: set[str] = set()
    if "Brave" in names:
        found.add("install_brave")
    if "Steam" in names:
        found.add("install_steam")
    if "Discord" in names:
        found.add("install_discord")
    if any(n == "Claude" or n.startswith("Claude ") for n in names):
        found.add("install_claude")
    if appx_installed("5319275A.WhatsAppDesktop_"):
        found.add("install_whatsapp")
    return found


def _env(name: str) -> str:
    return os.environ.get(name, "")


def browser_paths() -> list[str]:
    pf, pf86, local = _env("ProgramFiles"), _env("ProgramFiles(x86)"), _env("LOCALAPPDATA")
    return [
        os.path.join(pf, r"BraveSoftware\Brave-Browser\Application\brave.exe"),
        os.path.join(pf86, r"BraveSoftware\Brave-Browser\Application\brave.exe"),
        os.path.join(local, r"BraveSoftware\Brave-Browser\Application\brave.exe"),
        os.path.join(pf, r"Google\Chrome\Application\chrome.exe"),
        os.path.join(pf86, r"Google\Chrome\Application\chrome.exe"),
        os.path.join(local, r"Google\Chrome\Application\chrome.exe"),
        os.path.join(pf, r"Mozilla Firefox\firefox.exe"),
        os.path.join(local, r"Programs\Opera\opera.exe"),
        os.path.join(local, r"Programs\Opera GX\opera.exe"),
        os.path.join(local, r"Vivaldi\Application\vivaldi.exe"),
    ]


def other_browser_installed() -> bool:
    return any(os.path.exists(p) for p in browser_paths())


def edge_installed() -> bool:
    return os.path.exists(os.path.join(_env("ProgramFiles(x86)"), r"Microsoft\Edge\Application\msedge.exe"))


def powershell_exe() -> str:
    root = _env("SystemRoot") or r"C:\Windows"
    # Processo 32 bits em Windows 64 bits: usar o PowerShell nativo (evita redirecionamento do registro)
    if sys.maxsize <= 2 ** 32 and os.path.exists(os.path.join(root, "Sysnative")):
        return os.path.join(root, r"Sysnative\WindowsPowerShell\v1.0\powershell.exe")
    return os.path.join(root, r"System32\WindowsPowerShell\v1.0\powershell.exe")


def restart_pc(delay: int = 5) -> None:
    subprocess.Popen(["shutdown.exe", "/r", "/t", str(delay), "/c", "Prisma: reiniciando para aplicar as otimizações."],
                     creationflags=0x08000000)
