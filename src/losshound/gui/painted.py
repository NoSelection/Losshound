"""Custom-painted widgets and primitives for the HUD theme.

Everything in this module is a ``QWidget`` (or mixin) that paints itself via
``paintEvent`` because the look it produces — dotted bitmap textures, soft
spotlights, sparklines, blinking dots, animated halos — is outside what
QSS can express.
"""
from __future__ import annotations

import math
import time
from collections import deque
from typing import Deque, Iterable, Optional

from PySide6.QtCore import (
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    Signal,
    QTimer,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QSizePolicy,
    QStylePainter,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from losshound.gui.palette import (
    chrome_font,
    dotted_texture,
    flowing_dot_field,
    halo_pixmap,
    label_font,
    mono_font,
    qc,
)


# ---------------------------------------------------------------------------
# TexturedSurface — paints the continuous dotted field beneath all panels.
# ---------------------------------------------------------------------------


class TexturedSurface(QWidget):
    """An animated, interactive QWidget that paints a dynamic halftone Quantum Atom backdrop.

    Used as the dashboard content background so dots run unbroken across
    panel boundaries. Responsive to mouse movement and moves at a smooth 30 FPS.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setAutoFillBackground(False)
        self.setMouseTracking(True)

        self._start_time = time.time()
        self._mouse_x = 0
        self._mouse_y = 0
        self._mouse_target_x = 0
        self._mouse_target_y = 0
        self._mouse_hover = False

        # 30 FPS update timer
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self.update_animation)
        self._timer.start()

    def update_animation(self) -> None:
        # Resolve cursor position relative to this widget, ignoring child intercepts
        local_pos = self.mapFromGlobal(QCursor.pos())
        w = self.width()
        h = self.height()
        
        if self.rect().contains(local_pos):
            self._mouse_hover = True
            self._mouse_x = local_pos.x()
            self._mouse_y = local_pos.y()
        else:
            self._mouse_hover = False

        # Soft mouse interpolation
        if self._mouse_hover:
            self._mouse_target_x += (self._mouse_x - self._mouse_target_x) * 0.15
            self._mouse_target_y += (self._mouse_y - self._mouse_target_y) * 0.15
        else:
            # Gentle floating idle movement
            t = (time.time() - self._start_time) * 0.8
            self._mouse_target_x = w / 2.0 + math.cos(t * 0.8) * (w / 3.0)
            self._mouse_target_y = h / 2.0 + math.sin(t * 0.5) * (h / 4.0)

        self.update()

    def paintEvent(self, event):  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect()
        painter.fillRect(rect, qc("bg_window"))

        w = rect.width()
        h = rect.height()
        if w < 10 or h < 10:
            return

        max_dim = max(w, h)
        centerX = w / 2.0
        centerY = h / 2.0
        t_val = (time.time() - self._start_time) * 0.8

        # Halftone grid parameters
        cell = 9
        dot_size = 2.4

        try:
            import numpy as np
            # Vectorized coordinate computation for maximum performance
            xs = np.arange(cell / 2.0, w, cell)
            ys = np.arange(cell / 2.0, h, cell)
            X, Y = np.meshgrid(xs, ys)

            DX = X - centerX
            DY = Y - centerY
            D = np.sqrt(DX*DX + DY*DY)

            # Central nucleus glow
            nucleus_radius = max_dim * 0.08
            N_GLOW = np.exp(-D / nucleus_radius) * 0.95

            # Orbital loops (3 distinct angled ellipses)
            ORBIT_PROXIMITY = np.zeros_like(D)
            ELECTRON_PROXIMITY = np.zeros_like(D)

            majorAxis = max_dim * 0.28
            minorAxis = max_dim * 0.095

            orbits = [
                {"angle": math.pi / 6.0, "speedMult": 1.2, "index": 0},
                {"angle": -math.pi / 6.0, "speedMult": 0.95, "index": 1},
                {"angle": math.pi / 2.0, "speedMult": 1.5, "index": 2}
            ]

            for orbit in orbits:
                cosA = math.cos(orbit["angle"])
                sinA = math.sin(orbit["angle"])

                RX = DX * cosA + DY * sinA
                RY = -DX * sinA + DY * cosA

                radialFactor = np.sqrt((RX/majorAxis)**2 + (RY/minorAxis)**2)
                proximity = np.exp(-((radialFactor - 1.0)**2) / (0.12 + math.sin(t_val + orbit["index"]) * 0.04))

                # Electron trace
                orbitTime = t_val * orbit["speedMult"]
                eX = math.cos(orbitTime) * majorAxis
                eY = math.sin(orbitTime) * minorAxis

                electronPx = eX * cosA - eY * sinA + centerX
                electronPy = eX * sinA + eY * cosA + centerY

                EDx = X - electronPx
                EDy = Y - electronPy
                distToElectron = np.sqrt(EDx*EDx + EDy*EDy)
                electronHalo = np.exp(-distToElectron / (max_dim * 0.075)) * 0.7

                ORBIT_PROXIMITY += proximity * 0.15
                ELECTRON_PROXIMITY += electronHalo

            # Mouse gravity trail
            mDx = X - self._mouse_target_x
            mDy = Y - self._mouse_target_y
            distToMouse = np.sqrt(mDx*mDx + mDy*mDy)
            mouseGlow = np.exp(-distToMouse / (max_dim * 0.18)) * 0.28

            # Calculate individual contributions to guide colors
            blue_weight = N_GLOW * 1.1 + ORBIT_PROXIMITY
            green_weight = ELECTRON_PROXIMITY
            mouse_weight = mouseGlow

            STRENGTH = blue_weight + green_weight + mouse_weight
            STRENGTH = (STRENGTH - 0.5) * 1.35 + 0.5 * 1.1
            INTENSITY = np.clip(STRENGTH, 0.0, 1.0)

            # Flatten coordinates and weights for iteration
            flat_x = X.ravel()
            flat_y = Y.ravel()
            flat_intensity = INTENSITY.ravel()
            flat_blue = blue_weight.ravel()
            flat_green = green_weight.ravel()
            flat_mouse = mouse_weight.ravel()

            for idx in range(len(flat_x)):
                intensity = flat_intensity[idx]
                px = flat_x[idx]
                py = flat_y[idx]

                if intensity <= 0.005:
                    # Render standard base dot pattern
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor(228, 234, 244, 12))
                    painter.drawRect(QRectF(px - 0.5, py - 0.5, 1.0, 1.0))
                else:
                    # Clean monochrome black & white halftone style (white dots with varying alpha)
                    alpha = int(18 + 225 * intensity)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor(255, 255, 255, alpha))

                    radius = max(1.0, intensity * dot_size)
                    painter.drawEllipse(QPointF(px, py), radius, radius)

        except Exception:
            # Safe non-numpy fallback with a larger cell size to protect framerate
            fallback_cell = 14
            for px in range(int(fallback_cell / 2), w, fallback_cell):
                for py in range(int(fallback_cell / 2), h, fallback_cell):
                    dx = px - centerX
                    dy = py - centerY
                    d = math.sqrt(dx*dx + dy*dy)

                    nucleus_radius = max_dim * 0.08
                    nGlow = math.exp(-d / nucleus_radius) * 0.95 if d > 0 else 0.95

                    rx = dx
                    ry = dy
                    radialFactor = math.sqrt((rx / (max_dim * 0.28))**2 + (ry / (max_dim * 0.095))**2)
                    proximity = math.exp(-((radialFactor - 1.0)**2) / 0.12)

                    mDx = px - self._mouse_target_x
                    mDy = py - self._mouse_target_y
                    distToMouse = math.sqrt(mDx*mDx + mDy*mDy)
                    mouseGlow = math.exp(-distToMouse / (max_dim * 0.18)) * 0.28

                    strength = nGlow * 1.1 + proximity * 0.15 * 0.58 + mouseGlow
                    strength = (strength - 0.5) * 1.35 + 0.5 * 1.1
                    intensity = max(0.0, min(1.0, strength))

                    if intensity <= 0.01:
                        painter.setPen(Qt.PenStyle.NoPen)
                        painter.setBrush(QColor(228, 234, 244, 12))
                        painter.drawRect(QRectF(px - 0.5, py - 0.5, 1.0, 1.0))
                    else:
                        alpha = int(18 + 225 * intensity)
                        painter.setPen(Qt.PenStyle.NoPen)
                        painter.setBrush(QColor(255, 255, 255, alpha))
                        radius = max(1.0, intensity * 2.4)
                        painter.drawEllipse(QPointF(px, py), radius, radius)

        # Draw scanning lines and vignette overlay on top
        scanline = QPen(QColor(255, 255, 255, 4))
        scanline.setWidth(1)
        scanline.setCosmetic(True)
        painter.setPen(scanline)
        for y in range(0, h, 6):
            painter.drawLine(0, y, w, y)

        gradient = QLinearGradient(0, 0, 0, h)
        gradient.setColorAt(0.0, QColor(0, 0, 0, 0))
        gradient.setColorAt(0.72, QColor(0, 0, 0, 12))
        gradient.setColorAt(1.0, QColor(0, 0, 0, 76))
        painter.fillRect(rect, QBrush(gradient))


# ---------------------------------------------------------------------------
# BracketedPanel — every dashboard panel sits inside one of these.
# ---------------------------------------------------------------------------


class BracketedPanel(QWidget):
    """A 1px-bordered panel filled with the HUD dotted texture.

    Optionally renders a small uppercase title strip at the top-left and a
    radial spotlight that mimics the bleed-through visible in the reference.
    """

    def __init__(
        self,
        title: Optional[str] = None,
        spotlight: bool = True,
        title_color_token: str = "info",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._title = title.upper() if title else None
        self._spotlight = spotlight
        self._title_color = qc(title_color_token)

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setAutoFillBackground(False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        # Reserve space for the title strip + border breathing room.
        top_margin = 32 if self._title else 14
        layout.setContentsMargins(14, top_margin, 14, 12)
        layout.setSpacing(8)

    def set_title(self, title: str) -> None:
        self._title = title.upper()
        margins = self.layout().contentsMargins()
        self.layout().setContentsMargins(
            margins.left(), 32, margins.right(), margins.bottom()
        )
        self.update()

    def paintEvent(self, event):  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        rect = self.rect()

        # Transparent background — the dashboard paints the continuous
        # texture beneath us. We only contribute a light 1px divider and
        # an uppercase title strip.

        painter.fillRect(rect.adjusted(1, 1, -1, -1), QColor(0, 0, 0, 66))

        # Title strip
        if self._title:
            painter.setPen(self._title_color)
            font = label_font()
            font.setPointSize(9)
            painter.setFont(font)
            metrics = QFontMetrics(font)
            text_rect = QRect(14, 8, rect.width() - 28, metrics.height() + 4)
            painter.drawText(
                text_rect,
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                self._title,
            )

        # Light 1px border so panels read as discrete cells against the
        # unified textured field.
        pen = QPen(qc("border"))
        pen.setWidth(1)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect.adjusted(0, 0, -1, -1))


# ---------------------------------------------------------------------------
# Sparkline
# ---------------------------------------------------------------------------


class Sparkline(QWidget):
    """A compact inline live chart of the last N numeric samples."""

    def __init__(
        self,
        capacity: int = 40,
        height: int = 18,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._values: Deque[float] = deque(maxlen=capacity)
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def push(self, value: Optional[float]) -> None:
        if value is None:
            return
        self._values.append(float(value))
        self.update()

    def clear(self) -> None:
        self._values.clear()
        self.update()

    def set_history(self, values: Iterable[float]) -> None:
        self._values.clear()
        for v in values:
            if v is None:
                continue
            self._values.append(float(v))
        self.update()

    def paintEvent(self, event):  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect()
        if len(self._values) < 2:
            return

        lo = min(self._values)
        hi = max(self._values)
        if hi - lo < 1e-6:
            hi = lo + 1.0
        n = len(self._values)

        w = rect.width()
        h = rect.height()
        padding = 2
        usable_h = h - padding * 2

        points = []
        for i, v in enumerate(self._values):
            x = (i / (n - 1)) * (w - 1)
            y = padding + (1.0 - (v - lo) / (hi - lo)) * usable_h
            points.append(QPointF(x, y))

        # Fill under the curve with a faint mint gradient.
        path = QPainterPath()
        path.moveTo(points[0].x(), h)
        for p in points:
            path.lineTo(p)
        path.lineTo(points[-1].x(), h)
        path.closeSubpath()

        gradient = QLinearGradient(0, 0, 0, h)
        gradient.setColorAt(0.0, QColor(95, 214, 160, 70))
        gradient.setColorAt(1.0, QColor(95, 214, 160, 0))
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(path)

        # Stroke
        pen = QPen(qc("mint"))
        pen.setWidth(1)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(1, len(points)):
            painter.drawLine(points[i - 1], points[i])

        # Trailing dot at the latest sample.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(qc("mint"))
        last = points[-1]
        painter.drawEllipse(last, 2.0, 2.0)


# ---------------------------------------------------------------------------
# LiveDot — soft blinking presence indicator.
# ---------------------------------------------------------------------------


class LiveDot(QWidget):
    """A 7px circle that breathes softly via an opacity animation."""

    def __init__(
        self,
        color_token: str = "mint",
        size: int = 8,
        period_ms: int = 1400,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._color = qc(color_token)
        self._size = size
        self.setFixedSize(size + 2, size + 2)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(1.0)
        self.setGraphicsEffect(self._effect)

        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setStartValue(1.0)
        self._anim.setKeyValueAt(0.5, 0.35)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(period_ms)
        self._anim.setLoopCount(-1)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._anim.start()

    def set_color(self, token: str) -> None:
        self._color = qc(token)
        self.update()

    def stop(self) -> None:
        self._anim.stop()
        self._effect.setOpacity(0.4)

    def paintEvent(self, event):  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)

        # Faint outer glow
        glow = QColor(self._color)
        glow.setAlpha(70)
        painter.setBrush(glow)
        painter.drawEllipse(self.rect())

        # Solid core
        painter.setBrush(self._color)
        d = self._size
        margin = (self.width() - d) // 2
        painter.drawEllipse(margin, margin, d, d)


# ---------------------------------------------------------------------------
# AlertGlyph — small shape painted before a feed row.
# ---------------------------------------------------------------------------


class AlertGlyph(QWidget):
    """Coloured dot/triangle/cross prefix for AlertsFeed rows."""

    KINDS = ("info", "warn", "error")

    def __init__(self, kind: str = "info", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._kind = kind if kind in self.KINDS else "info"
        self.setFixedSize(14, 14)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def set_kind(self, kind: str) -> None:
        if kind in self.KINDS and kind != self._kind:
            self._kind = kind
            self.update()

    def paintEvent(self, event):  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)

        rect = QRectF(2, 2, 10, 10)
        if self._kind == "info":
            painter.setBrush(qc("mint"))
            painter.drawEllipse(rect)
        elif self._kind == "warn":
            painter.setBrush(qc("warn"))
            triangle = QPolygonF(
                [
                    QPointF(rect.center().x(), rect.top()),
                    QPointF(rect.right(), rect.bottom()),
                    QPointF(rect.left(), rect.bottom()),
                ]
            )
            painter.drawPolygon(triangle)
        else:
            painter.setBrush(qc("error"))
            painter.drawEllipse(rect)
            painter.setPen(QPen(QColor("#0a0d11"), 2))
            painter.drawLine(
                rect.left() + 2.5,
                rect.center().y(),
                rect.right() - 2.5,
                rect.center().y(),
            )


# ---------------------------------------------------------------------------
# LosshoundTabBar — flat tabs with mint underline.
# ---------------------------------------------------------------------------


class LosshoundTabBar(QTabBar):
    """A custom QTabBar with vertical dividers and a mint selection underline."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setDrawBase(False)
        self.setExpanding(True)
        self.setUsesScrollButtons(False)
        self.setFont(mono_font(10))

    def tabSizeHint(self, index: int) -> QSize:  # type: ignore[override]
        size = super().tabSizeHint(index)
        size.setHeight(38)
        size.setWidth(max(size.width() + 28, 122))
        return size

    def paintEvent(self, event):  # type: ignore[override]
        painter = QStylePainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        painter.fillRect(self.rect(), qc("bg_window"))

        font = mono_font(10, QFont.Weight.Medium)
        font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 106)
        font.setCapitalization(QFont.Capitalization.AllUppercase)
        painter.setFont(font)

        cell_pen = QPen(qc("border"))
        cell_pen.setWidth(1)
        cell_pen.setCosmetic(True)
        active_pen = QPen(qc("info"))
        active_pen.setWidth(2)
        active_pen.setCosmetic(True)

        for i in range(self.count()):
            r = self.tabRect(i)
            selected = i == self.currentIndex()
            painter.setPen(cell_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(r.adjusted(0, 0, -1, -1))

            color = qc("text_primary") if selected else qc("text_secondary")
            painter.setPen(color)
            painter.drawText(r, int(Qt.AlignmentFlag.AlignCenter), self.tabText(i))

            if selected:
                painter.setPen(active_pen)
                painter.drawLine(r.left() + 1, r.bottom() - 2, r.right() - 1, r.bottom() - 2)

        pen = QPen(qc("border"))
        pen.setWidth(1)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)


