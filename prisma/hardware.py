"""Detecção rápida (somente leitura) de placas de vídeo e dispositivos sem driver."""
from __future__ import annotations

import json
import subprocess
import threading

from PySide6.QtCore import QObject, Signal

from . import sysinfo

_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false } catch {}
$g = @(Get-CimInstance Win32_VideoController | Where-Object { $_.PNPDeviceID -like 'PCI\*' } | ForEach-Object {
    [pscustomobject]@{ name = $_.Name; pnp = $_.PNPDeviceID; version = $_.DriverVersion;
                       date = $(if ($_.DriverDate) { $_.DriverDate.ToString('dd/MM/yyyy') } else { '' }) } })
$b = @(Get-CimInstance Win32_PnPEntity | Where-Object { $_.ConfigManagerErrorCode -ne 0 } | ForEach-Object {
    [pscustomobject]@{ name = $_.Name; code = [int]$_.ConfigManagerErrorCode } })
[pscustomobject]@{ gpus = $g; problems = $b } | ConvertTo-Json -Depth 4 -Compress
"""

VENDORS = {
    "VEN_10DE": ("NVIDIA", "NVIDIA App"),
    "VEN_1002": ("AMD", "AMD Adrenalin"),
    "VEN_8086": ("Intel", "Intel Driver & Support Assistant"),
}


def _as_list(v) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def scan(timeout: int = 25) -> dict:
    proc = subprocess.run(
        [sysinfo.powershell_exe(), "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", _SCRIPT],
        capture_output=True, timeout=timeout, creationflags=0x08000000)
    data = json.loads(proc.stdout.decode("utf-8", errors="replace") or "{}")
    gpus = []
    for g in _as_list(data.get("gpus")):
        pnp = str(g.get("pnp") or "").upper()
        vendor, tool = next(((v, t) for k, (v, t) in VENDORS.items() if k in pnp), ("", ""))
        gpus.append({"name": g.get("name") or "Placa de vídeo", "version": g.get("version") or "",
                     "date": g.get("date") or "", "vendor": vendor, "tool": tool})
    problems = [{"name": p.get("name") or "Dispositivo desconhecido", "code": int(p.get("code") or 0)}
                for p in _as_list(data.get("problems"))]
    return {"gpus": gpus, "problems": problems}


class HardwareScanner(QObject):
    """Roda scan() numa thread e entrega o resultado no thread da interface."""
    done = Signal(dict)

    def start(self) -> None:
        threading.Thread(target=self._work, daemon=True).start()

    def _work(self) -> None:
        try:
            result = scan()
        except Exception as exc:  # detecção é só informativa: nunca derruba o app
            result = {"error": str(exc), "gpus": [], "problems": []}
        self.done.emit(result)
