"""
Packet table widget — shows unique packets sorted by count.
"""

from __future__ import annotations

from PySide6.QtCore    import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLabel,
)

from analyzer.i18n   import tr, on_language_changed
from analyzer.models import PacketRecord


class PacketTableWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._header_lbl = QLabel()
        layout.addWidget(self._header_lbl)

        self._table = QTableWidget(0, 4)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(False)
        layout.addWidget(self._table)

        self.retranslate_ui()
        on_language_changed(lambda _: self.retranslate_ui())

    def retranslate_ui(self) -> None:
        self._header_lbl.setText(tr("<b>Unique Packets</b>"))
        self._header_lbl.setToolTip(
            "Каждая строка — уникальная байтовая последовательность.\n"
            "Одинаковые пакеты объединяются и считаются. Сортировка по убыванию частоты."
        )
        self._table.setHorizontalHeaderLabels([
            tr("Packet (hex)"),
            tr("Count"),
            "%",
            tr("Last seen (us)"),
        ])
        # Tooltips on column headers
        hdr = self._table.horizontalHeader()
        hdr.setToolTip(
            "Колонки: HEX-содержимое пакета | количество повторений | "
            "доля от общего числа пакетов | метка времени последнего приёма в µс"
        )
        if self._table.horizontalHeaderItem(0):
            self._table.horizontalHeaderItem(0).setToolTip(
                "Содержимое пакета в шестнадцатеричном виде (пробелы между байтами)"
            )
        if self._table.horizontalHeaderItem(1):
            self._table.horizontalHeaderItem(1).setToolTip(
                "Сколько раз встречался этот пакет с начала захвата"
            )
        if self._table.horizontalHeaderItem(2):
            self._table.horizontalHeaderItem(2).setToolTip(
                "Доля этого пакета от всех принятых пакетов, в процентах"
            )
        if self._table.horizontalHeaderItem(3):
            self._table.horizontalHeaderItem(3).setToolTip(
                "Метка времени последнего приёма этого пакета в микросекундах (µс)\n"
                "по внутренним часам Arduino (millis/micros)"
            )

    def update_records(self, records: list[PacketRecord], total: int) -> None:
        self._table.setRowCount(len(records))
        for row, rec in enumerate(records):
            pct = 100.0 * rec.count / total if total else 0.0
            self._table.setItem(row, 0, _item(rec.hex_str))
            self._table.setItem(row, 1, _item_num(rec.count))
            self._table.setItem(row, 2, _item(f"{pct:.1f}%"))
            self._table.setItem(row, 3, _item_num(rec.last_seen))


def _item(text: str) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    return it


def _item_num(val) -> QTableWidgetItem:
    it = QTableWidgetItem(f"{val:,}")
    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return it
