import ctypes
import sys
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPalette, QRadialGradient
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QWidget


THEMES = {
    "ocean_dark": {
        "name": "Ocean Glass",
        "is_dark": True,
        "bg_start": "#07111F",
        "bg_mid": "#0D1E36",
        "bg_end": "#0A1728",
        "orb_1": "rgba(16, 185, 129, 70)",
        "orb_2": "rgba(56, 189, 248, 65)",
        "orb_3": "rgba(139, 92, 246, 50)",
        "glass_bg": "rgba(255, 255, 255, 0.075)",
        "glass_bg_strong": "rgba(16, 28, 48, 0.72)",
        "glass_bg_hover": "rgba(255, 255, 255, 0.12)",
        "glass_border": "rgba(255, 255, 255, 0.17)",
        "glass_border_strong": "rgba(255, 255, 255, 0.28)",
        "input_bg": "rgba(8, 17, 32, 0.58)",
        "input_bg_focus": "rgba(12, 25, 46, 0.80)",
        "text_primary": "#F1F5F9",
        "text_secondary": "#94A3B8",
        "text_muted": "#64748B",
        "accent": "#10B981",
        "accent_hover": "#34D399",
        "accent_pressed": "#059669",
        "accent_soft": "rgba(16, 185, 129, 0.20)",
        "secondary_accent": "#38BDF8",
        "secondary_soft": "rgba(56, 189, 248, 0.18)",
        "danger": "#FB7185",
        "danger_soft": "rgba(251, 113, 133, 0.18)",
        "warning": "#FBBF24",
        "warning_soft": "rgba(251, 191, 36, 0.18)",
        "table_alt": "rgba(255, 255, 255, 0.03)",
        "table_header": "rgba(255, 255, 255, 0.08)",
        "selection_bg": "rgba(16, 185, 129, 0.28)",
        "shadow_color": QColor(0, 0, 0, 115),
    },
    "crystal_light": {
        "name": "Crystal Frost",
        "is_dark": False,
        "bg_start": "#E6F2F8",
        "bg_mid": "#EEF6FB",
        "bg_end": "#E2EFF4",
        "orb_1": "rgba(16, 185, 129, 55)",
        "orb_2": "rgba(14, 165, 233, 55)",
        "orb_3": "rgba(99, 102, 241, 40)",
        "glass_bg": "rgba(255, 255, 255, 0.62)",
        "glass_bg_strong": "rgba(255, 255, 255, 0.80)",
        "glass_bg_hover": "rgba(255, 255, 255, 0.85)",
        "glass_border": "rgba(255, 255, 255, 0.88)",
        "glass_border_strong": "rgba(15, 23, 42, 0.15)",
        "input_bg": "rgba(255, 255, 255, 0.78)",
        "input_bg_focus": "rgba(255, 255, 255, 0.96)",
        "text_primary": "#0F172A",
        "text_secondary": "#475569",
        "text_muted": "#64748B",
        "accent": "#059669",
        "accent_hover": "#10B981",
        "accent_pressed": "#047857",
        "accent_soft": "rgba(5, 150, 105, 0.14)",
        "secondary_accent": "#0284C7",
        "secondary_soft": "rgba(2, 132, 199, 0.14)",
        "danger": "#E11D48",
        "danger_soft": "rgba(225, 29, 72, 0.12)",
        "warning": "#D97706",
        "warning_soft": "rgba(217, 119, 6, 0.14)",
        "table_alt": "rgba(15, 23, 42, 0.025)",
        "table_header": "rgba(255, 255, 255, 0.72)",
        "selection_bg": "rgba(5, 150, 105, 0.18)",
        "shadow_color": QColor(15, 23, 42, 32),
    },
}


def apply_windows_titlebar_theme(widget, dark: bool):
    """Best-effort Windows 10/11 DWM titlebar dark-mode & rounded-corner hint."""
    if sys.platform != "win32":
        return
    try:
        hwnd = int(widget.winId())
        dwmapi = ctypes.windll.dwmapi
        use_dark = ctypes.c_int(1 if dark else 0)
        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20 (Win11 / Win10 2004+)
        dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(use_dark), ctypes.sizeof(use_dark))
        # DWMWA_WINDOW_CORNER_PREFERENCE = 33 (DWMWCP_ROUND = 2)
        corner_pref = ctypes.c_int(2)
        dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corner_pref), ctypes.sizeof(corner_pref))
    except Exception:
        pass


