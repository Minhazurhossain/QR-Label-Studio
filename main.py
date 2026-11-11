import json
import os
import sys
from datetime import datetime

from PySide6.QtCore import QDate, QRectF, Qt, QTime, Signal
from PySide6.QtGui import QAction, QColor, QKeySequence, QPageLayout, QPageSize, QPainter, QShortcut
from PySide6.QtPrintSupport import QPrintDialog, QPrintPreviewDialog, QPrinter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from database import Database
from qr_label import (
    LabelCanvasWidget,
    LabelPainter,
    QRCodeGenerator,
    QRLabelCard,
    build_qr_payload,
    normalize_detail_record,
)
from styles import (
    GlassCanvas,
    GlassCard,
    THEMES,
    apply_windows_titlebar_theme,
    build_palette,
    build_stylesheet,
)
from widgets import BulkAddDialog, KpiCard, SegmentedControl, ToastManager


PRESET_SPECS = {
    "Mango (Gutti)": {"brix": 16.2, "acidity": 1.41, "ph": 3.55, "evap": 68.0, "steril": 108.0, "fill": 38.0},
    "Mango (Ashina)": {"brix": 17.0, "acidity": 1.35, "ph": 3.60, "evap": 68.0, "steril": 108.0, "fill": 38.0},
    "Tomato": {"brix": 28.0, "acidity": 1.85, "ph": 4.15, "evap": 72.0, "steril": 112.0, "fill": 40.0},
    "Guava": {"brix": 12.5, "acidity": 0.95, "ph": 3.85, "evap": 65.0, "steril": 106.0, "fill": 36.0},
    "Aloe-Vera": {"brix": 2.4, "acidity": 0.35, "ph": 4.20, "evap": 60.0, "steril": 102.0, "fill": 35.0},
}


