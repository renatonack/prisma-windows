"""Janela principal do Prisma."""
from __future__ import annotations

import html
import os

from PySide6.QtCore import (QEasingCurve, QObject, QPoint, QPointF, QRectF, Qt, QThread, QTimer, QUrl,
                            QVariantAnimation, Signal)
from PySide6.QtGui import (QBrush, QColor, QDesktopServices, QFont, QLinearGradient, QPainter, QPainterPath,
                           QPalette, QPen)
from PySide6.QtWidgets import (QApplication, QFrame, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QLabel,
                               QPlainTextEdit, QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget)

from . import APP_NAME, APP_VERSION, sysinfo
from .glass import (AA, Backdrop, Chip, Fonts, GlassButton, GlassPanel, GlyphLabel, Icon, IconButton, K,
                    LiquidLens, PrismLogo, ProgressLine, Toggle, W, _Hover, font, make_app_icon, paint_glass)
from .runner import Runner, log_dir, plan_run
from .tasks import (PAGE_DEBLOAT, PAGE_INSTALAR, PAGE_OTIMIZACAO, PAGE_REMOVER, TASKS, Task, tasks_for_page,
                    video_tasks)

VIDEO_URL = "https://youtu.be/BQjZOr1Nye4"
VIDEO_TITLE = "Windows 11 lento? Como fazer DEBLOAT"
PAGE_NAMES = ["Início", "Debloat", "Otimização", "Remover apps", "Instalar apps"]
PAGE_KEYS = [None, PAGE_DEBLOAT, PAGE_OTIMIZACAO, PAGE_REMOVER, PAGE_INSTALAR]
MEDIUM = QFont.Weight.Medium
SEMI = QFont.Weight.DemiBold


def label(text: str, px: float = 13, weight: QFont.Weight = QFont.Weight.Normal, alpha: float = 235,
          family: str | None = None, wrap: bool = False, spacing: float | None = None, rich: bool = False) -> QLabel:
    lab = QLabel(text)
    lab.setFont(font(px, weight, family, spacing))
    pal = lab.palette()
    pal.setColor(QPalette.ColorRole.WindowText, W(alpha))
    pal.setColor(QPalette.ColorRole.Text, W(alpha))
    lab.setPalette(pal)
    lab.setWordWrap(wrap)
    lab.setTextFormat(Qt.TextFormat.RichText if rich else Qt.TextFormat.PlainText)
    lab.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    return lab


def icon_html(glyph: str) -> str:
    return f"<span style=\"font-family:'{Fonts.icons}';\">{glyph}</span>"


def set_alpha(lab: QLabel, alpha: float) -> None:
    pal = lab.palette()
    pal.setColor(QPalette.ColorRole.WindowText, W(alpha))
    lab.setPalette(pal)


SCROLL_CSS = """
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 6px 2px 6px 0; }
QScrollBar::handle:vertical { background: rgba(255,255,255,46); border-radius: 3px; min-height: 40px; }
QScrollBar::handle:vertical:hover { background: rgba(255,255,255,90); }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
"""


def make_scroll(inner: QWidget) -> QScrollArea:
    sc = QScrollArea()
    sc.setWidgetResizable(True)
    sc.setFrameShape(QFrame.Shape.NoFrame)
    sc.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    sc.setStyleSheet(SCROLL_CSS)
    sc.viewport().setAutoFillBackground(False)
    inner.setAutoFillBackground(False)
    sc.setWidget(inner)
    # o vidro amostra o fundo pela posição: ao rolar, redesenha tudo (sem "blit")
    sc.verticalScrollBar().valueChanged.connect(lambda _v: sc.viewport().update())
    return sc


# ---------------------------------------------------------------------------
# Estado de seleção
# ---------------------------------------------------------------------------
class Selection(QObject):
    changed = Signal(str, bool)

    def __init__(self) -> None:
        super().__init__()
        self.state = {t.id: t.default for t in TASKS}

    def set(self, tid: str, on: bool) -> None:
        if self.state.get(tid) != on:
            self.state[tid] = on
            self.changed.emit(tid, on)

    def selected(self, page: str | None = None) -> list[str]:
        return [t.id for t in TASKS if self.state[t.id] and (page is None or t.page == page)]


# ---------------------------------------------------------------------------
# Blocos
# ---------------------------------------------------------------------------
class DragArea(QWidget):
    """Região que arrasta a janela (e maximiza com duplo clique)."""

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            handle = self.window().windowHandle()
            if handle is not None:
                handle.startSystemMove()
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e) -> None:
        win = self.window()
        if hasattr(win, "toggle_maximize"):
            win.toggle_maximize()


class TaskRow(_Hover, QWidget):
    def __init__(self, task: Task, sel: Selection, parent: QWidget | None = None):
        super().__init__(parent)
        self._init_hover()
        self.task, self.sel = task, sel
        self.last = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 13, 16, 13)
        lay.setSpacing(14)
        texts = QVBoxLayout()
        texts.setSpacing(3)
        texts.addWidget(label(task.title, 14, MEDIUM, 242))
        texts.addWidget(label(task.desc, 12, alpha=140, wrap=True))
        if task.note:
            texts.addWidget(label(f"{icon_html(Icon.INFO)}&nbsp; {html.escape(task.note)}", 12, alpha=205,
                                  wrap=True, rich=True))
        lay.addLayout(texts, 1)
        if task.video:
            lay.addWidget(Chip("vídeo"), 0, Qt.AlignmentFlag.AlignVCenter)
        self.status = GlyphLabel("", 14, 235)
        lay.addWidget(self.status, 0, Qt.AlignmentFlag.AlignVCenter)
        self.toggle = Toggle(self, sel.state[task.id])
        lay.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignVCenter)
        self.toggle.toggled.connect(lambda on: sel.set(task.id, on))
        sel.changed.connect(self._on_sel)

    def _on_sel(self, tid: str, on: bool) -> None:
        if tid == self.task.id:
            self.toggle.set_quiet(on)

    def set_busy(self, busy: bool) -> None:
        self.toggle.setEnabled(not busy)

    def set_status(self, status: str) -> None:
        glyph = {"ok": Icon.CHECK, "warn": Icon.WARN, "err": Icon.ERROR, "run": Icon.SPARKLE}.get(status, "")
        self.status.set_glyph(glyph, 140 if status == "run" else 235)

    def mousePressEvent(self, e) -> None:
        e.accept()

    def mouseReleaseEvent(self, e) -> None:
        if (e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint())
                and self.toggle.isEnabled()):
            self.toggle.toggle()
        super().mouseReleaseEvent(e)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(AA)
        if self._h > 0.01:
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect()).adjusted(6, 3, -6, -3), 12, 12)
            p.fillPath(path, W(9 * self._h))
        if not self.last:
            p.setPen(QPen(W(16), 1))
            y = self.height() - 0.5
            p.drawLine(QPointF(18, y), QPointF(self.width() - 16, y))


