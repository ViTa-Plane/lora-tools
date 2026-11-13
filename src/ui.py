# version = 1.0.26

import json
from copy import deepcopy
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QLabel, QFileDialog, QScrollArea,
    QFrame, QSplitter, QTextEdit, QTreeWidget, QTreeWidgetItem,
    QGridLayout, QListWidget, QListWidgetItem, QMessageBox, QHeaderView,
    QTabWidget, QMenu, QAbstractItemView, QSizePolicy, QToolButton, QStyle, QDialog
)
from PySide6.QtCore import Qt, Signal, QSize, QThread, QObject, QFileSystemWatcher, QTimer, QUrl
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QKeySequence, QShortcut, QClipboard, QIcon, QPen, \
    QDesktopServices, QMouseEvent

from .helpers import open_containing_folder

# ==========================================
# Custom UI Components
# ==========================================

class ClickableBrandLabel(QLabel):
    """Custom clickable label for the app title that opens GitHub repository."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Click to open GitHub repository (https://github.com/ViTa-Plane/lora-tools)")

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            QDesktopServices.openUrl(QUrl("https://github.com/ViTa-Plane/lora-tools"))
        super().mousePressEvent(event)

class ClearableLineEdit(QLineEdit):
    """A search input field equipped with a visible clear (X) button overlay."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.clear_btn = QToolButton(self)
        self.clear_btn.setText("✕")
        self.clear_btn.setStyleSheet("""
            QToolButton {
                background: transparent;
                border: none;
                color: #94a3b8;
                font-weight: bold;
                font-size: 13px;
                padding: 0px;
            }
            QToolButton:hover {
                color: #f8fafc;
            }
        """)
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.hide()
        self.clear_btn.clicked.connect(self.clear)

        self.textChanged.connect(self._on_text_changed)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        sz = self.clear_btn.sizeHint()

        frame_width = 2
        try:
            style = self.style()
            if style:
                frame_width = style.pixelMetric(QStyle.PixelMetric.PM_DefaultFrameWidth, None, self)
        except Exception:
            pass

        self.clear_btn.move(
            self.rect().right() - frame_width - sz.width() - 8,
            (self.rect().height() - sz.height()) // 2
        )

    def _on_text_changed(self, text: str):
        self.clear_btn.setVisible(bool(text))
        m = self.textMargins()
        self.setTextMargins(m.left(), m.top(), 24 if text else 4, m.bottom())

