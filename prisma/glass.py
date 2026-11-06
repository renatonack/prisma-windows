"""Primitivas visuais "liquid glass" em preto e branco.

O fundo da janela é uma cena monocromática (luzes, fitas líquidas e bolhas).
Cada painel de vidro desenha por baixo uma cópia desfocada e levemente ampliada
desse fundo (efeito de refração), mais tinta branca, brilho e borda iluminada.
"""
from __future__ import annotations

import random

from PySide6.QtCore import (QEasingCurve, QPoint, QPointF, QRectF, QSize, Qt, QVariantAnimation, Signal)
from PySide6.QtGui import (QBrush, QColor, QFont, QFontDatabase, QFontMetricsF, QIcon, QImage, QLinearGradient,
                           QPainter, QPainterPath, QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import (QAbstractButton, QGraphicsBlurEffect, QGraphicsPixmapItem, QGraphicsScene,
                               QSizePolicy, QWidget)

AA = QPainter.RenderHint.Antialiasing
SMOOTH = QPainter.RenderHint.SmoothPixmapTransform


def W(a: float) -> QColor:
    return QColor(255, 255, 255, max(0, min(255, int(a))))


def K(a: float) -> QColor:
    return QColor(0, 0, 0, max(0, min(255, int(a))))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def mix(c1: QColor, c2: QColor, t: float) -> QColor:
    return QColor(int(lerp(c1.red(), c2.red(), t)), int(lerp(c1.green(), c2.green(), t)),
                  int(lerp(c1.blue(), c2.blue(), t)), int(lerp(c1.alpha(), c2.alpha(), t)))


# ---------------------------------------------------------------------------
# Fontes e ícones
# ---------------------------------------------------------------------------
class Fonts:
    text = "Segoe UI"
    display = "Segoe UI"
    icons = "Segoe MDL2 Assets"
    mono = "Consolas"

    @classmethod
    def init(cls) -> None:
        fams = set(QFontDatabase.families())

        def pick(*names: str) -> str:
            for n in names:
                if n in fams:
                    return n
            return names[-1]

        cls.text = pick("Segoe UI Variable Text", "Segoe UI Variable", "Segoe UI")
        cls.display = pick("Segoe UI Variable Display", "Segoe UI Variable", "Segoe UI")
        cls.icons = pick("Segoe Fluent Icons", "Segoe MDL2 Assets")
        cls.mono = pick("Cascadia Mono", "Consolas")


def font(px: float, weight: QFont.Weight = QFont.Weight.Normal, family: str | None = None,
         spacing: float | None = None) -> QFont:
    f = QFont(family or Fonts.text)
    f.setPixelSize(int(px))
    f.setWeight(weight)
    if spacing is not None:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return f


class Icon:
    HOME = ""
    SHIELD = ""
    BOLT = ""
    DELETE = ""
    DOWNLOAD = ""
    PLAY = ""
    VIDEO = ""
    CHECK = ""
    WARN = ""
    ERROR = ""
    INFO = ""
    CLOSE = ""
    MIN = ""
    MAX = ""
    RESTORE = ""
    UP = ""
    DOWN = ""
    STOP = ""
    FOLDER = ""
    POWER = ""
    SPARKLE = ""
    CPU = ""
    LIST = ""
    DEVICES = ""


# ---------------------------------------------------------------------------
# Cena de fundo
# ---------------------------------------------------------------------------
def _orb(p: QPainter, cx: float, cy: float, r: float, alpha: float) -> None:
    g = QRadialGradient(QPointF(cx, cy), r)
    g.setColorAt(0.0, W(alpha))
    g.setColorAt(0.35, W(alpha * 0.45))
    g.setColorAt(0.7, W(alpha * 0.12))
    g.setColorAt(1.0, W(0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawEllipse(QPointF(cx, cy), r, r)


def _ribbon(p: QPainter, pts, w: float, h: float, width: float, alpha: float) -> None:
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = pts
    path = QPainterPath(QPointF(x0 * w, y0 * h))
    path.cubicTo(QPointF(x1 * w, y1 * h), QPointF(x2 * w, y2 * h), QPointF(x3 * w, y3 * h))
    p.setBrush(Qt.BrushStyle.NoBrush)
    for frac, a in ((1.0, alpha * 0.35), (0.62, alpha * 0.6), (0.34, alpha), (0.12, alpha * 1.8), (0.03, alpha * 4.5)):
        pen = QPen(W(a), max(1.0, width * frac))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawPath(path)
    # sombra fina embaixo para dar volume de "tubo líquido"
    p.save()
    p.translate(0, width * 0.42)
    pen = QPen(K(70), max(1.0, width * 0.18))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawPath(path)
    p.restore()


def _bubble(p: QPainter, cx: float, cy: float, r: float) -> None:
    c = QPointF(cx, cy)
    body = QRadialGradient(QPointF(cx - r * 0.3, cy - r * 0.35), r * 1.35)
    body.setColorAt(0.0, W(40))
    body.setColorAt(0.45, W(8))
    body.setColorAt(0.82, W(4))
    body.setColorAt(1.0, W(46))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(body)
    p.drawEllipse(c, r, r)
    rim = QLinearGradient(cx - r, cy - r, cx + r, cy + r)
    rim.setColorAt(0.0, W(190))
    rim.setColorAt(0.45, W(18))
    rim.setColorAt(1.0, W(110))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QBrush(rim), max(1.0, r * 0.022)))
    p.drawEllipse(c, r, r)
    hl = QRadialGradient(QPointF(cx - r * 0.42, cy - r * 0.5), r * 0.36)
    hl.setColorAt(0.0, W(170))
    hl.setColorAt(1.0, W(0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(hl)
    p.drawEllipse(QPointF(cx - r * 0.42, cy - r * 0.5), r * 0.36, r * 0.22)


def paint_scene(p: QPainter, x: float, y: float, w: float, h: float) -> None:
    p.save()
    p.translate(x, y)
    p.setRenderHint(AA)
    base = QLinearGradient(0, 0, w, h)
    base.setColorAt(0.0, QColor(22, 22, 24))
    base.setColorAt(0.5, QColor(8, 8, 9))
    base.setColorAt(1.0, QColor(3, 3, 4))
    p.fillRect(QRectF(0, 0, w, h), base)
    big = max(w, h)
    _orb(p, w * 0.06, h * 0.0, big * 0.62, 70)
    _orb(p, w * 1.02, h * 1.04, big * 0.52, 46)
    _orb(p, w * 0.66, h * 0.16, big * 0.22, 30)
    _ribbon(p, [(-0.08, 0.80), (0.28, 0.48), (0.50, 1.10), (1.08, 0.58)], w, h, big * 0.11, 22)
    _ribbon(p, [(-0.06, 0.26), (0.36, 0.02), (0.62, 0.52), (1.08, 0.10)], w, h, big * 0.07, 18)
    _bubble(p, w * 0.88, h * 0.30, big * 0.12)
    _bubble(p, w * 0.30, h * 0.90, big * 0.075)
    _bubble(p, w * 0.58, h * 0.64, big * 0.04)
    p.restore()


_NOISE: QImage | None = None


def noise_tile() -> QImage:
    global _NOISE
    if _NOISE is None:
        size = 128
        rnd = random.Random(11)
        img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        for _ in range(size * size // 3):
            p.setPen(W(9) if rnd.random() > 0.5 else K(14))
            p.drawPoint(rnd.randrange(size), rnd.randrange(size))
        p.end()
        _NOISE = img
    return _NOISE


def blur_image(img: QImage, radius: float) -> QImage:
    scene = QGraphicsScene()
    item = QGraphicsPixmapItem(QPixmap.fromImage(img))
    eff = QGraphicsBlurEffect()
    eff.setBlurRadius(radius)
    eff.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
    item.setGraphicsEffect(eff)
    scene.addItem(item)
    out = QImage(img.size(), QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    rect = QRectF(0, 0, img.width(), img.height())
    scene.render(p, rect, rect)
    p.end()
    return out


class Backdrop:
    """Fundo nítido + versão desfocada, no tamanho da janela inteira (em pixels físicos)."""

    def __init__(self) -> None:
        self.sharp: QImage | None = None
        self.blurred: QImage | None = None
        self.dpr = 1.0
        self._key = None

    def ensure(self, w: int, h: int, dpr: float, inner: QRectF) -> bool:
        key = (w, h, round(dpr, 3), inner.x(), inner.y(), inner.width(), inner.height())
        if key == self._key:
            return False
        self._key = key
        self.dpr = dpr
        pw, ph = max(1, round(w * dpr)), max(1, round(h * dpr))

        sharp = QImage(pw, ph, QImage.Format.Format_ARGB32_Premultiplied)
        sharp.fill(Qt.GlobalColor.transparent)
        p = QPainter(sharp)
        p.scale(dpr, dpr)
        paint_scene(p, inner.x(), inner.y(), inner.width(), inner.height())
        p.fillRect(inner, QBrush(noise_tile()))
        p.end()
        sharp.setDevicePixelRatio(dpr)
        self.sharp = sharp

        scale = 0.5
        margin = 48
        sw, sh = max(1, int(w * scale)), max(1, int(h * scale))
        src = QImage(sw + 2 * margin, sh + 2 * margin, QImage.Format.Format_ARGB32_Premultiplied)
        src.fill(QColor(8, 8, 9))
        p = QPainter(src)
        p.translate(margin, margin)
        p.scale(scale, scale)
        paint_scene(p, inner.x(), inner.y(), inner.width(), inner.height())
        p.end()
        small = blur_image(src, 26).copy(margin, margin, sw, sh)
        blurred = small.scaled(pw, ph, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        blurred.setDevicePixelRatio(dpr)
        self.blurred = blurred
        return True


def window_backdrop(widget: QWidget) -> Backdrop | None:
    return getattr(widget.window(), "backdrop", None)


def paint_glass(p: QPainter, widget: QWidget, rect: QRectF, radius: float, *, tint: float = 12,
                sample: bool = True, rim: float = 1.0, sheen: bool = True, lens: float = 0.04,
                sharp: bool = False) -> None:
    """Desenha um pedaço de vidro líquido em `rect` (coordenadas do widget)."""
    p.setRenderHint(AA)
    p.setRenderHint(SMOOTH)
    r = rect.adjusted(0.5, 0.5, -0.5, -0.5)
    path = QPainterPath()
    path.addRoundedRect(r, radius, radius)
    bd = window_backdrop(widget)
    p.save()
    p.setClipPath(path)
    if sample and bd is not None and bd.blurred is not None:
        img = bd.sharp if sharp else bd.blurred
        off = widget.mapTo(widget.window(), QPoint(0, 0))
        d = bd.dpr
        sx, sy = (off.x() + rect.x()) * d, (off.y() + rect.y()) * d
        sw, sh = rect.width() * d, rect.height() * d
        src = QRectF(sx + sw * lens / 2, sy + sh * lens / 2, sw * (1 - lens), sh * (1 - lens))
        p.drawImage(rect, img, src)
    if tint:
        p.fillPath(path, W(tint))
    if sheen:
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0.0, W(30))
        g.setColorAt(min(0.45, 22 / max(1.0, r.height())), W(10))
        g.setColorAt(0.55, W(0))
        g.setColorAt(1.0, W(7))
        p.fillPath(path, g)
    p.restore()
    if rim > 0:
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0.0, W(165 * rim))
        g.setColorAt(0.3, W(40 * rim))
        g.setColorAt(0.7, W(16 * rim))
        g.setColorAt(1.0, W(85 * rim))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QBrush(g), 1.0))
        p.drawPath(path)
        inner = QPainterPath()
        ir = max(0.0, radius - 1)
        inner.addRoundedRect(r.adjusted(1, 1, -1, -1), ir, ir)
        g2 = QLinearGradient(r.topLeft(), r.bottomLeft())
        g2.setColorAt(0.0, W(44 * rim))
        g2.setColorAt(0.2, W(0))
        g2.setColorAt(0.85, W(0))
        g2.setColorAt(1.0, W(16 * rim))
        p.setPen(QPen(QBrush(g2), 1.0))
        p.drawPath(inner)


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------
class GlassPanel(QWidget):
    def __init__(self, parent: QWidget | None = None, radius: float = 20, tint: float = 12,
                 sample: bool = True, rim: float = 1.0, sheen: bool = True):
        super().__init__(parent)
        self.radius, self.tint, self.sample, self.rim, self.sheen = radius, tint, sample, rim, sheen

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        paint_glass(p, self, QRectF(self.rect()), self.radius, tint=self.tint, sample=self.sample,
                    rim=self.rim, sheen=self.sheen)
        self.paint_extra(p)

    def paint_extra(self, p: QPainter) -> None:
        pass


class _Hover:
    """Mixin com animação de hover 0..1."""

    def _init_hover(self, duration: int = 160) -> None:
        self._h = 0.0
        self._hanim = QVariantAnimation(self)
        self._hanim.setDuration(duration)
        self._hanim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hanim.valueChanged.connect(self._set_h)

    def _set_h(self, v) -> None:
        self._h = float(v)
        self.update()

    def _hover_to(self, target: float) -> None:
        self._hanim.stop()
        self._hanim.setStartValue(self._h)
        self._hanim.setEndValue(target)
        self._hanim.start()

    def enterEvent(self, e) -> None:
        self._hover_to(1.0)
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:
        self._hover_to(0.0)
        super().leaveEvent(e)


class Toggle(_Hover, QAbstractButton):
    """Interruptor preto e branco com bolinha animada."""

    def __init__(self, parent: QWidget | None = None, checked: bool = False):
        super().__init__(parent)
        self._init_hover()
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(46, 26)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self._t = 1.0 if checked else 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self._anim.valueChanged.connect(self._set_t)
        self.toggled.connect(self._animate)

    def _set_t(self, v) -> None:
        self._t = float(v)
        self.update()

    def _animate(self, on: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._t)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def set_quiet(self, on: bool) -> None:
        """Muda o estado sem emitir sinal (usado ao sincronizar seleção)."""
        if on == self.isChecked():
            return
        self.blockSignals(True)
        self.setChecked(on)
        self.blockSignals(False)
        self._animate(on)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(AA)
        if not self.isEnabled():
            p.setOpacity(0.4)
        t = max(0.0, min(1.0, self._t))
        tt = max(-0.15, min(1.15, self._t))
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        rad = r.height() / 2
        track = QPainterPath()
        track.addRoundedRect(r, rad, rad)
        p.fillPath(track, mix(W(18 + 10 * self._h), W(236 + 14 * self._h), t))
        if t > 0.01:
            g = QLinearGradient(r.topLeft(), r.bottomLeft())
            g.setColorAt(0, W(255 * t))
            g.setColorAt(1, QColor(200, 200, 204, int(255 * t)))
            p.fillPath(track, g)
        rim = QLinearGradient(r.topLeft(), r.bottomRight())
        rim.setColorAt(0, W(lerp(120, 255, t)))
        rim.setColorAt(1, W(lerp(40, 160, t)))
        p.setPen(QPen(QBrush(rim), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(track)
        d = r.height() - 6
        x = r.left() + 3 + (r.width() - 6 - d) * tt
        knob = QRectF(x, r.top() + 3, d, d)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(K(70 * (1 - t) + 30))
        p.drawEllipse(knob.translated(0, 1.2))
        p.setBrush(mix(QColor(236, 236, 238), QColor(12, 12, 13), t))
        p.drawEllipse(knob)
        hl = QRadialGradient(knob.center() + QPointF(-d * 0.18, -d * 0.22), d * 0.5)
        hl.setColorAt(0, W(lerp(255, 90, t)))
        hl.setColorAt(1, W(0))
        p.setBrush(hl)
        p.drawEllipse(knob)


class GlassButton(_Hover, QAbstractButton):
    """Botão em pílula. Variantes: primary (branco sólido), glass, ghost."""

    def __init__(self, text: str = "", icon: str = "", variant: str = "glass",
                 parent: QWidget | None = None, height: int = 40, px: int = 14):
        super().__init__(parent)
        self._init_hover()
        self._icon = icon
        self.variant = variant
        self._height = height
        self._px = px
        self.setText(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._pressed = 0.0

    def set_icon_glyph(self, glyph: str) -> None:
        self._icon = glyph
        self.updateGeometry()
        self.update()

    def _font(self) -> QFont:
        return font(self._px, QFont.Weight.DemiBold if self.variant == "primary" else QFont.Weight.Medium)

    def sizeHint(self) -> QSize:
        fm = QFontMetricsF(self._font())
        w = fm.horizontalAdvance(self.text()) if self.text() else 0
        pad = self._height * 0.55
        if self._icon:
            w += self._px + 2 + (8 if self.text() else 0)
        if not self.text():
            return QSize(self._height, self._height)
        return QSize(int(w + pad * 2), self._height)

    def setText(self, text: str) -> None:
        super().setText(text)
        self.updateGeometry()

    def mousePressEvent(self, e) -> None:
        self._pressed = 1.0
        self.update()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        self._pressed = 0.0
        self.update()
        super().mouseReleaseEvent(e)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(AA)
        h = self._h if self.isEnabled() else 0.0
        if not self.isEnabled():
            p.setOpacity(0.38)
        if self._pressed:
            c = QRectF(self.rect()).center()
            p.translate(c)
            p.scale(0.97, 0.97)
            p.translate(-c)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        rad = r.height() / 2
        if self.variant == "primary":
            path = QPainterPath()
            path.addRoundedRect(r, rad, rad)
            g = QLinearGradient(r.topLeft(), r.bottomLeft())
            g.setColorAt(0, W(255))
            g.setColorAt(1, mix(QColor(214, 214, 218), QColor(236, 236, 240), h))
            p.fillPath(path, g)
            gl = QLinearGradient(r.topLeft(), QPointF(r.left(), r.center().y()))
            gl.setColorAt(0, W(255))
            gl.setColorAt(1, W(0))
            p.fillPath(path, gl)
            p.setPen(QPen(W(255), 1))
            p.drawPath(path)
            fg = QColor(8, 8, 9)
        elif self.variant == "glass":
            paint_glass(p, self, r, rad, tint=16 + 18 * h, rim=0.9 + 0.3 * h, lens=0.0)
            fg = W(235 + 20 * h)
        else:  # ghost
            if h > 0.01:
                path = QPainterPath()
                path.addRoundedRect(r, rad, rad)
                p.fillPath(path, W(16 * h))
            fg = W(175 + 80 * h)
        self._paint_label(p, r, fg)

    def _paint_label(self, p: QPainter, r: QRectF, fg: QColor) -> None:
        f = self._font()
        fm = QFontMetricsF(f)
        tw = fm.horizontalAdvance(self.text()) if self.text() else 0.0
        iw = (self._px + 2) if self._icon else 0.0
        gap = 8.0 if (self._icon and self.text()) else 0.0
        x = r.center().x() - (tw + iw + gap) / 2
        p.setPen(fg)
        if self._icon:
            p.setFont(font(self._px + 1, family=Fonts.icons))
            p.drawText(QRectF(x, r.top(), iw, r.height()), Qt.AlignmentFlag.AlignCenter, self._icon)
        if self.text():
            p.setFont(f)
            p.drawText(QRectF(x + iw + gap, r.top(), tw + 2, r.height()),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text())


class IconButton(GlassButton):
    def __init__(self, glyph: str, parent: QWidget | None = None, size: int = 32, variant: str = "ghost",
                 danger: bool = False):
        super().__init__("", glyph, variant, parent, height=size, px=11)
        self.setFixedSize(size, size)
        self.danger = danger

    def paintEvent(self, e) -> None:
        if not self.danger:
            return super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(AA)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(r, r.height() / 2, r.height() / 2)
        p.fillPath(path, W(235 * self._h))
        self._paint_label(p, r, mix(W(200), QColor(0, 0, 0), self._h))


class Chip(QWidget):
    """Etiqueta pequena (ex.: VÍDEO, JÁ INSTALADO)."""

    def __init__(self, text: str, solid: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self._text = text.upper()
        self.solid = solid
        self._f = font(9.5, QFont.Weight.Bold, spacing=0.9)
        fm = QFontMetricsF(self._f)
        self.setFixedSize(int(fm.horizontalAdvance(self._text) + 18), 20)

    def set_text(self, text: str) -> None:
        self._text = text.upper()
        fm = QFontMetricsF(self._f)
        self.setFixedSize(int(fm.horizontalAdvance(self._text) + 18), 20)
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(AA)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, r.height() / 2, r.height() / 2)
        if self.solid:
            p.fillPath(path, W(232))
            p.setPen(QColor(10, 10, 10))
        else:
            p.fillPath(path, W(14))
            p.setPen(QPen(W(80), 1))
            p.drawPath(path)
            p.setPen(W(215))
        p.setFont(self._f)
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, self._text)


class GlyphLabel(QWidget):
    """Um ícone do Segoe Fluent Icons desenhado num tamanho fixo."""

    def __init__(self, glyph: str, px: int = 16, alpha: float = 220, parent: QWidget | None = None):
        super().__init__(parent)
        self.glyph, self.px, self.alpha = glyph, px, alpha
        self.setFixedSize(px + 6, px + 6)

    def set_glyph(self, glyph: str, alpha: float | None = None) -> None:
        self.glyph = glyph
        if alpha is not None:
            self.alpha = alpha
        self.update()

    def paintEvent(self, _e) -> None:
        if not self.glyph:
            return
        p = QPainter(self)
        p.setRenderHint(AA)
        p.setPen(W(self.alpha))
        p.setFont(font(self.px, family=Fonts.icons))
        p.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignCenter, self.glyph)


class ProgressLine(QWidget):
    """Barra de progresso fina, com brilho correndo enquanto trabalha."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(6)
        self._value = 0.0
        self._shown = 0.0
        self._phase = 0.0
        self.busy = False
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(420)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._set_shown)
        self._shine = QVariantAnimation(self)
        self._shine.setStartValue(0.0)
        self._shine.setEndValue(1.0)
        self._shine.setDuration(1600)
        self._shine.setLoopCount(-1)
        self._shine.valueChanged.connect(self._set_phase)

    def _set_shown(self, v) -> None:
        self._shown = float(v)
        self.update()

    def _set_phase(self, v) -> None:
        self._phase = float(v)
        self.update()

    def set_value(self, v: float) -> None:
        self._value = max(0.0, min(1.0, v))
        self._anim.stop()
        self._anim.setStartValue(self._shown)
        self._anim.setEndValue(self._value)
        self._anim.start()

    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        if busy:
            self._shine.start()
        else:
            self._shine.stop()
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(AA)
        r = QRectF(self.rect()).adjusted(0, 1, 0, -1)
        rad = r.height() / 2
        track = QPainterPath()
        track.addRoundedRect(r, rad, rad)
        p.fillPath(track, W(20))
        if self._shown > 0.001:
            fr = QRectF(r.left(), r.top(), max(r.height(), r.width() * self._shown), r.height())
            fill = QPainterPath()
            fill.addRoundedRect(fr, rad, rad)
            p.fillPath(fill, W(235))
            if self.busy:
                cx = fr.left() + fr.width() * self._phase
                g = QLinearGradient(cx - 60, 0, cx + 60, 0)
                g.setColorAt(0, QColor(140, 140, 145, 0))
                g.setColorAt(0.5, QColor(120, 120, 126, 200))
                g.setColorAt(1, QColor(140, 140, 145, 0))
                p.save()
                p.setClipPath(fill)
                p.fillRect(fr, g)
                p.restore()


class PrismLogo(QWidget):
    """Logo: um prisma de vidro com um raio de luz (monocromático)."""

    def __init__(self, size: int = 30, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(size, size)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        draw_prism(p, QRectF(self.rect()))


def draw_prism(p: QPainter, r: QRectF) -> None:
    p.setRenderHint(AA)
    s = min(r.width(), r.height())
    ox, oy = r.center().x() - s / 2, r.center().y() - s / 2
    # raio de luz entrando
    p.setPen(QPen(W(150), max(1.0, s * 0.045), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(QPointF(ox + s * 0.0, oy + s * 0.62), QPointF(ox + s * 0.36, oy + s * 0.52))
    tri = QPainterPath()
    tri.moveTo(ox + s * 0.5, oy + s * 0.1)
    tri.lineTo(ox + s * 0.9, oy + s * 0.84)
    tri.lineTo(ox + s * 0.1, oy + s * 0.84)
    tri.closeSubpath()
    g = QLinearGradient(QPointF(ox, oy), QPointF(ox + s, oy + s))
    g.setColorAt(0, W(240))
    g.setColorAt(0.55, W(70))
    g.setColorAt(1, W(150))
    p.fillPath(tri, g)
    p.setPen(QPen(W(255), max(1.0, s * 0.035)))
    p.drawPath(tri)
    # feixe saindo (tons de cinza no lugar do arco-íris)
    for i, a in enumerate((230, 170, 110)):
        p.setPen(QPen(W(a), max(1.0, s * 0.04), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        y = oy + s * (0.40 + i * 0.075)
        p.drawLine(QPointF(ox + s * 0.66, oy + s * 0.48), QPointF(ox + s * 1.0, y))


def make_app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(AA)
        r = QRectF(0, 0, size, size)
        path = QPainterPath()
        path.addRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), size * 0.24, size * 0.24)
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, QColor(46, 46, 50))
        g.setColorAt(1, QColor(6, 6, 7))
        p.fillPath(path, g)
        p.setPen(QPen(W(90), 1))
        p.drawPath(path)
        draw_prism(p, r.adjusted(size * 0.16, size * 0.16, -size * 0.16, -size * 0.12))
        p.end()
        icon.addPixmap(pm)
    return icon


class LiquidLens(QWidget):
    """Gota de vidro decorativa que amplia o fundo nítido atrás dela."""

    def __init__(self, parent: QWidget | None = None, size: int = 200):
        super().__init__(parent)
        self.setFixedSize(size, size)

    def paintEvent(self, _e) -> None:
        # estática de propósito: animação contínua forçaria a janela inteira a redesenhar o tempo todo
        p = QPainter(self)
        p.setRenderHint(AA)
        p.setRenderHint(SMOOTH)
        s = self.width()
        r = QRectF(s * 0.08, s * 0.08, s * 0.84, s * 0.84)
        path = QPainterPath()
        path.addEllipse(r)
        # sombra
        p.setPen(Qt.PenStyle.NoPen)
        sh = QRadialGradient(r.center() + QPointF(0, s * 0.05), s * 0.47)
        sh.setColorAt(0.75, K(90))
        sh.setColorAt(1.0, K(0))
        p.setBrush(sh)
        p.drawEllipse(r.center() + QPointF(0, s * 0.05), s * 0.47, s * 0.47)
        bd = window_backdrop(self)
        p.save()
        p.setClipPath(path)
        if bd is not None and bd.sharp is not None:
            off = self.mapTo(self.window(), QPoint(0, 0))
            d = bd.dpr
            mag = 0.62  # amplia ~1.6x
            cx, cy = (off.x() + r.center().x()) * d, (off.y() + r.center().y()) * d
            sw, sh_ = r.width() * d * mag, r.height() * d * mag
            p.drawImage(r, bd.sharp, QRectF(cx - sw / 2, cy - sh_ / 2, sw, sh_))
        body = QRadialGradient(r.center() + QPointF(-s * 0.12, -s * 0.16), s * 0.55)
        body.setColorAt(0.0, W(40))
        body.setColorAt(0.55, W(6))
        body.setColorAt(0.86, W(10))
        body.setColorAt(1.0, W(70))
        p.fillPath(path, body)
        # brilho de baixo (cáustica)
        ca = QRadialGradient(QPointF(r.center().x() + s * 0.08, r.bottom() - s * 0.1), s * 0.3)
        ca.setColorAt(0, W(80))
        ca.setColorAt(1, W(0))
        p.fillPath(path, ca)
        p.restore()
        rim = QLinearGradient(r.topLeft(), r.bottomRight())
        rim.setColorAt(0.0, W(240))
        rim.setColorAt(0.4, W(40))
        rim.setColorAt(0.75, W(30))
        rim.setColorAt(1.0, W(170))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QBrush(rim), 1.6))
        p.drawPath(path)
        # reflexo especular
        hl = QPainterPath()
        hr = QRectF(r.left() + r.width() * 0.16, r.top() + r.height() * 0.08, r.width() * 0.42, r.height() * 0.22)
        hl.addEllipse(hr)
        g = QLinearGradient(hr.topLeft(), hr.bottomLeft())
        g.setColorAt(0, W(200))
        g.setColorAt(1, W(0))
        p.fillPath(hl, g)
        p.setPen(QPen(W(150), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(r.adjusted(s * 0.05, s * 0.05, -s * 0.05, -s * 0.05), 118 * 16, 34 * 16)
