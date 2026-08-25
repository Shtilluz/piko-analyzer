"""
Log panel — shows all application log messages in real time.

Colour coding:
  DEBUG    → grey
  INFO     → white / default
  WARNING  → orange
  ERROR    → red
  CRITICAL → bright red + bold
"""

from __future__ import annotations

import logging
import os

from PySide6.QtCore    import Qt, QMetaObject, Q_ARG, Slot
from PySide6.QtGui     import QColor, QTextCharFormat, QFont, QTextCursor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QPlainTextEdit, QLabel, QComboBox,
)

from analyzer.i18n    import tr, on_language_changed
from analyzer.logger  import LOG_FILE

# Map log level → (colour_hex, bold)
_LEVEL_STYLE: dict[int, tuple[str, bool]] = {
    logging.DEBUG:    ("#888888", False),
    logging.INFO:     ("#dddddd", False),
    logging.WARNING:  ("#ffaa00", False),
    logging.ERROR:    ("#ff4444", True),
    logging.CRITICAL: ("#ff0000", True),
}


class LogViewWidget(QWidget):
    """
    Read-only scrolling log panel.

    Thread safety: append_record() may be called from any thread via
    Qt.QueuedConnection — it always posts to the GUI thread.
    """

    MAX_LINES = 2_000   # keep last N lines to avoid unbounded memory use

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        on_language_changed(lambda _: self.retranslate_ui())

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # ---- Toolbar ----
        toolbar = QHBoxLayout()

        self._lbl_filter = QLabel()
        toolbar.addWidget(self._lbl_filter)

        self._level_combo = QComboBox()
        self._level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self._level_combo.setCurrentText("DEBUG")
        self._level_combo.currentTextChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self._level_combo)

        toolbar.addStretch()

        self._btn_clear = QPushButton()
        self._btn_clear.clicked.connect(self._log_edit.clear if hasattr(self, "_log_edit") else lambda: None)
        toolbar.addWidget(self._btn_clear)

        self._btn_copy = QPushButton()
        self._btn_copy.clicked.connect(self._copy_to_clipboard)
        toolbar.addWidget(self._btn_copy)

        self._btn_open_file = QPushButton()
        self._btn_open_file.clicked.connect(self._open_log_file)
        toolbar.addWidget(self._btn_open_file)

        layout.addLayout(toolbar)

        # ---- Text area ----
        self._log_edit = QPlainTextEdit()
        self._log_edit.setReadOnly(True)
        self._log_edit.setMaximumBlockCount(self.MAX_LINES)
        # Monospace font for alignment
        font = QFont("Courier New", 9)
        font.setStyleHint(QFont.Monospace)
        self._log_edit.setFont(font)
        self._log_edit.setStyleSheet("QPlainTextEdit { background: #1e1e1e; color: #dddddd; }")
        layout.addWidget(self._log_edit)

        # ---- Status line ----
        self._status_lbl = QLabel()
        layout.addWidget(self._status_lbl)

        self._line_count = 0
        self._min_level  = logging.DEBUG

        # Wire clear button now that _log_edit exists
        self._btn_clear.clicked.disconnect()
        self._btn_clear.clicked.connect(self._clear)

        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self._lbl_filter.setText(tr("Log level:") if tr("Log level:") != "Log level:" else "Уровень:")
        self._lbl_filter.setToolTip(
            "Минимальный уровень сообщений для отображения.\n"
            "DEBUG — всё (включая каждую принятую строку).\n"
            "INFO  — основные события (подключение, пакеты).\n"
            "WARNING — потенциальные проблемы.\n"
            "ERROR — только ошибки."
        )
        self._level_combo.setToolTip(
            "Фильтр уровня лога. Выберите уровень, начиная с которого\n"
            "сообщения будут отображаться в этой панели.\n"
            "Файл лога (data/piko_analyzer.log) всегда пишется на уровне DEBUG."
        )
        self._btn_clear.setText("Очистить")
        self._btn_clear.setToolTip(
            "Очистить текст в этой панели.\n"
            "Файл лога на диске не удаляется и продолжает пополняться."
        )
        self._btn_copy.setText("Копировать")
        self._btn_copy.setToolTip(
            "Скопировать весь текст лога из этой панели в буфер обмена.\n"
            "Удобно для вставки в баг-репорт или сохранения вручную."
        )
        self._btn_open_file.setText("Открыть файл лога")
        self._btn_open_file.setToolTip(
            f"Открыть файл лога во внешнем текстовом редакторе.\n"
            f"Путь: data/piko_analyzer.log\n"
            f"Файл ротируется при достижении 2 МБ (хранится 3 резервных копии)."
        )
        self._update_status()

    def _update_status(self) -> None:
        path = os.path.abspath(LOG_FILE)
        self._status_lbl.setText(f"Лог: {path}  |  строк: {self._line_count}")

    # ---- Public API ----

    def append_record(self, level: int, message: str) -> None:
        """Thread-safe: can be called from any thread."""
        QMetaObject.invokeMethod(
            self, "_append_in_gui_thread",
            Qt.QueuedConnection,
            Q_ARG(int, level),
            Q_ARG(str, message),
        )

    @Slot(int, str)
    def _append_in_gui_thread(self, level: int, message: str) -> None:
        if level < self._min_level:
            return

        colour_hex, bold = _LEVEL_STYLE.get(level, ("#dddddd", False))

        fmt = QTextCharFormat()
        fmt.setForeground(QColor(colour_hex))
        if bold:
            fmt.setFontWeight(QFont.Bold)

        cursor = self._log_edit.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(message + "\n", fmt)

        # Auto-scroll to bottom
        sb = self._log_edit.verticalScrollBar()
        sb.setValue(sb.maximum())

        self._line_count += 1
        self._update_status()

    def _on_filter_changed(self, text: str) -> None:
        self._min_level = getattr(logging, text, logging.DEBUG)

    def _clear(self) -> None:
        self._log_edit.clear()
        self._line_count = 0
        self._update_status()

    def _copy_to_clipboard(self) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self._log_edit.toPlainText())

    def _open_log_file(self) -> None:
        import subprocess, sys
        path = os.path.abspath(LOG_FILE)
        if not os.path.exists(path):
            return
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
