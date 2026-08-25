"""
Centralized logging for the whole application.

Every module does:
    from analyzer.logger import get_logger
    log = get_logger(__name__)

Output goes to THREE places simultaneously:
  1. Console (stderr)          — always, level DEBUG
  2. File  data/piko_analyzer.log — always, level DEBUG, rotated at 2 MB
  3. Qt signal → GUI log panel  — level DEBUG (shown colour-coded)

The Qt handler is registered lazily when install_qt_handler() is called
from the GUI thread (after QApplication exists).
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import traceback
from typing import Callable

# ---- Log file ------------------------------------------------------------ #

LOG_FILE = os.path.join("data", "piko_analyzer.log")
LOG_FORMAT = "%(asctime)s.%(msecs)03d [%(levelname)-8s] %(name)s — %(message)s"
LOG_DATE   = "%H:%M:%S"


def _setup_root_logger() -> logging.Logger:
    os.makedirs("data", exist_ok=True)

    root = logging.getLogger("piko")
    root.setLevel(logging.DEBUG)

    if root.handlers:
        return root

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE))
    root.addHandler(ch)

    # Rotating file handler — 2 MB max, keep 3 backups
    try:
        fh = logging.handlers.RotatingFileHandler(
            LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE))
        root.addHandler(fh)
    except OSError as exc:
        root.warning(f"Cannot open log file {LOG_FILE}: {exc}")

    return root


_root = _setup_root_logger()


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the 'piko' namespace."""
    return _root.getChild(name.replace("analyzer.", ""))


# ---- Qt signal bridge ---------------------------------------------------- #
# Installed once, from the GUI thread, after QApplication is created.

class _QtLogHandler(logging.Handler):
    """Forwards log records to a callback (Qt signal emit)."""

    def __init__(self, callback: Callable[[int, str], None]):
        super().__init__(logging.DEBUG)
        self._cb = callback
        self.setFormatter(logging.Formatter("%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s — %(message)s", LOG_DATE))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self._cb(record.levelno, msg)
        except Exception:
            pass   # never crash the logging machinery


def install_qt_handler(callback: Callable[[int, str], None]) -> None:
    """
    Register a Qt-side callback that receives (level: int, message: str).
    Call this once from the main window __init__, after QApplication exists.
    """
    handler = _QtLogHandler(callback)
    _root.addHandler(handler)


# ---- Convenience: log uncaught exceptions -------------------------------- #

import sys

def _excepthook(exc_type, exc_value, exc_tb):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    _root.critical(f"Uncaught exception:\n{msg}")

sys.excepthook = _excepthook