# ---------------------------------------------------------------------------
# HeaderHalo — dynamic animated halftone Quantum Atom backdrop for header.
# ---------------------------------------------------------------------------


class HeaderHalo(QWidget):
    """An animated, interactive QWidget that paints a dynamic halftone Quantum Atom backdrop for the header.

    Responsive to mouse movement and moves at a smooth 30 FPS.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._start_time = time.time()
        self._mouse_x = 0
        self._mouse_y = 0
        self._mouse_target_x = 0
        self._mouse_target_y = 0
        self._mouse_hover = False

        # 30 FPS update timer
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self.update_animation)
        self._timer.start()

    def update_animation(self) -> None:
        # Resolve cursor position relative to this widget
        local_pos = self.mapFromGlobal(QCursor.pos())
        w = self.width()
        h = self.height()

        if self.rect().contains(local_pos):
            self._mouse_hover = True
            self._mouse_x = local_pos.x()
            self._mouse_y = local_pos.y()
        else:
            self._mouse_hover = False

        # Soft mouse interpolation
        if self._mouse_hover:
            self._mouse_target_x += (self._mouse_x - self._mouse_target_x) * 0.15
            self._mouse_target_y += (self._mouse_y - self._mouse_target_y) * 0.15
        else:
            # Floating idle movement in the header
            t = (time.time() - self._start_time) * 0.8
            self._mouse_target_x = w / 2.0 + math.cos(t * 0.8) * (w / 3.0)
            self._mouse_target_y = h / 2.0 + math.sin(t * 0.5) * (h / 4.0)

        self.update()

    def paintEvent(self, event):  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect()

        w = rect.width()
        h = rect.height()
        if w < 10 or h < 10:
            return

        centerX = w / 2.0
        centerY = h / 2.0
        t_val = (time.time() - self._start_time) * 0.8

        # Halftone grid parameters for header
        cell = 7
        dot_size = 2.0

        try:
            import numpy as np
            xs = np.arange(cell / 2.0, w, cell)
            ys = np.arange(cell / 2.0, h, cell)
            X, Y = np.meshgrid(xs, ys)

            DX = X - centerX
            DY = Y - centerY
            D = np.sqrt(DX*DX + DY*DY)

            # Central nucleus glow (scaled to header height)
            nucleus_radius = h * 0.25
            N_GLOW = np.exp(-D / nucleus_radius) * 0.95

            # Orbital loops (scaled to header height)
            ORBIT_PROXIMITY = np.zeros_like(D)
            ELECTRON_PROXIMITY = np.zeros_like(D)

            majorAxis = w * 0.32
            minorAxis = h * 0.45

            orbits = [
                {"angle": math.pi / 12.0, "speedMult": 1.2, "index": 0},
                {"angle": -math.pi / 12.0, "speedMult": 0.95, "index": 1},
                {"angle": math.pi / 2.0, "speedMult": 1.5, "index": 2}
            ]

            for orbit in orbits:
                cosA = math.cos(orbit["angle"])
                sinA = math.sin(orbit["angle"])

                RX = DX * cosA + DY * sinA
                RY = -DX * sinA + DY * cosA

                radialFactor = np.sqrt((RX/majorAxis)**2 + (RY/minorAxis)**2)
                proximity = np.exp(-((radialFactor - 1.0)**2) / (0.12 + math.sin(t_val + orbit["index"]) * 0.04))

                # Electron trace
                orbitTime = t_val * orbit["speedMult"]
                eX = math.cos(orbitTime) * majorAxis
                eY = math.sin(orbitTime) * minorAxis

                electronPx = eX * cosA - eY * sinA + centerX
                electronPy = eX * sinA + eY * cosA + centerY

                EDx = X - electronPx
                EDy = Y - electronPy
                distToElectron = np.sqrt(EDx*EDx + EDy*EDy)
                electronHalo = np.exp(-distToElectron / (h * 0.5)) * 0.7

                ORBIT_PROXIMITY += proximity * 0.15
                ELECTRON_PROXIMITY += electronHalo

            # Mouse gravity trail
            mDx = X - self._mouse_target_x
            mDy = Y - self._mouse_target_y
            distToMouse = np.sqrt(mDx*mDx + mDy*mDy)
            mouseGlow = np.exp(-distToMouse / (h * 0.8)) * 0.28

            STRENGTH = N_GLOW * 1.1 + ORBIT_PROXIMITY + ELECTRON_PROXIMITY + mouseGlow
            STRENGTH = (STRENGTH - 0.5) * 1.35 + 0.5 * 1.1
            INTENSITY = np.clip(STRENGTH, 0.0, 1.0)

            flat_x = X.ravel()
            flat_y = Y.ravel()
            flat_intensity = INTENSITY.ravel()

            for idx in range(len(flat_x)):
                intensity = flat_intensity[idx]
                px = flat_x[idx]
                py = flat_y[idx]

                if intensity <= 0.005:
                    # Draw a very faint background dot grid
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor(228, 234, 244, 10))
                    painter.drawRect(QRectF(px - 0.5, py - 0.5, 1.0, 1.0))
                else:
                    alpha = int(18 + 225 * intensity)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor(255, 255, 255, alpha))

                    radius = max(1.0, intensity * dot_size)
                    painter.drawEllipse(QPointF(px, py), radius, radius)

        except Exception:
            # Fallback pure Python drawing for header
            fallback_cell = 10
            for px in range(int(fallback_cell / 2), w, fallback_cell):
                for py in range(int(fallback_cell / 2), h, fallback_cell):
                    dx = px - centerX
                    dy = py - centerY
                    d = math.sqrt(dx*dx + dy*dy)

                    nucleus_radius = h * 0.25
                    nGlow = math.exp(-d / nucleus_radius) * 0.95 if d > 0 else 0.95

                    rx = dx
                    ry = dy
                    radialFactor = math.sqrt((rx / (w * 0.32))**2 + (ry / (h * 0.45))**2)
                    proximity = math.exp(-((radialFactor - 1.0)**2) / 0.12)

                    mDx = px - self._mouse_target_x
                    mDy = py - self._mouse_target_y
                    distToMouse = math.sqrt(mDx*mDx + mDy*mDy)
                    mouseGlow = math.exp(-distToMouse / (h * 0.8)) * 0.28

                    strength = nGlow * 1.1 + proximity * 0.15 * 0.58 + mouseGlow
                    strength = (strength - 0.5) * 1.35 + 0.5 * 1.1
                    intensity = max(0.0, min(1.0, strength))

                    if intensity <= 0.01:
                        painter.setPen(Qt.PenStyle.NoPen)
                        painter.setBrush(QColor(228, 234, 244, 10))
                        painter.drawRect(QRectF(px - 0.5, py - 0.5, 1.0, 1.0))
                    else:
                        alpha = int(18 + 225 * intensity)
                        painter.setPen(Qt.PenStyle.NoPen)
                        painter.setBrush(QColor(255, 255, 255, alpha))
                        radius = max(1.0, intensity * 2.0)
                        painter.drawEllipse(QPointF(px, py), radius, radius)



