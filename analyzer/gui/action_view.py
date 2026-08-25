"""
Action recording and comparison panel.
"""

from __future__ import annotations

from PySide6.QtCore    import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QGroupBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QSplitter,
)

from analyzer.i18n            import tr, on_language_changed
from analyzer.action_recorder import ActionRecorder
from analyzer.models          import ActionRecord
from analyzer.correlation     import find_correlations


class ActionWidget(QWidget):
    def __init__(self, recorder: ActionRecorder, parent=None):
        super().__init__(parent)
        self._rec = recorder
        self._build_ui()
        on_language_changed(lambda _: self.retranslate_ui())

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Vertical)
        layout.addWidget(splitter)

        # ---- Recording panel ----
        self._rec_group = QGroupBox()
        rec_layout = QVBoxLayout(self._rec_group)

        row1 = QHBoxLayout()
        self._lbl_label = QLabel()
        row1.addWidget(self._lbl_label)
        self._lbl_edit = QLineEdit()
        self._lbl_edit.setToolTip(
            "Название этой записи. Используйте понятные имена: speed_3, f0_on, reverse.\n"
            "Для корреляционного анализа применяйте числовой суффикс: speed_0, speed_1, speed_2…"
        )
        row1.addWidget(self._lbl_edit)
        rec_layout.addLayout(row1)

        row2 = QHBoxLayout()
        self._lbl_note = QLabel()
        row2.addWidget(self._lbl_note)
        self._note_edit = QLineEdit()
        self._note_edit.setToolTip(
            "Необязательный комментарий: что именно вы делали на контроллере.\n"
            "Сохраняется в сессии и помогает разобраться позже."
        )
        row2.addWidget(self._note_edit)
        rec_layout.addLayout(row2)

        btn_row = QHBoxLayout()
        self._btn_baseline = QPushButton()
        self._btn_action   = QPushButton()
        self._btn_stop     = QPushButton()
        self._btn_cancel   = QPushButton()

        self._btn_baseline.setToolTip(
            "ШАГ 1: Начать сбор базовой линии.\n"
            "После нажатия — ничего НЕ делайте на контроллере 10–20 секунд.\n"
            "Программа запоминает, как выглядят пакеты в состоянии покоя."
        )
        self._btn_action.setToolTip(
            "ШАГ 2: Отметить момент выполнения действия.\n"
            "Нажмите точно когда выполняете действие на контроллере\n"
            "(нажатие кнопки, поворот ручки, смена режима и т.д.)."
        )
        self._btn_stop.setToolTip(
            "ШАГ 3: Завершить запись и сохранить.\n"
            "Программа сравнит доминирующие пакеты базовой линии и действия,\n"
            "покажет какие байты изменились."
        )
        self._btn_cancel.setToolTip(
            "Отменить текущую запись без сохранения.\n"
            "Возвращает в режим ожидания."
        )

        self._btn_baseline.clicked.connect(self._start_baseline)
        self._btn_action.clicked.connect(self._mark_action)
        self._btn_stop.clicked.connect(self._stop)
        self._btn_cancel.clicked.connect(self._cancel)

        self._btn_action.setEnabled(False)
        self._btn_stop.setEnabled(False)

        for b in (self._btn_baseline, self._btn_action,
                  self._btn_stop, self._btn_cancel):
            btn_row.addWidget(b)
        rec_layout.addLayout(btn_row)

        self._state_label = QLabel()
        rec_layout.addWidget(self._state_label)

        splitter.addWidget(self._rec_group)

        # ---- Results panel ----
        results_widget = QWidget()
        results_layout = QVBoxLayout(results_widget)
        results_layout.setContentsMargins(0, 0, 0, 0)

        self._history_header = QLabel()
        results_layout.addWidget(self._history_header)

        self._history_table = QTableWidget(0, 4)
        self._history_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._history_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._history_table.setToolTip(
            "Список сохранённых записей действий.\n"
            "Нажмите на строку, чтобы увидеть детальное сравнение пакетов ниже.\n"
            "Колонки: метка | доминирующий пакет базы | доминирующий пакет действия | изменённые байты"
        )
        self._history_table.selectionModel().selectionChanged.connect(
            self._on_history_select
        )
        results_layout.addWidget(self._history_table)

        self._diff_text = QTextEdit()
        self._diff_text.setReadOnly(True)
        self._diff_text.setMaximumHeight(200)
        self._diff_text.setToolTip(
            "Детальное сравнение для выбранной записи.\n"
            "Показывает какие байты изменились и как (HEX + двоичный вид).\n"
            "Символы ^ указывают позиции изменившихся битов."
        )
        results_layout.addWidget(self._diff_text)

        self._btn_correlation = QPushButton()
        self._btn_correlation.setToolTip(
            "Корреляционный анализ: ищет байты/биты, значение которых\n"
            "линейно коррелирует с числовым суффиксом метки действия.\n"
            "Например, если вы записали speed_0, speed_1, speed_2, speed_3 —\n"
            "находит байт, который кодирует скорость.\n"
            "Требуется минимум 3 записи с числовыми суффиксами одного типа."
        )
        self._btn_correlation.clicked.connect(self._run_correlation)
        results_layout.addWidget(self._btn_correlation)

        self._corr_text = QTextEdit()
        self._corr_text.setReadOnly(True)
        self._corr_text.setMaximumHeight(150)
        self._corr_text.setToolTip(
            "Результаты корреляционного анализа: кандидаты на поля данных\n"
            "с указанием позиции байта, диапазона битов и степени уверенности."
        )
        results_layout.addWidget(self._corr_text)

        splitter.addWidget(results_widget)

        self.retranslate_ui()

    # ---- Retranslation ----

    def retranslate_ui(self) -> None:
        self._rec_group.setTitle(tr("Record Action"))
        self._lbl_label.setText(tr("Label:"))
        self._lbl_edit.setPlaceholderText(tr("e.g.  speed_3  or  f0_on"))
        self._lbl_note.setText(tr("Note:"))
        self._note_edit.setPlaceholderText(tr("optional description"))
        self._btn_baseline.setText(tr("1. Start Baseline"))
        self._btn_action.setText(tr("2. Action Now"))
        self._btn_stop.setText(tr("3. Stop & Save"))
        self._btn_cancel.setText(tr("Cancel"))
        self._history_header.setText(tr("<b>Action History &amp; Diff</b>"))
        self._history_table.setHorizontalHeaderLabels([
            tr("Label"),
            tr("Baseline dominant"),
            tr("Action dominant"),
            tr("Changed bytes"),
        ])
        self._btn_correlation.setText(tr("Run Correlation Analysis"))
        # Refresh state label to current language
        self._update_state_label()
        # Refresh history table headers only (data stays)
        self.refresh()

    def _update_state_label(self) -> None:
        state = self._rec.state
        if state == ActionRecorder.IDLE:
            self._state_label.setText(tr("State: IDLE"))
        elif state == ActionRecorder.BASELINE:
            self._state_label.setText(
                tr("State: COLLECTING BASELINE — do nothing on controller")
            )
        elif state == ActionRecorder.RECORDING:
            self._state_label.setText(
                tr("State: RECORDING ACTION — perform the action now")
            )

    # ---- Recording state machine ----

    def _start_baseline(self) -> None:
        label = self._lbl_edit.text().strip()
        if not label:
            self._state_label.setText(tr("State: ERROR — enter a label first"))
            return
        self._rec.start_baseline(label, self._note_edit.text().strip())
        self._btn_baseline.setEnabled(False)
        self._btn_action.setEnabled(True)
        self._state_label.setText(
            tr("State: COLLECTING BASELINE — do nothing on controller")
        )

    def _mark_action(self) -> None:
        self._rec.switch_to_action()
        self._btn_action.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._state_label.setText(
            tr("State: RECORDING ACTION — perform the action now")
        )

    def _stop(self) -> None:
        rec = self._rec.stop_recording()
        self._btn_baseline.setEnabled(True)
        self._btn_action.setEnabled(False)
        self._btn_stop.setEnabled(False)
        if rec:
            self._state_label.setText(
                tr("State: IDLE") + f" — saved '{rec.label}'"
            )
        else:
            self._state_label.setText(tr("State: IDLE"))
        self.refresh()

    def _cancel(self) -> None:
        self._rec.cancel()
        self._btn_baseline.setEnabled(True)
        self._btn_action.setEnabled(False)
        self._btn_stop.setEnabled(False)
        self._state_label.setText(tr("State: IDLE (cancelled)"))

    # ---- UI refresh ----

    def refresh(self) -> None:
        records = self._rec.records
        self._history_table.setRowCount(len(records))
        for row, rec in enumerate(records):
            diffs   = self._rec.compare_dominant(rec)
            changed = ", ".join(f"B{pos}" for pos, _, _ in diffs)
            self._history_table.setItem(row, 0, _item(rec.label))
            self._history_table.setItem(row, 1, _item(_hex_or_none(rec.baseline_dominant)))
            self._history_table.setItem(row, 2, _item(_hex_or_none(rec.action_dominant)))
            self._history_table.setItem(row, 3, _item(changed or "—"))

    def _on_history_select(self) -> None:
        rows = self._history_table.selectionModel().selectedRows()
        if not rows:
            return
        idx = rows[0].row()
        rec = self._rec.records[idx]
        self._show_diff(rec)

    def _show_diff(self, rec: ActionRecord) -> None:
        lines = [f"{tr('Action: {label}', label=rec.label)}"]
        if rec.description:
            lines.append(tr("Note: {desc}", desc=rec.description))
        lines.append("")
        lines.append(
            tr("Baseline dominant : {pkt}", pkt=_hex_or_none(rec.baseline_dominant))
        )
        lines.append(
            tr("Action dominant   : {pkt}", pkt=_hex_or_none(rec.action_dominant))
        )
        lines.append("")

        diffs = self._rec.compare_dominant(rec)
        if not diffs:
            lines.append(tr("No differences detected."))
        else:
            lines.append(tr("Changed bytes:"))
            for pos, bv, av in diffs:
                bv_str = f"{bv:02X}  ({bv:08b})" if bv is not None else "—"
                av_str = f"{av:02X}  ({av:08b})" if av is not None else "—"
                lines.append(f"  BYTE {pos}:  {bv_str}  →  {av_str}")
                if bv is not None and av is not None:
                    diff_bits = bv ^ av
                    marks = "".join(
                        "^" if diff_bits & (1 << (7 - b)) else " "
                        for b in range(8)
                    )
                    lines.append(
                        f"           {'  ' * 7}{marks}  {tr('← changed bits')}"
                    )

        self._diff_text.setPlainText("\n".join(lines))

    def _run_correlation(self) -> None:
        triples = self._rec.records_for_correlation()
        if len(triples) < 3:
            self._corr_text.setPlainText(
                tr(
                    "Need at least 3 labelled actions with numeric suffixes "
                    "(e.g. speed_0, speed_1, speed_2…) to compute correlation."
                )
            )
            return

        candidates = find_correlations(triples)
        if not candidates:
            self._corr_text.setPlainText(
                tr("No correlation found above the confidence threshold.")
            )
            return

        lines = [tr("Correlation candidates (sorted by confidence):\n")]
        for c in candidates[:15]:
            bit_range = (
                f"B{c.bit_high}" if c.bit_high == c.bit_low
                else f"B{c.bit_high}:B{c.bit_low}"
            )
            lines.append(
                f"  {tr('Possible {field} field', field=c.label.upper())}  "
                f"BYTE {c.byte_pos} [{bit_range}]  "
                f"{tr('confidence={conf}', conf=f'{c.confidence:.1%}')}  {c.note}"
            )
        self._corr_text.setPlainText("\n".join(lines))


# ---- Helpers ----

def _hex_or_none(data) -> str:
    if data is None:
        return "—"
    return " ".join(f"{b:02X}" for b in data)


def _item(text: str) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    return it
