from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    QTime,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from styles import THEMES, apply_windows_titlebar_theme


class SegmentedControl(QWidget):
    """Mutually exclusive pill selector for short option lists."""

    currentChanged = Signal(str)

    def __init__(self, options: list[str], initial: str | None = None, parent=None):
        super().__init__(parent)
        self._options = options
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        for idx, opt in enumerate(options):
            btn = QPushButton(opt)
            btn.setObjectName("SegmentedBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._group.addButton(btn, idx)
            self._buttons[opt] = btn
            layout.addWidget(btn)
            btn.clicked.connect(lambda _checked, val=opt: self.currentChanged.emit(val))

        target = initial if initial in self._buttons else (options[0] if options else None)
        if target:
            self._buttons[target].setChecked(True)

    def current_value(self) -> str:
        for val, btn in self._buttons.items():
            if btn.isChecked():
                return val
        return self._options[0] if self._options else ""

    def set_value(self, value: str):
        if value in self._buttons:
            self._buttons[value].setChecked(True)


class KpiCard(QFrame):
    """Compact glass metric tile."""

    def __init__(self, title: str, value: str = "0", accent_hex: str = "#10B981", parent=None):
        super().__init__(parent)
        self.setObjectName("GlassCard")
        self.setMinimumWidth(145)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)

        top = QHBoxLayout()
        dot = QFrame()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background-color: {accent_hex}; border-radius: 4px; border: none;")
        top.addWidget(dot)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("SectionSubtitle")
        top.addWidget(self.lbl_title)
        top.addStretch()
        layout.addLayout(top)

        self.lbl_value = QLabel(value)
        self.lbl_value.setStyleSheet("font-size: 21px; font-weight: 800;")
        layout.addWidget(self.lbl_value)

    def set_value(self, value):
        self.lbl_value.setText(str(value))


class ToastBanner(QFrame):
    """Floating glass toast notification with smooth fade-in/fade-out."""

    closed = Signal(object)

    COLORS = {
        "success": ("#10B981", "rgba(16, 185, 129, 0.22)"),
        "info": ("#38BDF8", "rgba(56, 189, 248, 0.22)"),
        "warning": ("#FBBF24", "rgba(251, 191, 36, 0.22)"),
        "error": ("#FB7185", "rgba(251, 113, 133, 0.24)"),
    }

    def __init__(self, message: str, kind: str = "info", dark: bool = True, parent=None):
        super().__init__(parent)
        accent, tint = self.COLORS.get(kind, self.COLORS["info"])
        bg = "rgba(15, 23, 42, 0.90)" if dark else "rgba(255, 255, 255, 0.94)"
        fg = "#F8FAFC" if dark else "#0F172A"

        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: {bg};
                border: 1px solid {accent};
                border-left: 4px solid {accent};
                border-radius: 12px;
            }}
            QLabel {{
                background: transparent;
                color: {fg};
                font-weight: 600;
                font-size: 13px;
            }}
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)

        badge = QLabel("●")
        badge.setStyleSheet(f"color: {accent}; font-size: 13px;")
        layout.addWidget(badge)

        lbl = QLabel(message)
        lbl.setWordWrap(True)
        lbl.setMaximumWidth(340)
        layout.addWidget(lbl)

        self.adjustSize()

        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._anim = QPropertyAnimation(self._opacity, b"opacity", self)
        self._anim.setDuration(220)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()

        QTimer.singleShot(2800, self.dismiss)

    def dismiss(self):
        self._anim = QPropertyAnimation(self._opacity, b"opacity", self)
        self._anim.setDuration(240)
        self._anim.setStartValue(self._opacity.opacity())
        self._anim.setEndValue(0.0)
        self._anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._anim.finished.connect(self._finish)
        self._anim.start()

    def _finish(self):
        self.closed.emit(self)
        self.deleteLater()


