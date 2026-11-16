# version = 1.0.30

import json
from pathlib import Path
from PySide6.QtWidgets import QFileDialog, QMessageBox,QDialog

from src.ui import MetadataEditDialog, MetadataAddDialog

try:
    import torch
    from safetensors import safe_open
    from safetensors.torch import save_file as safe_write
except ImportError:
    pass


def _safetensors_purge_operation(input_path: str | Path, output_path: str | Path):
    input_path = Path(input_path)
    output_path = Path(output_path)
    tensors = {}
    with safe_open(str(input_path), framework="pt", device="cpu") as f:
        for key in f.keys():
            tensors[key] = f.get_tensor(key)
    safe_write(tensors, str(output_path), metadata={})


def _safetensors_replace_operation(input_path: str | Path, new_metadata: dict, output_path: str | Path):
    """Safely writes tensors and updated metadata to a new output safetensors file."""
    input_path = Path(input_path)
    output_path = Path(output_path)
    clean_metadata = {str(k): str(v) for k, v in new_metadata.items()}

    tensors = {}
    with safe_open(str(input_path), framework="pt", device="cpu") as f:
        for key in f.keys():
            tensors[key] = f.get_tensor(key)

    safe_write(tensors, str(output_path), metadata=clean_metadata)


def purge_metadata_action(parent_window, inspector):
    data = inspector.current_data
    if not data:
        QMessageBox.warning(parent_window, "Warning", "No LoRa selected to purge metadata from.")
        return

    source_path = Path(data.get("path", ""))
    if not source_path.exists():
        QMessageBox.warning(parent_window, "Error", "Source file path not found.")
        return

    default_output = source_path.with_name(f"{source_path.stem}_purged.safetensors")
    save_path, _ = QFileDialog.getSaveFileName(
        parent_window, "Save Purged Safetensors", str(default_output), "Safetensors Files (*.safetensors)"
    )

    if save_path:
        try:
            _safetensors_purge_operation(source_path, save_path)
            QMessageBox.information(
                parent_window,
                "Success",
                f"Metadata successfully purged!\nSaved safely to:\n{save_path}\n\n(Original file was left untouched)."
            )
        except Exception as e:
            QMessageBox.critical(parent_window, "Error", f"Failed during purge operation:\n{str(e)}")

def replace_metadata_action(parent_window, inspector, edited_metadata: dict):
    """Executes replacement using the provided edited metadata dictionary as the source."""
    data = inspector.current_data
    if not data:
        QMessageBox.warning(parent_window, "Warning", "No LoRa selected to replace metadata for.")
        return

    source_path = Path(data.get("path", ""))
    if not source_path.exists():
        QMessageBox.warning(parent_window, "Error", "Source file path not found.")
        return

    default_output = source_path.with_name(f"{source_path.stem}_replaced.safetensors")
    save_path, _ = QFileDialog.getSaveFileName(
        parent_window, "Save Replaced Safetensors", str(default_output), "Safetensors Files (*.safetensors)"
    )

    if save_path:
        try:
            _safetensors_replace_operation(source_path, edited_metadata, save_path)
            QMessageBox.information(
                parent_window,
                "Success",
                f"Metadata replaced successfully!\nSaved safely to:\n{save_path}\n\n(Original file was left untouched)."
            )
        except Exception as e:
            QMessageBox.critical(parent_window, "Error", f"Failed during metadata replacement:\n{str(e)}")

def add_metadata_action(parent_window, inspector):
    data = inspector.current_data
    if not data:
        QMessageBox.warning(parent_window, "Warning", "No LoRa selected to add metadata to.")
        return

    current_meta = data.get("metadata", {})
    dialog = MetadataAddDialog(current_meta)
    if dialog.exec() == QDialog.Accepted and dialog.updated_metadata is not None:
        # Pass edited metadata dictionary directly into the replace function workflow
        replace_metadata_action(inspector, dialog.updated_metadata)