class GlassCanvas(QWidget):
    """Root atmospheric gradient canvas with ambient glowing orbs behind glass cards."""

    def __init__(self, theme_key="ocean_dark", parent=None):
        super().__init__(parent)
        self.theme_key = theme_key

    def set_theme(self, theme_key: str):
        self.theme_key = theme_key
        self.update()

    def paintEvent(self, event):
        t = THEMES[self.theme_key]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        grad = QLinearGradient(0, 0, rect.width(), rect.height())
        grad.setColorAt(0.0, QColor(t["bg_start"]))
        grad.setColorAt(0.55, QColor(t["bg_mid"]))
        grad.setColorAt(1.0, QColor(t["bg_end"]))
        painter.fillRect(rect, grad)

        # Soft ambient glassmorphism color orbs
        orbs = [
            (rect.width() * 0.14, rect.height() * 0.18, max(rect.width(), rect.height()) * 0.42, (16, 185, 129, 68 if t["is_dark"] else 48)),
            (rect.width() * 0.86, rect.height() * 0.22, max(rect.width(), rect.height()) * 0.40, (56, 189, 248, 60 if t["is_dark"] else 45)),
            (rect.width() * 0.55, rect.height() * 0.88, max(rect.width(), rect.height()) * 0.45, (139, 92, 246, 48 if t["is_dark"] else 32)),
        ]
        for cx, cy, radius, rgba in orbs:
            radial = QRadialGradient(cx, cy, radius)
            radial.setColorAt(0.0, QColor(*rgba))
            radial.setColorAt(0.6, QColor(rgba[0], rgba[1], rgba[2], int(rgba[3] * 0.3)))
            radial.setColorAt(1.0, QColor(rgba[0], rgba[1], rgba[2], 0))
            painter.setBrush(radial)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))


class GlassCard(QFrame):
    """Frosted-glass container card with soft elevation shadow and specular sheen."""

    def __init__(self, parent=None, strong=False, radius=16, shadow=True):
        super().__init__(parent)
        self.setObjectName("GlassCardStrong" if strong else "GlassCard")
        self._radius = radius
        self._is_dark = True
        self.setProperty("glassRadius", radius)
        if shadow:
            effect = QGraphicsDropShadowEffect(self)
            effect.setBlurRadius(28)
            effect.setOffset(0, 8)
            effect.setColor(QColor(0, 0, 0, 85))
            self.setGraphicsEffect(effect)
            self._shadow = effect
        else:
            self._shadow = None

    def update_shadow(self, theme_key: str):
        self._is_dark = THEMES[theme_key]["is_dark"]
        if self._shadow is not None:
            self._shadow.setColor(THEMES[theme_key]["shadow_color"])
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        sheen = QLinearGradient(0, 0, 0, min(140.0, r.height()))
        top_alpha = 26 if self._is_dark else 110
        sheen.setColorAt(0.0, QColor(255, 255, 255, top_alpha))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(sheen)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(r, self._radius, self._radius)
        painter.end()


