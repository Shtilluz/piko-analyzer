"""
Byte analysis panel — per-byte-position statistics.
"""

from __future__ import annotations

from PySide6.QtCore    import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QLabel, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView,
)

from analyzer.i18n   import tr, on_language_changed
from analyzer.models import ByteStats


class ByteAnalysisWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._header_lbl = QLabel()
        layout.addWidget(self._header_lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._container = QWidget()
        self._inner     = QVBoxLayout(self._container)
        self._inner.setAlignment(Qt.AlignTop)
        scroll.setWidget(self._container)
        layout.addWidget(scroll)

        self._byte_frames: list[_ByteFrame] = []
        self._current_stats: list[ByteStats] = []

        self.retranslate_ui()
        on_language_changed(lambda _: self._on_lang_changed())

    def retranslate_ui(self) -> None:
        self._header_lbl.setText(tr("<b>Byte Analysis</b>"))
        self._header_lbl.setToolTip(
            "Анализ каждой позиции байта во всех принятых пакетах.\n"
            "CONSTANT — байт не меняется (возможно: преамбула, адрес устройства).\n"
            "MOSTLY_CONSTANT — меняется редко (≤10% пакетов).\n"
            "VARIABLE — активно меняется (возможно: данные, счётчик, контрольная сумма)."
        )
        for f in self._byte_frames:
            f.retranslate_ui()

    def _on_lang_changed(self) -> None:
        self.retranslate_ui()
        if self._current_stats:
            self.update_stats(self._current_stats)

    def update_stats(self, byte_stats: list[ByteStats]) -> None:
        self._current_stats = byte_stats

        while len(self._byte_frames) < len(byte_stats):
            frame = _ByteFrame()
            self._byte_frames.append(frame)
            self._inner.addWidget(frame)

        for i, bs in enumerate(byte_stats):
            self._byte_frames[i].refresh(bs)
            self._byte_frames[i].show()

        for i in range(len(byte_stats), len(self._byte_frames)):
            self._byte_frames[i].hide()


class _ByteFrame(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._header = QLabel()
        self._header.setStyleSheet("font-weight: bold;")
        layout.addWidget(self._header)

        self._table = QTableWidget(0, 3)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setMaximumHeight(160)
        layout.addWidget(self._table)

        self._last_bs: ByteStats | None = None
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self._table.setHorizontalHeaderLabels([tr("Value"), tr("Count"), "%"])
        self._table.setToolTip(
            "Топ-10 значений для этой позиции байта, по убыванию частоты.\n"
            "Value — значение в HEX  |  Count — количество вхождений  |  % — доля"
        )
        if self._last_bs is not None:
            self.refresh(self._last_bs)

    def refresh(self, bs: ByteStats) -> None:
        self._last_bs = bs
        variability   = tr(bs.variability_label)
        self._header.setText(
            f"BYTE {bs.position}   [{variability}]   "
            f"{bs.unique_count} {tr('unique values')} / {bs.total} {tr('total')}"
        )
        _variability_hints = {
            "CONSTANT":        "Значение не меняется — вероятно преамбула или фиксированный адрес.",
            "MOSTLY_CONSTANT": "Иногда меняется — возможно флаг режима или тип команды.",
            "VARIABLE":        "Активно меняется — кандидат на данные, счётчик или контрольную сумму.",
        }
        hint = _variability_hints.get(bs.variability_label, "")
        self._header.setToolTip(
            f"Позиция байта {bs.position} в пакете (счёт с 0).\n"
            f"Уникальных значений: {bs.unique_count}  из  {bs.total} пакетов.\n"
            f"{hint}"
        )

        sorted_vals = sorted(
            bs.value_counts.items(), key=lambda kv: kv[1], reverse=True
        )[:10]

        self._table.setRowCount(len(sorted_vals))
        for row, (val, cnt) in enumerate(sorted_vals):
            pct = 100.0 * cnt / bs.total if bs.total else 0.0
            self._table.setItem(row, 0, _item(f"{val:02X}"))
            self._table.setItem(row, 1, _item_r(f"{cnt:,}"))
            self._table.setItem(row, 2, _item_r(f"{pct:.1f}%"))


def _item(text: str) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    return it


def _item_r(text: str) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return it
