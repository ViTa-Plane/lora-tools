# version = 1.0.27

import tempfile
import sys
import subprocess
import json
from pathlib import Path

# ==========================================
# Settings & Cache Persistence Helpers
# ==========================================

SETTINGS_PATH = Path("src/settings.json")
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