class Card(GlassPanel):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent, radius=20, tint=10)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 4, 0, 4)
        self.lay.setSpacing(0)


def section_label(text: str) -> QLabel:
    lab = label(text.upper(), 11, SEMI, 125, spacing=1.3)
    lab.setContentsMargins(6, 8, 0, 0)
    return lab


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str, parent: QWidget | None = None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(4, 0, 4, 0)
        v.setSpacing(6)
        v.addWidget(label(title, 30, SEMI, 250, family=Fonts.display))
        sub = label(subtitle, 13.5, alpha=150, wrap=True)
        sub.setMaximumWidth(760)
        v.addWidget(sub)


class TaskPage(QWidget):
    apply_requested = Signal(str)

    def __init__(self, page: str, title: str, subtitle: str, sel: Selection, verb: str, noun: str,
                 section_order: list[str] | None = None, pinned: tuple[str, ...] = (), quick_video: bool = False):
        super().__init__()
        self.page, self.sel, self.verb, self.noun = page, sel, verb, noun
        self.rows: dict[str, TaskRow] = {}
        self.busy = False
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(14)
        v.addWidget(PageHeader(title, subtitle))

        inner = QWidget()
        iv = QVBoxLayout(inner)
        iv.setContentsMargins(0, 0, 12, 10)
        iv.setSpacing(10)
        tasks = tasks_for_page(page)
        sections: list[str] = []
        for t in tasks:
            if t.section not in sections:
                sections.append(t.section)
        if section_order:
            sections.sort(key=lambda s: section_order.index(s) if s in section_order else 99)
        for s in sections:
            iv.addWidget(section_label(s))
            card = Card()
            items = [t for t in tasks if t.section == s]
            items.sort(key=lambda t: (t.id not in pinned, t.order))
            for t in items:
                row = TaskRow(t, sel)
                self.rows[t.id] = row
                card.lay.addWidget(row)
            row.last = True
            iv.addWidget(card)
        iv.addStretch(1)
        v.addWidget(make_scroll(inner), 1)

        foot = QHBoxLayout()
        foot.setContentsMargins(4, 0, 0, 0)
        foot.setSpacing(6)
        self.quick: list[GlassButton] = []
        for text, fn in (("Marcar tudo", self._all), ("Desmarcar", self._none)) + \
                ((("Só o do vídeo", self._video),) if quick_video else ()):
            b = GlassButton(text, variant="ghost", height=34, px=13)
            b.clicked.connect(fn)
            foot.addWidget(b)
            self.quick.append(b)
        foot.addStretch(1)
        self.apply = GlassButton("", Icon.PLAY, "primary", height=44, px=14)
        self.apply.clicked.connect(lambda: self.apply_requested.emit(self.page))
        foot.addWidget(self.apply)
        v.addLayout(foot)
        sel.changed.connect(lambda *_: self.refresh())
        self.refresh()

    def _ids(self) -> list[str]:
        return [t.id for t in tasks_for_page(self.page)]

    def _all(self) -> None:
        for i in self._ids():
            self.sel.set(i, True)

    def _none(self) -> None:
        for i in self._ids():
            self.sel.set(i, False)

    def _video(self) -> None:
        for t in tasks_for_page(self.page):
            self.sel.set(t.id, t.video)

    def refresh(self) -> None:
        n = len(self.sel.selected(self.page))
        self.apply.setText(f"{self.verb} {n} {self.noun if n != 1 else self.noun.rstrip('s')}")
        self.apply.setEnabled(n > 0 and not self.busy)

    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        for r in self.rows.values():
            r.set_busy(busy)
        for b in self.quick:
            b.setEnabled(not busy)
        self.refresh()


class Monogram(QWidget):
    def __init__(self, letter: str, size: int = 50, parent: QWidget | None = None):
        super().__init__(parent)
        self.letter = letter
        self.setFixedSize(size, size)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        paint_glass(p, self, r, r.height() / 2, tint=22, lens=0.0)
        p.setPen(W(248))
        p.setFont(font(self.height() * 0.44, QFont.Weight.Bold, Fonts.display))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, self.letter)


class AppCard(_Hover, GlassPanel):
    def __init__(self, task: Task, sel: Selection, installed: bool, parent: QWidget | None = None):
        super().__init__(parent, radius=22, tint=11)
        self._init_hover()
        self.task, self.sel = task, sel
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(172)
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 18, 18, 16)
        v.setSpacing(8)
        top = QHBoxLayout()
        top.addWidget(Monogram(task.glyph))
        top.addStretch(1)
        self.toggle = Toggle(self, sel.state[task.id])
        top.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignTop)
        v.addLayout(top)
        v.addSpacing(4)
        v.addWidget(label(task.title, 17, SEMI, 248, family=Fonts.display))
        v.addWidget(label(task.desc, 12, alpha=145, wrap=True))
        v.addStretch(1)
        bottom = QHBoxLayout()
        self.chip = Chip("")
        bottom.addWidget(self.chip)
        bottom.addStretch(1)
        self.status = GlyphLabel("", 14, 235)
        bottom.addWidget(self.status)
        v.addLayout(bottom)
        self.set_installed(installed)
        self.toggle.toggled.connect(lambda on: sel.set(task.id, on))
        sel.changed.connect(self._on_sel)

    def set_installed(self, installed: bool) -> None:
        if installed:
            self.chip.set_text("já instalado")
            self.chip.solid = True
        else:
            self.chip.set_text("microsoft store" if self.task.id == "install_whatsapp" else "winget")
            self.chip.solid = False
        self.chip.update()

    def _on_sel(self, tid: str, on: bool) -> None:
        if tid == self.task.id:
            self.toggle.set_quiet(on)

    def set_busy(self, busy: bool) -> None:
        self.toggle.setEnabled(not busy)

    def set_status(self, status: str) -> None:
        glyph = {"ok": Icon.CHECK, "warn": Icon.WARN, "err": Icon.ERROR}.get(status, "")
        self.status.set_glyph(glyph)

    def mousePressEvent(self, e) -> None:
        e.accept()

    def mouseReleaseEvent(self, e) -> None:
        if (e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint())
                and self.toggle.isEnabled()):
            self.toggle.toggle()
        super().mouseReleaseEvent(e)

    def paint_extra(self, p: QPainter) -> None:
        if self._h > 0.01:
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), self.radius, self.radius)
            p.fillPath(path, W(10 * self._h))


