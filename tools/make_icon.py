"""Gera assets/prisma.ico (vários tamanhos, PNG dentro do ICO) a partir do ícone desenhado no app."""
import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from prisma.glass import make_app_icon  # noqa: E402


def main() -> None:
    app = QApplication(sys.argv[:1])  # noqa: F841
    icon = make_app_icon()
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    blobs = []
    for s in sizes:
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        icon.pixmap(QSize(s, s)).toImage().save(buf, "PNG")
        blobs.append(bytes(ba.data()))
    header = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries = b""
    for s, data in zip(sizes, blobs):
        dim = 0 if s >= 256 else s
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    out = pathlib.Path(__file__).resolve().parents[1] / "assets" / "prisma.ico"
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(header + entries + b"".join(blobs))
    print(f"ícone gerado: {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
