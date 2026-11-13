# version = 1.0.27

import struct
import cv2
from copy import deepcopy
import json
from pathlib import Path
from PySide6.QtCore import Signal, QObject

from .helpers import load_folder_cache, save_folder_cache

# ==========================================
# Metadata & Thumbnail Logic
# ==========================================

MEDIA_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".jfif", ".mp4", ".webm", ".preview.png"}

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
