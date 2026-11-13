# version = 1.0.33

import sys
import json
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QLabel, QFileDialog, QScrollArea,
    QFrame, QSplitter, QMessageBox, QDialog
)
from PySide6.QtCore import Qt, QThread, QFileSystemWatcher
from PySide6.QtGui import  QKeySequence, QShortcut, QIcon


from src import thumbnails, ui, helpers, tools
from src.ui import LeftToolsToolbar, MetadataEditDialog


# ==========================================
# Main Application Window
# ==========================================

class LoraToolsWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Lora Tools — Safetensors Metadata Viewer & Editor")
        self.resize(1560, 920)

        icon_path = Path("assets/icon.png")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.scanner_thread: QThread | None = None
        self.scanner_worker: thumbnails.FolderScannerWorker | None = None

        self.file_watcher = QFileSystemWatcher(self)
        self.file_watcher.directoryChanged.connect(self._on_directory_changed)

        self._setup_ui()
        self._setup_shortcuts()
        self._load_stylesheet()

        settings = helpers.load_settings()
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

        app_label = ui.ClickableBrandLabel("⚡ LoRa Tools")
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

        # Left Container
        left_container = QWidget()
        left_main_layout = QVBoxLayout(left_container)
        left_main_layout.setContentsMargins(16, 16, 16, 16)
        left_main_layout.setSpacing(10)

        # Content layout containing the Left Toolbar + Thumbnails Grid Side-by-Side
        grid_content_layout = QHBoxLayout()
        grid_content_layout.setContentsMargins(0, 0, 0, 0)
        grid_content_layout.setSpacing(12)

        # Instantiate and configure Left Tools Toolbar
        self.left_toolbar = LeftToolsToolbar(self)

        # Connect Toolbar signals to src/tools.py functions
        self.left_toolbar.export_clicked.connect(self._export_current_metadata_json)
        self.left_toolbar.replace_clicked.connect(self._handle_replace_from_json_file)
        self.left_toolbar.edit_clicked.connect(self._open_metadata_editor_dialog)
        self.left_toolbar.purge_clicked.connect(
            lambda: tools.purge_metadata_action(self, self.inspector)
        )

        grid_content_layout.addWidget(self.left_toolbar)

        # Right side sub-layout containing Filter Box + Scroll Area Grid
        right_grid_layout = QVBoxLayout()
        right_grid_layout.setContentsMargins(0, 0, 0, 0)
        right_grid_layout.setSpacing(10)

        # Filter Toolbar aligned to the right/top of the grid
        filter_layout = QHBoxLayout()
        filter_layout.setAlignment(Qt.AlignRight)  # Align filter box to the right matching grid edge

        self.search_input = ui.ClearableLineEdit()
        self.search_input.setPlaceholderText("🔍 Filter by name or tag...")
        self.search_input.setFixedWidth(300)
        self.search_input.textChanged.connect(self._on_search_changed)

        filter_layout.addWidget(self.search_input)
        right_grid_layout.addLayout(filter_layout)

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

        self.grid_widget = ui.ResponsiveGridWidget()
        self.scroll_area.setWidget(self.grid_widget)
        right_grid_layout.addWidget(self.scroll_area, stretch=1)

        grid_content_layout.addLayout(right_grid_layout, stretch=1)
        left_main_layout.addLayout(grid_content_layout, stretch=1)

        self.inspector = ui.MetadataInspector()
        # self.grid_widget.card_selected.connect(self.inspector.display_lora)
        self.grid_widget.card_selected.connect(self._on_card_selected_action)
        self.inspector.export_requested.connect(self._export_current_metadata_json)

        splitter.addWidget(left_container)
        splitter.addWidget(self.inspector)
        splitter.setSizes([1050, 500])

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

    def _on_card_selected_action(self, data):
        """Displays the selected LoRa in the inspector and updates the footer count label."""
        self.inspector.display_lora(data)
        if data:
            self.count_label.setText("1 item")

    def _setup_shortcuts(self):
        self.undo_shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        self.undo_shortcut.activated.connect(self.inspector.undo)

        self.redo_shortcut = QShortcut(QKeySequence("Ctrl+Shift+Z"), self)
        self.redo_shortcut.activated.connect(self.inspector.redo)

    def _browse_folder(self):
        settings = helpers.load_settings()
        default_dir = settings.get("last_directory", "")
        if not default_dir or not Path(default_dir).exists():
            default_dir = ""

        folder = QFileDialog.getExistingDirectory(self, "Select LoRa Directory", default_dir)
        if folder:
            self.path_input.setText(folder)
            helpers.save_settings({"last_directory": folder})
            self._start_scan(folder)

    def _scan_current_path(self):
        folder = self.path_input.text().strip()
        if folder and Path(folder).exists():
            helpers.save_settings({"last_directory": folder})
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
        self.scanner_worker = thumbnails.FolderScannerWorker(folder)
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
        qss_path = Path("src/styles.qss")
        if qss_path.exists():
            try:
                with open(qss_path, "r", encoding="utf-8") as f:
                    self.setStyleSheet(f.read())
            except Exception as e:
                print(f"Failed to load styles.qss: {e}")

    def _on_card_selected_action(self, data):
        """Displays selected model in inspector and updates footer count to 1 item."""
        self.inspector.display_lora(data)
        if data:
            self.count_label.setText("1 item")

    def _open_metadata_editor_dialog(self):
        """Opens the interactive dark mode tabbed metadata editor dialog."""
        data = self.inspector.current_data
        if not data:
            QMessageBox.warning(self, "Warning", "No LoRa selected to edit metadata.")
            return

        current_meta = data.get("metadata", {})
        dialog = MetadataEditDialog(current_meta, self)
        if dialog.exec() == QDialog.Accepted and dialog.updated_metadata is not None:
            # Pass edited metadata dictionary directly into the replace function workflow
            tools.replace_metadata_action(self, self.inspector, dialog.updated_metadata)

    def _handle_replace_from_json_file(self):
        """Allows replacing metadata by picking an external JSON source file."""
        data = self.inspector.current_data
        if not data:
            QMessageBox.warning(self, "Warning", "No LoRa selected to replace metadata for.")
            return

        json_file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Replacement Metadata JSON", "", "JSON Files (*.json)"
        )
        if json_file_path:
            try:
                with open(json_file_path, "r", encoding="utf-8") as f:
                    file_meta = json.load(f)
                tools.replace_metadata_action(self, self.inspector, file_meta)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load JSON file:\n{str(e)}")


if __name__ == "__main__":
    # print(f"v {version}")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = LoraToolsWindow()
    window.show()
    sys.exit(app.exec())