class AppsPage(QWidget):
    apply_requested = Signal(str)

    def __init__(self, sel: Selection, installed: set[str]):
        super().__init__()
        self.sel = sel
        self.busy = False
        self.cards: dict[str, AppCard] = {}
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(14)
        v.addWidget(PageHeader(
            "Instalar apps",
            "Instalados pelo winget, direto das fontes oficiais. Se o winget falhar (comum logo após formatar), "
            "o Prisma baixa do site oficial e confere a assinatura digital antes de instalar."))
        inner = QWidget()
        iv = QVBoxLayout(inner)
        iv.setContentsMargins(0, 0, 12, 10)
        iv.setSpacing(12)
        grid = QGridLayout()
        grid.setSpacing(12)
        for i, t in enumerate(tasks_for_page(PAGE_INSTALAR)):
            card = AppCard(t, sel, t.id in installed)
            self.cards[t.id] = card
            grid.addWidget(card, i // 3, i % 3)
        for c in range(3):
            grid.setColumnStretch(c, 1)
        iv.addLayout(grid)
        tip = GlassPanel(radius=18, tint=8)
        th = QHBoxLayout(tip)
        th.setContentsMargins(18, 14, 18, 14)
        th.setSpacing(12)
        th.addWidget(GlyphLabel(Icon.INFO, 16, 200), 0, Qt.AlignmentFlag.AlignTop)
        th.addWidget(label("Ordem segura: os apps são instalados antes da remoção do Edge — assim você nunca fica "
                           "sem navegador. Apps já instalados são só atualizados.", 12.5, alpha=175, wrap=True), 1)
        iv.addWidget(tip)
        iv.addStretch(1)
        v.addWidget(make_scroll(inner), 1)
        foot = QHBoxLayout()
        foot.setContentsMargins(4, 0, 0, 0)
        self.quick = []
        for text, on in (("Marcar tudo", True), ("Desmarcar", False)):
            b = GlassButton(text, variant="ghost", height=34, px=13)
            b.clicked.connect(lambda _=False, on=on: [sel.set(i, on) for i in self.cards])
            foot.addWidget(b)
            self.quick.append(b)
        foot.addStretch(1)
        self.apply = GlassButton("", Icon.DOWNLOAD, "primary", height=44, px=14)
        self.apply.clicked.connect(lambda: self.apply_requested.emit(PAGE_INSTALAR))
        foot.addWidget(self.apply)
        v.addLayout(foot)
        sel.changed.connect(lambda *_: self.refresh())
        self.refresh()

    def refresh(self) -> None:
        n = len(self.sel.selected(PAGE_INSTALAR))
        self.apply.setText(f"Instalar {n} app{'s' if n != 1 else ''}")
        self.apply.setEnabled(n > 0 and not self.busy)

    def set_installed(self, installed: set[str]) -> None:
        for tid, card in self.cards.items():
            card.set_installed(tid in installed)

    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        for c in self.cards.values():
            c.set_busy(busy)
        for b in self.quick:
            b.setEnabled(not busy)
        self.refresh()


class StatTile(GlassPanel):
    def __init__(self, value: str, title: str, sub: str, parent: QWidget | None = None):
        super().__init__(parent, radius=20, tint=10)
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 16, 18, 16)
        v.setSpacing(2)
        self.value = label(value, 30, SEMI, 250, family=Fonts.display)
        self.title = label(title, 12.5, MEDIUM, 215)
        self.sub = label(sub, 11.5, alpha=125, wrap=True)
        v.addWidget(self.value)
        v.addWidget(self.title)
        v.addWidget(self.sub)
        v.addStretch(1)


class HomePage(QWidget):
    run_video = Signal()
    run_all = Signal()

    def __init__(self, sel: Selection, sysline: tuple[str, str, str]):
        super().__init__()
        self.sel = sel
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        inner = QWidget()
        v = QVBoxLayout(inner)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        outer.addWidget(make_scroll(inner))

        hero = GlassPanel(radius=28, tint=9)
        hh = QHBoxLayout(hero)
        hh.setContentsMargins(34, 30, 26, 30)
        hh.setSpacing(18)
        left = QVBoxLayout()
        left.setSpacing(14)
        eyebrow = QHBoxLayout()
        eyebrow.addWidget(Chip("pós-formatação · windows 11", solid=True))
        eyebrow.addStretch(1)
        left.addLayout(eyebrow)
        left.addWidget(label("Windows leve,\nem um clique.", 44, SEMI, 252, family=Fonts.display))
        body = label("Aplica exatamente o que o Canaltech recomendou no vídeo — WinUtil + O&O ShutUp10 — "
                     "já adaptado para Brave, Steam, Discord, WhatsApp e Claude. Remove o Edge e o que a "
                     "Microsoft instala para encher o saco.", 14, alpha=172, wrap=True)
        body.setMaximumWidth(560)
        left.addWidget(body)
        left.addSpacing(6)
        btns = QHBoxLayout()
        btns.setSpacing(10)
        self.video_btn = GlassButton("Aplicar recomendações do vídeo", Icon.PLAY, "primary", height=48, px=14)
        self.all_btn = GlassButton("Fazer tudo", Icon.BOLT, "glass", height=48, px=14)
        self.video_btn.clicked.connect(self.run_video)
        self.all_btn.clicked.connect(self.run_all)
        btns.addWidget(self.video_btn)
        btns.addWidget(self.all_btn)
        btns.addStretch(1)
        left.addLayout(btns)
        foot = label(f"{icon_html(Icon.SHIELD)}&nbsp; Um ponto de restauração é criado antes de qualquer mudança.",
                     12, alpha=120, rich=True)
        left.addWidget(foot)
        hh.addLayout(left, 1)
        hh.addWidget(LiquidLens(size=210), 0, Qt.AlignmentFlag.AlignVCenter)
        v.addWidget(hero)

        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        self.t_video = StatTile(str(len(video_tasks())), "ajustes do vídeo", "WinUtil + O&O ShutUp10")
        self.t_remove = StatTile("0", "apps para remover", "inclui o Microsoft Edge")
        self.t_install = StatTile("0", "apps para instalar", "Brave, Steam, Discord, WhatsApp, Claude")
        self.t_sys = StatTile(sysline[0], sysline[1], sysline[2])
        for t in (self.t_video, self.t_remove, self.t_install, self.t_sys):
            tiles.addWidget(t, 1)
        v.addLayout(tiles)

        strip = GlassPanel(radius=18, tint=8)
        sh = QHBoxLayout(strip)
        sh.setContentsMargins(16, 12, 12, 12)
        sh.setSpacing(12)
        sh.addWidget(GlyphLabel(Icon.VIDEO, 18, 220))
        col = QVBoxLayout()
        col.setSpacing(1)
        col.addWidget(label("Baseado no vídeo do Canaltech", 12.5, MEDIUM, 225))
        col.addWidget(label(f"“{VIDEO_TITLE}” · youtu.be/BQjZOr1Nye4", 11.5, alpha=125))
        sh.addLayout(col, 1)
        watch = GlassButton("Assistir", Icon.PLAY, "ghost", height=34, px=13)
        watch.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(VIDEO_URL)))
        sh.addWidget(watch)
        v.addWidget(strip)
        v.addStretch(1)
        sel.changed.connect(lambda *_: self.refresh())
        self.refresh()

    def refresh(self) -> None:
        rem = self.sel.selected(PAGE_REMOVER)
        self.t_remove.value.setText(str(len(rem)))
        self.t_remove.sub.setText("inclui o Microsoft Edge" if "remove_edge" in rem else "Edge mantido")
        self.t_install.value.setText(str(len(self.sel.selected(PAGE_INSTALAR))))

    def set_busy(self, busy: bool) -> None:
        self.video_btn.setEnabled(not busy)
        self.all_btn.setEnabled(not busy)


