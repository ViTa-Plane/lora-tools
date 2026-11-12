# version = 1.0.14

import sys
import os
import json
import struct
import tempfile
import subprocess
import cv2
from copy import deepcopy
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QLabel, QFileDialog, QScrollArea,
    QFrame, QSplitter, QTextEdit, QTreeWidget, QTreeWidgetItem,
    QGridLayout, QListWidget, QListWidgetItem, QMessageBox, QHeaderView,
    QTabWidget, QMenu, QAbstractItemView, QSizePolicy, QToolButton, QStyle
)
from PySide6.QtCore import Qt, Signal, QSize, QThread, QObject, QFileSystemWatcher, QTimer, QUrl
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QKeySequence, QShortcut, QClipboard, QIcon, QPen, \
    QDesktopServices, QMouseEvent

# ==========================================
# 0. Settings & Cache Persistence Helpers
# ==========================================

SETTINGS_PATH = Path("settings.json")
CACHE_DIR = Path(tempfile.gettempdir()) / "lora_tools_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def load_settings() -> dict:
    if SETTINGS_PATH.exists():
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_settings(settings: dict):
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except Exception:
        pass


def get_cache_file_path(folder_path: str) -> Path:
    folder_hash = abs(hash(str(folder_path)))
    return CACHE_DIR / f"cache_{folder_hash}.json"


def load_folder_cache(folder_path: str) -> dict:
    cache_file = get_cache_file_path(folder_path)
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_folder_cache(folder_path: str, cache_data: dict):
    cache_file = get_cache_file_path(folder_path)
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, indent=2)
    except Exception:
        pass


def open_containing_folder(file_path: str):
    try:
        path_obj = Path(file_path)
        if sys.platform == "win32":
            subprocess.run(["explorer.exe", "/select,", str(path_obj.resolve())])
        elif sys.platform == "darwin":
            subprocess.run(
                ["osascript", "-e", f'tell application "Finder" to reveal POSIX file "{path_obj.resolve()}"'])
            subprocess.run(["osascript", "-e", 'tell application "Finder" to activate'])
        else:
            folder_path = path_obj.parent
            subprocess.run(["xdg-open", str(folder_path)])
    except Exception as e:
        print(f"Failed to open and select file: {e}")


# ==========================================
# 1. Safetensors Metadata & Thumbnail Logic
# ==========================================


def read_safetensors_metadata(filepath: Path) -> dict:
    """
    Reads only the JSON header of a .safetensors file.
    Format: [8-byte uint64 little-endian header_size][header_json_bytes][tensor_data...]
    """
    try:
        with open(filepath, "rb") as f:
            header_size_bytes = f.read(8)
            if len(header_size_bytes) < 8:
                return {}
            header_size = struct.unpack("<Q", header_size_bytes)[0]
            if header_size > 50 * 1024 * 1024:
                return {}
            header_bytes = f.read(header_size)
            header_data = json.loads(header_bytes.decode("utf-8"))
            return header_data.get("__metadata__", {})
    except Exception:
        return {}


def generate_video_thumbnail(video_path: Path) -> Path | None:
    """Extracts the first frame of a video in the background thread via OpenCV."""
    thumb_cache_path = video_path.with_suffix(video_path.suffix + ".thumb.jpg")

    if thumb_cache_path.exists():
        return thumb_cache_path

    try:
        cap = cv2.VideoCapture(str(video_path))
        cap.set(cv2.CAP_PROP_POS_FRAMES, 5)  # Jump 5 frames in for a better preview
        success, frame = cap.read()

        if not success:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            success, frame = cap.read()

        if success:
            cv2.imwrite(str(thumb_cache_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            cap.release()
            return thumb_cache_path

        cap.release()
    except Exception:
        pass

    return None


MEDIA_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".jfif", ".mp4", ".webm", ".preview.png"}


def find_thumbnail(safetensor_path: Path, fast_mode: bool = False) -> Path | None:
    stem = safetensor_path.stem
    parent = safetensor_path.parent

    try:
        candidates = list(parent.glob(f"{stem}.*"))

        # Priority 1: Look for a static image first (instant)
        for candidate in candidates:
            if candidate.is_file() and candidate.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif",
                                                                    ".jfif"}:
                return candidate

        # If fast_mode is enabled, skip video extraction during bulk scan to prevent lagging
        if fast_mode:
            return None

        # Priority 2: Look for video files (.mp4, .webm) and extract a thumbnail
        for candidate in candidates:
            if candidate.is_file() and candidate.suffix.lower() in {".mp4", ".webm"}:
                extracted_thumb = generate_video_thumbnail(candidate)
                if extracted_thumb and extracted_thumb.exists():
                    return extracted_thumb

    except Exception:
        pass

    return None


