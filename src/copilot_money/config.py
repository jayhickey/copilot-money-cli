from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from pydantic import BaseModel, Field


class SafariPermissionError(Exception):
    """Raised when Safari data cannot be accessed due to macOS permissions."""

    pass


CONFIG_DIR = Path.home() / ".config" / "copilot-money"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Arc browser's LevelDB storage for Copilot Money
ARC_LEVELDB_PATH = (
    Path.home() / "Library" / "Application Support" / "Arc" / "User Data" / "Default"
    / "IndexedDB" / "https_app.copilot.money_0.indexeddb.leveldb"
)
CHROME_LEVELDB_PATH = (
    Path.home() / "Library" / "Application Support" / "Google" / "Chrome" / "Default"
    / "IndexedDB" / "https_app.copilot.money_0.indexeddb.leveldb"
)
SAFARI_LOCALSTORAGE_DIR = Path.home() / "Library" / "Safari" / "LocalStorage"
FIREFOX_PROFILES_DIR = (
    Path.home() / "Library" / "Application Support" / "Firefox" / "Profiles"
)

TOKEN_REGEX = re.compile(r"AMf-[A-Za-z0-9_-]{100,}")


class CopilotConfig(BaseModel):
    refresh_token: Optional[str] = None
    access_token: Optional[str] = None
    expires_at: Optional[float] = Field(default=None, description="Unix epoch seconds")
    source: Optional[str] = None
    source_path: Optional[str] = None

    def is_access_token_valid(self) -> bool:
        if not self.access_token or not self.expires_at:
            return False
        now = datetime.now(timezone.utc).timestamp()
        return now < (self.expires_at - 60)


def ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _extract_refresh_token_from_files(file_paths: Iterable[Path]) -> Optional[str]:
    for file_path in file_paths:
        if not file_path.is_file():
            continue
        try:
            result = subprocess.run(
                ["strings", str(file_path)],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            continue
        match = TOKEN_REGEX.search(result.stdout)
        if match:
            return match.group(0)
    return None


def _leveldb_files(leveldb_path: Path) -> list[Path]:
    if not leveldb_path.exists():
        return []
    files: list[Path] = []
    for pattern in ("*.log", "*.ldb"):
        files.extend(sorted(leveldb_path.glob(pattern)))
    return files


def _firefox_idb_paths() -> list[Path]:
    if not FIREFOX_PROFILES_DIR.exists():
        return []
    return sorted(
        FIREFOX_PROFILES_DIR.glob(
            "*/storage/default/https+++app.copilot.money/idb"
        )
    )


def _firefox_idb_files() -> list[Path]:
    files: list[Path] = []
    for idb_path in _firefox_idb_paths():
        for file_path in idb_path.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix in {".sqlite", ".sqlite-wal", ".sqlite-shm", ".log", ".ldb"}:
                files.append(file_path)
    return files


def get_token_from_arc() -> Optional[str]:
    """Extract the refresh token from Arc browser's LevelDB storage."""
    return _extract_refresh_token_from_files(_leveldb_files(ARC_LEVELDB_PATH))


def get_token_from_chrome() -> Optional[str]:
    """Extract the refresh token from Chrome's LevelDB storage."""
    return _extract_refresh_token_from_files(_leveldb_files(CHROME_LEVELDB_PATH))


def get_token_from_safari() -> Optional[str]:
    """Attempt to extract the refresh token from Safari local storage.

    Raises:
        SafariPermissionError: If macOS denies access to Safari data.
    """
    if not SAFARI_LOCALSTORAGE_DIR.exists():
        return None

    # Python's glob() silently returns empty list on permission denied,
    # so we need to explicitly check read access
    if not os.access(SAFARI_LOCALSTORAGE_DIR, os.R_OK):
        raise SafariPermissionError(
            "macOS requires Full Disk Access to read Safari data. "
            f"The {SAFARI_LOCALSTORAGE_DIR} directory is protected by macOS privacy controls.\n\n"
            "To fix this:\n"
            "1. Open System Settings → Privacy & Security → Full Disk Access\n"
            "2. Click the + button and add your terminal app\n"
            "3. Restart your terminal and try again"
        )

    safari_files = sorted(SAFARI_LOCALSTORAGE_DIR.glob("*copilot.money*"))
    return _extract_refresh_token_from_files(safari_files)


def get_token_from_firefox() -> Optional[str]:
    """Extract the refresh token from Firefox profile IndexedDB storage."""
    return _extract_refresh_token_from_files(_firefox_idb_files())


def get_token_auto() -> tuple[Optional[str], Optional[str]]:
    """Tries Arc → Chrome → Safari → Firefox, returns first success."""
    arc_token = get_token_from_arc()
    if arc_token:
        return arc_token, "arc"
    chrome_token = get_token_from_chrome()
    if chrome_token:
        return chrome_token, "chrome"
    try:
        safari_token = get_token_from_safari()
        if safari_token:
            return safari_token, "safari"
    except SafariPermissionError:
        # Skip Safari if permission denied during auto-detection
        pass
    firefox_token = get_token_from_firefox()
    if firefox_token:
        return firefox_token, "firefox"
    return None, None


def get_source_path(source: Optional[str]) -> Optional[str]:
    if source == "arc":
        return str(ARC_LEVELDB_PATH)
    if source == "chrome":
        return str(CHROME_LEVELDB_PATH)
    if source == "safari":
        return str(SAFARI_LOCALSTORAGE_DIR)
    if source == "firefox":
        paths = _firefox_idb_paths()
        return str(paths[0]) if paths else None
    return None


def load_config() -> CopilotConfig:
    """Load config, auto-fetching refresh token if needed."""
    config = CopilotConfig()
    
    # Try loading from config file first
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text())
            config = CopilotConfig.model_validate(data)
        except json.JSONDecodeError:
            pass
    
    # If no refresh token, try to get it from browsers
    if not config.refresh_token:
        token, source = get_token_auto()
        if token:
            config.refresh_token = token
            config.source = source
            config.source_path = get_source_path(source)
            save_config(config)
    
    return config


def save_config(config: CopilotConfig) -> None:
    ensure_config_dir()
    CONFIG_FILE.write_text(config.model_dump_json(indent=2))