# ---------------------------------------------------------------------------
# Barra lateral
# ---------------------------------------------------------------------------
class NavButton(_Hover, QWidget):
    clicked = Signal()

    def __init__(self, text: str, glyph: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._init_hover()
        self.text, self.glyph = text, glyph
        self.checked = False
        self.badge = ""
        self.setFixedHeight(44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_checked(self, on: bool) -> None:
        self.checked = on
        self.update()

    def set_badge(self, text: str) -> None:
        self.badge = text
        self.update()

    def mousePressEvent(self, e) -> None:
        e.accept()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(AA)
        r = QRectF(self.rect())
        if not self.checked and self._h > 0.01:
            path = QPainterPath()
            path.addRoundedRect(r.adjusted(0, 1, 0, -1), 13, 13)
            p.fillPath(path, W(10 * self._h))
        a = 255 if self.checked else 165 + 70 * self._h
        p.setPen(W(a))
        p.setFont(font(16, family=Fonts.icons))
        p.drawText(QRectF(14, 0, 22, r.height()), Qt.AlignmentFlag.AlignCenter, self.glyph)
        p.setFont(font(14, SEMI if self.checked else MEDIUM))
        p.drawText(QRectF(48, 0, r.width() - 90, r.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text)
        if self.badge:
            f = font(11, SEMI)
            p.setFont(f)
            bw = max(24.0, p.fontMetrics().horizontalAdvance(self.badge) + 14.0)
            br = QRectF(r.width() - bw - 10, r.center().y() - 10, bw, 20)
            path = QPainterPath()
            path.addRoundedRect(br, 10, 10)
            if self.checked:
                p.fillPath(path, W(235))
                p.setPen(QColor(10, 10, 10))
            else:
                p.fillPath(path, W(18))
                p.setPen(W(190))
            p.drawText(br, Qt.AlignmentFlag.AlignCenter, self.badge)


class Sidebar(GlassPanel):
    page_selected = Signal(int)

    def __init__(self, info_lines: list[tuple[str, str]], dry_run: bool, parent: QWidget | None = None):
        super().__init__(parent, radius=24, tint=9)
        self.setFixedWidth(238)
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 16, 12, 16)
        v.setSpacing(4)
        brand = DragArea()
        bh = QHBoxLayout(brand)
        bh.setContentsMargins(8, 2, 4, 2)
        bh.setSpacing(10)
        bh.addWidget(PrismLogo(32))
        col = QVBoxLayout()
        col.setSpacing(0)
        col.addWidget(label(APP_NAME, 19, SEMI, 252, family=Fonts.display))
        col.addWidget(label("pós-formatação do Windows", 11, alpha=125))
        bh.addLayout(col, 1)
        v.addWidget(brand)
        v.addSpacing(22)
        self.items: list[NavButton] = []
        for i, (name, glyph) in enumerate(zip(PAGE_NAMES, (Icon.HOME, Icon.SHIELD, Icon.BOLT, Icon.DELETE,
                                                          Icon.DOWNLOAD))):
            b = NavButton(name, glyph)
            b.clicked.connect(lambda i=i: self.page_selected.emit(i))
            v.addWidget(b)
            self.items.append(b)
        v.addStretch(1)
        info = GlassPanel(radius=16, tint=6, sample=False, rim=0.6, sheen=False)
        iv = QVBoxLayout(info)
        iv.setContentsMargins(12, 12, 12, 12)
        iv.setSpacing(7)
        for glyph, text in info_lines:
            row = QHBoxLayout()
            row.setSpacing(8)
            row.addWidget(GlyphLabel(glyph, 12, 170))
            row.addWidget(label(text, 11.5, alpha=165, wrap=True), 1)
            iv.addLayout(row)
        if dry_run:
            chip_row = QHBoxLayout()
            chip_row.addWidget(Chip("modo simulação", solid=True))
            chip_row.addStretch(1)
            iv.addLayout(chip_row)
        v.addWidget(info)
        v.addSpacing(6)
        v.addWidget(label(f"v{APP_VERSION}  ·  feito com PySide6", 10.5, alpha=90))
        self._ind = QRectF()
        self._current = 0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(380)
        self._anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self._anim.valueChanged.connect(self._set_ind)

    def _set_ind(self, r) -> None:
        self._ind = QRectF(r)
        self.update()

    def select(self, i: int, animate: bool = True) -> None:
        self._current = i
        for j, b in enumerate(self.items):
            b.set_checked(i == j)
        target = QRectF(self.items[i].geometry())
        if animate and not self._ind.isNull():
            self._anim.stop()
            self._anim.setStartValue(self._ind)
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self._set_ind(target)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        QTimer.singleShot(0, lambda: self.select(self._current, animate=False))

    def paint_extra(self, p: QPainter) -> None:
        if not self._ind.isNull():
            paint_glass(p, self, self._ind, 14, tint=26, sample=False, rim=1.1, sheen=True)


# ---------------------------------------------------------------------------
# Painel de atividade (progresso + registro)
# ---------------------------------------------------------------------------
class ActivityPanel(GlassPanel):
    stop_requested = Signal()
    open_log = Signal()
    COLLAPSED = 64
    EXPANDED = 290

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent, radius=22, tint=11)
        self.setFixedHeight(self.COLLAPSED)
        self.expanded = False
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 12, 12, 12)
        v.setSpacing(10)
        top = QHBoxLayout()
        top.setSpacing(12)
        self.glyph = GlyphLabel(Icon.CHECK, 15, 210)
        top.addWidget(self.glyph, 0, Qt.AlignmentFlag.AlignVCenter)
        col = QVBoxLayout()
        col.setSpacing(5)
        self.title = label("Pronto. Escolha o que fazer e clique em aplicar.", 13, MEDIUM, 225)
        self.progress = ProgressLine()
        col.addWidget(self.title)
        col.addWidget(self.progress)
        top.addLayout(col, 1)
        self.count = label("", 12, alpha=150)
        top.addWidget(self.count)
        self.stop_btn = GlassButton("Parar", Icon.STOP, "ghost", height=34, px=12)
        self.stop_btn.clicked.connect(self.stop_requested)
        self.stop_btn.hide()
        top.addWidget(self.stop_btn)
        self.file_btn = GlassButton("Arquivo", Icon.FOLDER, "ghost", height=34, px=12)
        self.file_btn.clicked.connect(self.open_log)
        top.addWidget(self.file_btn)
        self.log_btn = GlassButton("Registro", Icon.UP, "ghost", height=34, px=12)
        self.log_btn.clicked.connect(lambda: self.set_expanded(not self.expanded))
        top.addWidget(self.log_btn)
        v.addLayout(top)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(6000)
        self.log.setFont(font(12, family=Fonts.mono))
        self.log.setFrameShape(QFrame.Shape.NoFrame)
        self.log.setStyleSheet(
            "QPlainTextEdit { background: transparent; color: rgba(255,255,255,200); border: none;"
            " selection-background-color: rgba(255,255,255,200); selection-color: black; }" + SCROLL_CSS)
        self.log.viewport().setAutoFillBackground(False)
        self.log.hide()
        v.addWidget(self.log, 1)
        self._hanim = QVariantAnimation(self)
        self._hanim.setDuration(320)
        self._hanim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hanim.valueChanged.connect(lambda h: self.setFixedHeight(int(h)))
        self._hanim.finished.connect(self._anim_done)
        self.append("info", "Registro de atividades do Prisma. Tudo o que for feito aparece aqui.")

    def _anim_done(self) -> None:
        if not self.expanded:
            self.log.hide()

    def set_expanded(self, on: bool) -> None:
        if on == self.expanded:
            return
        self.expanded = on
        self.log_btn.set_icon_glyph(Icon.DOWN if on else Icon.UP)
        if on:
            self.log.show()
        self._hanim.stop()
        self._hanim.setStartValue(self.height())
        self._hanim.setEndValue(self.EXPANDED if on else self.COLLAPSED)
        self._hanim.start()

    def append(self, kind: str, text: str) -> None:
        t = html.escape(text)
        ic = lambda g: f"<span style=\"font-family:'{Fonts.icons}';\">{g}</span>&nbsp;"  # noqa: E731
        if kind == "head":
            line = f"<br><span style='color:#ffffff; font-weight:600;'>{ic(Icon.PLAY)}{t}</span>"
        elif kind == "ok":
            line = f"<span style='color:#f2f2f2;'>{ic(Icon.CHECK)}{t}</span>"
        elif kind == "warn":
            line = f"<span style='color:#c8c8c8; font-style:italic;'>{ic(Icon.WARN)}{t}</span>"
        elif kind == "err":
            line = f"<span style='color:#ffffff; font-weight:700; text-decoration:underline;'>{ic(Icon.ERROR)}{t}</span>"
        elif kind == "info":
            line = f"<span style='color:#9a9a9e;'>{ic(Icon.INFO)}{t}</span>"
        else:
            line = f"<span style='color:#8e8e93;'>{t.replace('  ', '&nbsp;&nbsp;')}</span>"
        self.log.appendHtml(line)
        sb = self.log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def start(self, total: int, title: str) -> None:
        self.glyph.set_glyph(Icon.SPARKLE, 230)
        self.title.setText(title)
        self.count.setText(f"0 de {total}")
        self.progress.set_value(0.0)
        self.progress.set_busy(True)
        self.stop_btn.show()
        self.stop_btn.setEnabled(True)
        self.stop_btn.setText("Parar")

    def step(self, i: int, total: int, title: str) -> None:
        self.title.setText(title)
        self.count.setText(f"{i + 1} de {total}")
        self.progress.set_value(i / max(1, total))

    def stopping(self) -> None:
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText("Parando...")

    def done(self, summary: dict) -> None:
        self.progress.set_busy(False)
        self.progress.set_value(1.0)
        self.stop_btn.hide()
        bad = summary.get("err", 0)
        self.glyph.set_glyph(Icon.ERROR if bad else Icon.CHECK, 230)
        mins, secs = divmod(int(summary.get("seconds", 0)), 60)
        done = summary.get("ok", 0) + summary.get("warn", 0) + bad
        self.title.setText(("Simulação concluída" if summary.get("dry_run") else "Concluído")
                           + f" em {mins}min {secs:02d}s")
        self.count.setText(f"{done} de {summary.get('total', done)}")


