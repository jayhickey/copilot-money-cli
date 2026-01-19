"""Tests for config module."""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from copilot_money.config import (
    CopilotConfig,
    TOKEN_REGEX,
    _extract_refresh_token_from_files,
    get_source_path,
    save_config,
)


class TestTokenRegex:
    """Test the Firebase refresh token regex pattern."""

    def test_matches_valid_token(self):
        # Firebase refresh tokens start with AMf- followed by base64-like chars
        token = "AMf-" + "a" * 100
        assert TOKEN_REGEX.search(token) is not None

    def test_matches_token_with_mixed_chars(self):
        token = "AMf-vCh8cHHRHi_abc123XYZ-_" + "x" * 80
        assert TOKEN_REGEX.search(token) is not None

    def test_rejects_short_token(self):
        token = "AMf-" + "a" * 50  # Too short
        assert TOKEN_REGEX.search(token) is None

    def test_rejects_wrong_prefix(self):
        token = "ABC-" + "a" * 100
        assert TOKEN_REGEX.search(token) is None

    def test_extracts_token_from_text(self):
        text = f'some data before AMf-{"x" * 100} some data after'
        match = TOKEN_REGEX.search(text)
        assert match is not None
        assert match.group().startswith("AMf-")


class TestCopilotConfig:
    """Test the CopilotConfig model."""

    def test_default_values(self):
        config = CopilotConfig()
        assert config.refresh_token is None
        assert config.access_token is None
        assert config.expires_at is None
        assert config.source is None
        assert config.source_path is None

    def test_with_values(self):
        config = CopilotConfig(
            refresh_token="test_token",
            source="arc",
            source_path="/some/path",
        )
        assert config.refresh_token == "test_token"
        assert config.source == "arc"
        assert config.source_path == "/some/path"

    def test_serialization(self):
        config = CopilotConfig(refresh_token="test", source="chrome")
        data = config.model_dump()
        assert data["refresh_token"] == "test"
        assert data["source"] == "chrome"

    def test_access_token_validity(self):
        now = datetime.now(timezone.utc).timestamp()
        config = CopilotConfig(access_token="token", expires_at=now + 120)
        assert config.is_access_token_valid()

        config.expires_at = now + 30
        assert not config.is_access_token_valid()


class TestSaveAndLoadConfig:
    """Test config file save/load."""

    def test_save_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "copilot-money"
            config_file = config_dir / "config.json"

            with patch("copilot_money.config.CONFIG_DIR", config_dir), \
                 patch("copilot_money.config.CONFIG_FILE", config_file):
                
                # Save config
                original = CopilotConfig(
                    refresh_token="my_token",
                    source="manual",
                )
                save_config(original)

                # Verify file exists
                assert config_file.exists()

                # Load and verify
                with open(config_file) as f:
                    data = json.load(f)
                assert data["refresh_token"] == "my_token"
                assert data["source"] == "manual"


class TestGetSourcePath:
    """Test source path resolution."""

    def test_arc_source(self):
        path = get_source_path("arc")
        assert path is not None
        assert "Arc" in path

    def test_chrome_source(self):
        path = get_source_path("chrome")
        assert path is not None
        assert "Chrome" in path

    def test_safari_source(self):
        path = get_source_path("safari")
        assert path is not None
        assert "Safari" in path

    def test_manual_source(self):
        path = get_source_path("manual")
        assert path is None

    def test_unknown_source(self):
        path = get_source_path("unknown")
        assert path is None


class TestExtractTokenFromFiles:
    """Test token extraction from files."""

    def test_extracts_token_from_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file with a token
            token = "AMf-" + "x" * 100
            test_file = Path(tmpdir) / "test.log"
            test_file.write_text(f"some prefix {token} some suffix")

            result = _extract_refresh_token_from_files([test_file])
            assert result == token

    def test_returns_none_for_no_token(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.log"
            test_file.write_text("no token here")

            result = _extract_refresh_token_from_files([test_file])
            assert result is None

    def test_returns_none_for_missing_file(self):
        result = _extract_refresh_token_from_files([Path("/nonexistent/file")])
        assert result is None

    def test_returns_none_for_empty_list(self):
        result = _extract_refresh_token_from_files([])
        assert result is None
