"""Executa as tarefas em PowerShell numa thread separada e transmite a saída."""
from __future__ import annotations

import datetime
import os
import pathlib
import subprocess
import tempfile
import time

from PySide6.QtCore import QObject, Signal, Slot

from . import sysinfo
from .tasks import BY_ID, Task, build_script, ordered

CREATE_NO_WINDOW = 0x08000000
_RANK = {"ok": 0, "warn": 1, "err": 2}


def log_dir() -> pathlib.Path:
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    d = pathlib.Path(base) / "Prisma" / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def classify(line: str) -> tuple[str, str]:
    s = line.strip()
    for prefix, kind in (("[ok]", "ok"), ("[aviso]", "warn"), ("[erro]", "err")):
        if s.startswith(prefix):
            return kind, s[len(prefix):].strip()
    return "out", line.rstrip()


def plan_run(ids) -> tuple[list[Task], list[str]]:
    """Ordena as tarefas e aplica as regras de segurança. Retorna (tarefas, avisos)."""
    chosen = {i for i in ids if i in BY_ID}
    notes: list[str] = []
    if "remove_edge" in chosen and sysinfo.edge_installed() and "install_brave" not in chosen \
            and not sysinfo.other_browser_installed():
        chosen.add("install_brave")
        notes.append("O Brave será instalado antes de remover o Edge, para você não ficar sem navegador.")
    return ordered(chosen), notes


class Runner(QObject):
    task_started = Signal(int, int, str, str)   # índice, total, id, título
    line = Signal(str, str)                     # tipo (ok/warn/err/out/head), texto
    task_finished = Signal(str, str)            # id, status (ok/warn/err)
    finished = Signal(dict)

    def __init__(self, tasks: list[Task], dry_run: bool = False):
        super().__init__()
        self.tasks = tasks
        self.dry_run = dry_run
        self._stop = False

    def request_stop(self) -> None:
        """Para depois da tarefa atual (interromper no meio pode deixar algo pela metade)."""
        self._stop = True

    @Slot()
    def run(self) -> None:
        workdir = pathlib.Path(tempfile.gettempdir()) / "prisma-run"
        workdir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        logpath = log_dir() / f"prisma-{stamp}.log"
        summary = {"ok": 0, "warn": 0, "err": 0, "skipped": 0, "stopped": False,
                   "dry_run": self.dry_run, "log": str(logpath), "total": len(self.tasks)}
        started = time.monotonic()
        with open(logpath, "w", encoding="utf-8") as log:
            log.write(f"Prisma — {stamp} — {'SIMULAÇÃO' if self.dry_run else 'execução real'}\n")
            for i, task in enumerate(self.tasks):
                if self._stop:
                    summary["stopped"] = True
                    summary["skipped"] = len(self.tasks) - i
                    self.line.emit("warn", f"Parado pelo usuário. {summary['skipped']} tarefas não foram feitas.")
                    break
                self.task_started.emit(i, len(self.tasks), task.id, task.title)
                self.line.emit("head", task.title)
                log.write(f"\n=== {task.title} [{task.id}] ===\n")
                log.flush()
                try:
                    status = self._simulate(task, log) if self.dry_run else self._execute(task, workdir, log)
                except Exception as exc:  # nunca derrubar a fila inteira por causa de uma tarefa
                    status = "err"
                    self.line.emit("err", f"Falha interna: {exc}")
                    log.write(f"[erro] Falha interna: {exc}\n")
                summary[status] += 1
                self.task_finished.emit(task.id, status)
            summary["seconds"] = int(time.monotonic() - started)
            log.write(f"\nResumo: {summary}\n")
        self.finished.emit(summary)

    # ------------------------------------------------------------------
    def _emit(self, kind: str, text: str, log) -> None:
        self.line.emit(kind, text)
        tag = {"ok": "[ok] ", "warn": "[aviso] ", "err": "[erro] "}.get(kind, "")
        log.write(tag + text + "\n")

    def _simulate(self, task: Task, log) -> str:
        lines = [ln.strip() for ln in task.script.strip().splitlines()
                 if ln.strip() and not ln.strip().startswith("#")]
        self._emit("out", f"  simulação — nada foi alterado ({len(lines)} comandos)", log)
        for ln in lines[:2]:
            self._emit("out", "  > " + (ln if len(ln) < 110 else ln[:107] + "..."), log)
        time.sleep(0.12)
        self._emit("ok", "Simulado", log)
        return "ok"

    def _execute(self, task: Task, workdir: pathlib.Path, log) -> str:
        script = workdir / f"{task.id}.ps1"
        script.write_text(build_script(task), encoding="utf-8-sig")
        cmd = [sysinfo.powershell_exe(), "-NoLogo", "-NoProfile", "-NonInteractive",
               "-ExecutionPolicy", "Bypass", "-File", str(script)]
        worst = "ok"
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
        assert proc.stdout is not None
        for raw in iter(proc.stdout.readline, b""):
            text = raw.decode("utf-8", errors="replace")
            # barras de progresso usam \r: fica só o último trecho
            text = [seg for seg in text.replace("\r\n", "\n").rstrip("\n").split("\r") if seg.strip()]
            if not text:
                continue
            kind, msg = classify(text[-1])
            if kind == "out" and not msg.strip():
                continue
            if _RANK.get(kind, 0) > _RANK[worst]:
                worst = kind
            self._emit(kind, msg, log)
        code = proc.wait()
        if code != 0 and worst == "ok":
            worst = "warn"
            self._emit("warn", f"PowerShell terminou com código {code}", log)
        try:
            script.unlink()
        except OSError:
            pass
        return worst