# ---------------------------------------------------------------------------
# Diálogo sobreposto
# ---------------------------------------------------------------------------
class Overlay(QWidget):
    def __init__(self, host: "MainWindow", glyph: str, title: str, body_html: str,
                 buttons: list[tuple[str, str, object]], dismissable: bool = True):
        super().__init__(host)
        self.host = host
        self.dismissable = dismissable
        self.setGeometry(host.inner_rect().toRect())
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        outer = QVBoxLayout(self)
        outer.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        self.card = GlassPanel(radius=28, tint=24)
        self.card.setFixedWidth(520)
        cv = QVBoxLayout(self.card)
        cv.setContentsMargins(30, 28, 30, 24)
        cv.setSpacing(14)
        head = QHBoxLayout()
        head.setSpacing(12)
        head.addWidget(GlyphLabel(glyph, 22, 245))
        head.addWidget(label(title, 22, SEMI, 252, family=Fonts.display), 1)
        cv.addLayout(head)
        body = label(body_html, 13.5, alpha=195, wrap=True, rich=True)
        body.setOpenExternalLinks(False)
        cv.addWidget(body)
        cv.addSpacing(6)
        bh = QHBoxLayout()
        bh.setSpacing(8)
        bh.addStretch(1)
        first_primary = None
        for text, variant, cb in buttons:
            b = GlassButton(text, variant=variant, height=42, px=13.5)
            b.clicked.connect(lambda _=False, cb=cb: self._choose(cb))
            bh.addWidget(b)
            if variant == "primary" and first_primary is None:
                first_primary = b
        cv.addLayout(bh)
        row.addWidget(self.card)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)
        self._fx = QGraphicsOpacityEffect(self)
        self._fx.setOpacity(0.0)
        self.setGraphicsEffect(self._fx)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(lambda v: self._fx.setOpacity(float(v)))
        self.show()
        self.raise_()
        self.setFocus()
        self._fade(0.0, 1.0)

    def _fade(self, a: float, b: float, then=None) -> None:
        self._anim.stop()
        self._after = then or (lambda: self.setGraphicsEffect(None))
        if not getattr(self, "_wired", False):
            self._anim.finished.connect(lambda: self._after())
            self._wired = True
        if self.graphicsEffect() is None:
            self._fx = QGraphicsOpacityEffect(self)
            self.setGraphicsEffect(self._fx)
        self._fx.setOpacity(a)
        self._anim.setStartValue(a)
        self._anim.setEndValue(b)
        self._anim.start()

    def _choose(self, cb) -> None:
        self.close_overlay()
        if callable(cb):
            QTimer.singleShot(0, cb)

    def close_overlay(self) -> None:
        self._fade(1.0, 0.0, then=self.deleteLater)

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Escape and self.dismissable:
            self.close_overlay()
        else:
            super().keyPressEvent(e)

    def mousePressEvent(self, e) -> None:
        if self.dismissable and not self.card.geometry().contains(e.position().toPoint()):
            self.close_overlay()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(AA)
        path = QPainterPath()
        rad = self.host.radius()
        path.addRoundedRect(QRectF(self.rect()), rad, rad)
        p.fillPath(path, K(150))