class PrintStudioWidget(QWidget):
    """Interactive print & export studio used both inside the main workspace and standalone."""

    batchPrinted = Signal(int, list)

    def __init__(self, db: Database | None = None, toast: ToastManager | None = None, parent=None):
        super().__init__(parent)
        self.db = db
        self.toast = toast
        self.batch_id: int | None = None
        self.batch_details: list[dict] = []
        self.label_cards: list[QRLabelCard] = []
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        # Toolbar Glass Card
        toolbar = GlassCard(strong=True)
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(16, 12, 16, 12)
        tb_layout.setSpacing(12)

        info_col = QVBoxLayout()
        info_col.setSpacing(2)
        self.lbl_batch_title = QLabel("Print & Export Studio")
        self.lbl_batch_title.setObjectName("SectionTitle")
        info_col.addWidget(self.lbl_batch_title)

        self.lbl_batch_meta = QLabel("Select a batch from History or save a new batch to preview & print labels.")
        self.lbl_batch_meta.setObjectName("SectionSubtitle")
        info_col.addWidget(self.lbl_batch_meta)
        tb_layout.addLayout(info_col, stretch=1)

        # Layout preset
        tb_layout.addWidget(QLabel("Layout:"))
        self.layout_combo = QComboBox()
        self.layout_combo.addItems([
            "A4 Grid (2 × 4)",
            "A4 Compact (3 × 3)",
            "Thermal 3\"×2\" (1 / page)",
        ])
        self.layout_combo.setMinimumWidth(165)
        tb_layout.addWidget(self.layout_combo)

        # Zoom slider
        tb_layout.addWidget(QLabel("Zoom:"))
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(55, 130)
        self.zoom_slider.setValue(85)
        self.zoom_slider.setFixedWidth(110)
        self.zoom_slider.valueChanged.connect(self._on_zoom_changed)
        tb_layout.addWidget(self.zoom_slider)

        self.lbl_zoom = QLabel("85%")
        self.lbl_zoom.setMinimumWidth(38)
        tb_layout.addWidget(self.lbl_zoom)

        # Selection shortcuts
        btn_all = QPushButton("Select All")
        btn_all.clicked.connect(lambda: self._set_all_selected(True))
        tb_layout.addWidget(btn_all)

        btn_none = QPushButton("None")
        btn_none.clicked.connect(lambda: self._set_all_selected(False))
        tb_layout.addWidget(btn_none)

        # Export & Print actions
        self.btn_export_png = QPushButton("🖼️ PNGs")
        self.btn_export_png.setToolTip("Export selected labels as 300 DPI PNG images")
        self.btn_export_png.clicked.connect(self.export_pngs)
        tb_layout.addWidget(self.btn_export_png)

        self.btn_save_pdf = QPushButton("📄 Save PDF")
        self.btn_save_pdf.setObjectName("SecondaryAccentBtn")
        self.btn_save_pdf.clicked.connect(self.save_as_pdf)
        tb_layout.addWidget(self.btn_save_pdf)

        self.btn_preview_print = QPushButton("👁️ Print Preview")
        self.btn_preview_print.clicked.connect(self.open_print_preview)
        tb_layout.addWidget(self.btn_preview_print)

        self.btn_print = QPushButton("🖨️ Print Labels")
        self.btn_print.setObjectName("PrimaryBtn")
        self.btn_print.clicked.connect(self.print_labels)
        tb_layout.addWidget(self.btn_print)

        root.addWidget(toolbar)

        # Scroll area for cards
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.container = QWidget()
        self.grid = QGridLayout(self.container)
        self.grid.setContentsMargins(6, 6, 6, 16)
        self.grid.setSpacing(16)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.scroll.setWidget(self.container)
        root.addWidget(self.scroll, stretch=1)

        self._show_empty_state()

    def _notify(self, msg: str, kind: str = "info"):
        if self.toast:
            self.toast.show(msg, kind)
        else:
            QMessageBox.information(self, "PRAN QR Studio", msg)

    def _show_empty_state(self):
        self._clear_grid()
        empty = GlassCard()
        el = QVBoxLayout(empty)
        el.setContentsMargins(36, 48, 36, 48)
        el.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = QLabel("🏷️")
        icon.setStyleSheet("font-size: 38px;")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(icon)

        title = QLabel("No Batch Loaded in Print Studio")
        title.setObjectName("SectionTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(title)

        sub = QLabel("Create a batch in Batch Designer or double-click any batch in Batch History.")
        sub.setObjectName("SectionSubtitle")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(sub)

        self.grid.addWidget(empty, 0, 0)
        self._set_actions_enabled(False)

    def _set_actions_enabled(self, enabled: bool):
        for btn in (self.btn_export_png, self.btn_save_pdf, self.btn_preview_print, self.btn_print):
            btn.setEnabled(enabled)

    def _clear_grid(self):
        self.label_cards.clear()
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def load_batch(self, batch_details: list, batch_id: int | None = None):
        self.batch_id = batch_id
        self.batch_details = [normalize_detail_record(d) for d in batch_details]
        self._clear_grid()

        if not self.batch_details:
            self.lbl_batch_title.setText("Print & Export Studio")
            self.lbl_batch_meta.setText("No drum records found in this batch.")
            self._show_empty_state()
            return

        first = self.batch_details[0]
        if self.batch_id is None:
            self.batch_id = first.get("batch_id")

        self.lbl_batch_title.setText(
            f"Batch #{first.get('batch_no', '-')}  •  {first.get('item_name', '-')}"
        )
        self.lbl_batch_meta.setText(
            f"{len(self.batch_details)} drum label(s) ready  •  "
            f"Type: {first.get('product_type', '-')}  •  "
            f"Shift: {first.get('shift_code', '-')}"
        )

        zoom = self.zoom_slider.value() / 100.0
        for idx, rec in enumerate(self.batch_details):
            card = QRLabelCard(idx, rec, zoom=zoom)
            card.selectionChanged.connect(self._update_selected_count)
            self.label_cards.append(card)

        self._relayout_cards()
        self._set_actions_enabled(True)
        self._update_selected_count()

    def _relayout_cards(self):
        if not self.label_cards:
            return
        # Remove without deleting
        while self.grid.count():
            self.grid.takeAt(0)

        zoom = self.zoom_slider.value() / 100.0
        card_w = int(450 * zoom) + 36
        avail = max(card_w, self.scroll.viewport().width() - 24)
        cols = max(1, min(4, avail // card_w))

        for idx, card in enumerate(self.label_cards):
            self.grid.addWidget(card, idx // cols, idx % cols)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.label_cards:
            self._relayout_cards()

    def _on_zoom_changed(self, value: int):
        self.lbl_zoom.setText(f"{value}%")
        zoom = value / 100.0
        for card in self.label_cards:
            card.set_zoom(zoom)
        self._relayout_cards()

    def _set_all_selected(self, selected: bool):
        for card in self.label_cards:
            card.set_selected(selected)
        self._update_selected_count()

    def _selected_cards(self) -> list[QRLabelCard]:
        return [c for c in self.label_cards if c.is_selected()]

    def _update_selected_count(self, *_args):
        if not self.batch_details:
            return
        sel = len(self._selected_cards())
        first = self.batch_details[0]
        self.lbl_batch_meta.setText(
            f"{sel} of {len(self.batch_details)} label(s) selected  •  "
            f"Type: {first.get('product_type', '-')}  •  "
            f"Shift: {first.get('shift_code', '-')}"
        )

    def _configure_printer(self, printer: QPrinter):
        mode = self.layout_combo.currentText()
        if "Thermal" in mode:
            # Qt QPageSize expects portrait base dims (50.8 x 76.2 mm) before Landscape rotation -> 3"x2"
            custom_size = QPageSize(
                QSizeF_mm(50.8, 76.2),
                QPageSize.Unit.Millimeter,
                "Label 3x2in",
            )
            printer.setPageSize(custom_size)
            printer.setPageOrientation(QPageLayout.Orientation.Landscape)
            printer.setPageMargins(QMarginsF_zero(), QPageLayout.Unit.Millimeter)
        else:
            printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
            printer.setPageOrientation(QPageLayout.Orientation.Portrait)

    def _render_to_printer(self, printer: QPrinter, records: list[dict]):
        mode = self.layout_combo.currentText()
        painter = QPainter(printer)
        page_rect = printer.pageRect(QPrinter.Unit.DevicePixel)

        if "Thermal" in mode:
            margin = min(page_rect.width(), page_rect.height()) * 0.02
            avail_w = page_rect.width() - margin * 2
            avail_h = page_rect.height() - margin * 2
            if avail_w / max(1.0, avail_h) > 1.5:
                draw_h = avail_h
                draw_w = draw_h * 1.5
            else:
                draw_w = avail_w
                draw_h = draw_w / 1.5
            ox = (page_rect.width() - draw_w) / 2.0
            oy = (page_rect.height() - draw_h) / 2.0
            target = QRectF(ox, oy, draw_w, draw_h)
            for idx, rec in enumerate(records):
                if idx > 0:
                    printer.newPage()
                LabelPainter.paint_label(painter, target, rec, draw_border=True)
        else:
            cols, rows = (3, 3) if "3 × 3" in mode else (2, 4)
            per_page = cols * rows
            margin_x = page_rect.width() * 0.04
            margin_y = page_rect.height() * 0.035
            gap_x = page_rect.width() * 0.025
            gap_y = page_rect.height() * 0.02

            avail_w = page_rect.width() - 2 * margin_x - (cols - 1) * gap_x
            avail_h = page_rect.height() - 2 * margin_y - (rows - 1) * gap_y
            cell_w = avail_w / cols
            cell_h = avail_h / rows

            # Preserve exact 3:2 label aspect ratio inside each grid cell
            if cell_w / cell_h > 1.5:
                draw_h = cell_h
                draw_w = draw_h * 1.5
            else:
                draw_w = cell_w
                draw_h = draw_w / 1.5

            for idx, rec in enumerate(records):
                if idx > 0 and idx % per_page == 0:
                    printer.newPage()
                slot = idx % per_page
                r = slot // cols
                c = slot % cols
                cx = margin_x + c * (cell_w + gap_x) + (cell_w - draw_w) / 2.0
                cy = margin_y + r * (cell_h + gap_y) + (cell_h - draw_h) / 2.0
                LabelPainter.paint_label(painter, QRectF(cx, cy, draw_w, draw_h), rec, draw_border=True)

        painter.end()

    def _mark_selected_printed(self, cards: list[QRLabelCard]):
        detail_ids = [c.record.get("detail_id") for c in cards if c.record.get("detail_id")]
        for c in cards:
            c.mark_printed_ui()
        if self.db and self.batch_id is not None:
            self.db.mark_batch_printed(self.batch_id, detail_ids or None)
            self.batchPrinted.emit(self.batch_id, detail_ids)

    def save_as_pdf(self):
        cards = self._selected_cards()
        if not cards:
            self._notify("Select at least one label to export.", "warning")
            return

        batch_no = cards[0].record.get("batch_no", "batch")
        default_name = f"PRAN_QR_Batch_{batch_no}.pdf"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save QR Labels as PDF", default_name, "PDF Files (*.pdf)"
        )
        if not file_path:
            return

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(file_path)
        self._configure_printer(printer)

        self._render_to_printer(printer, [c.record for c in cards])
        self._notify(f"Saved {len(cards)} label(s) to PDF: {os.path.basename(file_path)}", "success")

    def export_pngs(self):
        cards = self._selected_cards()
        if not cards:
            self._notify("Select at least one label to export.", "warning")
            return

        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder for PNG Labels")
        if not folder:
            return

        saved = 0
        for card in cards:
            rec = card.record
            img = LabelPainter.render_to_qimage(rec, dpi_scale=2.0)
            fname = f"Batch_{rec.get('batch_no', 'X')}_Drum_{rec.get('drum_sl_no', saved + 1)}.png"
            safe_name = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in fname)
            if img.save(os.path.join(folder, safe_name), "PNG"):
                saved += 1

        self._notify(f"Exported {saved} high-DPI PNG label(s) to {folder}", "success")

    def open_print_preview(self):
        cards = self._selected_cards()
        if not cards:
            self._notify("Select at least one label to preview.", "warning")
            return

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        self._configure_printer(printer)
        preview = QPrintPreviewDialog(printer, self)
        preview.setWindowTitle("Print Preview - PRAN Agro QR Labels")
        preview.paintRequested.connect(lambda p: self._render_to_printer(p, [c.record for c in cards]))
        if preview.exec() == QPrintPreviewDialog.DialogCode.Accepted:
            self._mark_selected_printed(cards)

    def print_labels(self):
        cards = self._selected_cards()
        if not cards:
            self._notify("Select at least one label to print.", "warning")
            return

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        self._configure_printer(printer)
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle("Print QR Drum Labels")
        if dialog.exec() == QPrintDialog.DialogCode.Accepted:
            self._render_to_printer(printer, [c.record for c in cards])
            self._mark_selected_printed(cards)
            self._notify(f"Sent {len(cards)} label(s) to printer & marked PRINTED.", "success")


def QSizeF_mm(w: float, h: float):
    from PySide6.QtCore import QSizeF
    return QSizeF(w, h)


def QMarginsF_zero():
    from PySide6.QtCore import QMarginsF
    return QMarginsF(0, 0, 0, 0)


class PrintPreviewWindow(QMainWindow):
    """Backward-compatible standalone Print Preview window wrapping PrintStudioWidget."""

    def __init__(self, batch_details, db: Database | None = None):
        super().__init__()
        self.setWindowTitle("QR Code Print Studio")
        self.resize(1280, 860)
        canvas = GlassCanvas("ocean_dark")
        self.setCentralWidget(canvas)
        layout = QVBoxLayout(canvas)
        layout.setContentsMargins(18, 18, 18, 18)

        self.toast = ToastManager(canvas)
        self.studio = PrintStudioWidget(db=db, toast=self.toast)
        layout.addWidget(self.studio)
        self.studio.load_batch(batch_details)
        self.setStyleSheet(build_stylesheet("ocean_dark"))
        apply_windows_titlebar_theme(self, True)


class BatchDesignerPage(QWidget):
    """Interactive two-pane batch & drum designer with live 3x2 label preview."""

    batchSaved = Signal(int, bool)  # batch_id, open_print_studio

    def __init__(self, db: Database, toast: ToastManager, parent=None):
        super().__init__(parent)
        self.db = db
        self.toast = toast
        self.drums_data: list[dict] = []
        self.selected_row: int | None = None
        self.editing_batch_id: int | None = None
        self.editing_batch_status: str = "DRAFT"
        self.theme_key = "ocean_dark"
        self._build_ui()
        self._connect_live_preview()
        self.update_live_preview()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(6)
        splitter.setChildrenCollapsible(False)

        # LEFT: Scrollable form & staged table
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(2, 2, 10, 12)
        left_layout.setSpacing(14)

        # ---- Card 1: Batch Header ----
        header_card = GlassCard()
        hc_layout = QVBoxLayout(header_card)
        hc_layout.setContentsMargins(18, 16, 18, 16)
        hc_layout.setSpacing(12)

        hc_top = QHBoxLayout()
        hc_title = QLabel("1. Batch Information")
        hc_title.setObjectName("SectionTitle")
        hc_top.addWidget(hc_title)

        self.lbl_edit_banner = QLabel("")
        self.lbl_edit_banner.setObjectName("BadgePill")
        self.lbl_edit_banner.setVisible(False)
        hc_top.addWidget(self.lbl_edit_banner)

        self.btn_cancel_edit = QPushButton("✕ Cancel Edit")
        self.btn_cancel_edit.setObjectName("DangerBtn")
        self.btn_cancel_edit.setVisible(False)
        self.btn_cancel_edit.clicked.connect(self.cancel_edit)
        hc_top.addWidget(self.btn_cancel_edit)

        hc_top.addStretch()

        self.btn_apply_preset = QPushButton("✨ Apply Item Defaults")
        self.btn_apply_preset.setObjectName("GhostBtn")
        self.btn_apply_preset.setToolTip("Load standard Brix, Acidity, pH & Temps for the selected Item Name")
        self.btn_apply_preset.clicked.connect(self.apply_item_preset)
        hc_top.addWidget(self.btn_apply_preset)
        hc_layout.addLayout(hc_top)

        hg = QGridLayout()
        hg.setHorizontalSpacing(12)
        hg.setVerticalSpacing(10)

        # Row 0: Batch No + Auto button | Item Name
        hg.addWidget(self._field_lbl("Batch No *"), 0, 0)
        batch_row = QHBoxLayout()
        batch_row.setSpacing(6)
        self.batch_no = QLineEdit()
        self.batch_no.setPlaceholderText("e.g. 261111-01")
        batch_row.addWidget(self.batch_no)
        self.btn_auto_batch = QPushButton("⚡ Auto")
        self.btn_auto_batch.setToolTip("Generate a batch number from today's date")
        self.btn_auto_batch.clicked.connect(self.suggest_batch_no)
        batch_row.addWidget(self.btn_auto_batch)
        hg.addLayout(batch_row, 0, 1)

        hg.addWidget(self._field_lbl("Item Name"), 0, 2)
        self.item_name = QComboBox()
        self.item_name.addItems(["Mango (Gutti)", "Mango (Ashina)", "Tomato", "Guava", "Aloe-Vera"])
        self.item_name.setEditable(True)
        hg.addWidget(self.item_name, 0, 3)

        # Row 1: Product Type | Shift Code
        hg.addWidget(self._field_lbl("Product Type"), 1, 0)
        self.product_type = SegmentedControl(["ASEPTIC", "NON_ASEPTIC"], "ASEPTIC")
        hg.addWidget(self.product_type, 1, 1)

        hg.addWidget(self._field_lbl("Shift Code"), 1, 2)
        self.shift_code = SegmentedControl(["A", "B", "C"], "A")
        self.shift_code.currentChanged.connect(self._sync_shift_prefix)
        hg.addWidget(self.shift_code, 1, 3)

        # Row 2: Plant Location | Quantity | Created By
        hg.addWidget(self._field_lbl("Plant Location"), 2, 0)
        self.plant_location = QLineEdit("Amanatpur, Godagari, Rajshahi")
        hg.addWidget(self.plant_location, 2, 1)

        qty_user_row = QHBoxLayout()
        qty_user_row.setSpacing(8)
        self.quantity_kg = QDoubleSpinBox()
        self.quantity_kg.setRange(1.0, 5000.0)
        self.quantity_kg.setValue(128.0)
        self.quantity_kg.setSuffix(" kg")
        qty_user_row.addWidget(self.quantity_kg)

        self.created_by = QLineEdit("User")
        self.created_by.setPlaceholderText("Operator")
        self.created_by.setMaximumWidth(120)
        qty_user_row.addWidget(self.created_by)
        hg.addWidget(self._field_lbl("Qty / Operator"), 2, 2)
        hg.addLayout(qty_user_row, 2, 3)

        hc_layout.addLayout(hg)
        left_layout.addWidget(header_card)

        # ---- Card 2: Drum Parameters ----
        drum_card = GlassCard()
        dc_layout = QVBoxLayout(drum_card)
        dc_layout.setContentsMargins(18, 16, 18, 16)
        dc_layout.setSpacing(12)

        dc_top = QHBoxLayout()
        dc_title = QLabel("2. Drum Parameters")
        dc_title.setObjectName("SectionTitle")
        dc_top.addWidget(dc_title)
        dc_top.addStretch()

        self.btn_toggle_adv = QPushButton("▸ Preservatives & Pasteurization")
        self.btn_toggle_adv.setObjectName("GhostBtn")
        self.btn_toggle_adv.setCheckable(True)
        self.btn_toggle_adv.toggled.connect(self._toggle_advanced_panel)
        dc_top.addWidget(self.btn_toggle_adv)
        dc_layout.addLayout(dc_top)

        fg = QGridLayout()
        fg.setHorizontalSpacing(10)
        fg.setVerticalSpacing(9)

        fg.addWidget(self._field_lbl("Drum SL No"), 0, 0)
        self.drum_sl_no = QSpinBox()
        self.drum_sl_no.setRange(1, 9999)
        self.drum_sl_no.setValue(1)
        fg.addWidget(self.drum_sl_no, 0, 1)

        fg.addWidget(self._field_lbl("MFD"), 0, 2)
        self.mfd = QDateEdit()
        self.mfd.setDate(QDate.currentDate())
        self.mfd.setDisplayFormat("yyyy-MM-dd")
        self.mfd.setCalendarPopup(True)
        self.mfd.dateChanged.connect(lambda d: self.exp.setDate(d.addYears(2)))
        fg.addWidget(self.mfd, 0, 3)

        fg.addWidget(self._field_lbl("EXP"), 0, 4)
        self.exp = QDateEdit()
        self.exp.setDate(QDate.currentDate().addYears(2))
        self.exp.setDisplayFormat("yyyy-MM-dd")
        self.exp.setCalendarPopup(True)
        fg.addWidget(self.exp, 0, 5)

        fg.addWidget(self._field_lbl("Shift Time"), 1, 0)
        self.shift_time = QLineEdit("A/12")
        fg.addWidget(self.shift_time, 1, 1)

        fg.addWidget(self._field_lbl("Prod. Time"), 1, 2)
        self.production_time = QTimeEdit()
        self.production_time.setTime(QTime.currentTime())
        self.production_time.setDisplayFormat("HH:mm")
        fg.addWidget(self.production_time, 1, 3)

        fg.addWidget(self._field_lbl("Brix (°)"), 1, 4)
        self.brix = QDoubleSpinBox()
        self.brix.setRange(0, 100)
        self.brix.setDecimals(2)
        self.brix.setValue(16.20)
        fg.addWidget(self.brix, 1, 5)

        fg.addWidget(self._field_lbl("Acidity (%)"), 2, 0)
        self.acidity = QDoubleSpinBox()
        self.acidity.setRange(0, 15)
        self.acidity.setDecimals(2)
        self.acidity.setValue(1.41)
        fg.addWidget(self.acidity, 2, 1)

        fg.addWidget(self._field_lbl("pH Value"), 2, 2)
        self.ph_value = QDoubleSpinBox()
        self.ph_value.setRange(0, 14)
        self.ph_value.setDecimals(2)
        self.ph_value.setValue(3.55)
        fg.addWidget(self.ph_value, 2, 3)

        fg.addWidget(self._field_lbl("Evap Temp (°C)"), 2, 4)
        self.evap_temp = QDoubleSpinBox()
        self.evap_temp.setRange(0, 180)
        self.evap_temp.setDecimals(1)
        self.evap_temp.setValue(68.0)
        fg.addWidget(self.evap_temp, 2, 5)

        fg.addWidget(self._field_lbl("Steril Temp (°C)"), 3, 0)
        self.steril_temp = QDoubleSpinBox()
        self.steril_temp.setRange(0, 200)
        self.steril_temp.setDecimals(1)
        self.steril_temp.setValue(108.0)
        fg.addWidget(self.steril_temp, 3, 1)

        fg.addWidget(self._field_lbl("Fill Temp (°C)"), 3, 2)
        self.fill_temp = QDoubleSpinBox()
        self.fill_temp.setRange(0, 120)
        self.fill_temp.setDecimals(1)
        self.fill_temp.setValue(38.0)
        fg.addWidget(self.fill_temp, 3, 3)

        fg.addWidget(self._field_lbl("Ascorbic (ppm)"), 3, 4)
        self.ascorbic_acid = QDoubleSpinBox()
        self.ascorbic_acid.setRange(0, 1000)
        self.ascorbic_acid.setDecimals(1)
        self.ascorbic_acid.setValue(100.0)
        fg.addWidget(self.ascorbic_acid, 3, 5)

        dc_layout.addLayout(fg)

        # Collapsible Advanced Panel
        self.adv_panel = QFrame()
        self.adv_panel.setObjectName("SubGlassPanel")
        self.adv_panel.setVisible(False)
        adv_grid = QGridLayout(self.adv_panel)
        adv_grid.setContentsMargins(12, 10, 12, 10)
        adv_grid.setSpacing(8)

        adv_grid.addWidget(self._field_lbl("Pasteurize (°C)"), 0, 0)
        self.pasteurize_temp = QDoubleSpinBox()
        self.pasteurize_temp.setRange(0, 180)
        self.pasteurize_temp.setDecimals(1)
        self.pasteurize_temp.setValue(0.0)
        adv_grid.addWidget(self.pasteurize_temp, 0, 1)

        adv_grid.addWidget(self._field_lbl("KMS (ppm)"), 0, 2)
        self.kms_ppm = QDoubleSpinBox()
        self.kms_ppm.setRange(0, 2000)
        adv_grid.addWidget(self.kms_ppm, 0, 3)

        adv_grid.addWidget(self._field_lbl("Na-MS (ppm)"), 0, 4)
        self.na_ms_ppm = QDoubleSpinBox()
        self.na_ms_ppm.setRange(0, 2000)
        adv_grid.addWidget(self.na_ms_ppm, 0, 5)

        adv_grid.addWidget(self._field_lbl("SB (ppm)"), 1, 0)
        self.sb_ppm = QDoubleSpinBox()
        self.sb_ppm.setRange(0, 2000)
        adv_grid.addWidget(self.sb_ppm, 1, 1)

        adv_grid.addWidget(self._field_lbl("K-Sorbate (ppm)"), 1, 2)
        self.potassium_sorbet_ppm = QDoubleSpinBox()
        self.potassium_sorbet_ppm.setRange(0, 2000)
        adv_grid.addWidget(self.potassium_sorbet_ppm, 1, 3)

        dc_layout.addWidget(self.adv_panel)

        # Drum Action Buttons
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(8)

        self.btn_add_drum = QPushButton("＋ Add Drum")
        self.btn_add_drum.setObjectName("PrimaryBtn")
        self.btn_add_drum.clicked.connect(self.add_drum_to_list)
        btn_bar.addWidget(self.btn_add_drum)

        self.btn_update_drum = QPushButton("✏️ Update Selected")
        self.btn_update_drum.setObjectName("SecondaryAccentBtn")
        self.btn_update_drum.setEnabled(False)
        self.btn_update_drum.clicked.connect(self.update_selected_drum)
        btn_bar.addWidget(self.btn_update_drum)

        self.btn_bulk_add = QPushButton("⚡ Bulk Add...")
        self.btn_bulk_add.clicked.connect(self.open_bulk_add)
        btn_bar.addWidget(self.btn_bulk_add)

        self.btn_clear_form = QPushButton("↺ Reset Drum")
        self.btn_clear_form.clicked.connect(self.clear_drum_form)
        btn_bar.addWidget(self.btn_clear_form)

        btn_bar.addStretch()
        dc_layout.addLayout(btn_bar)
        left_layout.addWidget(drum_card)

        # ---- Card 3: Staged Drums Table ----
        table_card = GlassCard()
        tc_layout = QVBoxLayout(table_card)
        tc_layout.setContentsMargins(18, 14, 18, 16)
        tc_layout.setSpacing(10)

        tc_top = QHBoxLayout()
        tc_title = QLabel("3. Staged Drums")
        tc_title.setObjectName("SectionTitle")
        tc_top.addWidget(tc_title)

        self.lbl_staged_count = QLabel("0 drums")
        self.lbl_staged_count.setObjectName("InfoPill")
        tc_top.addWidget(self.lbl_staged_count)
        tc_top.addStretch()

        self.btn_dup_drum = QPushButton("❐ Duplicate")
        self.btn_dup_drum.setEnabled(False)
        self.btn_dup_drum.clicked.connect(self.duplicate_selected_drum)
        tc_top.addWidget(self.btn_dup_drum)

        self.btn_remove_drum = QPushButton("✕ Remove")
        self.btn_remove_drum.setObjectName("DangerBtn")
        self.btn_remove_drum.setEnabled(False)
        self.btn_remove_drum.clicked.connect(self.remove_selected_drum)
        tc_top.addWidget(self.btn_remove_drum)

        self.btn_clear_all = QPushButton("Clear List")
        self.btn_clear_all.clicked.connect(self.clear_all_drums)
        tc_top.addWidget(self.btn_clear_all)
        tc_layout.addLayout(tc_top)

        self.drum_table = QTableWidget(0, 8)
        self.drum_table.setHorizontalHeaderLabels([
            "Drum SL", "MFD", "EXP", "Shift", "Time", "Brix", "Acidity", "pH"
        ])
        self.drum_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.drum_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.drum_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.drum_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.drum_table.setAlternatingRowColors(True)
        self.drum_table.verticalHeader().setVisible(False)
        self.drum_table.setMinimumHeight(180)
        self.drum_table.itemSelectionChanged.connect(self._on_drum_row_selected)
        tc_layout.addWidget(self.drum_table)

        del_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), self.drum_table)
        del_shortcut.activated.connect(self.remove_selected_drum)

        left_layout.addWidget(table_card)
        left_scroll.setWidget(left_container)
        splitter.addWidget(left_scroll)

        # RIGHT: Sticky Live Label Preview
        right_card = GlassCard(strong=True)
        right_card.setMinimumWidth(420)
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(18, 16, 18, 16)
        right_layout.setSpacing(12)

        rp_top = QHBoxLayout()
        rp_title = QLabel("Live 3\"×2\" Label Preview")
        rp_title.setObjectName("SectionTitle")
        rp_top.addWidget(rp_title)
        rp_top.addStretch()

        self.lbl_preview_mode = QLabel("Form Draft")
        self.lbl_preview_mode.setObjectName("BadgePill")
        rp_top.addWidget(self.lbl_preview_mode)
        right_layout.addLayout(rp_top)

        # Spotlight container for the crisp label
        preview_stage = QFrame()
        preview_stage.setObjectName("SubGlassPanel")
        stage_layout = QVBoxLayout(preview_stage)
        stage_layout.setContentsMargins(14, 18, 14, 18)
        stage_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.live_label = LabelCanvasWidget(zoom=0.88)
        stage_layout.addWidget(self.live_label, alignment=Qt.AlignmentFlag.AlignCenter)
        right_layout.addWidget(preview_stage)

        # QR JSON Inspector
        json_hdr = QHBoxLayout()
        json_lbl = QLabel("Encoded QR Payload (JSON)")
        json_lbl.setObjectName("FieldLabel")
        json_hdr.addWidget(json_lbl)
        json_hdr.addStretch()

        btn_copy_json = QPushButton("Copy JSON")
        btn_copy_json.setObjectName("GhostBtn")
        btn_copy_json.clicked.connect(self._copy_qr_json)
        json_hdr.addWidget(btn_copy_json)
        right_layout.addLayout(json_hdr)

        self.json_preview = QPlainTextEdit()
        self.json_preview.setReadOnly(True)
        self.json_preview.setMaximumHeight(115)
        self.json_preview.setStyleSheet("font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 11px;")
        right_layout.addWidget(self.json_preview)

        right_layout.addStretch()

        # Primary Save CTA buttons
        save_col = QVBoxLayout()
        save_col.setSpacing(8)

        self.btn_save_and_print = QPushButton("🚀 Save Batch & Open Print Studio")
        self.btn_save_and_print.setObjectName("PrimaryBtn")
        self.btn_save_and_print.clicked.connect(lambda: self.save_batch(open_print=True))
        save_col.addWidget(self.btn_save_and_print)

        self.btn_save_draft = QPushButton("💾 Save as Draft Only")
        self.btn_save_draft.setObjectName("SecondaryAccentBtn")
        self.btn_save_draft.clicked.connect(lambda: self.save_batch(open_print=False))
        save_col.addWidget(self.btn_save_draft)

        right_layout.addLayout(save_col)
        splitter.addWidget(right_card)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter)

        QShortcut(QKeySequence("Ctrl+Return"), self).activated.connect(self.add_drum_to_list)
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(lambda: self.save_batch(open_print=False))

    def _field_lbl(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("FieldLabel")
        return lbl

    def _toggle_advanced_panel(self, checked: bool):
        self.adv_panel.setVisible(checked)
        self.btn_toggle_adv.setText(
            "▾ Preservatives & Pasteurization" if checked else "▸ Preservatives & Pasteurization"
        )

    def _sync_shift_prefix(self, code: str):
        cur = self.shift_time.text().strip()
        if not cur or (len(cur) >= 2 and cur[1] == "/" and cur[0] in ("A", "B", "C")):
            suffix = cur[1:] if len(cur) >= 2 else "/12"
            self.shift_time.setText(f"{code}{suffix}")

    def suggest_batch_no(self):
        prefix = datetime.now().strftime("%y%m%d")
        existing = self.db.get_batches_summary(search=prefix)
        seq = len(existing) + 1
        self.batch_no.setText(f"{prefix}-{seq:02d}")
        self.toast.show(f"Generated Batch No: {self.batch_no.text()}", "info")

    def apply_item_preset(self):
        item = self.item_name.currentText()
        spec = PRESET_SPECS.get(item)
        if not spec:
            self.toast.show(f"No preset configured for '{item}'", "warning")
            return
        self.brix.setValue(spec["brix"])
        self.acidity.setValue(spec["acidity"])
        self.ph_value.setValue(spec["ph"])
        self.evap_temp.setValue(spec["evap"])
        self.steril_temp.setValue(spec["steril"])
        self.fill_temp.setValue(spec["fill"])
        self.toast.show(f"Applied standard specs for {item}", "success")

    def _connect_live_preview(self):
        for w in (self.batch_no, self.plant_location, self.shift_time, self.created_by):
            w.textChanged.connect(self.update_live_preview)
        self.item_name.currentTextChanged.connect(self.update_live_preview)
        self.product_type.currentChanged.connect(self.update_live_preview)
        self.shift_code.currentChanged.connect(self.update_live_preview)
        for sp in (
            self.quantity_kg, self.drum_sl_no, self.brix, self.acidity, self.ph_value,
            self.evap_temp, self.steril_temp, self.fill_temp, self.ascorbic_acid,
        ):
            sp.valueChanged.connect(self.update_live_preview)
        self.mfd.dateChanged.connect(self.update_live_preview)
        self.exp.dateChanged.connect(self.update_live_preview)
        self.production_time.timeChanged.connect(self.update_live_preview)

    def _collect_header_dict(self) -> dict:
        return {
            "batch_no": self.batch_no.text().strip() or "DRAFT",
            "item_name": self.item_name.currentText().strip(),
            "product_type": self.product_type.current_value(),
            "plant_location": self.plant_location.text().strip(),
            "shift_code": self.shift_code.current_value(),
            "quantity_kg": self.quantity_kg.value(),
            "created_by": self.created_by.text().strip() or "User",
        }

    def _collect_drum_dict(self, sl_override: int | None = None, time_override: str | None = None) -> dict:
        return {
            "drum_sl_no": sl_override if sl_override is not None else self.drum_sl_no.value(),
            "mfd": self.mfd.date().toString("yyyy-MM-dd"),
            "exp": self.exp.date().toString("yyyy-MM-dd"),
            "shift_time": self.shift_time.text().strip(),
            "production_time": time_override if time_override is not None else self.production_time.time().toString("HH:mm"),
            "brix": round(self.brix.value(), 2),
            "acidity": round(self.acidity.value(), 2),
            "ph_value": round(self.ph_value.value(), 2),
            "evaporation_temp": round(self.evap_temp.value(), 1),
            "sterilization_temp": round(self.steril_temp.value(), 1),
            "filling_temp": round(self.fill_temp.value(), 1),
            "ascorbic_acid_ppm": round(self.ascorbic_acid.value(), 1),
            "pasteurize_temp": self.pasteurize_temp.value() or None,
            "kms_ppm": self.kms_ppm.value() or None,
            "na_ms_ppm": self.na_ms_ppm.value() or None,
            "sb_ppm": self.sb_ppm.value() or None,
            "potassium_sorbet_ppm": self.potassium_sorbet_ppm.value() or None,
        }

    def update_live_preview(self):
        rec = {**self._collect_header_dict(), **self._collect_drum_dict()}
        self.live_label.set_record(rec)
        payload = json.loads(build_qr_payload(rec))
        self.json_preview.setPlainText(json.dumps(payload, indent=2, ensure_ascii=False))

    def _copy_qr_json(self):
        QApplication.clipboard().setText(self.json_preview.toPlainText())
        self.toast.show("Copied QR JSON payload to clipboard", "info")

    def _refresh_drum_table(self):
        self.drum_table.setRowCount(0)
        for d in self.drums_data:
            row = self.drum_table.rowCount()
            self.drum_table.insertRow(row)
            vals = [
                f"#{d['drum_sl_no']}",
                d["mfd"],
                d["exp"],
                d["shift_time"],
                d["production_time"],
                f"{d['brix']:.2f}",
                f"{d['acidity']:.2f}",
                f"{d['ph_value']:.2f}",
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.drum_table.setItem(row, col, item)

        count = len(self.drums_data)
        self.lbl_staged_count.setText(f"{count} drum{'s' if count != 1 else ''}")

    def add_drum_to_list(self):
        drum_data = self._collect_drum_dict()
        self.drums_data.append(drum_data)
        self._refresh_drum_table()
        self.drum_table.scrollToBottom()

        # Auto-increment Drum SL for smooth rapid entry
        self.drum_sl_no.setValue(drum_data["drum_sl_no"] + 1)
        self.production_time.setTime(self.production_time.time().addSecs(60))
        self.lbl_preview_mode.setText("Form Draft")
        self.toast.show(f"Added Drum #{drum_data['drum_sl_no']} to batch list", "success")

    def open_bulk_add(self):
        dlg = BulkAddDialog(
            start_sl=self.drum_sl_no.value(),
            start_time=self.production_time.time(),
            theme_key=self.theme_key,
            parent=self,
        )
        if dlg.exec() == BulkAddDialog.DialogCode.Accepted:
            count, start_sl, step_min = dlg.values()
            base_time = self.production_time.time()
            for i in range(count):
                t_str = base_time.addSecs(i * step_min * 60).toString("HH:mm")
                self.drums_data.append(self._collect_drum_dict(sl_override=start_sl + i, time_override=t_str))
            self._refresh_drum_table()
            self.drum_table.scrollToBottom()
            self.drum_sl_no.setValue(start_sl + count)
            self.toast.show(f"Bulk added {count} drums (#{start_sl} → #{start_sl + count - 1})", "success")

    def _on_drum_row_selected(self):
        rows = self.drum_table.selectionModel().selectedRows()
        has_sel = len(rows) > 0
        self.btn_update_drum.setEnabled(has_sel)
        self.btn_dup_drum.setEnabled(has_sel)
        self.btn_remove_drum.setEnabled(has_sel)

        if not has_sel:
            self.selected_row = None
            self.lbl_preview_mode.setText("Form Draft")
            self.update_live_preview()
            return

        row = rows[0].row()
        self.selected_row = row
        d = self.drums_data[row]
        self._load_drum_into_form(d)
        self.lbl_preview_mode.setText(f"Editing Drum #{d['drum_sl_no']}")

    def _load_drum_into_form(self, d: dict):
        # Block signals briefly so we don't thrash preview
        widgets = [
            self.drum_sl_no, self.mfd, self.exp, self.shift_time, self.production_time,
            self.brix, self.acidity, self.ph_value, self.evap_temp, self.steril_temp,
            self.fill_temp, self.ascorbic_acid,
        ]
        for w in widgets:
            w.blockSignals(True)
        try:
            self.drum_sl_no.setValue(int(d.get("drum_sl_no", 1)))
            if d.get("mfd"):
                self.mfd.setDate(QDate.fromString(d["mfd"], "yyyy-MM-dd"))
            if d.get("exp"):
                self.exp.setDate(QDate.fromString(d["exp"], "yyyy-MM-dd"))
            self.shift_time.setText(str(d.get("shift_time") or ""))
            if d.get("production_time"):
                self.production_time.setTime(QTime.fromString(d["production_time"], "HH:mm"))
            self.brix.setValue(float(d.get("brix") or 0))
            self.acidity.setValue(float(d.get("acidity") or 0))
            self.ph_value.setValue(float(d.get("ph_value") or 0))
            self.evap_temp.setValue(float(d.get("evaporation_temp") or 0))
            self.steril_temp.setValue(float(d.get("sterilization_temp") or 0))
            self.fill_temp.setValue(float(d.get("filling_temp") or 0))
            self.ascorbic_acid.setValue(float(d.get("ascorbic_acid_ppm") or 0))
        finally:
            for w in widgets:
                w.blockSignals(False)
        self.update_live_preview()

    def update_selected_drum(self):
        if self.selected_row is None or self.selected_row >= len(self.drums_data):
            return
        updated = self._collect_drum_dict()
        self.drums_data[self.selected_row] = updated
        self._refresh_drum_table()
        self.drum_table.selectRow(self.selected_row)
        self.toast.show(f"Updated Drum #{updated['drum_sl_no']}", "success")

    def duplicate_selected_drum(self):
        if self.selected_row is None or self.selected_row >= len(self.drums_data):
            return
        src = dict(self.drums_data[self.selected_row])
        max_sl = max((d["drum_sl_no"] for d in self.drums_data), default=0)
        src["drum_sl_no"] = max_sl + 1
        self.drums_data.append(src)
        self._refresh_drum_table()
        self.drum_table.selectRow(len(self.drums_data) - 1)
        self.toast.show(f"Duplicated as Drum #{src['drum_sl_no']}", "info")

    def remove_selected_drum(self):
        if self.selected_row is None or self.selected_row >= len(self.drums_data):
            return
        removed = self.drums_data.pop(self.selected_row)
        self.selected_row = None
        self._refresh_drum_table()
        self.lbl_preview_mode.setText("Form Draft")
        self.toast.show(f"Removed Drum #{removed['drum_sl_no']}", "warning")

    def clear_all_drums(self):
        if not self.drums_data:
            return
        self.drums_data.clear()
        self.selected_row = None
        self._refresh_drum_table()
        self.drum_sl_no.setValue(1)
        self.lbl_preview_mode.setText("Form Draft")
        self.toast.show("Cleared staged drums list", "info")

    def clear_drum_form(self):
        next_sl = max((d["drum_sl_no"] for d in self.drums_data), default=0) + 1
        self.drum_sl_no.setValue(next_sl)
        self.production_time.setTime(QTime.currentTime())
        self.drum_table.clearSelection()
        self.selected_row = None
        self.lbl_preview_mode.setText("Form Draft")
        self.apply_item_preset()

    def _populate_from_batch(self, header: dict, details: list[dict], batch_no_text: str):
        self.batch_no.setText(batch_no_text)
        self.item_name.setCurrentText(header.get("item_name") or "")
        self.product_type.set_value(header.get("product_type") or "ASEPTIC")
        self.shift_code.set_value(header.get("shift_code") or "A")
        self.plant_location.setText(header.get("plant_location") or "")
        if header.get("quantity_kg"):
            self.quantity_kg.setValue(float(header["quantity_kg"]))
        self.created_by.setText(header.get("created_by") or "User")

        self.drums_data = [dict(d) for d in details]
        self._refresh_drum_table()
        if self.drums_data:
            self.drum_table.selectRow(0)

    def _set_edit_mode(self, batch_id: int | None, batch_no: str = "", status: str = "DRAFT"):
        self.editing_batch_id = batch_id
        self.editing_batch_status = status
        is_edit = batch_id is not None
        self.lbl_edit_banner.setVisible(is_edit)
        self.btn_cancel_edit.setVisible(is_edit)
        if is_edit:
            self.lbl_edit_banner.setText(f"Editing Batch #{batch_no} (ID {batch_id})")
            self.btn_save_and_print.setText("💾 Update Batch & Open Print Studio")
            self.btn_save_draft.setText("💾 Save Changes")
        else:
            self.btn_save_and_print.setText("🚀 Save Batch & Open Print Studio")
            self.btn_save_draft.setText("💾 Save as Draft Only")

    def cancel_edit(self):
        self._set_edit_mode(None)
        self.drums_data.clear()
        self.selected_row = None
        self._refresh_drum_table()
        self.batch_no.clear()
        self.drum_sl_no.setValue(1)
        self.lbl_preview_mode.setText("Form Draft")
        self.toast.show("Exited batch edit mode", "info")

    def load_batch_clone(self, header: dict, details: list[dict]):
        """Populate Designer from an existing batch for quick repeat runs."""
        self._set_edit_mode(None)
        self._populate_from_batch(header, details, f"{header.get('batch_no', '')}-COPY")
        self.toast.show(f"Cloned batch '{header.get('batch_no')}' ({len(details)} drums)", "info")

    def load_batch_for_edit(self, header: dict, details: list[dict]):
        """Load an existing batch into Designer for in-place editing."""
        self._set_edit_mode(
            header["batch_id"],
            header.get("batch_no", ""),
            header.get("status") or "DRAFT",
        )
        self._populate_from_batch(header, details, header.get("batch_no", ""))
        self.toast.show(f"Editing batch '{header.get('batch_no')}' ({len(details)} drums)", "info")

    def save_batch(self, open_print: bool = True):
        batch_no = self.batch_no.text().strip()
        if not batch_no:
            self.batch_no.setFocus()
            self.toast.show("Please enter a Batch No before saving.", "error")
            return

        if not self.drums_data:
            self.toast.show("Add at least one drum to the staged list first.", "error")
            return

        header_data = {
            "batch_no": batch_no,
            "item_name": self.item_name.currentText().strip(),
            "product_type": self.product_type.current_value(),
            "plant_location": self.plant_location.text().strip(),
            "shift_code": self.shift_code.current_value(),
            "quantity_kg": self.quantity_kg.value(),
            "created_by": self.created_by.text().strip() or "User",
            "status": self.editing_batch_status if self.editing_batch_id is not None else "DRAFT",
        }

        try:
            if self.editing_batch_id is not None:
                batch_id = self.db.update_full_batch(self.editing_batch_id, header_data, self.drums_data)
                action_verb = "Updated"
            else:
                batch_id = self.db.save_full_batch(header_data, self.drums_data)
                action_verb = "Saved"
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", f"Could not save batch:\n{exc}")
            return

        count = len(self.drums_data)
        self._set_edit_mode(None)
        self.drums_data.clear()
        self.selected_row = None
        self._refresh_drum_table()
        self.batch_no.clear()
        self.drum_sl_no.setValue(1)
        self.lbl_preview_mode.setText("Form Draft")

        self.toast.show(f"{action_verb} Batch #{batch_no} with {count} drum(s)!", "success")
        self.batchSaved.emit(batch_id, open_print)


class BatchHistoryPage(QWidget):
    """Searchable batch history with KPIs, status filters, inspector, edit/clone, and delete."""

    openPrintRequested = Signal(int)
    cloneBatchRequested = Signal(int)
    editBatchRequested = Signal(int)
    statsChanged = Signal()

    def __init__(self, db: Database, toast: ToastManager, parent=None):
        super().__init__(parent)
        self.db = db
        self.toast = toast
        self.batches: list[dict] = []
        self._inspected_details: list[dict] = []
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        # KPI Row
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)
        self.kpi_batches = KpiCard("Total Batches", "0", "#38BDF8")
        self.kpi_drums = KpiCard("Total Drums", "0", "#10B981")
        self.kpi_printed = KpiCard("Printed Labels", "0", "#A78BFA")
        self.kpi_drafts = KpiCard("Pending Drafts", "0", "#FBBF24")
        for k in (self.kpi_batches, self.kpi_drums, self.kpi_printed, self.kpi_drafts):
            kpi_row.addWidget(k)
        root.addLayout(kpi_row)

        # Filter Glass Bar
        filter_card = GlassCard(strong=True)
        fl = QHBoxLayout(filter_card)
        fl.setContentsMargins(16, 12, 16, 12)
        fl.setSpacing(12)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search by Batch No, Item Name, Plant, or Type...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self.refresh)
        fl.addWidget(self.search_input, stretch=1)

        self.status_filter = SegmentedControl(["ALL", "DRAFT", "PARTIAL", "PRINTED"], "ALL")
        self.status_filter.currentChanged.connect(lambda _: self.refresh())
        fl.addWidget(self.status_filter)

        btn_refresh = QPushButton("🔄 Refresh")
        btn_refresh.clicked.connect(self.refresh)
        fl.addWidget(btn_refresh)
        root.addWidget(filter_card)

        # Split Table + Batch Inspector
        body_split = QSplitter(Qt.Orientation.Horizontal)
        body_split.setChildrenCollapsible(False)

        # Batch Table Card
        table_card = GlassCard()
        tl = QVBoxLayout(table_card)
        tl.setContentsMargins(16, 14, 16, 14)
        tl.setSpacing(12)

        self.batch_table = QTableWidget(0, 9)
        self.batch_table.setHorizontalHeaderLabels([
            "ID", "Batch No", "Item Name", "Type", "Shift", "Drums", "Printed", "Created On", "Status"
        ])
        self.batch_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.batch_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.batch_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.batch_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.batch_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.batch_table.setAlternatingRowColors(True)
        self.batch_table.verticalHeader().setVisible(False)
        self.batch_table.doubleClicked.connect(self._open_selected_print)
        self.batch_table.itemSelectionChanged.connect(self._on_selection_changed)
        tl.addWidget(self.batch_table, stretch=1)

        # Action bar
        actions = QHBoxLayout()
        actions.setSpacing(8)

        hint = QLabel("Double-click to open Print Studio.")
        hint.setObjectName("SectionSubtitle")
        actions.addWidget(hint)
        actions.addStretch()

        self.btn_edit = QPushButton("✏️ Edit Batch")
        self.btn_edit.setEnabled(False)
        self.btn_edit.clicked.connect(self._edit_selected)
        actions.addWidget(self.btn_edit)

        self.btn_clone = QPushButton("📋 Clone")
        self.btn_clone.setEnabled(False)
        self.btn_clone.clicked.connect(self._clone_selected)
        actions.addWidget(self.btn_clone)

        self.btn_mark_printed = QPushButton("✅ Mark Printed")
        self.btn_mark_printed.setEnabled(False)
        self.btn_mark_printed.clicked.connect(self._mark_selected_printed)
        actions.addWidget(self.btn_mark_printed)

        self.btn_delete = QPushButton("🗑️ Delete")
        self.btn_delete.setObjectName("DangerBtn")
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(self._delete_selected)
        actions.addWidget(self.btn_delete)

        self.btn_open_print = QPushButton("🖨️ Print Studio")
        self.btn_open_print.setObjectName("PrimaryBtn")
        self.btn_open_print.setEnabled(False)
        self.btn_open_print.clicked.connect(self._open_selected_print)
        actions.addWidget(self.btn_open_print)

        tl.addLayout(actions)
        body_split.addWidget(table_card)

        # Right: Batch Inspector Glass Card
        inspector_card = GlassCard(strong=True)
        inspector_card.setMinimumWidth(340)
        il = QVBoxLayout(inspector_card)
        il.setContentsMargins(16, 14, 16, 14)
        il.setSpacing(10)

        self.lbl_insp_title = QLabel("Batch Inspector")
        self.lbl_insp_title.setObjectName("SectionTitle")
        il.addWidget(self.lbl_insp_title)

        self.lbl_insp_meta = QLabel("Select a batch row to inspect its drums & label preview.")
        self.lbl_insp_meta.setObjectName("SectionSubtitle")
        self.lbl_insp_meta.setWordWrap(True)
        il.addWidget(self.lbl_insp_meta)

        self.insp_drum_table = QTableWidget(0, 4)
        self.insp_drum_table.setHorizontalHeaderLabels(["Drum", "Time", "Brix", "Status"])
        self.insp_drum_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.insp_drum_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.insp_drum_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.insp_drum_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.insp_drum_table.verticalHeader().setVisible(False)
        self.insp_drum_table.setMaximumHeight(170)
        self.insp_drum_table.itemSelectionChanged.connect(self._on_insp_drum_selected)
        il.addWidget(self.insp_drum_table)

        preview_box = QFrame()
        preview_box.setObjectName("SubGlassPanel")
        pbl = QVBoxLayout(preview_box)
        pbl.setContentsMargins(10, 12, 10, 12)
        pbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.insp_label_preview = LabelCanvasWidget(zoom=0.68)
        self.insp_label_preview.setVisible(False)
        pbl.addWidget(self.insp_label_preview, alignment=Qt.AlignmentFlag.AlignCenter)
        il.addWidget(preview_box, stretch=1)

        body_split.addWidget(inspector_card)
        body_split.setStretchFactor(0, 3)
        body_split.setStretchFactor(1, 2)
        root.addWidget(body_split, stretch=1)

    def refresh(self):
        stats = self.db.get_dashboard_stats()
        self.kpi_batches.set_value(stats["total_batches"])
        self.kpi_drums.set_value(stats["total_drums"])
        self.kpi_printed.set_value(stats["printed_drums"])
        self.kpi_drafts.set_value(stats["draft_batches"])

        self.batches = self.db.get_batches_summary(
            search=self.search_input.text(),
            status_filter=self.status_filter.current_value(),
        )
        self.batch_table.setRowCount(0)
        for b in self.batches:
            row = self.batch_table.rowCount()
            self.batch_table.insertRow(row)
            printed = b.get("printed_count") or 0
            drums = b.get("drum_count") or 0
            status = b.get("status") or "DRAFT"

            cells = [
                str(b["batch_id"]),
                str(b["batch_no"]),
                str(b.get("item_name") or "-"),
                str(b.get("product_type") or "-"),
                str(b.get("shift_code") or "-"),
                str(drums),
                f"{printed}/{drums}",
                str(b.get("created_on") or "-"),
                status,
            ]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col in (0, 3, 4, 5, 6, 8):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col == 8:
                    if status == "PRINTED":
                        item.setForeground(QColor("#10B981"))
                    elif status == "PARTIAL":
                        item.setForeground(QColor("#38BDF8"))
                    else:
                        item.setForeground(QColor("#FBBF24"))
                self.batch_table.setItem(row, col, item)

        self._on_selection_changed()

    def _selected_batch_id(self) -> int | None:
        rows = self.batch_table.selectionModel().selectedRows()
        if not rows:
            return None
        row = rows[0].row()
        return int(self.batch_table.item(row, 0).text())

    def _on_selection_changed(self):
        bid = self._selected_batch_id()
        has_sel = bid is not None
        for btn in (self.btn_edit, self.btn_clone, self.btn_mark_printed, self.btn_delete, self.btn_open_print):
            btn.setEnabled(has_sel)

        self.insp_drum_table.setRowCount(0)
        self._inspected_details = []
        if not has_sel:
            self.lbl_insp_title.setText("Batch Inspector")
            self.lbl_insp_meta.setText("Select a batch row to inspect its drums & label preview.")
            self.insp_label_preview.setVisible(False)
            return

        header = self.db.get_batch_header(bid)
        details = self.db.get_batch_details_dicts(bid)
        self._inspected_details = details
        if header:
            self.lbl_insp_title.setText(f"Batch #{header['batch_no']} • {header.get('item_name', '-')}")
            self.lbl_insp_meta.setText(
                f"Plant: {header.get('plant_location') or '-'}  •  "
                f"Qty: {header.get('quantity_kg') or '-'} kg  •  "
                f"By: {header.get('created_by') or '-'}"
            )

        for d in details:
            r = self.insp_drum_table.rowCount()
            self.insp_drum_table.insertRow(r)
            for c, txt in enumerate([
                f"#{d.get('drum_sl_no', '-')}",
                str(d.get("production_time") or "-"),
                f"{d.get('brix', '-')}",
                str(d.get("print_status") or "PENDING"),
            ]):
                it = QTableWidgetItem(txt)
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.insp_drum_table.setItem(r, c, it)

        if details:
            self.insp_drum_table.selectRow(0)
        else:
            self.insp_label_preview.setVisible(False)

    def _on_insp_drum_selected(self):
        rows = self.insp_drum_table.selectionModel().selectedRows()
        if not rows or rows[0].row() >= len(self._inspected_details):
            self.insp_label_preview.setVisible(False)
            return
        self.insp_label_preview.set_record(self._inspected_details[rows[0].row()])
        self.insp_label_preview.setVisible(True)

    def _open_selected_print(self):
        bid = self._selected_batch_id()
        if bid is not None:
            self.openPrintRequested.emit(bid)

    def _edit_selected(self):
        bid = self._selected_batch_id()
        if bid is not None:
            self.editBatchRequested.emit(bid)

    def _clone_selected(self):
        bid = self._selected_batch_id()
        if bid is not None:
            self.cloneBatchRequested.emit(bid)

    def _mark_selected_printed(self):
        bid = self._selected_batch_id()
        if bid is None:
            return
        self.db.mark_batch_printed(bid)
        self.refresh()
        self.statsChanged.emit()
        self.toast.show(f"Marked batch #{bid} as PRINTED", "success")

    def _delete_selected(self):
        bid = self._selected_batch_id()
        if bid is None:
            return
        reply = QMessageBox.question(
            self,
            "Delete Batch",
            f"Permanently delete batch ID #{bid} and all of its drum records?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.db.delete_batch(bid)
            self.refresh()
            self.statsChanged.emit()
            self.toast.show(f"Deleted batch #{bid}", "warning")


class BatchEntryWindow(QMainWindow):
    """Main PRAN Agro Glassmorphism PySide6 Workspace."""

    def __init__(self):
        super().__init__()
        self.db = Database()
        self.theme_key = "ocean_dark"
        self._build_ui()
        self.apply_theme(self.theme_key)

    def _build_ui(self):
        self.setWindowTitle("PRAN Agro · Bulk QR Code & Drum Label Studio")
        self.resize(1380, 880)
        self.setMinimumSize(1120, 720)

        self.canvas = GlassCanvas(self.theme_key)
        self.setCentralWidget(self.canvas)

        main_layout = QVBoxLayout(self.canvas)
        main_layout.setContentsMargins(18, 16, 18, 18)
        main_layout.setSpacing(14)

        self.toast = ToastManager(self.canvas)

        # ---- Top Glass Navigation Bar ----
        top_bar = QFrame()
        top_bar.setObjectName("TopGlassBar")
        tb = QHBoxLayout(top_bar)
        tb.setContentsMargins(18, 10, 16, 10)
        tb.setSpacing(14)

        # Brand emblem
        emblem = QLabel("QR")
        emblem.setFixedSize(38, 38)
        emblem.setAlignment(Qt.AlignmentFlag.AlignCenter)
        emblem.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #10B981, stop:1 #38BDF8);"
            "color: white; font-weight: 900; font-size: 14px; border-radius: 10px;"
        )
        tb.addWidget(emblem)

        brand_col = QVBoxLayout()
        brand_col.setSpacing(0)
        title = QLabel("PRAN Agro · QR Label Studio")
        title.setObjectName("BrandTitle")
        brand_col.addWidget(title)
        sub = QLabel("Interactive Drum Traceability & Thermal/A4 Batch Printing")
        sub.setObjectName("BrandSub")
        brand_col.addWidget(sub)
        tb.addLayout(brand_col)

        tb.addSpacing(18)

        # Navigation Pills
        self.nav_buttons: list[QPushButton] = []
        nav_items = [
            ("✨ Batch Designer", 0),
            ("🗂️ Batch History", 1),
            ("🖨️ Print Studio", 2),
        ]
        for label, idx in nav_items:
            btn = QPushButton(label)
            btn.setObjectName("NavPill")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _checked, i=idx: self.switch_page(i))
            self.nav_buttons.append(btn)
            tb.addWidget(btn)
        self.nav_buttons[0].setChecked(True)

        tb.addStretch()

        self.lbl_header_stats = QLabel("0 Batches • 0 Drums")
        self.lbl_header_stats.setObjectName("InfoPill")
        tb.addWidget(self.lbl_header_stats)

        self.btn_theme = QPushButton("☀️ Crystal Frost")
        self.btn_theme.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_theme.clicked.connect(self.toggle_theme)
        tb.addWidget(self.btn_theme)

        main_layout.addWidget(top_bar)

        # ---- Stacked Pages ----
        self.pages = QStackedWidget()
        self.designer_page = BatchDesignerPage(self.db, self.toast)
        self.history_page = BatchHistoryPage(self.db, self.toast)
        self.print_page = PrintStudioWidget(self.db, self.toast)

        self.pages.addWidget(self.designer_page)
        self.pages.addWidget(self.history_page)
        self.pages.addWidget(self.print_page)
        main_layout.addWidget(self.pages, stretch=1)

        # Connect cross-page signals
        self.designer_page.batchSaved.connect(self._on_batch_saved)
        self.history_page.openPrintRequested.connect(self.open_batch_in_print_studio)
        self.history_page.cloneBatchRequested.connect(self.clone_batch_to_designer)
        self.history_page.editBatchRequested.connect(self.edit_batch_in_designer)
        self.history_page.statsChanged.connect(self.update_header_stats)
        self.print_page.batchPrinted.connect(lambda _bid, _ids: self._refresh_all_stats())

        self.update_header_stats()

    def switch_page(self, index: int):
        self.pages.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)
        if index == 1:
            self.history_page.refresh()

    def toggle_theme(self):
        next_theme = "crystal_light" if self.theme_key == "ocean_dark" else "ocean_dark"
        self.apply_theme(next_theme)

    def apply_theme(self, theme_key: str):
        self.theme_key = theme_key
        t = THEMES[theme_key]
        app = QApplication.instance()
        if app is not None:
            app.setPalette(build_palette(theme_key))
        self.canvas.set_theme(theme_key)
        self.setStyleSheet(build_stylesheet(theme_key))
        apply_windows_titlebar_theme(self, t["is_dark"])

        self.toast.is_dark = t["is_dark"]
        self.designer_page.theme_key = theme_key
        for card in self.findChildren(GlassCard):
            card.update_shadow(theme_key)

        self.btn_theme.setText("☀️ Crystal Frost" if t["is_dark"] else "🌙 Ocean Glass")

    def update_header_stats(self):
        stats = self.db.get_dashboard_stats()
        self.lbl_header_stats.setText(
            f"{stats['total_batches']} Batches • {stats['total_drums']} Drums"
        )

    def _refresh_all_stats(self):
        self.history_page.refresh()
        self.update_header_stats()

    def _on_batch_saved(self, batch_id: int, open_print: bool):
        self._refresh_all_stats()
        if open_print:
            self.open_batch_in_print_studio(batch_id)

    def open_batch_in_print_studio(self, batch_id: int):
        details = self.db.get_batch_details_dicts(batch_id)
        self.print_page.load_batch(details, batch_id=batch_id)
        self.switch_page(2)

    def clone_batch_to_designer(self, batch_id: int):
        header = self.db.get_batch_header(batch_id)
        details = self.db.get_batch_details_dicts(batch_id)
        if header:
            self.designer_page.load_batch_clone(header, details)
            self.switch_page(0)

    def edit_batch_in_designer(self, batch_id: int):
        header = self.db.get_batch_header(batch_id)
        details = self.db.get_batch_details_dicts(batch_id)
        if header:
            self.designer_page.load_batch_for_edit(header, details)
            self.switch_page(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "toast"):
            self.toast.reposition()

    def closeEvent(self, event):
        self.db.close()
        super().closeEvent(event)


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("PRAN Agro QR Label Studio")

    window = BatchEntryWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
