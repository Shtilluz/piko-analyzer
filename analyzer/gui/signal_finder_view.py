"""
Signal Finder tab — universal detector for accessory decoder control signals.

Reads from the shared ActionRecorder, groups records by profile, runs
profile-specific analysis (find_direction_field, find_address_field) and
displays results.  The user picks "Export → Sketch Generator" to pre-fill
the Switch/Accessory tab with the discovered field layout.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from analyzer.i18n import on_language_changed, tr
from analyzer.models import ActionRecord
from analyzer.signal_profiles import (
    BUILTIN_PROFILES,
    ProfileAnalysisResult,
    ProfileDefinition,
    ProfileType,
    analyze_profile,
    detect_profile,
)

# Confidence colour thresholds
_CLR_HIGH   = QColor("#1e7a1e")   # dark green  ≥ 0.80
_CLR_MEDIUM = QColor("#7a6e00")   # dark yellow ≥ 0.50
_CLR_LOW    = QColor("#7a1e1e")   # dark red    < 0.50


def _confidence_color(c: float) -> QColor:
    if c >= 0.80:
        return _CLR_HIGH
    if c >= 0.50:
        return _CLR_MEDIUM
    return _CLR_LOW


def _make_item(text: str, align: int = Qt.AlignLeft | Qt.AlignVCenter) -> QTableWidgetItem:
    it = QTableWidgetItem(str(text))
    it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
    it.setTextAlignment(align)
    return it


class SignalFinderWidget(QWidget):
    """
    Tab widget for the universal signal finder.

    Signals
    -------
    export_requested(ProfileAnalysisResult)
        Emitted when the user clicks "Export to Sketch Generator".
        Connected in main_window to SketchGeneratorWidget.prefill_switch().
    """

    export_requested = Signal(object)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._records:         list[ActionRecord]           = []
        self._last_count:      int                          = -1
        self._last_result:     Optional[ProfileAnalysisResult] = None
        self._profile_items:   list[Optional[ProfileType]]  = []  # parallel to combo

        self._build_ui()
        on_language_changed(lambda _: self.retranslate_ui())

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # ---- Top controls bar ----
        top = QHBoxLayout()

        self._lbl_profile = QLabel()
        top.addWidget(self._lbl_profile)

        self._combo_profile = QComboBox()
        self._combo_profile.setMinimumWidth(200)
        self._combo_profile.currentIndexChanged.connect(self._on_profile_changed)
        top.addWidget(self._combo_profile)

        self._btn_analyze = QPushButton()
        self._btn_analyze.clicked.connect(self._run_analysis)
        top.addWidget(self._btn_analyze)

        top.addStretch()

        self._lbl_status = QLabel()
        font = QFont()
        font.setItalic(True)
        self._lbl_status.setFont(font)
        top.addWidget(self._lbl_status)

        root.addLayout(top)

        # ---- Middle: matched records + discovered fields ----
        mid_splitter = QSplitter(Qt.Horizontal)

        # Left: matched records
        self._grp_matched = QGroupBox()
        left_layout = QVBoxLayout(self._grp_matched)
        left_layout.setContentsMargins(4, 4, 4, 4)
        self._tbl_matched = QTableWidget(0, 3)
        self._tbl_matched.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._tbl_matched.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._tbl_matched.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._tbl_matched.verticalHeader().setDefaultSectionSize(22)
        self._tbl_matched.setSelectionBehavior(QTableWidget.SelectRows)
        self._tbl_matched.setEditTriggers(QTableWidget.NoEditTriggers)
        left_layout.addWidget(self._tbl_matched)
        mid_splitter.addWidget(self._grp_matched)

        # Right: discovered fields
        self._grp_fields = QGroupBox()
        right_layout = QVBoxLayout(self._grp_fields)
        right_layout.setContentsMargins(4, 4, 4, 4)
        self._tbl_fields = QTableWidget(0, 5)
        self._tbl_fields.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._tbl_fields.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._tbl_fields.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._tbl_fields.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._tbl_fields.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self._tbl_fields.verticalHeader().setDefaultSectionSize(22)
        self._tbl_fields.setSelectionBehavior(QTableWidget.SelectRows)
        self._tbl_fields.setEditTriggers(QTableWidget.NoEditTriggers)
        right_layout.addWidget(self._tbl_fields)
        mid_splitter.addWidget(self._grp_fields)

        mid_splitter.setSizes([350, 450])
        root.addWidget(mid_splitter, stretch=1)

        # ---- Bottom: warnings + export ----
        bot = QVBoxLayout()

        self._grp_warnings = QGroupBox()
        warn_layout = QVBoxLayout(self._grp_warnings)
        warn_layout.setContentsMargins(4, 4, 4, 4)
        self._txt_warnings = QTextEdit()
        self._txt_warnings.setReadOnly(True)
        self._txt_warnings.setMaximumHeight(80)
        warn_layout.addWidget(self._txt_warnings)
        bot.addWidget(self._grp_warnings)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._btn_export = QPushButton()
        self._btn_export.setEnabled(False)
        self._btn_export.clicked.connect(self._export)
        btn_row.addWidget(self._btn_export)
        bot.addLayout(btn_row)

        root.addLayout(bot)

        self._populate_combo()
        self.retranslate_ui()

    def _populate_combo(self) -> None:
        self._combo_profile.clear()
        self._profile_items = []

        # Auto-detect entry
        self._combo_profile.addItem(tr("Auto-detect"))
        self._profile_items.append(None)

        for ptype, profile in BUILTIN_PROFILES.items():
            self._combo_profile.addItem(tr(profile.name))
            self._profile_items.append(ptype)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self, records: list[ActionRecord]) -> None:
        """Called from main_window refresh timer with current action records."""
        self._records = records
        count = len(records)
        if count == self._last_count:
            return
        self._last_count = count

        # Auto-run if enough records match the selected profile
        profile = self._get_selected_profile()
        if profile is not None:
            matched = [r for r in records if profile.compiled.match(r.label)]
        else:
            # auto-detect: try all profiles
            ptype = detect_profile(records)
            if ptype is not None:
                matched = [r for r in records if BUILTIN_PROFILES[ptype].compiled.match(r.label)]
            else:
                matched = []

        if len(matched) >= 4:
            self._run_analysis()

    def retranslate_ui(self) -> None:
        self._lbl_profile.setText(tr("Profile:"))
        self._btn_analyze.setText(tr("Analyze"))
        self._btn_export.setText(tr("Export to Sketch Generator"))

        self._grp_matched.setTitle(tr("Matched records"))
        self._tbl_matched.setHorizontalHeaderLabels([
            tr("Label"),
            tr("Baseline pkt"),
            tr("Action pkt"),
        ])

        self._grp_fields.setTitle(tr("Discovered fields"))
        self._tbl_fields.setHorizontalHeaderLabels([
            tr("Name"),
            tr("Byte"),
            tr("Bits"),
            tr("Confidence"),
            tr("Note"),
        ])

        self._grp_warnings.setTitle(tr("Warnings / missing data"))
        self._btn_export.setToolTip(
            tr("Export to Sketch Generator")
        )

        # Rebuild profile combo to translate profile names
        current_idx = self._combo_profile.currentIndex()
        self._populate_combo()
        if 0 <= current_idx < self._combo_profile.count():
            self._combo_profile.setCurrentIndex(current_idx)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_selected_profile(self) -> Optional[ProfileDefinition]:
        idx = self._combo_profile.currentIndex()
        if idx < 0 or idx >= len(self._profile_items):
            return None
        ptype = self._profile_items[idx]
        if ptype is None:
            return None
        return BUILTIN_PROFILES[ptype]

    def _on_profile_changed(self, _idx: int) -> None:
        self._last_count = -1   # force re-analysis next refresh

    def _run_analysis(self) -> None:
        records = self._records
        profile = self._get_selected_profile()

        if profile is None:
            # auto-detect
            ptype = detect_profile(records)
            if ptype is None:
                self._lbl_status.setText(tr("No profile matched"))
                self._txt_warnings.setPlainText(tr("No profile matched"))
                return
            profile = BUILTIN_PROFILES[ptype]
            # Sync combo to detected profile
            for i, pt in enumerate(self._profile_items):
                if pt == ptype:
                    self._combo_profile.blockSignals(True)
                    self._combo_profile.setCurrentIndex(i)
                    self._combo_profile.blockSignals(False)
                    break

        result = analyze_profile(records, profile)
        self._last_result = result

        self._populate_matched_table(result, profile)
        self._populate_fields_table(result)

        all_msgs = result.warnings + result.missing_states
        self._txt_warnings.setPlainText("\n".join(all_msgs) if all_msgs else "")

        self._lbl_status.setText(tr("Matched records: {n}", n=result.matched_count))
        self._btn_export.setEnabled(bool(result.fields))

    def _populate_matched_table(
        self, result: ProfileAnalysisResult, profile: ProfileDefinition
    ) -> None:
        matched = [r for r in self._records if profile.compiled.match(r.label)]
        self._tbl_matched.setRowCount(len(matched))

        for row, rec in enumerate(matched):
            bl = rec.baseline_dominant
            ac = rec.action_dominant
            self._tbl_matched.setItem(row, 0, _make_item(rec.label))
            self._tbl_matched.setItem(row, 1, _make_item(
                " ".join(f"{b:02X}" for b in bl) if bl else "—"
            ))
            self._tbl_matched.setItem(row, 2, _make_item(
                " ".join(f"{b:02X}" for b in ac) if ac else "—"
            ))

    def _populate_fields_table(self, result: ProfileAnalysisResult) -> None:
        self._tbl_fields.setRowCount(len(result.fields))

        for row, f in enumerate(result.fields):
            bits_str = (
                f"b{f.bit_high}" if f.bit_high == f.bit_low
                else f"b{f.bit_high}:b{f.bit_low}"
            )
            conf_str = f"{f.confidence * 100:.0f}%"

            name_item = _make_item(tr(f.name))
            byte_item = _make_item(str(f.byte_pos), Qt.AlignCenter | Qt.AlignVCenter)
            bits_item = _make_item(bits_str, Qt.AlignCenter | Qt.AlignVCenter)
            conf_item = _make_item(conf_str, Qt.AlignCenter | Qt.AlignVCenter)
            note_item = _make_item(f.note)

            clr = _confidence_color(f.confidence)
            for it in (name_item, byte_item, bits_item, conf_item, note_item):
                it.setForeground(clr)

            self._tbl_fields.setItem(row, 0, name_item)
            self._tbl_fields.setItem(row, 1, byte_item)
            self._tbl_fields.setItem(row, 2, bits_item)
            self._tbl_fields.setItem(row, 3, conf_item)
            self._tbl_fields.setItem(row, 4, note_item)

    def _export(self) -> None:
        if self._last_result is not None and self._last_result.fields:
            self.export_requested.emit(self._last_result)