class LoraCard(QFrame):
    clicked = Signal(dict)

    CARD_WIDTH = 194
    CARD_HEIGHT = 264
    IMG_HEIGHT = 200

    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        self.data = data
        self.selected = False
        self.setFixedSize(self.CARD_WIDTH, self.CARD_HEIGHT)
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("LoraCard")

        self._setup_ui()
        self._update_style()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.img_label = QLabel()
        self.img_label.setFixedSize(self.CARD_WIDTH - 16, self.IMG_HEIGHT)
        self.img_label.setAlignment(Qt.AlignCenter)
        self.img_label.setObjectName("CardImage")
        self.img_label.setPixmap(self._load_pixmap())

        self.title_label = QLabel(self.data["name"])
        self.title_label.setAlignment(Qt.AlignCenter | Qt.AlignTop)
        self.title_label.setWordWrap(True)
        self.title_label.setObjectName("CardTitle")
        self.title_label.setToolTip(self.data["name"])
        self.title_label.setFixedHeight(38)

        layout.addWidget(self.img_label)
        layout.addWidget(self.title_label)

    def _load_pixmap(self) -> QPixmap:
        target_w = self.CARD_WIDTH - 16
        target_h = self.IMG_HEIGHT
        thumb_path = self.data.get("thumbnail")

        pix = QPixmap()
        if thumb_path and Path(thumb_path).exists():
            pix = QPixmap(thumb_path)

        if not pix.isNull():
            return pix.scaled(
                target_w, target_h,
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation
            )

        # Generic Styled Overlay Placeholder for items without a preview image
        placeholder = QPixmap(target_w, target_h)
        placeholder.fill(QColor("#0f172a"))

        painter = QPainter(placeholder)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.setPen(QPen(QColor("#1e293b"), 2))
        painter.setBrush(QColor("#131b2e"))
        painter.drawRoundedRect(placeholder.rect().adjusted(4, 4, -4, -4), 8, 8)

        icon_rect = placeholder.rect().adjusted(45, 55, -45, -75)
        painter.setBrush(QColor("#1e293b"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(icon_rect, 6, 6)

        painter.setPen(QColor("#64748b"))
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        painter.drawText(icon_rect, Qt.AlignCenter, "NO PREVIEW")

        painter.setPen(QColor("#475569"))
        painter.setFont(QFont("Segoe UI", 8))
        sub_rect = placeholder.rect().adjusted(10, 115, -10, -45)
        painter.drawText(sub_rect, Qt.AlignCenter, ".safetensors")

        painter.end()
        return placeholder

    def set_selected(self, state: bool):
        self.selected = state
        self._update_style()

    def _update_style(self):
        if self.selected:
            self.setStyleSheet("""
                #LoraCard {
                    background-color: #1a233a;
                    border: 2px solid #6366f1;
                    border-radius: 12px;
                }
            """)
        else:
            self.setStyleSheet("""
                #LoraCard {
                    background-color: #131b2e;
                    border: 1px solid #1e293b;
                    border-radius: 12px;
                }
                #LoraCard:hover {
                    background-color: #172138;
                    border: 1px solid #334155;
                }
            """)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.data)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            open_containing_folder(self.data["path"])
        super().mouseDoubleClickEvent(event)

class ResponsiveGridWidget(QWidget):
    card_selected = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.grid = QGridLayout(self)
        self.grid.setHorizontalSpacing(16)
        self.grid.setVerticalSpacing(16)
        self.grid.setContentsMargins(20, 20, 20, 20)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.cards: list[LoraCard] = []
        self.visible_cards: list[LoraCard] = []
        self.selected_card: LoraCard | None = None
        self._current_cols = 0

        self._pending_cards_data = []
        self._batch_timer = QTimer(self)
        self._batch_timer.setInterval(25)
        self._batch_timer.timeout.connect(self._process_batch)

    def sizeHint(self) -> QSize:
        if not self.visible_cards:
            return QSize(self.width(), 200)

        available_width = self.width() - 40
        card_step = LoraCard.CARD_WIDTH + self.grid.horizontalSpacing()
        cols = max(1, available_width // card_step) if available_width > 0 else 4

        rows = (len(self.visible_cards) + cols - 1) // cols

        total_height = (
                self.grid.contentsMargins().top() +
                self.grid.contentsMargins().bottom() +
                (rows * LoraCard.CARD_HEIGHT) +
                (max(0, rows - 1) * self.grid.verticalSpacing())
        )
        return QSize(self.width(), total_height)

    def add_lora(self, data: dict):
        self._pending_cards_data.append(data)
        if not self._batch_timer.isActive():
            self._batch_timer.start()

    def _process_batch(self):
        if not self._pending_cards_data:
            self._batch_timer.stop()
            return

        chunk = self._pending_cards_data[:30]
        self._pending_cards_data = self._pending_cards_data[30:]

        available_width = self.width() - 40
        card_step = LoraCard.CARD_WIDTH + self.grid.horizontalSpacing()
        cols = max(1, available_width // card_step) if available_width > 0 else 4
        self._current_cols = cols

        self.setUpdatesEnabled(False)
        for data in chunk:
            card = LoraCard(data)
            card.clicked.connect(lambda d, c=card: self._on_card_clicked(c, d))
            self.cards.append(card)
            self.visible_cards.append(card)

            idx = len(self.visible_cards) - 1
            row = idx // cols
            col = idx % cols
            self.grid.addWidget(card, row, col)

        self.updateGeometry()
        self.setUpdatesEnabled(True)
        self.update()

        if not self._pending_cards_data:
            self._batch_timer.stop()

    def clear_cards(self):
        self._batch_timer.stop()
        self._pending_cards_data.clear()
        for card in self.cards:
            self.grid.removeWidget(card)
            card.deleteLater()
        self.cards.clear()
        self.visible_cards.clear()
        self.selected_card = None
        self._current_cols = 0
        self.updateGeometry()

    def filter_cards(self, query: str):
        self._batch_timer.stop()
        self._pending_cards_data.clear()
        q = query.strip().lower()
        self.visible_cards = []
        for card in self.cards:
            match = q in card.data["name"].lower()
            if not match:
                meta_str = json.dumps(card.data["metadata"]).lower()
                match = q in meta_str
            card.setVisible(match)
            if match:
                self.visible_cards.append(card)
        self._relayout(force=True)

    def _on_card_clicked(self, card: LoraCard, data: dict):
        if self.selected_card:
            self.selected_card.set_selected(False)
        self.selected_card = card
        card.set_selected(True)
        self.card_selected.emit(data)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout(force=False)

    def _relayout(self, force=False):
        available_width = self.width() - 40
        if available_width <= 0:
            return

        card_step = LoraCard.CARD_WIDTH + self.grid.horizontalSpacing()
        cols = max(1, available_width // card_step)

        if cols == self._current_cols and not force:
            return
        self._current_cols = cols

        self.setUpdatesEnabled(False)
        for card in self.visible_cards:
            self.grid.removeWidget(card)

        for idx, card in enumerate(self.visible_cards):
            if card.isVisible():
                row = idx // cols
                col = idx % cols
                self.grid.addWidget(card, row, col)

        self.updateGeometry()
        self.setUpdatesEnabled(True)
        self.update()

class MetadataInspector(QWidget):
    metadata_changed = Signal()
    export_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(420)
        self.current_data: dict | None = None

        self.undo_stack: list[dict] = []
        self.redo_stack: list[dict] = []

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.header_title = QLabel("Select a LoRa")
        self.header_title.setObjectName("InspectorTitle")
        self.header_title.setWordWrap(True)

        self.file_info = QLabel("No file selected")
        self.file_info.setObjectName("SubtleText")
        self.file_info.setWordWrap(True)

        export_layout = QHBoxLayout()
        self.export_btn = QPushButton("Export Metadata")
        self.export_btn.setObjectName("PrimaryButton")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self.export_requested.emit)

        self.dirty_label = QLabel("")
        self.dirty_label.setObjectName("DirtyLabel")
        export_layout.addWidget(self.export_btn)
        export_layout.addWidget(self.dirty_label)
        export_layout.addStretch()

        layout.addWidget(self.header_title)
        layout.addWidget(self.file_info)
        layout.addLayout(export_layout)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("InspectorTabs")

        self.overview_tab = QWidget()
        ov_layout = QVBoxLayout(self.overview_tab)
        ov_layout.setContentsMargins(8, 8, 8, 8)
        ov_layout.setSpacing(12)

        hl_label = QLabel("Core Training Metrics")
        hl_label.setObjectName("SectionHeader")

        self.highlights_box = QTextEdit()
        self.highlights_box.setReadOnly(True)
        self.highlights_box.setObjectName("HighlightsBox")
        self.highlights_box.setPlaceholderText("Detailed training metrics will appear here...")

        self.highlights_box.verticalScrollBar().setStyleSheet("""
            QScrollBar:vertical { border: none; background-color: #0f172a; width: 10px; margin: 0px; }
            QScrollBar::handle:vertical { background-color: #334155; min-height: 20px; border-radius: 5px; margin: 2px; }
            QScrollBar::handle:vertical:hover { background-color: #475569; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; background: none; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
        """)

        ov_layout.addWidget(hl_label)
        ov_layout.addWidget(self.highlights_box)

        self.tags_tab = QWidget()
        tags_layout = QVBoxLayout(self.tags_tab)
        tags_layout.setContentsMargins(8, 8, 8, 8)
        tags_layout.setSpacing(10)

        kw_label = QLabel("Keywords / Tags (Right-click to copy)")
        kw_label.setObjectName("SectionHeader")

        self.keyword_list = QListWidget()
        self.keyword_list.setSelectionMode(QListWidget.SingleSelection)
        self.keyword_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.keyword_list.customContextMenuRequested.connect(self._show_keyword_context_menu)
        self.keyword_list.verticalScrollBar().setStyleSheet("""
            QScrollBar:vertical { border: none; background-color: #0f172a; width: 10px; margin: 0px; }
            QScrollBar::handle:vertical { background-color: #334155; min-height: 20px; border-radius: 5px; margin: 2px; }
            QScrollBar::handle:vertical:hover { background-color: #475569; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; background: none; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
        """)

        tags_layout.addWidget(kw_label)
        tags_layout.addWidget(self.keyword_list)

        self.raw_tab = QWidget()
        raw_layout = QVBoxLayout(self.raw_tab)
        raw_layout.setContentsMargins(8, 8, 8, 8)
        raw_layout.setSpacing(10)

        tree_label = QLabel("Full Header Metadata Key-Value Tree")
        tree_label.setObjectName("SectionHeader")

        self.meta_tree = QTreeWidget()
        self.meta_tree.setHeaderLabels(["Key", "Value"])
        self.meta_tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.meta_tree.header().setStretchLastSection(True)
        self.meta_tree.setAlternatingRowColors(False)
        self.meta_tree.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)

        self.meta_tree.header().setStyleSheet("""
            QHeaderView::section {
                background-color: #131b2e;
                color: #94a3b8;
                border-bottom: 1px solid #1e293b;
                border-right: 1px solid #1e293b;
                padding: 6px;
                font-weight: 600;
            }
        """)

        self.meta_tree.verticalScrollBar().setStyleSheet("""
            QScrollBar:vertical { border: none; background-color: #0f172a; width: 10px; margin: 0px; }
            QScrollBar::handle:vertical { background-color: #334155; min-height: 20px; border-radius: 5px; margin: 2px; }
            QScrollBar::handle:vertical:hover { background-color: #475569; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; background: none; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
        """)

        self.meta_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.meta_tree.customContextMenuRequested.connect(self._show_meta_context_menu)

        raw_layout.addWidget(tree_label)
        raw_layout.addWidget(self.meta_tree)

        self.tabs.addTab(self.overview_tab, "Overview")
        self.tabs.addTab(self.tags_tab, "Keywords & Tags")
        self.tabs.addTab(self.raw_tab, "Raw Metadata")

        layout.addWidget(self.tabs)

    def _show_keyword_context_menu(self, pos):
        item = self.keyword_list.itemAt(pos)
        if not item:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #131b2e;
                color: #f1f5f9;
                border: 1px solid #1e293b;
                border-radius: 8px;
                padding: 6px;
            }
            QMenu::item {
                padding: 7px 18px;
                border-radius: 6px;
            }
            QMenu::item:selected {
                background-color: #1a233a;
                color: #38bdf8;
            }
        """)

        copy_action = menu.addAction("Copy Keyword")
        action = menu.exec(self.keyword_list.viewport().mapToGlobal(pos))

        if action == copy_action:
            tag_name = item.text().split(" (")[0]
            QApplication.clipboard().setText(tag_name)

    def _show_meta_context_menu(self, pos):
        item = self.meta_tree.itemAt(pos)
        if not item:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #131b2e;
                color: #f1f5f9;
                border: 1px solid #1e293b;
                border-radius: 8px;
                padding: 6px;
            }
            QMenu::item {
                padding: 7px 18px;
                border-radius: 6px;
            }
            QMenu::item:selected {
                background-color: #1a233a;
                color: #38bdf8;
            }
        """)

        copy_key_action = menu.addAction("Copy Key")
        copy_val_action = menu.addAction("Copy Value")
        copy_pair_action = menu.addAction("Copy Key & Value")

        action = menu.exec(self.meta_tree.viewport().mapToGlobal(pos))
        clipboard = QApplication.clipboard()

        if action == copy_key_action:
            clipboard.setText(item.text(0))
        elif action == copy_val_action:
            clipboard.setText(item.text(1))
        elif action == copy_pair_action:
            clipboard.setText(f"{item.text(0)}: {item.text(1)}")

    def display_lora(self, data: dict):
        self.current_data = data
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.export_btn.setEnabled(True)
        self._refresh_inspector_view()

    def _refresh_inspector_view(self):
        if not self.current_data:
            return

        data = self.current_data
        self.header_title.setText(data["name"])
        dirty_marker = " [UNSAVED]" if data["is_dirty"] else ""
        self.file_info.setText(f"Size: {data['size_mb']} MB{dirty_marker}  |  Path: {data['path']}")
        self.dirty_label.setText("⚠️ Unsaved changes" if data["is_dirty"] else "")

        meta = data.get("metadata", {})
        self._populate_highlights(meta)
        self._populate_keywords(meta)
        self._populate_tree(meta)

    def push_undo_state(self):
        if not self.current_data:
            return
        self.undo_stack.append(deepcopy(self.current_data["metadata"]))
        self.redo_stack.clear()
        self.current_data["is_dirty"] = True
        self.metadata_changed.emit()

    def undo(self):
        if not self.current_data or not self.undo_stack:
            return
        self.redo_stack.append(deepcopy(self.current_data["metadata"]))
        previous_meta = self.undo_stack.pop()
        self.current_data["metadata"] = previous_meta

        if self.current_data["metadata"] == self.current_data["original_metadata"]:
            self.current_data["is_dirty"] = False

        self._refresh_inspector_view()
        self.metadata_changed.emit()

    def redo(self):
        if not self.current_data or not self.redo_stack:
            return
        self.undo_stack.append(deepcopy(self.current_data["metadata"]))
        next_meta = self.redo_stack.pop()
        self.current_data["metadata"] = next_meta
        self.current_data["is_dirty"] = True

        self._refresh_inspector_view()
        self.metadata_changed.emit()

    def _populate_highlights(self, meta: dict):
        if not meta:
            self.highlights_box.setPlainText("No __metadata__ header found.")
            return

        lines = []
        base_model = meta.get("ss_sd_model_name") or meta.get("modelspec.architecture") or meta.get("ss_v2")
        if base_model:
            model_mapping = {
                "290640.safetensors": "Pony Diffusion V6 XL",
                "hollowstrawberry/67AB2F": "Pony Diffusion V6 XL",
                "889818.safetensors": "Illustrious-XL v0.1",
                "1761560.safetensors": "WAI-illustrious-SDXL v14.0",
                "EMS-544361-EMS.safetensors": "Illustrious-XL",
                "urn:air:sdxl:checkpoint:civitai:795765@889818": "Illustrious-XL v0.1",
            }
            mapped_name = model_mapping.get(str(base_model).strip())
            if mapped_name:
                lines.append(f"Base Model: {base_model} ({mapped_name})")
            else:
                lines.append(f"Base Model: {base_model}")

        dim = meta.get("ss_network_dim")
        alpha = meta.get("ss_network_alpha")
        if dim or alpha:
            lines.append(f"Network Dim: {dim} / Alpha: {alpha} ")

        epochs = meta.get("ss_epoch") or meta.get("ss_num_epochs")
        steps = meta.get("ss_steps")
        if epochs or steps:
            lines.append(f"Epochs: {epochs} / Steps: {steps}   ")

        lr = meta.get("ss_learning_rate")
        unet_lr = meta.get("ss_unet_lr")
        text_lr = meta.get("ss_text_encoder_lr")
        if lr:
            lines.append(f"Learning Rate: {lr}")
        if unet_lr:
            lines.append(f"UNet LR: {unet_lr}")
        if text_lr:
            lines.append(f"Text Encoder LR: {text_lr}")

        scheduler = meta.get("ss_lr_scheduler") or meta.get("ss_lr_scheduler_type")
        if scheduler:
            lines.append(f"Scheduler: {scheduler}")

        batch_sizes = []
        ss_datasets_raw = meta.get("ss_datasets")
        if ss_datasets_raw:
            try:
                datasets_list = json.loads(ss_datasets_raw) if isinstance(ss_datasets_raw, str) else ss_datasets_raw
                if isinstance(datasets_list, list):
                    for ds in datasets_list:
                        if isinstance(ds, dict) and "batch_size_per_device" in ds:
                            batch_sizes.append(str(ds["batch_size_per_device"]))
            except Exception as e:
                print(f"Error parsing ss_datasets: {e}")

        if batch_sizes:
            unique_bs = ", ".join(sorted(list(set(batch_sizes))))
            lines.append(f"Batch Size per Device: {unique_bs}")

        total_images = 0
        total_steps_per_epoch = 0
        dataset_breakdown = []
        ds_dirs_raw = meta.get("ss_dataset_dirs")

        if ds_dirs_raw:
            try:
                ds_data = json.loads(ds_dirs_raw) if isinstance(ds_dirs_raw, str) else ds_dirs_raw
                if isinstance(ds_data, dict):
                    for folder_name, props in ds_data.items():
                        if isinstance(props, dict):
                            img_count = props.get("img_count", 0)
                            n_repeats = props.get("n_repeats", 1)
                            total_images += img_count
                            total_steps_per_epoch += (img_count * n_repeats)
                            dataset_breakdown.append(f"  • {folder_name}: {img_count} imgs (×{n_repeats} repeats)")
            except Exception as e:
                print(f"Error parsing ss_dataset_dirs: {e}")

        if total_images > 0:
            lines.append(f"Training Images: {total_images} total ({total_steps_per_epoch} per epoch)")
            if dataset_breakdown:
                lines.append("Sub-Datasets:\n" + "\n".join(dataset_breakdown))
        else:
            dataset_raw = meta.get("dataset")
            img_count = None
            if dataset_raw:
                try:
                    parsed_ds = json.loads(dataset_raw) if isinstance(dataset_raw, str) else dataset_raw
                    if isinstance(parsed_ds, dict):
                        img_count = parsed_ds.get("img_count")
                except Exception:
                    pass
            if img_count is not None:
                lines.append(f"Training Images: {img_count}")
            else:
                num_imgs = meta.get("ss_num_train_images")
                if num_imgs:
                    lines.append(f"Training Images: {num_imgs}")

        start_time = meta.get("ss_training_started_at")
        end_time = meta.get("ss_training_finished_at")

        if start_time and end_time:
            try:
                duration_sec = float(end_time) - float(start_time)
                if duration_sec > 0:
                    total_mins = int(duration_sec // 60)
                    hrs = total_mins // 60
                    mins = total_mins % 60
                    lines.append(f"Training Duration: {hrs:02d}:{mins:02d} (hh:mm)")
            except Exception:
                pass

        if not start_time or not end_time:
            train_time = meta.get("ss_training_time") or meta.get("time elapsed")
            if train_time:
                try:
                    sec = float(train_time)
                    total_mins = int(sec // 60)
                    hrs = total_mins // 60
                    mins = total_mins % 60
                    lines.append(f"Training Duration: {hrs:02d}:{mins:02d} (hh:mm)")
                except Exception:
                    lines.append(f"Training Duration: {train_time}")

        resolution = meta.get("ss_resolution")
        if resolution:
            lines.append(f"Resolution: {resolution}")

        optimizer = meta.get("ss_optimizer")
        if optimizer:
            lines.append(f"Optimizer: {optimizer}")

        tag_freq_raw = meta.get("ss_tag_frequency")
        if tag_freq_raw:
            try:
                tag_freq = json.loads(tag_freq_raw) if isinstance(tag_freq_raw, str) else tag_freq_raw
                tag_counts = {}
                for dataset_tags in tag_freq.values():
                    if isinstance(dataset_tags, dict):
                        for tag, count in dataset_tags.items():
                            tag_counts[tag] = tag_counts.get(tag, 0) + count
                if tag_counts:
                    sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]
                    top_tags_str = ", ".join([t for t, c in sorted_tags])
                    lines.append("-" * 30)
                    lines.append(f"Top 10 Keywords:\n{top_tags_str}")
            except Exception:
                pass

        self.highlights_box.setPlainText("\n".join(lines) if lines else "No standard core training parameters found.")

    def _populate_keywords(self, meta: dict):
        self.keyword_list.clear()
        tag_freq_raw = meta.get("ss_tag_frequency")
        if not tag_freq_raw:
            return
        try:
            tag_freq = json.loads(tag_freq_raw) if isinstance(tag_freq_raw, str) else tag_freq_raw
            tag_counts = {}
            for dataset_tags in tag_freq.values():
                if isinstance(dataset_tags, dict):
                    for tag, count in dataset_tags.items():
                        tag_counts[tag] = tag_counts.get(tag, 0) + count

            sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
            for tag, count in sorted_tags:
                item = QListWidgetItem(f"{tag} ({count})")
                self.keyword_list.addItem(item)
        except Exception:
            pass

    def _populate_tree(self, meta: dict):
        self.meta_tree.clear()
        if not meta:
            return

        for key, val in sorted(meta.items()):
            display_val = str(val)
            if isinstance(val, str) and (val.startswith("{") or val.startswith("[")):
                try:
                    parsed = json.loads(val)
                    display_val = json.dumps(parsed, indent=2)
                except Exception:
                    pass

            item = QTreeWidgetItem([str(key), display_val])
            self.meta_tree.addTopLevelItem(item)

class MetadataEditDialog(QDialog):
    """Fancy dark style modal dialog with tabs for editing keywords and raw metadata."""

    def __init__(self, current_metadata: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit LoRa Metadata")
        self.resize(700, 550)
        self.updated_metadata = None
        self._current_meta = current_metadata or {}

        self._setup_ui()
        self._apply_dark_style()
        self._load_data()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # Title header
        title = QLabel("✏️ Metadata Editor")
        title.setObjectName("DialogTitle")
        layout.addWidget(title)

        # Tabs setup
        self.tabs = QTabWidget()
        self.tabs.setObjectName("EditorTabs")

        # Tab 1: Keywords / Tags
        self.keywords_edit = QTextEdit()
        self.keywords_edit.setPlaceholderText("Enter keywords or tags (comma or newline separated)...")
        self.tabs.addTab(self.keywords_edit, "Keywords / Tags")

        # Tab 2: Raw Metadata JSON
        self.raw_json_edit = QTextEdit()
        self.raw_json_edit.setPlaceholderText("Edit raw metadata JSON dictionary...")
        self.tabs.addTab(self.raw_json_edit, "Raw Metadata (JSON)")

        layout.addWidget(self.tabs, stretch=1)

        # Buttons layout
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.apply_btn = QPushButton("Apply Changes")
        self.apply_btn.setObjectName("PrimaryButton")
        self.apply_btn.clicked.connect(self._on_apply)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("SecondaryButton")
        self.cancel_btn.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.apply_btn)

        layout.addLayout(btn_layout)

    def _load_data(self):
        keywords_list = []
        meta_data = self._current_meta

        # 1. Inspect ss_tag_frequency to find the dataset hierarchy
        tag_freq = meta_data.get("ss_tag_frequency", {})
        if isinstance(tag_freq, str):
            try:
                tag_freq = json.loads(tag_freq)
            except Exception:
                tag_freq = {}

        # If it uses the nested dataset structure (e.g. {"dataset_name": {"tag1": count}})
        if isinstance(tag_freq, dict) and tag_freq:
            # Look inside the dataset containers
            for ds_key, ds_val in tag_freq.items():
                if isinstance(ds_val, dict):
                    keywords_list.extend(ds_val.keys())
                elif isinstance(ds_val, (int, float)):
                    # Flat structure fallback
                    keywords_list.append(ds_key)
        else:
            # Fallback to general keywords
            raw_keywords = meta_data.get("keywords", meta_data.get("tags", ""))
            if isinstance(raw_keywords, str):
                try:
                    parsed = json.loads(raw_keywords)
                    if isinstance(parsed, list):
                        keywords_list = [str(k) for k in parsed]
                    elif isinstance(parsed, dict):
                        keywords_list = list(parsed.keys())
                except Exception:
                    keywords_list = [k.strip() for k in raw_keywords.replace("\n", ",").split(",") if k.strip()]
            elif isinstance(raw_keywords, list):
                keywords_list = [str(k) for k in raw_keywords]

        # Deduplicate while preserving order
        seen = set()
        unique_keywords = [x for x in keywords_list if not (x in seen or seen.add(x))]

        # Display tags one per line in the textbox
        self.keywords_edit.setPlainText("\n".join(unique_keywords))

        # Format full metadata dict as pretty JSON for the raw metadata tab
        try:
            pretty_json = json.dumps(self._current_meta, indent=4, ensure_ascii=False)
            self.raw_json_edit.setPlainText(pretty_json)
        except Exception:
            self.raw_json_edit.setPlainText("{}")

    def _on_apply(self):
        current_tab_index = self.tabs.currentIndex()

        if current_tab_index == 1:
            # Raw JSON Tab active
            raw_text = self.raw_json_edit.toPlainText()
            try:
                parsed_dict = json.loads(raw_text)
                if not isinstance(parsed_dict, dict):
                    raise ValueError("JSON root must be an object/dictionary.")
                self.updated_metadata = parsed_dict
                self.accept()
            except Exception as e:
                QMessageBox.critical(self, "Invalid JSON", f"Failed to parse raw metadata JSON:\n{str(e)}")
        else:
            # Keywords Tab active - Read line-by-line
            kw_text = self.keywords_edit.toPlainText()
            cleaned_keywords = [k.strip() for k in kw_text.splitlines() if k.strip()]

            updated = dict(self._current_meta)

            # --- 1. Update ss_tag_frequency ---
            if "ss_tag_frequency" in updated:
                orig_val = updated["ss_tag_frequency"]
                is_stringified = isinstance(orig_val, str)
                try:
                    tag_freq_dict = json.loads(orig_val) if is_stringified else dict(orig_val)
                except Exception:
                    tag_freq_dict = {}

                new_tag_freq = {}
                if isinstance(tag_freq_dict, dict) and tag_freq_dict:
                    for ds_key, ds_val in tag_freq_dict.items():
                        if isinstance(ds_val, dict):
                            new_ds_dict = {}
                            for tag in cleaned_keywords:
                                # Restore previous frequency count if it existed, otherwise default to 1
                                if tag in ds_val:
                                    new_ds_dict[tag] = ds_val[tag]
                                else:
                                    new_ds_dict[tag] = 1
                            new_tag_freq[ds_key] = new_ds_dict
                        else:
                            for tag in cleaned_keywords:
                                new_tag_freq[tag] = tag_freq_dict.get(tag, 1)
                            break
                else:
                    new_tag_freq = {"dataset": {tag: 1 for tag in cleaned_keywords}}

                updated["ss_tag_frequency"] = json.dumps(new_tag_freq, ensure_ascii=False) if is_stringified else new_tag_freq

            # --- 2. Update ss_datasets ---
            if "ss_datasets" in updated:
                ds_val_raw = updated["ss_datasets"]
                is_ds_stringified = isinstance(ds_val_raw, str)
                try:
                    ds_list = json.loads(ds_val_raw) if is_ds_stringified else list(ds_val_raw)
                except Exception:
                    ds_list = []

                if isinstance(ds_list, list):
                    for dataset_item in ds_list:
                        if isinstance(dataset_item, dict):
                            # Check if this dataset container has a nested tag frequency map
                            for sub_k in ["tag_frequency", "ss_tag_frequency"]:
                                if sub_k in dataset_item:
                                    sub_dict = dataset_item[sub_k]
                                    if isinstance(sub_dict, str):
                                        try:
                                            sub_dict = json.loads(sub_dict)
                                        except Exception:
                                            sub_dict = {}

                                    if isinstance(sub_dict, dict):
                                        # Rebuild keeping frequencies intact
                                        new_sub_freq = {}
                                        for ds_k, ds_v in sub_dict.items():
                                            if isinstance(ds_v, dict):
                                                new_inner = {}
                                                for tag in cleaned_keywords:
                                                    if tag in ds_v:
                                                        new_inner[tag] = ds_v[tag]
                                                    else:
                                                        new_inner[tag] = 1
                                                new_sub_freq[ds_k] = new_inner
                                            else:
                                                for tag in cleaned_keywords:
                                                    new_sub_freq[tag] = ds_v.get(tag, 1) if isinstance(ds_v, dict) else 1
                                                break

                                        dataset_item[sub_k] = json.dumps(new_sub_freq, ensure_ascii=False) if isinstance(dataset_item[sub_k], str) else new_sub_freq

                    updated["ss_datasets"] = json.dumps(ds_list, ensure_ascii=False) if is_ds_stringified else ds_list

            self.updated_metadata = updated
            self.accept()

    def _apply_dark_style(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #080c14;
                color: #f8fafc;
                font-family: sans-serif;
            }
            QLabel#DialogTitle {
                font-size: 16px;
                font-weight: bold;
                color: #f8fafc;
            }
            QTabWidget::pane {
                border: 1px solid #1e293b;
                background-color: #0b0f19;
                border-radius: 6px;
            }
            QTabBar::tab {
                background-color: #131b2e;
                color: #94a3b8;
                padding: 8px 16px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #1e293b;
                color: #f8fafc;
                font-weight: bold;
            }
            QTextEdit {
                background-color: #05070a;
                color: #e2e8f0;
                border: 1px solid #1e293b;
                border-radius: 6px;
                padding: 8px;
                font-family: monospace;
                font-size: 12px;
            }
            
            /* --- Fancy Custom Scrollbars for Text Edits / Dialog --- */
            QScrollBar:vertical {
                border: none;
                background-color: #0b0f19;
                width: 10px;
                margin: 0px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background-color: #334155;
                min-height: 25px;
                border-radius: 5px;
                margin: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #475569;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                background: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }

            QScrollBar:horizontal {
                border: none;
                background-color: #0b0f19;
                height: 10px;
                margin: 0px;
                border-radius: 5px;
            }
            QScrollBar::handle:horizontal {
                background-color: #334155;
                min-width: 25px;
                border-radius: 5px;
                margin: 2px;
            }
            QScrollBar::handle:horizontal:hover {
                background-color: #475569;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
                background: none;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
            }

            /* --- Buttons --- */
            QPushButton#PrimaryButton {
                background-color: #3b82f6;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton#PrimaryButton:hover {
                background-color: #2563eb;
            }
            QPushButton#SecondaryButton {
                background-color: #1e293b;
                color: #cbd5e1;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
            }
            QPushButton#SecondaryButton:hover {
                background-color: #334155;
            }
        """)

class LeftToolsToolbar(QFrame):
    """Left toolbar frame housing metadata tools with inline/local QSS styling."""
    export_clicked = Signal()
    replace_clicked = Signal()
    edit_clicked = Signal()
    purge_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MetadataToolsFrame")
        self._setup_ui()
        self._apply_inline_styles()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 14, 10, 14)
        layout.setSpacing(10)

        title_label = QLabel("Metadata")
        title_label.setObjectName("ToolsSectionTitle")
        layout.addWidget(title_label)

        self.export_btn = QPushButton("Export")
        self.export_btn.setObjectName("ToolButton")
        self.export_btn.setToolTip("Export Metadata JSON")
        self.export_btn.clicked.connect(self.export_clicked.emit)

        self.replace_btn = QPushButton("Replace")
        self.replace_btn.setObjectName("ToolButton")
        self.replace_btn.setToolTip("Replace Metadata from JSON")
        self.replace_btn.clicked.connect(self.replace_clicked.emit)

        self.edit_btn = QPushButton("Edit")
        self.edit_btn.setObjectName("ToolButton")
        self.edit_btn.setToolTip("Edit Metadata Interactively")
        self.edit_btn.clicked.connect(self.edit_clicked.emit)

        self.purge_btn = QPushButton("Purge")
        self.purge_btn.setObjectName("ToolButton")
        self.purge_btn.setToolTip("Purge All Metadata Headers")
        self.purge_btn.clicked.connect(self.purge_clicked.emit)

        layout.addWidget(self.export_btn)
        layout.addWidget(self.replace_btn)
        layout.addWidget(self.edit_btn)
        layout.addWidget(self.purge_btn)
        layout.addStretch()

    def _apply_inline_styles(self):
        self.setStyleSheet("""
            #MetadataToolsFrame {
                background-color: #0b0f19;
                border: 1px solid #1e293b;
                border-radius: 10px;
                min-width: 95px;
                max-width: 105px;
            }
            #ToolsSectionTitle {
                color: #94a3b8;
                font-size: 11px;
                font-weight: bold;
                padding: 4px 6px;
                text-transform: uppercase;
                margin-bottom: 4px;
            }
            #ToolButton {
                background-color: #131b2e;
                color: #f8fafc;
                border: 1px solid #1e293b;
                border-radius: 8px;
                padding: 8px 6px;
                font-size: 12px;
                font-weight: 600;
                text-align: center;
            }
            #ToolButton:hover {
                background-color: #1a233a;
                border: 1px solid #334155;
            }
        """)

