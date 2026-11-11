import io
import json
import qrcode
from PIL import Image
from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)
from styles import GlassCard


def build_qr_payload(record: dict) -> str:
    """Build the canonical JSON string encoded into each drum's QR code."""
    payload = {
        "batch": record.get("batch_no", ""),
        "item": record.get("item_name", ""),
        "drum": record.get("drum_sl_no", 1),
        "mfd": record.get("mfd", ""),
        "exp": record.get("exp", ""),
        "shift": record.get("shift_time", ""),
        "time": record.get("production_time", ""),
        "brix": record.get("brix", 0.0),
        "acidity": record.get("acidity", 0.0),
        "ph": record.get("ph_value", 0.0),
    }
    return json.dumps(payload, ensure_ascii=False)


def normalize_detail_record(detail) -> dict:
    """Accept either a dict record or the legacy 17-tuple from Database.get_batch_details."""
    if isinstance(detail, dict):
        return detail
    return {
        "batch_no": detail[0],
        "item_name": detail[1],
        "product_type": detail[2],
        "shift_code": detail[3],
        "detail_id": detail[4],
        "drum_sl_no": detail[5],
        "mfd": detail[6],
        "exp": detail[7],
        "shift_time": detail[8],
        "production_time": detail[9],
        "brix": detail[10],
        "acidity": detail[11],
        "ph_value": detail[12],
        "evaporation_temp": detail[13],
        "sterilization_temp": detail[14],
        "filling_temp": detail[15],
        "ascorbic_acid_ppm": detail[16],
    }