def build_stylesheet(theme_key: str) -> str:
    t = THEMES[theme_key]
    popup_bg = "#111E33" if t["is_dark"] else "#FFFFFF"
    popup_border = "rgba(255, 255, 255, 0.22)" if t["is_dark"] else "rgba(15, 23, 42, 0.14)"
    scroll_handle = "rgba(255, 255, 255, 0.22)" if t["is_dark"] else "rgba(15, 23, 42, 0.20)"
    scroll_hover = "rgba(255, 255, 255, 0.38)" if t["is_dark"] else "rgba(15, 23, 42, 0.35)"

    return f"""
    QWidget {{
        font-family: "Segoe UI Variable", "Segoe UI", "Inter", sans-serif;
        font-size: 13px;
        color: {t["text_primary"]};
    }}

    QMainWindow {{
        background: transparent;
    }}

    QFrame#GlassCard {{
        background-color: {t["glass_bg"]};
        border: 1px solid {t["glass_border"]};
        border-radius: 16px;
    }}

    QFrame#GlassCardStrong {{
        background-color: {t["glass_bg_strong"]};
        border: 1px solid {t["glass_border_strong"]};
        border-radius: 18px;
    }}

    QFrame#TopGlassBar {{
        background-color: {t["glass_bg_strong"]};
        border: 1px solid {t["glass_border"]};
        border-radius: 16px;
    }}

    QFrame#SubGlassPanel {{
        background-color: {t["input_bg"]};
        border: 1px solid {t["glass_border"]};
        border-radius: 12px;
    }}

    QLabel {{
        background: transparent;
        color: {t["text_primary"]};
    }}

    QLabel#SectionTitle {{
        font-size: 15px;
        font-weight: 700;
        color: {t["text_primary"]};
        letter-spacing: 0.2px;
    }}

    QLabel#SectionSubtitle {{
        font-size: 12px;
        color: {t["text_secondary"]};
    }}

    QLabel#FieldLabel {{
        font-size: 12px;
        font-weight: 600;
        color: {t["text_secondary"]};
    }}

    QLabel#BrandTitle {{
        font-size: 17px;
        font-weight: 700;
        color: {t["text_primary"]};
    }}

    QLabel#BrandSub {{
        font-size: 11px;
        color: {t["text_secondary"]};
    }}

    QLabel#BadgePill {{
        background-color: {t["accent_soft"]};
        color: {t["accent_hover"] if t["is_dark"] else t["accent"]};
        border: 1px solid {t["accent"]};
        border-radius: 10px;
        padding: 3px 10px;
        font-size: 11px;
        font-weight: 700;
    }}

    QLabel#InfoPill {{
        background-color: {t["secondary_soft"]};
        color: {t["secondary_accent"]};
        border: 1px solid {t["secondary_accent"]};
        border-radius: 10px;
        padding: 3px 10px;
        font-size: 11px;
        font-weight: 700;
    }}

    /* Inputs */
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit, QPlainTextEdit {{
        background-color: {t["input_bg"]};
        border: 1px solid {t["glass_border"]};
        border-radius: 10px;
        padding: 7px 10px;
        color: {t["text_primary"]};
        selection-background-color: {t["accent"]};
        selection-color: #FFFFFF;
        min-height: 20px;
    }}

    QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QDateEdit:hover, QTimeEdit:hover {{
        border: 1px solid {t["glass_border_strong"]};
        background-color: {t["input_bg_focus"]};
    }}

    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus, QTimeEdit:focus {{
        border: 1.5px solid {t["accent"]};
        background-color: {t["input_bg_focus"]};
    }}

    QComboBox::drop-down, QDateEdit::drop-down {{
        border: none;
        width: 24px;
    }}

    QComboBox QAbstractItemView {{
        background-color: {popup_bg};
        border: 1px solid {popup_border};
        border-radius: 10px;
        padding: 4px;
        color: {t["text_primary"]};
        selection-background-color: {t["selection_bg"]};
        selection-color: {t["text_primary"]};
        outline: 0;
    }}

    QSpinBox::up-button, QDoubleSpinBox::up-button, QTimeEdit::up-button,
    QSpinBox::down-button, QDoubleSpinBox::down-button, QTimeEdit::down-button {{
        background: transparent;
        border: none;
        width: 18px;
    }}

    /* Buttons */
    QPushButton {{
        background-color: {t["glass_bg"]};
        border: 1px solid {t["glass_border"]};
        border-radius: 10px;
        padding: 8px 15px;
        font-weight: 600;
        color: {t["text_primary"]};
    }}

    QPushButton:hover {{
        background-color: {t["glass_bg_hover"]};
        border: 1px solid {t["glass_border_strong"]};
    }}

    QPushButton:pressed {{
        background-color: {t["selection_bg"]};
    }}

    QPushButton:disabled {{
        background-color: {t["table_alt"]};
        border: 1px solid {t["glass_border"]};
        color: {t["text_muted"]};
    }}

    QPushButton#PrimaryBtn {{
        background-color: {t["accent"]};
        border: 1px solid {t["accent_hover"]};
        color: #FFFFFF;
        font-weight: 700;
        padding: 10px 18px;
    }}

    QPushButton#PrimaryBtn:hover {{
        background-color: {t["accent_hover"]};
    }}

    QPushButton#PrimaryBtn:pressed {{
        background-color: {t["accent_pressed"]};
    }}

    QPushButton#SecondaryAccentBtn {{
        background-color: {t["secondary_soft"]};
        border: 1px solid {t["secondary_accent"]};
        color: {t["text_primary"]};
        font-weight: 700;
    }}

    QPushButton#SecondaryAccentBtn:hover {{
        background-color: {t["secondary_accent"]};
        color: #FFFFFF;
    }}

    QPushButton#DangerBtn {{
        background-color: {t["danger_soft"]};
        border: 1px solid {t["danger"]};
        color: {t["danger"]};
        font-weight: 600;
    }}

    QPushButton#DangerBtn:hover {{
        background-color: {t["danger"]};
        color: #FFFFFF;
    }}

    QPushButton#GhostBtn {{
        background-color: transparent;
        border: 1px solid transparent;
        border-radius: 10px;
        padding: 6px 12px;
        color: {t["text_secondary"]};
    }}

    QPushButton#GhostBtn:hover {{
        background-color: {t["glass_bg_hover"]};
        color: {t["text_primary"]};
        border: 1px solid {t["glass_border"]};
    }}

    QPushButton#NavPill {{
        background-color: transparent;
        border: 1px solid transparent;
        border-radius: 11px;
        padding: 8px 16px;
        font-weight: 600;
        color: {t["text_secondary"]};
    }}

    QPushButton#NavPill:hover {{
        background-color: {t["glass_bg"]};
        color: {t["text_primary"]};
    }}

    QPushButton#NavPill:checked {{
        background-color: {t["accent_soft"]};
        border: 1px solid {t["accent"]};
        color: {t["text_primary"]};
    }}

    QPushButton#SegmentedBtn {{
        background-color: {t["input_bg"]};
        border: 1px solid {t["glass_border"]};
        border-radius: 9px;
        padding: 6px 12px;
        font-weight: 600;
        color: {t["text_secondary"]};
    }}

    QPushButton#SegmentedBtn:hover {{
        background-color: {t["glass_bg_hover"]};
        color: {t["text_primary"]};
    }}

    QPushButton#SegmentedBtn:checked {{
        background-color: {t["accent"]};
        border: 1px solid {t["accent_hover"]};
        color: #FFFFFF;
    }}

    /* Tables */
    QTableWidget {{
        background-color: {t["input_bg"]};
        alternate-background-color: {t["table_alt"]};
        border: 1px solid {t["glass_border"]};
        border-radius: 12px;
        gridline-color: {t["glass_border"]};
        selection-background-color: {t["selection_bg"]};
        selection-color: {t["text_primary"]};
        outline: 0;
    }}

    QTableWidget::item {{
        padding: 6px 10px;
        border: none;
    }}

    QHeaderView::section {{
        background-color: {t["table_header"]};
        color: {t["text_secondary"]};
        font-weight: 700;
        font-size: 12px;
        padding: 8px 10px;
        border: none;
        border-bottom: 1px solid {t["glass_border"]};
    }}

    /* ScrollArea & ScrollBars */
    QScrollArea {{
        background: transparent;
        border: none;
    }}

    QScrollArea > QWidget > QWidget {{
        background: transparent;
    }}

    QScrollBar:vertical {{
        background: transparent;
        width: 8px;
        margin: 4px 0 4px 0;
    }}

    QScrollBar::handle:vertical {{
        background: {scroll_handle};
        border-radius: 4px;
        min-height: 28px;
    }}

    QScrollBar::handle:vertical:hover {{
        background: {scroll_hover};
    }}

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: transparent;
        height: 0px;
    }}

    QScrollBar:horizontal {{
        background: transparent;
        height: 8px;
        margin: 0 4px 0 4px;
    }}

    QScrollBar::handle:horizontal {{
        background: {scroll_handle};
        border-radius: 4px;
        min-width: 28px;
    }}

    QScrollBar::handle:horizontal:hover {{
        background: {scroll_hover};
    }}

    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: transparent;
        width: 0px;
    }}

    /* Slider */
    QSlider::groove:horizontal {{
        height: 6px;
        background: {t["input_bg"]};
        border-radius: 3px;
        border: 1px solid {t["glass_border"]};
    }}

    QSlider::handle:horizontal {{
        background: {t["accent"]};
        border: 2px solid #FFFFFF;
        width: 16px;
        height: 16px;
        margin: -6px 0;
        border-radius: 9px;
    }}

    /* CheckBox */
    QCheckBox {{
        spacing: 8px;
        color: {t["text_primary"]};
    }}

    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border-radius: 6px;
        border: 1px solid {t["glass_border_strong"]};
        background-color: {t["input_bg"]};
    }}

    QCheckBox::indicator:checked {{
        background-color: {t["accent"]};
        border: 1px solid {t["accent_hover"]};
    }}

    /* Dialogs & Calendar */
    QDialog, QMessageBox {{
        background-color: {popup_bg};
        color: {t["text_primary"]};
    }}

    QCalendarWidget QWidget {{
        background-color: {popup_bg};
        color: {t["text_primary"]};
    }}

    QToolTip {{
        background-color: {popup_bg};
        color: {t["text_primary"]};
        border: 1px solid {popup_border};
        border-radius: 8px;
        padding: 6px 10px;
    }}
    """


def build_palette(theme_key: str) -> QPalette:
    """Build a matching Qt QPalette so Fusion native icons/arrows match the theme."""
    t = THEMES[theme_key]
    pal = QPalette()
    bg = QColor(t["bg_mid"])
    base = QColor("#0B1629" if t["is_dark"] else "#FFFFFF")
    text = QColor(t["text_primary"])
    muted = QColor(t["text_muted"])
    accent = QColor(t["accent"])

    pal.setColor(QPalette.ColorRole.Window, bg)
    pal.setColor(QPalette.ColorRole.WindowText, text)
    pal.setColor(QPalette.ColorRole.Base, base)
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#10203A" if t["is_dark"] else "#F1F5F9"))
    pal.setColor(QPalette.ColorRole.Text, text)
    pal.setColor(QPalette.ColorRole.Button, bg)
    pal.setColor(QPalette.ColorRole.ButtonText, text)
    pal.setColor(QPalette.ColorRole.Highlight, accent)
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, muted)
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, muted)
    return pal