class FolderScannerWorker(QObject):
    item_found = Signal(dict)
    finished = Signal(int)

    def __init__(self, folder_path: str):
        super().__init__()
        self.folder_path = Path(folder_path)
        self._is_running = True

    def stop(self):
        self._is_running = False

    def run(self):
        if not self.folder_path.exists():
            self.finished.emit(0)
            return

        cache_data = load_folder_cache(str(self.folder_path))
        disk_files = sorted(self.folder_path.rglob("*.safetensors"))
        emitted_paths = set()
        count = 0

        # ---------------------------------------------------------
        # PHASE 1: Prioritize fast cache display for instant cards
        # ---------------------------------------------------------
        for file_path in disk_files:
            if not self._is_running:
                break

            str_path = str(file_path.resolve())
            cached_entry = cache_data.get(str_path)

            if cached_entry:
                try:
                    current_mtime = file_path.stat().st_mtime
                    if cached_entry.get("mtime") == current_mtime:
                        item_data = {
                            "name": file_path.stem,
                            "path": str_path,
                            "size_mb": cached_entry["size_mb"],
                            "thumbnail": cached_entry["thumbnail"],
                            "metadata": cached_entry["metadata"],
                            "original_metadata": deepcopy(cached_entry["metadata"]),
                            "is_dirty": False,
                        }
                        self.item_found.emit(item_data)
                        emitted_paths.add(str_path)
                        count += 1
                except Exception:
                    pass

        # ---------------------------------------------------------
        # PHASE 2: Background pass for new, modified, or uncached files
        # ---------------------------------------------------------
        new_cache_data = dict(cache_data)
        updated = False

        for file_path in disk_files:
            if not self._is_running:
                break

            str_path = str(file_path.resolve())
            try:
                current_mtime = file_path.stat().st_mtime
                file_size = file_path.stat().st_size
            except Exception:
                continue

            cached_entry = cache_data.get(str_path)
            if cached_entry and cached_entry.get("mtime") == current_mtime:
                continue

            updated = True
            # Use fast_mode=True to skip heavy video decoding checks during bulk scans
            thumb_path = find_thumbnail(file_path, fast_mode=True)
            metadata = read_safetensors_metadata(file_path)
            size_mb = round(file_size / (1024 * 1024), 2)

            new_cache_data[str_path] = {
                "mtime": current_mtime,
                "size_mb": size_mb,
                "thumbnail": str(thumb_path) if thumb_path else None,
                "metadata": metadata
            }

            item_data = {
                "name": file_path.stem,
                "path": str_path,
                "size_mb": size_mb,
                "thumbnail": str(thumb_path) if thumb_path else None,
                "metadata": metadata,
                "original_metadata": deepcopy(metadata),
                "is_dirty": False,
            }

            if str_path not in emitted_paths:
                self.item_found.emit(item_data)
                count += 1

        if updated:
            save_folder_cache(str(self.folder_path), new_cache_data)

        self.finished.emit(count)


# ==========================================
# 2. Custom UI Components
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


# ==========================================
# 3. Main Application Window
# ==========================================

class LoraToolsWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Lora Tools — Safetensors Metadata Viewer")
        self.resize(1560, 920)

        icon_path = Path("assets/icon.png")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.scanner_thread: QThread | None = None
        self.scanner_worker: FolderScannerWorker | None = None

        self.file_watcher = QFileSystemWatcher(self)
        self.file_watcher.directoryChanged.connect(self._on_directory_changed)

        self._setup_ui()
        self._setup_shortcuts()
        self._load_stylesheet()

        settings = load_settings()
        last_dir = settings.get("last_directory")
        if last_dir and Path(last_dir).exists():
            self.path_input.setText(last_dir)
            self._start_scan(last_dir)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Top Toolbar ---
        toolbar = QFrame()
        toolbar.setObjectName("TopToolbar")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(20, 12, 20, 12)
        tb_layout.setSpacing(14)

        app_label = ClickableBrandLabel("⚡ LoRa Tools")
        app_label.setObjectName("BrandTitle")

        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Select folder containing .safetensors files...")
        self.path_input.returnPressed.connect(self._scan_current_path)

        browse_btn = QPushButton("Browse Folders")
        browse_btn.setObjectName("PrimaryButton")
        browse_btn.clicked.connect(self._browse_folder)

        tb_layout.addWidget(app_label)
        tb_layout.addSpacing(6)
        tb_layout.addWidget(self.path_input, stretch=1)
        tb_layout.addWidget(browse_btn)

        main_layout.addWidget(toolbar)

        # --- Main Splitter ---
        splitter = QSplitter(Qt.Horizontal)

        # Left Container for Search Bar + Grid Scroll Area
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(16, 16, 16, 16)
        left_layout.setSpacing(10)

        # Filter Toolbar placed right above the grid with constant fixed width
        filter_layout = QHBoxLayout()
        filter_layout.setAlignment(Qt.AlignLeft)  # Dock elements to the left

        self.search_input = ClearableLineEdit()
        self.search_input.setPlaceholderText("🔍 Filter by name or tag...")
        self.search_input.setFixedWidth(300)
        self.search_input.textChanged.connect(self._on_search_changed)

        filter_layout.addWidget(self.search_input)
        left_layout.addLayout(filter_layout)

        # Scroll Area & Grid Setup
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setObjectName("GridScrollArea")
        self.scroll_area.verticalScrollBar().setStyleSheet("""
            QScrollBar:vertical { border: none; background-color: #0b0f19; width: 12px; margin: 0px; }
            QScrollBar::handle:vertical { background-color: #334155; min-height: 25px; border-radius: 6px; margin: 2px; }
            QScrollBar::handle:vertical:hover { background-color: #475569; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; background: none; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
        """)

        self.grid_widget = ResponsiveGridWidget()
        self.scroll_area.setWidget(self.grid_widget)
        left_layout.addWidget(self.scroll_area, stretch=1)

        self.inspector = MetadataInspector()

        self.grid_widget.card_selected.connect(self.inspector.display_lora)
        self.inspector.export_requested.connect(self._export_current_metadata_json)

        splitter.addWidget(left_container)
        splitter.addWidget(self.inspector)
        splitter.setSizes([980, 580])

        main_layout.addWidget(splitter, stretch=1)

        # --- Footer Status Bar ---
        footer_frame = QFrame()
        footer_frame.setObjectName("FooterBar")
        footer_frame.setStyleSheet("""
            #FooterBar {
                background-color: #080c14;
                border-top: 1px solid #1e293b;
            }
        """)
        footer_layout = QHBoxLayout(footer_frame)
        footer_layout.setContentsMargins(16, 8, 16, 8)

        self.count_label = QLabel("0 items")
        self.count_label.setObjectName("SubtleText")

        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("SubtleText")

        footer_layout.addWidget(self.count_label)
        footer_layout.addStretch()
        footer_layout.addWidget(self.status_label)

        main_layout.addWidget(footer_frame)

    def _setup_shortcuts(self):
        self.undo_shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        self.undo_shortcut.activated.connect(self.inspector.undo)

        self.redo_shortcut = QShortcut(QKeySequence("Ctrl+Shift+Z"), self)
        self.redo_shortcut.activated.connect(self.inspector.redo)

    def _browse_folder(self):
        settings = load_settings()
        default_dir = settings.get("last_directory", "")
        if not default_dir or not Path(default_dir).exists():
            default_dir = ""

        folder = QFileDialog.getExistingDirectory(self, "Select LoRa Directory", default_dir)
        if folder:
            self.path_input.setText(folder)
            save_settings({"last_directory": folder})
            self._start_scan(folder)

    def _scan_current_path(self):
        folder = self.path_input.text().strip()
        if folder and Path(folder).exists():
            save_settings({"last_directory": folder})
            self._start_scan(folder)

    def _start_scan(self, folder: str):
        if self.scanner_thread and self.scanner_thread.isRunning():
            self.scanner_worker.stop()
            self.scanner_thread.quit()
            self.scanner_thread.wait()

        folder_path = Path(folder)
        if not folder_path.exists():
            return

        existing_paths = self.file_watcher.directories()
        if existing_paths:
            self.file_watcher.removePaths(existing_paths)

        dirs_to_watch = [str(folder_path)] + [str(p) for p in folder_path.rglob("*") if p.is_dir()]
        self.file_watcher.addPaths(dirs_to_watch)

        self.grid_widget.clear_cards()
        self.status_label.setText("Loading Cache & Scanning...")
        self.count_label.setText("0 items")

        self.scanner_thread = QThread()
        self.scanner_worker = FolderScannerWorker(folder)
        self.scanner_worker.moveToThread(self.scanner_thread)

        self.scanner_thread.started.connect(self.scanner_worker.run)
        self.scanner_worker.item_found.connect(self.grid_widget.add_lora)
        self.scanner_worker.finished.connect(self._on_scan_finished)
        self.scanner_worker.finished.connect(self.scanner_thread.quit)

        self.scanner_thread.start()

    def _on_scan_finished(self, count: int):
        self.status_label.setText(f"{count} LoRas loaded successfully")
        self.count_label.setText(f"{len(self.grid_widget.cards)} items")
        if self.search_input.text():
            self.grid_widget.filter_cards(self.search_input.text())

    def _on_directory_changed(self, path: str):
        folder = self.path_input.text().strip()
        if folder and Path(folder).exists():
            self.status_label.setText("Changes detected, refreshing...")
            self._start_scan(folder)

    def _on_search_changed(self, text: str):
        self.grid_widget.filter_cards(text)
        total = len(self.grid_widget.cards)
        visible = len(self.grid_widget.visible_cards)
        if text.strip():
            self.count_label.setText(f"{visible} / {total} items")
        else:
            self.count_label.setText(f"{total} items")

    def _export_current_metadata_json(self):
        data = self.inspector.current_data
        if not data:
            return

        default_path = Path(data["path"]).with_name(f"{Path(data['path']).stem}_raw_metadata.json")
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Export Metadata JSON", str(default_path), "JSON Files (*.json)"
        )
        if save_path:
            try:
                with open(save_path, "w", encoding="utf-8") as f:
                    json.dump(data["metadata"], f, indent=2)

                if data["metadata"] == data["original_metadata"]:
                    data["is_dirty"] = False

                self.inspector._refresh_inspector_view()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export metadata:\n{str(e)}")

    def _load_stylesheet(self):
        qss_path = Path("styles.qss")
        if qss_path.exists():
            try:
                with open(qss_path, "r", encoding="utf-8") as f:
                    self.setStyleSheet(f.read())
            except Exception as e:
                print(f"Failed to load styles.qss: {e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = LoraToolsWindow()
    window.show()
    sys.exit(app.exec())