class QRCodeGenerator:
    """Generates sharp QR code images for on-screen preview and high-DPI printing."""

    @staticmethod
    def generate_qr_qimage(data: str, size: int = 300) -> QImage:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=2,
        )
        qr.add_data(data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        img = img.resize((size, size), Image.Resampling.NEAREST)

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        qimg = QImage()
        qimg.loadFromData(buffer.getvalue(), "PNG")
        return qimg

    @staticmethod
    def generate_qr_image(data: str, size: int = 200) -> QPixmap:
        return QPixmap.fromImage(QRCodeGenerator.generate_qr_qimage(data, size=size))


class LabelPainter:
    """Vector-style painter for crisp 3x2 inch industrial drum labels (logical 450x300)."""

    LOGICAL_W = 450.0
    LOGICAL_H = 300.0

    @classmethod
    def paint_label(
        cls,
        painter: QPainter,
        target_rect: QRectF,
        record: dict,
        draw_border: bool = True,
        qr_image: QImage | None = None,
    ):
        rec = normalize_detail_record(record)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)

        # Scale logical 450x300 coordinate space cleanly into target_rect
        painter.translate(target_rect.topLeft())
        sx = target_rect.width() / cls.LOGICAL_W
        sy = target_rect.height() / cls.LOGICAL_H
        painter.scale(sx, sy)

        # Crisp white label background
        card_rect = QRectF(0, 0, cls.LOGICAL_W, cls.LOGICAL_H)
        painter.setBrush(QColor("#FFFFFF"))
        if draw_border:
            painter.setPen(QPen(QColor("#1E293B"), 1.5))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(card_rect, 8, 8)

        # Top header band
        header_rect = QRectF(10, 10, cls.LOGICAL_W - 20, 36)
        painter.setBrush(QColor("#0F172A"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(header_rect, 6, 6)

        painter.setPen(QColor("#FFFFFF"))
        painter.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        painter.drawText(
            QRectF(20, 10, 290, 36),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            "PRAN AGRO LIMITED - BIP",
        )

        # Product type badge on header right
        ptype = str(rec.get("product_type") or "ASEPTIC")
        badge_color = QColor("#10B981") if ptype == "ASEPTIC" else QColor("#F59E0B")
        badge_rect = QRectF(cls.LOGICAL_W - 118, 16, 100, 24)
        painter.setBrush(badge_color)
        painter.drawRoundedRect(badge_rect, 5, 5)
        painter.setPen(QColor("#FFFFFF"))
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, ptype)

        # Left Info Grid
        x_label = 16
        x_val = 96
        y = 58
        row_h = 22

        rows = [
            ("Batch No", str(rec.get("batch_no") or "-")),
            ("Item", str(rec.get("item_name") or "-")),
            ("Drum SL", f"#{rec.get('drum_sl_no', '-')}"),
            ("MFD", str(rec.get("mfd") or "-")),
            ("EXP", str(rec.get("exp") or "-")),
            ("Shift / Time", f"{rec.get('shift_time') or '-'}  •  {rec.get('production_time') or '-'}"),
            ("Brix / pH", f"{rec.get('brix', '-')}°  |  pH {rec.get('ph_value', '-')}"),
            ("Acidity", f"{rec.get('acidity', '-')}%"),
        ]

        label_font = QFont("Segoe UI", 8.5, QFont.Weight.DemiBold)
        val_font = QFont("Segoe UI", 9.5, QFont.Weight.Bold)
        for idx, (k, v) in enumerate(rows):
            ry = y + idx * row_h
            if idx % 2 == 0:
                painter.setBrush(QColor("#F8FAFC"))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(QRectF(12, ry - 1, 250, row_h - 2), 4, 4)

            painter.setFont(label_font)
            painter.setPen(QColor("#64748B"))
            painter.drawText(
                QRectF(x_label, ry, 78, row_h),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                k,
            )
            painter.setFont(val_font)
            painter.setPen(QColor("#0F172A"))
            painter.drawText(
                QRectF(x_val, ry, 166, row_h),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                v,
            )

        # Right QR frame
        qr_box = QRectF(274, 58, 162, 162)
        painter.setBrush(QColor("#FFFFFF"))
        painter.setPen(QPen(QColor("#CBD5E1"), 1.2))
        painter.drawRoundedRect(qr_box, 8, 8)

        if qr_image is None:
            qr_data = rec.get("qr_data") or build_qr_payload(rec)
            qr_image = QRCodeGenerator.generate_qr_qimage(qr_data, size=320)

        qr_target = QRectF(282, 66, 146, 146)
        painter.drawImage(qr_target, qr_image)

        # Drum pill below QR
        drum_pill = QRectF(274, 226, 162, 26)
        painter.setBrush(QColor("#EFF6FF"))
        painter.setPen(QPen(QColor("#BFDBFE"), 1))
        painter.drawRoundedRect(drum_pill, 6, 6)
        painter.setPen(QColor("#1E3A8A"))
        painter.setFont(QFont("Segoe UI", 9.5, QFont.Weight.Bold))
        painter.drawText(
            drum_pill,
            Qt.AlignmentFlag.AlignCenter,
            f"DRUM SL #{rec.get('drum_sl_no', '-')}",
        )

        # Footer thermal/process line
        footer_rect = QRectF(12, 262, cls.LOGICAL_W - 24, 26)
        painter.setBrush(QColor("#F1F5F9"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(footer_rect, 5, 5)
        painter.setPen(QColor("#334155"))
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
        footer_text = (
            f"Evap: {rec.get('evaporation_temp', '-')}°C   •   "
            f"Steril: {rec.get('sterilization_temp', '-')}°C   •   "
            f"Fill: {rec.get('filling_temp', '-')}°C   •   "
            f"Ascorbic: {rec.get('ascorbic_acid_ppm', '-')} ppm"
        )
        painter.drawText(footer_rect, Qt.AlignmentFlag.AlignCenter, footer_text)

        painter.restore()

    @classmethod
    def render_to_qimage(cls, record: dict, dpi_scale: float = 2.0) -> QImage:
        """Render a label to an offscreen QImage (dpi_scale=2 -> 900x600 = 300 DPI for 3x2 in)."""
        w = int(cls.LOGICAL_W * dpi_scale)
        h = int(cls.LOGICAL_H * dpi_scale)
        image = QImage(w, h, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        cls.paint_label(painter, QRectF(0, 0, w, h), record, draw_border=True)
        painter.end()
        return image


class LabelCanvasWidget(QFrame):
    """Widget that paints the live vector QR label smoothly scaled to any zoom."""

    def __init__(self, record: dict | None = None, zoom: float = 1.0, parent=None):
        super().__init__(parent)
        self.record = record or {}
        self.zoom = zoom
        self._cached_qr_key = None
        self._cached_qr_img = None
        self._apply_size()
        self.setStyleSheet("background: transparent; border: none;")

    def set_record(self, record: dict):
        self.record = record
        self._cached_qr_key = None
        self.update()

    def set_zoom(self, zoom: float):
        self.zoom = max(0.5, min(1.8, zoom))
        self._apply_size()
        self.update()

    def _apply_size(self):
        self.setFixedSize(int(450 * self.zoom), int(300 * self.zoom))

    def paintEvent(self, event):
        if not self.record:
            return
        rec = normalize_detail_record(self.record)
        qr_data = rec.get("qr_data") or build_qr_payload(rec)
        if qr_data != self._cached_qr_key:
            self._cached_qr_key = qr_data
            self._cached_qr_img = QRCodeGenerator.generate_qr_qimage(qr_data, size=320)

        painter = QPainter(self)
        LabelPainter.paint_label(
            painter,
            QRectF(0, 0, self.width(), self.height()),
            rec,
            draw_border=True,
            qr_image=self._cached_qr_img,
        )
        painter.end()


class QRLabelCard(GlassCard):
    """Interactive glass container around a label in Print Studio (selectable & zoomable)."""

    selectionChanged = Signal(int, bool)

    def __init__(self, index: int, record: dict, zoom: float = 0.85, parent=None):
        super().__init__(parent=parent, strong=False, radius=16, shadow=True)
        self.index = index
        self.record = normalize_detail_record(record)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        # Top control strip
        top_bar = QHBoxLayout()
        self.checkbox = QCheckBox(f"Drum #{self.record.get('drum_sl_no', index + 1)}")
        self.checkbox.setChecked(True)
        self.checkbox.toggled.connect(lambda checked: self.selectionChanged.emit(self.index, checked))
        top_bar.addWidget(self.checkbox)

        top_bar.addStretch()

        status = self.record.get("print_status") or "PENDING"
        self.status_badge = QLabel(status)
        self.status_badge.setObjectName("BadgePill" if status == "PRINTED" else "InfoPill")
        top_bar.addWidget(self.status_badge)
        layout.addLayout(top_bar)

        self.canvas = LabelCanvasWidget(self.record, zoom=zoom)
        layout.addWidget(self.canvas, alignment=Qt.AlignmentFlag.AlignCenter)

    def set_zoom(self, zoom: float):
        self.canvas.set_zoom(zoom)

    def is_selected(self) -> bool:
        return self.checkbox.isChecked()

    def set_selected(self, selected: bool):
        self.checkbox.setChecked(selected)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.checkbox.toggle()
        super().mousePressEvent(event)

    def mark_printed_ui(self):
        self.status_badge.setText("PRINTED")
        self.status_badge.setObjectName("BadgePill")
        self.status_badge.style().unpolish(self.status_badge)
        self.status_badge.style().polish(self.status_badge)
