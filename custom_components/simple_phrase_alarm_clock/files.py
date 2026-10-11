"""Blocking file operations for the generated sentence files.

Everything here is blocking I/O: call it with hass.async_add_executor_job().
No Home Assistant imports.
"""

from __future__ import annotations

from datetime import datetime
import logging
import os
import shutil

from .const import (
    CONFIG_SENTENCES_FILENAME,
    LANGUAGE,
    S2P_SENTENCES_FILENAME,
    S2P_SHARE_ROOT,
)
from .sentences import (
    merge_into_share,
    render_config_file,
    strip_from_share,
)

_LOGGER = logging.getLogger(__name__)


def _read(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except FileNotFoundError:
        return None


def _backup(path: str) -> None:
    """Keep the previous version next to the file, never overwrite it."""
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        return
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = f"{path}.{stamp}.bak"
    shutil.copy2(path, backup)
    _LOGGER.info("Kept the previous version as %s", backup)


def _write_atomic(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = f"{path}.tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(temp, path)


def config_sentences_path(config_dir: str, language: str = LANGUAGE) -> str:
    """Return the path of the file Assist reads."""
    return os.path.join(
        config_dir, "custom_sentences", language, CONFIG_SENTENCES_FILENAME
    )


def share_sentences_path(
    language: str = LANGUAGE, share_root: str = S2P_SHARE_ROOT
) -> str:
    """Return the path of the file Speech-to-Phrase reads."""
    return os.path.join(share_root, language, S2P_SENTENCES_FILENAME)


def write_config_sentences(config_dir: str, language: str = LANGUAGE) -> bool:
    """Write the Assist sentence file. Return True if the content changed."""
    path = config_sentences_path(config_dir, language)
    new_text = render_config_file(language)
    if _read(path) == new_text:
        return False
    _backup(path)
    _write_atomic(path, new_text)
    return True


def share_available(share_root: str = S2P_SHARE_ROOT) -> bool:
    """Return True if a /share folder exists (Home Assistant OS)."""
    return os.path.isdir(os.path.dirname(os.path.dirname(share_root.rstrip("/"))))


def sync_share_sentences(
    language: str = LANGUAGE, share_root: str = S2P_SHARE_ROOT
) -> bool:
    """Merge our set into the Speech-to-Phrase file. Return True if it changed.

    Returns False without touching anything when /share does not exist, or
    when the existing file cannot be parsed (it is never overwritten then).
    """
    if not share_available(share_root):
        return False
    path = share_sentences_path(language, share_root)
    existing = _read(path)
    try:
        new_text = merge_into_share(existing, language)
    except ValueError as err:
        _LOGGER.error("Not touching %s, it could not be merged: %s", path, err)
        return False
    except Exception as err:  # YAML syntax errors and the like
        _LOGGER.error("Not touching %s, it could not be parsed: %s", path, err)
        return False
    if existing == new_text:
        return False
    _backup(path)
    _write_atomic(path, new_text)
    return True


def remove_generated(
    config_dir: str,
    language: str = LANGUAGE,
    share_root: str = S2P_SHARE_ROOT,
    include_share: bool = True,
) -> tuple[bool, bool]:
    """Remove what we generated. Return (config_changed, share_changed).

    With include_share False the Speech-to-Phrase file is left alone.
    """
    config_changed = False
    path = config_sentences_path(config_dir, language)
    if os.path.isfile(path):
        os.remove(path)
        config_changed = True

    share_changed = False
    if include_share and share_available(share_root):
        share_path = share_sentences_path(language, share_root)
        existing = _read(share_path)
        if existing is not None:
            try:
                stripped = strip_from_share(existing)
            except Exception as err:
                _LOGGER.error("Could not clean %s: %s", share_path, err)
                stripped = None
            if stripped is not None:
                _backup(share_path)
                _write_atomic(share_path, stripped)
                share_changed = True
    return config_changed, share_changed
