"""
Bit analysis panel — per-bit statistics for each byte position.
"""

from __future__ import annotations

from PySide6.QtCore    import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QLabel, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView,
)

from analyzer.i18n   import tr, on_language_changed
from analyzer.models import BitStats


class BitAnalysisWidget(QWidget):
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

        self._frames: list[_BitFrame] = []
        self._current_stats: list[list[BitStats]] = []

        self.retranslate_ui()
        on_language_changed(lambda _: self._on_lang_changed())

    def retranslate_ui(self) -> None:
        self._header_lbl.setText(tr("<b>Bit Analysis</b>"))
        self._header_lbl.setToolTip(
            "Анализ каждого бита в каждой позиции байта.\n"
            "Помогает находить битовые флаги, поля направления и счётчики.\n"
            "B7 — старший бит (MSB),  B0 — младший бит (LSB)."
        )
        for f in self._frames:
            f.retranslate_ui()

    def _on_lang_changed(self) -> None:
        self.retranslate_ui()
        if self._current_stats:
            self.update_stats(self._current_stats)

    def update_stats(self, bit_stats_2d: list[list[BitStats]]) -> None:
        self._current_stats = bit_stats_2d

        while len(self._frames) < len(bit_stats_2d):
            frame = _BitFrame()
            self._frames.append(frame)
            self._inner.addWidget(frame)

        for i, row in enumerate(bit_stats_2d):
            self._frames[i].refresh(i, row)
            self._frames[i].show()

        for i in range(len(bit_stats_2d), len(self._frames)):
            self._frames[i].hide()


class _BitFrame(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._header = QLabel()
        self._header.setStyleSheet("font-weight: bold;")
        layout.addWidget(self._header)

        self._table = QTableWidget(3, 8)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setMaximumHeight(110)
        layout.addWidget(self._table)

        self._last_byte_pos: int = 0
        self._last_bit_row: list[BitStats] = []
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self._table.setVerticalHeaderLabels([tr("%0"), tr("%1"), tr("trans%")])
        bit_headers = [f"B{b}" for b in range(7, -1, -1)]
        self._table.setHorizontalHeaderLabels(bit_headers)
        self._table.setToolTip(
            "Строки:\n"
            "  %0      — как часто бит равен 0 (в % от всех пакетов)\n"
            "  %1      — как часто бит равен 1\n"
            "  trans%  — как часто бит меняет значение между соседними пакетами\n\n"
            "Подсказки интерпретации:\n"
            "  %0≈100% или %1≈100%  →  константный бит (фиксированный флаг)\n"
            "  trans%≈50%           →  активно меняющийся бит (данные, счётчик)\n"
            "  trans% низкий        →  редко меняющийся (режим, адрес)"
        )
        if self._last_bit_row:
            self.refresh(self._last_byte_pos, self._last_bit_row)

    def refresh(self, byte_pos: int, bit_row: list[BitStats]) -> None:
        self._last_byte_pos = byte_pos
        self._last_bit_row  = bit_row
        self._header.setText(f"BYTE {byte_pos} — {tr('bit detail')}")
        self._header.setToolTip(
            f"Побитовый анализ байта на позиции {byte_pos} (счёт с 0).\n"
            "Каждый столбец — один бит. B7=MSB (старший), B0=LSB (младший)."
        )
        for bit in range(8):
            col = 7 - bit
            bs  = bit_row[bit]
            self._table.setItem(0, col, _item(f"{bs.pct_0:.0f}%"))
            self._table.setItem(1, col, _item(f"{bs.pct_1:.0f}%"))
            self._table.setItem(2, col, _item(f"{bs.transition_pct:.0f}%"))


def _item(text: str) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setTextAlignment(Qt.AlignCenter)
    return it