# ---------------------------------------------------------------------------
# Janela principal
# ---------------------------------------------------------------------------
class MainWindow(QWidget):
    SHADOW = 14
    RADIUS = 18

    def __init__(self, dry_run: bool = False):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowMinMaxButtonsHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.dry_run = dry_run
        self.setWindowTitle(APP_NAME + (" — simulação" if dry_run else ""))
        self.setWindowIcon(make_app_icon())
        self.backdrop = Backdrop()
        self.sel = Selection()
        self.busy = False
        self._close_after = False
        self.thread: QThread | None = None
        self.runner: Runner | None = None
        self.last_log: str | None = None
        self.installed = sysinfo.installed_apps()

        win_name, win_ver, build = sysinfo.windows_info()
        ram, load = sysinfo.memory()
        admin = sysinfo.is_admin()
        winget = sysinfo.winget_available()
        info_lines = [
            (Icon.CPU, f"{win_name} {win_ver}".strip()),
            (Icon.SHIELD, "Administrador" if admin else "Sem permissão de admin"),
            (Icon.DOWNLOAD, "winget disponível" if winget else "winget ausente (usa download direto)"),
        ]
        sysline = (win_ver or str(build), win_name, f"{ram:.0f} GB de RAM · {load}% em uso agora")

        root = QHBoxLayout(self)
        root.setSpacing(12)
        self.sidebar = Sidebar(info_lines, dry_run)
        self.sidebar.page_selected.connect(self.go)
        root.addWidget(self.sidebar)
        right = QVBoxLayout()
        right.setSpacing(12)
        top = DragArea()
        top.setFixedHeight(34)
        th = QHBoxLayout(top)
        th.setContentsMargins(6, 0, 0, 0)
        th.setSpacing(4)
        self.crumb = label("Início", 12.5, MEDIUM, 140)
        th.addWidget(self.crumb)
        th.addStretch(1)
        self.btn_min = IconButton(Icon.MIN, size=34)
        self.btn_max = IconButton(Icon.MAX, size=34)
        self.btn_close = IconButton(Icon.CLOSE, size=34, danger=True)
        self.btn_min.clicked.connect(self.showMinimized)
        self.btn_max.clicked.connect(self.toggle_maximize)
        self.btn_close.clicked.connect(self.close)
        for b in (self.btn_min, self.btn_max, self.btn_close):
            th.addWidget(b)
        right.addWidget(top)

        self.stack = QStackedWidget()
        self.home = HomePage(self.sel, sysline)
        self.home.run_video.connect(self.run_video)
        self.home.run_all.connect(self.run_everything)
        self.p_debloat = TaskPage(
            PAGE_DEBLOAT, "Debloat e privacidade",
            "Tudo o que o vídeo marca no WinUtil (essenciais, avançados, preferências e Windows Update) e no "
            "O&O ShutUp10. Itens com a etiqueta VÍDEO fazem parte do botão principal.",
            self.sel, "Aplicar", "ajustes", quick_video=True)
        self.p_otim = TaskPage(
            PAGE_OTIMIZACAO, "Otimização",
            "Limpeza (feita no vídeo) e ajustes extras de desempenho para jogos.",
            self.sel, "Aplicar", "ajustes", section_order=["Limpeza", "Desempenho", "Navegador", "Extras"],
            quick_video=True)
        self.p_remove = TaskPage(
            PAGE_REMOVER, "Remover apps inúteis",
            "Tira o Edge e o que a Microsoft instala para encher o saco. Os pacotes também saem para novos "
            "usuários, então não voltam sozinhos.",
            self.sel, "Remover", "itens", section_order=["Navegador", "Microsoft", "Pré-instalados"],
            pinned=("remove_onedrive",))
        self.p_install = AppsPage(self.sel, self.installed)
        for pg in (self.p_debloat, self.p_otim, self.p_remove, self.p_install):
            pg.apply_requested.connect(self.run_page)
        for w in (self.home, self.p_debloat, self.p_otim, self.p_remove, self.p_install):
            self.stack.addWidget(w)
        right.addWidget(self.stack, 1)
        self.activity = ActivityPanel()
        self.activity.stop_requested.connect(self.stop_run)
        self.activity.open_log.connect(self.open_log)
        right.addWidget(self.activity)
        root.addLayout(right, 1)

        self.sel.changed.connect(lambda *_: self._update_badges())
        self._update_badges()
        self._apply_margins()
        self._fit_to_screen()
        self.sidebar.select(0, animate=False)

    # ---------------------------------------------------------------- janela
    def _fit_to_screen(self) -> None:
        scr = QApplication.primaryScreen().availableGeometry()
        w = min(1240, scr.width() - 40)
        h = min(820, scr.height() - 40)
        self.setMinimumSize(min(1000, w), min(660, h))
        self.resize(w, h)
        self.move(scr.center() - QPoint(w // 2, h // 2))

    def margin(self) -> int:
        return 0 if self.isMaximized() else self.SHADOW

    def radius(self) -> float:
        return 0.0 if self.isMaximized() else float(self.RADIUS)

    def inner_rect(self) -> QRectF:
        m = self.margin()
        return QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m)

    def _apply_margins(self) -> None:
        m = self.margin() + 12
        self.layout().setContentsMargins(m, m, m, m)
        self.btn_max.set_icon_glyph(Icon.RESTORE if self.isMaximized() else Icon.MAX)

    def toggle_maximize(self) -> None:
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def changeEvent(self, e) -> None:
        super().changeEvent(e)
        if e.type() == e.Type.WindowStateChange:
            self._apply_margins()
            for ov in self.findChildren(Overlay):
                ov.setGeometry(self.inner_rect().toRect())
            self.update()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        for ov in self.findChildren(Overlay):
            ov.setGeometry(self.inner_rect().toRect())

    def _edges(self, pos: QPointF) -> Qt.Edge:
        m = max(6, self.margin())
        edges = Qt.Edge(0)
        if self.isMaximized():
            return edges
        if pos.x() < m:
            edges |= Qt.Edge.LeftEdge
        if pos.x() > self.width() - m:
            edges |= Qt.Edge.RightEdge
        if pos.y() < m:
            edges |= Qt.Edge.TopEdge
        if pos.y() > self.height() - m:
            edges |= Qt.Edge.BottomEdge
        return edges

    def mouseMoveEvent(self, e) -> None:
        ed = self._edges(e.position())
        shapes = {
            Qt.Edge.LeftEdge: Qt.CursorShape.SizeHorCursor, Qt.Edge.RightEdge: Qt.CursorShape.SizeHorCursor,
            Qt.Edge.TopEdge: Qt.CursorShape.SizeVerCursor, Qt.Edge.BottomEdge: Qt.CursorShape.SizeVerCursor,
            Qt.Edge.LeftEdge | Qt.Edge.TopEdge: Qt.CursorShape.SizeFDiagCursor,
            Qt.Edge.RightEdge | Qt.Edge.BottomEdge: Qt.CursorShape.SizeFDiagCursor,
            Qt.Edge.RightEdge | Qt.Edge.TopEdge: Qt.CursorShape.SizeBDiagCursor,
            Qt.Edge.LeftEdge | Qt.Edge.BottomEdge: Qt.CursorShape.SizeBDiagCursor,
        }
        if ed in shapes:
            self.setCursor(shapes[ed])
        else:
            self.unsetCursor()
        super().mouseMoveEvent(e)

    def mousePressEvent(self, e) -> None:
        ed = self._edges(e.position())
        if e.button() == Qt.MouseButton.LeftButton and ed != Qt.Edge(0) and self.windowHandle():
            self.windowHandle().startSystemResize(ed)
            return
        super().mousePressEvent(e)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(AA)
        inner = self.inner_rect()
        self.backdrop.ensure(self.width(), self.height(), self.devicePixelRatioF(), inner)
        m = self.margin()
        rad = self.radius()
        if m:
            p.setBrush(Qt.BrushStyle.NoBrush)
            for i in range(m):
                t = (i + 1) / m
                p.setPen(QPen(K(46 * t * t), 1.0))
                rr = QRectF(self.rect()).adjusted(i + 0.5, i + 2.5, -i - 0.5, -i + 1.5)
                p.drawRoundedRect(rr, rad + m - i, rad + m - i)
        path = QPainterPath()
        path.addRoundedRect(inner, rad, rad)
        p.save()
        p.setClipPath(path)
        if self.backdrop.sharp is not None:
            p.drawImage(QPointF(0, 0), self.backdrop.sharp)
        p.restore()
        g = QLinearGradient(inner.topLeft(), inner.bottomLeft())
        g.setColorAt(0, W(70))
        g.setColorAt(0.2, W(22))
        g.setColorAt(1, W(14))
        p.setPen(QPen(QBrush(g), 1))
        p.drawPath(path)

    # ---------------------------------------------------------------- navegação
    def go(self, i: int) -> None:
        self.stack.setCurrentIndex(i)
        self.sidebar.select(i)
        self.crumb.setText(PAGE_NAMES[i])

    def _update_badges(self) -> None:
        for i, key in enumerate(PAGE_KEYS):
            if key:
                n = len(self.sel.selected(key))
                self.sidebar.items[i].set_badge(str(n) if n else "")

    # ---------------------------------------------------------------- execução
    def run_video(self) -> None:
        self.request_run([t.id for t in video_tasks()], "Recomendações do vídeo",
                         "Vai aplicar tudo o que o Canaltech ativa no vídeo (WinUtil + O&O ShutUp10), já com as "
                         "adaptações para seus apps, e remover o Microsoft Edge.")

    def run_everything(self) -> None:
        self.request_run(self.sel.selected(), "Fazer tudo",
                         "Vai aplicar tudo o que está marcado em todas as páginas: debloat, otimização, "
                         "instalação e remoção de apps.")

    def run_page(self, page: str) -> None:
        ids = self.sel.selected(page)
        if page in (PAGE_OTIMIZACAO, PAGE_REMOVER) and self.sel.state.get("restore_point"):
            ids.append("restore_point")
        names = {PAGE_DEBLOAT: "Debloat e privacidade", PAGE_OTIMIZACAO: "Otimização",
                 PAGE_REMOVER: "Remover apps", PAGE_INSTALAR: "Instalar apps"}
        self.request_run(ids, names[page], "Vai aplicar os itens marcados nesta página.")

    def request_run(self, ids: list[str], title: str, intro: str) -> None:
        if self.busy:
            return
        tasks, notes = plan_run(ids)
        if not tasks:
            Overlay(self, Icon.INFO, "Nada marcado", "Marque pelo menos um item para continuar.",
                    [("Ok", "primary", None)])
            return
        counts: dict[str, int] = {}
        for t in tasks:
            counts[t.page] = counts.get(t.page, 0) + 1
        parts = []
        for key, one, many in ((PAGE_DEBLOAT, "ajuste de debloat", "ajustes de debloat"),
                               (PAGE_OTIMIZACAO, "de otimização", "de otimização"),
                               (PAGE_INSTALAR, "app para instalar", "apps para instalar"),
                               (PAGE_REMOVER, "item para remover", "itens para remover")):
            n = counts.get(key, 0)
            if n:
                parts.append(f"<b>{n}</b> {one if n == 1 else many}")
        system_change = any(t.page != PAGE_INSTALAR for t in tasks)
        body = f"{html.escape(intro)}<br><br>" + " · ".join(parts) + "."
        if any(t.id == "restore_point" for t in tasks):
            body += "<br>Primeiro é criado um ponto de restauração."
        for n in notes:
            body += f"<br>{icon_html(Icon.INFO)}&nbsp; {html.escape(n)}"
        body += "<br><br><span style='color:#a0a0a5;'>Leva de 5 a 20 minutos, depende da internet. "
        body += "Não desligue o PC no meio." + (" Reinicie no final." if system_change else "") + "</span>"
        if self.dry_run:
            body += "<br><b>Modo simulação:</b> nada será alterado no PC."
        Overlay(self, Icon.PLAY, title, body,
                [("Cancelar", "ghost", None), ("Começar", "primary", lambda: self.start_run(tasks, title))])

    def _pages(self):
        return (self.home, self.p_debloat, self.p_otim, self.p_remove, self.p_install)

    def _row_widgets(self, tid: str):
        for pg in (self.p_debloat, self.p_otim, self.p_remove):
            if tid in pg.rows:
                yield pg.rows[tid]
        if tid in self.p_install.cards:
            yield self.p_install.cards[tid]

    def start_run(self, tasks: list[Task], title: str) -> None:
        if self.busy:
            return
        self.busy = True
        for pg in self._pages():
            pg.set_busy(True)
        for t in tasks:
            for w in self._row_widgets(t.id):
                w.set_status("")
        self.activity.start(len(tasks), title)
        self.activity.append("info", f"{title}: {len(tasks)} tarefas" + (" (simulação)" if self.dry_run else ""))
        self.activity.set_expanded(True)
        self.thread = QThread(self)
        self.runner = Runner(tasks, dry_run=self.dry_run)
        self.runner.moveToThread(self.thread)
        self.thread.started.connect(self.runner.run)
        self.runner.task_started.connect(self._on_task_started)
        self.runner.line.connect(self.activity.append)
        self.runner.task_finished.connect(self._on_task_finished)
        self.runner.finished.connect(self._on_finished)
        self.runner.finished.connect(self.thread.quit)
        self.thread.finished.connect(self._cleanup_thread)
        self.thread.start()

    def _cleanup_thread(self) -> None:
        if self.thread is not None:
            self.thread.deleteLater()
        self.runner = None
        self.thread = None
        if self._close_after:
            self.close()

    def _on_task_started(self, i: int, total: int, tid: str, title: str) -> None:
        self.activity.step(i, total, title)
        for w in self._row_widgets(tid):
            if isinstance(w, TaskRow):
                w.set_status("run")

    def _on_task_finished(self, tid: str, status: str) -> None:
        for w in self._row_widgets(tid):
            w.set_status(status)

    def shutdown(self) -> None:
        """Chamado quando o app vai sair: espera a tarefa atual terminar."""
        if self.runner is not None:
            self.runner.request_stop()
        if self.thread is not None:
            self.thread.quit()
            self.thread.wait(60000)

    def stop_run(self) -> None:
        if self.runner is not None and self.busy:
            self.runner.request_stop()
            self.activity.stopping()
            self.activity.append("warn", "Vou parar assim que a tarefa atual terminar.")

    def _on_finished(self, summary: dict) -> None:
        self.busy = False
        self.last_log = summary.get("log")
        for pg in self._pages():
            pg.set_busy(False)
        self.activity.done(summary)
        self.installed = sysinfo.installed_apps()
        self.p_install.set_installed(self.installed)
        if self._close_after:
            return  # fecha quando a thread terminar (_cleanup_thread)
        ok, warn, err = summary.get("ok", 0), summary.get("warn", 0), summary.get("err", 0)
        stats = f"<b>{ok}</b> concluídas · <b>{warn}</b> com aviso · <b>{err}</b> com erro"
        if summary.get("stopped"):
            stats += f" · <b>{summary.get('skipped', 0)}</b> não feitas"
        if summary.get("dry_run"):
            Overlay(self, Icon.CHECK, "Simulação concluída",
                    f"{stats}.<br><br>Nada foi alterado. Rode o Prisma sem <b>--dry-run</b> para aplicar de verdade.",
                    [("Ver arquivo de registro", "ghost", self.open_log), ("Fechar", "primary", None)])
            return
        body = stats + ".<br><br>"
        if warn or err:
            body += "Avisos e erros estão no registro (painel de baixo). Itens com aviso normalmente foram aplicados " \
                    "em parte — por exemplo, um app que já não existia.<br><br>"
        body += "<b>Reinicie o PC</b> para que todas as mudanças tenham efeito."
        Overlay(self, Icon.CHECK if not err else Icon.WARN, "Pronto!", body,
                [("Ver arquivo de registro", "ghost", self.open_log), ("Depois", "glass", None),
                 ("Reiniciar agora", "primary", self.restart)])

    def restart(self) -> None:
        if not self.dry_run:
            sysinfo.restart_pc(5)
            self.activity.append("info", "O PC vai reiniciar em 5 segundos.")

    def open_log(self) -> None:
        target = self.last_log if self.last_log and os.path.exists(self.last_log) else str(log_dir())
        try:
            os.startfile(target)  # type: ignore[attr-defined]
        except OSError:
            QDesktopServices.openUrl(QUrl.fromLocalFile(target))

    def closeEvent(self, e) -> None:
        if self.thread is not None and (self.busy or self._close_after):
            e.ignore()
            if self._close_after:
                return  # já combinado: fecha sozinho quando a tarefa atual terminar

            def stop_and_close() -> None:
                self._close_after = True
                self.stop_run()

            Overlay(self, Icon.WARN, "Ainda trabalhando",
                    "Fechar agora pode deixar uma mudança pela metade. Posso parar depois da tarefa atual e "
                    "fechar sozinho.",
                    [("Continuar", "ghost", None), ("Parar e fechar", "primary", stop_and_close)])
            return
        super().closeEvent(e)