class ToastManager:
    """Manages stacked bottom-right toast banners inside a parent window."""

    def __init__(self, parent_widget: QWidget):
        self.parent_widget = parent_widget
        self.toasts: list[ToastBanner] = []
        self.is_dark = True

    def show(self, message: str, kind: str = "info"):
        banner = ToastBanner(message, kind=kind, dark=self.is_dark, parent=self.parent_widget)
        banner.closed.connect(self._remove)
        self.toasts.append(banner)
        banner.show()
        self.reposition()

    def _remove(self, banner):
        if banner in self.toasts:
            self.toasts.remove(banner)
        self.reposition()

    def reposition(self):
        pw = self.parent_widget.width()
        ph = self.parent_widget.height()
        y_offset = ph - 24
        for banner in reversed(self.toasts):
            banner.adjustSize()
            bw = banner.width()
            bh = banner.height()
            y_offset -= bh
            banner.move(max(16, pw - bw - 24), max(16, y_offset))
            banner.raise_()
            y_offset -= 10


class BulkAddDialog(QDialog):
    """Interactive dialog for generating sequential drums quickly."""

    def __init__(self, start_sl: int, start_time: QTime, theme_key: str = "ocean_dark", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bulk Generate Drums")
        self.setModal(True)
        self.setMinimumWidth(400)

        t = THEMES[theme_key]
        apply_windows_titlebar_theme(self, t["is_dark"])
        self.setStyleSheet(
            f"""
            QDialog {{
                background-color: {t["bg_mid"]};
                color: {t["text_primary"]};
            }}
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        title = QLabel("⚡ Bulk Add Sequential Drums")
        title.setObjectName("SectionTitle")
        root.addWidget(title)

        sub = QLabel(
            "Clone the current drum's quality & temperature settings across multiple sequential drums."
        )
        sub.setObjectName("SectionSubtitle")
        sub.setWordWrap(True)
        root.addWidget(sub)

        grid = QGridLayout()
        grid.setSpacing(10)

        grid.addWidget(QLabel("Number of Drums:"), 0, 0)
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 200)
        self.count_spin.setValue(5)
        grid.addWidget(self.count_spin, 0, 1)

        grid.addWidget(QLabel("Starting Drum SL No:"), 1, 0)
        self.start_sl_spin = QSpinBox()
        self.start_sl_spin.setRange(1, 9999)
        self.start_sl_spin.setValue(start_sl)
        grid.addWidget(self.start_sl_spin, 1, 1)

        grid.addWidget(QLabel("Time Step (minutes):"), 2, 0)
        self.step_min_spin = QSpinBox()
        self.step_min_spin.setRange(0, 120)
        self.step_min_spin.setValue(5)
        grid.addWidget(self.step_min_spin, 2, 1)

        root.addLayout(grid)

        self.start_time = start_time
        self.preview_lbl = QLabel()
        self.preview_lbl.setObjectName("InfoPill")
        self.preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.preview_lbl)

        self.count_spin.valueChanged.connect(self._update_preview)
        self.start_sl_spin.valueChanged.connect(self._update_preview)
        self.step_min_spin.valueChanged.connect(self._update_preview)
        self._update_preview()

        btns = QHBoxLayout()
        btns.addStretch()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_cancel)

        btn_ok = QPushButton("Generate Drums")
        btn_ok.setObjectName("PrimaryBtn")
        btn_ok.clicked.connect(self.accept)
        btns.addWidget(btn_ok)
        root.addLayout(btns)

    def _update_preview(self):
        c = self.count_spin.value()
        s = self.start_sl_spin.value()
        e = s + c - 1
        step = self.step_min_spin.value()
        end_t = self.start_time.addSecs((c - 1) * step * 60).toString("HH:mm")
        self.preview_lbl.setText(
            f"Creates {c} drums: SL #{s} → #{e}  |  {self.start_time.toString('HH:mm')} → {end_t}"
        )

    def values(self):
        return (
            self.count_spin.value(),
            self.start_sl_spin.value(),
            self.step_min_spin.value(),
        )
