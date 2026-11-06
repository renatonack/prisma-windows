"""Ponto de entrada do Prisma."""
from __future__ import annotations

import argparse
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from . import APP_NAME, sysinfo
from .glass import Fonts, font, make_app_icon


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(prog=APP_NAME, description="Debloat, otimização e apps pós-formatação.")
    ap.add_argument("--dry-run", action="store_true", help="simula tudo sem alterar nada no PC")
    ap.add_argument("--screenshot", help=argparse.SUPPRESS)
    ap.add_argument("--page", type=int, default=0, help=argparse.SUPPRESS)
    ap.add_argument("--demo", choices=["confirm", "run", "done"], help=argparse.SUPPRESS)
    ap.add_argument("--delay", type=int, default=1500, help=argparse.SUPPRESS)
    ap.add_argument("--size", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    test_mode = bool(args.screenshot)
    dry = args.dry_run or test_mode

    if not dry and not sysinfo.is_admin():
        if sysinfo.relaunch_as_admin(argv):
            return 0
        app = QApplication(sys.argv[:1])
        QMessageBox.warning(None, APP_NAME, "O Prisma precisa de permissão de administrador para alterar o "
                                            "Windows.\n\nAbra de novo e clique em “Sim” no aviso do Windows.")
        return 1

    sysinfo.set_app_id("Prisma.PosFormatacao")
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(make_app_icon())
    Fonts.init()
    app.setFont(font(13))

    from .ui import MainWindow
    from .tasks import video_tasks

    win = MainWindow(dry_run=dry)
    app.aboutToQuit.connect(win.shutdown)
    if args.size:
        w, h = (int(x) for x in args.size.lower().split("x"))
        win.resize(w, h)
    win.show()

    if test_mode:
        win.go(args.page)
        if args.demo == "confirm":
            QTimer.singleShot(300, win.run_video)
        elif args.demo in ("run", "done"):
            QTimer.singleShot(300, lambda: win.start_run(video_tasks(), "Recomendações do vídeo"))

        def shoot() -> None:
            win.grab().save(args.screenshot)
            win.shutdown()
            app.exit(0)  # quit() passaria pelo closeEvent, que recusa fechar no meio de uma tarefa

        QTimer.singleShot(args.delay, shoot)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
