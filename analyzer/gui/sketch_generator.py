"""
Arduino sketch generator.

The user fills in the discovered packet field layout, clicks Generate,
and gets a ready-to-flash .ino that can set speed / direction / functions.
"""

from __future__ import annotations

import datetime
import os

from PySide6.QtCore    import Qt
from PySide6.QtGui     import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QScrollArea,
    QGroupBox, QFormLayout, QLabel, QSpinBox, QComboBox,
    QCheckBox, QPushButton, QPlainTextEdit, QTableWidget,
    QTableWidgetItem, QHeaderView, QFileDialog, QApplication,
    QLineEdit, QTabWidget,
)

from analyzer.i18n import tr, on_language_changed

# ------------------------------------------------------------------ #
# Checksum algorithms understood by the generator                     #
# ------------------------------------------------------------------ #
_CS_ALGOS = ["None", "XOR", "SUM8", "SUM8_NEG", "SUM8_COMP2", "CRC8"]


class SketchGeneratorWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        on_language_changed(lambda _: self.retranslate_ui())

    # ================================================================ #
    # Build UI                                                           #
    # ================================================================ #

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Vertical)
        root.addWidget(splitter)

        # ---- Top: parameter form ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)
        form_layout.setContentsMargins(8, 8, 8, 8)
        form_layout.setSpacing(8)
        scroll.setWidget(form_widget)

        # --- Packet ---
        self._grp_pkt = QGroupBox()
        fl = QFormLayout(self._grp_pkt)
        self._spin_pkt_len = QSpinBox()
        self._spin_pkt_len.setRange(1, 32)
        self._spin_pkt_len.setValue(4)
        self._spin_pkt_len.setToolTip(
            "Длина одного пакета в байтах.\n"
            "Определяется по данным в таблице уникальных пакетов."
        )
        self._lbl_pkt_len = QLabel()
        fl.addRow(self._lbl_pkt_len, self._spin_pkt_len)
        form_layout.addWidget(self._grp_pkt)

        # --- Address ---
        self._grp_addr = QGroupBox()
        fl2 = QFormLayout(self._grp_addr)
        self._spin_addr_pos = QSpinBox()
        self._spin_addr_pos.setRange(0, 31)
        self._spin_addr_pos.setValue(0)
        self._spin_addr_pos.setToolTip(
            "Позиция байта адреса декодера (с 0).\n"
            "Обычно CONSTANT байт — одно и то же значение во всех пакетах."
        )
        self._edit_addr_val = QLineEdit("0x03")
        self._edit_addr_val.setToolTip(
            "Значение адреса декодера в hex, например 0x03 или 03.\n"
            "Берётся из колонки «Value» байта с меткой CONSTANT."
        )
        self._lbl_addr_pos = QLabel()
        self._lbl_addr_val = QLabel()
        fl2.addRow(self._lbl_addr_pos, self._spin_addr_pos)
        fl2.addRow(self._lbl_addr_val, self._edit_addr_val)
        form_layout.addWidget(self._grp_addr)

        # --- Speed ---
        self._grp_speed = QGroupBox()
        fl3 = QFormLayout(self._grp_speed)
        self._spin_speed_pos  = QSpinBox(); self._spin_speed_pos.setRange(0, 31); self._spin_speed_pos.setValue(1)
        self._edit_speed_mask = QLineEdit("0x7F")
        self._spin_speed_max  = QSpinBox(); self._spin_speed_max.setRange(1, 255); self._spin_speed_max.setValue(127)
        self._spin_speed_pos.setToolTip(
            "Позиция байта скорости (с 0).\n"
            "Ищите VARIABLE байт с равномерным распределением значений."
        )
        self._edit_speed_mask.setToolTip(
            "Битовая маска поля скорости в hex, например 0x7F (7 бит = 128 шагов)\n"
            "или 0xFF (полный байт = 256 шагов)."
        )
        self._spin_speed_max.setToolTip("Максимальное значение скорости (128 шагов → 127, 256 шагов → 255).")
        self._lbl_speed_pos  = QLabel()
        self._lbl_speed_mask = QLabel()
        self._lbl_speed_max  = QLabel()
        fl3.addRow(self._lbl_speed_pos,  self._spin_speed_pos)
        fl3.addRow(self._lbl_speed_mask, self._edit_speed_mask)
        fl3.addRow(self._lbl_speed_max,  self._spin_speed_max)
        form_layout.addWidget(self._grp_speed)

        # --- Direction ---
        self._grp_dir = QGroupBox()
        fl4 = QFormLayout(self._grp_dir)
        self._spin_dir_pos  = QSpinBox(); self._spin_dir_pos.setRange(0, 31); self._spin_dir_pos.setValue(1)
        self._spin_dir_bit  = QSpinBox(); self._spin_dir_bit.setRange(0, 7);  self._spin_dir_bit.setValue(5)
        self._chk_dir_fwd1  = QCheckBox()
        self._chk_dir_fwd1.setChecked(True)
        self._spin_dir_pos.setToolTip(
            "Позиция байта, содержащего бит направления (с 0)."
        )
        self._spin_dir_bit.setToolTip(
            "Номер бита направления внутри байта.\n"
            "0 = LSB (младший), 7 = MSB (старший).\n"
            "Используйте вкладку Bit Analysis чтобы найти активный бит."
        )
        self._chk_dir_fwd1.setToolTip(
            "Если отмечено: бит=1 означает движение «вперёд».\n"
            "Если снято: бит=0 означает «вперёд»."
        )
        self._lbl_dir_pos  = QLabel()
        self._lbl_dir_bit  = QLabel()
        self._lbl_dir_fwd1 = QLabel()
        fl4.addRow(self._lbl_dir_pos,  self._spin_dir_pos)
        fl4.addRow(self._lbl_dir_bit,  self._spin_dir_bit)
        fl4.addRow(self._lbl_dir_fwd1, self._chk_dir_fwd1)
        form_layout.addWidget(self._grp_dir)

        # --- Checksum ---
        self._grp_cs = QGroupBox()
        fl5 = QFormLayout(self._grp_cs)
        self._combo_cs_algo = QComboBox()
        self._combo_cs_algo.addItems(_CS_ALGOS)
        self._spin_cs_pos   = QSpinBox(); self._spin_cs_pos.setRange(0, 31); self._spin_cs_pos.setValue(3)
        self._combo_cs_algo.setToolTip(
            "Алгоритм контрольной суммы, найденный во вкладке Checksum.\n"
            "None — если контрольная сумма не найдена или не нужна."
        )
        self._spin_cs_pos.setToolTip(
            "Позиция байта контрольной суммы в пакете (с 0).\n"
            "Берётся из результатов вкладки Checksum."
        )
        self._lbl_cs_algo = QLabel()
        self._lbl_cs_pos  = QLabel()
        fl5.addRow(self._lbl_cs_algo, self._combo_cs_algo)
        fl5.addRow(self._lbl_cs_pos,  self._spin_cs_pos)
        form_layout.addWidget(self._grp_cs)

        # --- Functions ---
        self._grp_fn = QGroupBox()
        fn_layout = QVBoxLayout(self._grp_fn)
        self._fn_table = QTableWidget(8, 3)
        self._fn_table.setMaximumHeight(200)
        self._fn_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._fn_table.setEditTriggers(QTableWidget.AllEditTriggers)
        self._fn_table.setToolTip(
            "Таблица функций локомотива (F0–F7 и выше).\n"
            "Для каждой функции укажите позицию байта и номер бита.\n"
            "Снимите галку, если функция не используется."
        )
        # Default values
        _fn_defaults = [
            (2, 4, True),   # F0
            (2, 0, True),   # F1
            (2, 1, True),   # F2
            (2, 2, True),   # F3
            (2, 3, True),   # F4
            (2, 5, False),  # F5
            (2, 6, False),  # F6
            (2, 7, False),  # F7
        ]
        for row, (byte_pos, bit_pos, enabled) in enumerate(_fn_defaults):
            sp_byte = QSpinBox(); sp_byte.setRange(0, 31); sp_byte.setValue(byte_pos)
            sp_bit  = QSpinBox(); sp_bit.setRange(0, 7);  sp_bit.setValue(bit_pos)
            chk = QCheckBox(); chk.setChecked(enabled)
            self._fn_table.setCellWidget(row, 0, sp_byte)
            self._fn_table.setCellWidget(row, 1, sp_bit)
            self._fn_table.setCellWidget(row, 2, chk)
        fn_layout.addWidget(self._fn_table)
        form_layout.addWidget(self._grp_fn)

        # --- Generate button ---
        self._btn_generate = QPushButton()
        self._btn_generate.setToolTip(
            "Сгенерировать Arduino .ino скетч на основе заполненных полей.\n"
            "Результат появится в поле ниже."
        )
        self._btn_generate.clicked.connect(self._generate)
        form_layout.addWidget(self._btn_generate)
        form_layout.addStretch()

        # ---- Mode tabs: Locomotive + Switch/Accessory ----
        self._mode_tabs = QTabWidget()
        self._mode_tabs.addTab(scroll, "")          # text set in retranslate_ui

        sw_scroll = self._build_switch_form()
        self._mode_tabs.addTab(sw_scroll, "")       # text set in retranslate_ui

        splitter.addWidget(self._mode_tabs)

        # ---- Bottom: code output ----
        code_widget = QWidget()
        code_layout = QVBoxLayout(code_widget)
        code_layout.setContentsMargins(4, 4, 4, 4)

        self._lbl_output = QLabel()
        code_layout.addWidget(self._lbl_output)

        self._code_edit = QPlainTextEdit()
        self._code_edit.setReadOnly(True)
        font = QFont("Courier New", 9)
        font.setStyleHint(QFont.Monospace)
        self._code_edit.setFont(font)
        self._code_edit.setStyleSheet(
            "QPlainTextEdit { background: #1e1e1e; color: #d4d4d4; }"
        )
        self._code_edit.setToolTip(
            "Сгенерированный скетч Arduino. Нажмите «Генерировать» чтобы обновить.\n"
            "Скопируйте в Arduino IDE или сохраните как .ino файл."
        )
        code_layout.addWidget(self._code_edit)

        btn_row = QHBoxLayout()
        self._btn_copy = QPushButton()
        self._btn_copy.clicked.connect(self._copy_code)
        self._btn_copy.setToolTip("Скопировать код в буфер обмена")
        self._btn_save = QPushButton()
        self._btn_save.clicked.connect(self._save_ino)
        self._btn_save.setToolTip("Сохранить скетч как файл .ino")
        btn_row.addStretch()
        btn_row.addWidget(self._btn_copy)
        btn_row.addWidget(self._btn_save)
        code_layout.addLayout(btn_row)

        splitter.addWidget(code_widget)
        splitter.setSizes([400, 300])

        self.retranslate_ui()

    # ================================================================ #
    # Retranslation                                                      #
    # ================================================================ #

    def retranslate_ui(self) -> None:
        self._grp_pkt.setTitle(tr("Packet"))
        self._lbl_pkt_len.setText(tr("Packet length (bytes):"))

        self._grp_addr.setTitle(tr("Decoder Address"))
        self._lbl_addr_pos.setText(tr("Byte position:"))
        self._lbl_addr_val.setText(tr("Value (hex):"))

        self._grp_speed.setTitle(tr("Speed"))
        self._lbl_speed_pos.setText(tr("Byte position:"))
        self._lbl_speed_mask.setText(tr("Bitmask (hex):"))
        self._lbl_speed_max.setText(tr("Max value:"))

        self._grp_dir.setTitle(tr("Direction"))
        self._lbl_dir_pos.setText(tr("Byte position:"))
        self._lbl_dir_bit.setText(tr("Bit number (0=LSB):"))
        self._lbl_dir_fwd1.setText(tr("Bit=1 means Forward:"))
        self._chk_dir_fwd1.setText("")

        self._grp_cs.setTitle(tr("Checksum"))
        self._lbl_cs_algo.setText(tr("Algorithm:"))
        self._lbl_cs_pos.setText(tr("Byte position:"))

        self._grp_fn.setTitle(tr("Functions (F0–F7+)"))
        self._fn_table.setHorizontalHeaderLabels([
            tr("Byte pos"), tr("Bit"), tr("Enabled"),
        ])
        rows = self._fn_table.rowCount()
        self._fn_table.setVerticalHeaderLabels([f"F{i}" for i in range(rows)])

        self._btn_generate.setText(tr("Generate Sketch"))
        self._lbl_output.setText(tr("Generated Arduino sketch:"))
        self._btn_copy.setText(tr("Copy"))
        self._btn_save.setText(tr("Save .ino"))

        self._mode_tabs.setTabText(0, tr("Locomotive"))
        self._mode_tabs.setTabText(1, tr("Switch / Accessory"))

        # Switch form labels
        self._sw_grp_pkt.setTitle(tr("Packet"))
        self._sw_lbl_pkt_len.setText(tr("Packet length (bytes):"))
        self._sw_grp_addr.setTitle(tr("Switch Address"))
        self._sw_lbl_addr_pos.setText(tr("Byte position:"))
        self._sw_lbl_addr_mask.setText(tr("Address bitmask (hex):"))
        self._sw_grp_dir.setTitle(tr("Switch Direction"))
        self._sw_lbl_dir_pos.setText(tr("Byte position:"))
        self._sw_lbl_dir_bit.setText(tr("Bit number (0=LSB):"))
        self._sw_lbl_polarity.setText(tr("PLUS=1 (plus is bit=1):"))
        self._sw_grp_cs.setTitle(tr("Checksum"))
        self._sw_lbl_cs_algo.setText(tr("Algorithm:"))
        self._sw_lbl_cs_pos.setText(tr("Byte position:"))
        self._sw_btn_generate.setText(tr("Generate Switch Sketch"))

    # ================================================================ #
    # Code generation                                                    #
    # ================================================================ #

    def _build_switch_form(self) -> QScrollArea:
        """Build the Switch/Accessory parameter form and return its QScrollArea."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)
        form_layout.setContentsMargins(8, 8, 8, 8)
        form_layout.setSpacing(8)
        scroll.setWidget(form_widget)

        # Packet length
        self._sw_grp_pkt = QGroupBox()
        fl = QFormLayout(self._sw_grp_pkt)
        self._sw_spin_pkt_len = QSpinBox()
        self._sw_spin_pkt_len.setRange(1, 32)
        self._sw_spin_pkt_len.setValue(4)
        self._sw_lbl_pkt_len = QLabel()
        fl.addRow(self._sw_lbl_pkt_len, self._sw_spin_pkt_len)
        form_layout.addWidget(self._sw_grp_pkt)

        # Switch address
        self._sw_grp_addr = QGroupBox()
        fl2 = QFormLayout(self._sw_grp_addr)
        self._sw_spin_addr_pos = QSpinBox()
        self._sw_spin_addr_pos.setRange(0, 31)
        self._sw_spin_addr_pos.setValue(0)
        self._sw_spin_addr_pos.setToolTip(
            "Позиция байта, содержащего адрес стрелки (с 0).\n"
            "Ищите поле, значение которого меняется при переключении\n"
            "между разными стрелками и найдено в 'Адрес' Signal Finder."
        )
        self._sw_edit_addr_mask = QLineEdit("0x0F")
        self._sw_edit_addr_mask.setToolTip(
            "Битовая маска адреса в hex (например 0x0F = 4 бит = адреса 0–15).\n"
            "Определяется диапазоном бит из Signal Finder."
        )
        self._sw_lbl_addr_pos  = QLabel()
        self._sw_lbl_addr_mask = QLabel()
        fl2.addRow(self._sw_lbl_addr_pos,  self._sw_spin_addr_pos)
        fl2.addRow(self._sw_lbl_addr_mask, self._sw_edit_addr_mask)
        form_layout.addWidget(self._sw_grp_addr)

        # Switch direction
        self._sw_grp_dir = QGroupBox()
        fl3 = QFormLayout(self._sw_grp_dir)
        self._sw_spin_dir_pos = QSpinBox()
        self._sw_spin_dir_pos.setRange(0, 31)
        self._sw_spin_dir_pos.setValue(1)
        self._sw_spin_dir_pos.setToolTip(
            "Позиция байта, содержащего бит направления стрелки (с 0)."
        )
        self._sw_spin_dir_bit = QSpinBox()
        self._sw_spin_dir_bit.setRange(0, 7)
        self._sw_spin_dir_bit.setValue(3)
        self._sw_spin_dir_bit.setToolTip(
            "Номер бита направления: 0=LSB, 7=MSB.\n"
            "Найден в колонке 'Направление' Signal Finder."
        )
        self._sw_combo_polarity = QComboBox()
        self._sw_combo_polarity.addItems(["PLUS = bit 1", "PLUS = bit 0"])
        self._sw_combo_polarity.setToolTip(
            "PLUS = bit 1: бит=1 означает положение PLUS (по умолчанию).\n"
            "PLUS = bit 0: бит=0 означает положение PLUS."
        )
        self._sw_lbl_dir_pos  = QLabel()
        self._sw_lbl_dir_bit  = QLabel()
        self._sw_lbl_polarity = QLabel()
        fl3.addRow(self._sw_lbl_dir_pos,  self._sw_spin_dir_pos)
        fl3.addRow(self._sw_lbl_dir_bit,  self._sw_spin_dir_bit)
        fl3.addRow(self._sw_lbl_polarity, self._sw_combo_polarity)
        form_layout.addWidget(self._sw_grp_dir)

        # Checksum
        self._sw_grp_cs = QGroupBox()
        fl4 = QFormLayout(self._sw_grp_cs)
        self._sw_combo_cs_algo = QComboBox()
        self._sw_combo_cs_algo.addItems(_CS_ALGOS)
        self._sw_spin_cs_pos = QSpinBox()
        self._sw_spin_cs_pos.setRange(0, 31)
        self._sw_spin_cs_pos.setValue(3)
        self._sw_lbl_cs_algo = QLabel()
        self._sw_lbl_cs_pos  = QLabel()
        fl4.addRow(self._sw_lbl_cs_algo, self._sw_combo_cs_algo)
        fl4.addRow(self._sw_lbl_cs_pos,  self._sw_spin_cs_pos)
        form_layout.addWidget(self._sw_grp_cs)

        # Generate button
        self._sw_btn_generate = QPushButton()
        self._sw_btn_generate.clicked.connect(self._generate_switch)
        self._sw_btn_generate.setToolTip(
            "Сгенерировать Arduino скетч для управления стрелкой/аксессуаром.\n"
            "Скетч содержит функцию throwSwitch(address, plus)."
        )
        form_layout.addWidget(self._sw_btn_generate)
        form_layout.addStretch()

        return scroll

    def prefill_switch(self, result: object) -> None:
        """Pre-fill switch form from a ProfileAnalysisResult (from Signal Finder)."""
        fields = getattr(result, "fields", [])
        addr_fields = [f for f in fields if f.name == "address"]
        dir_fields  = [f for f in fields if f.name == "direction"]

        if addr_fields:
            best = addr_fields[0]
            self._sw_spin_addr_pos.setValue(best.byte_pos)
            mask = sum(1 << b for b in range(best.bit_low, best.bit_high + 1))
            self._sw_edit_addr_mask.setText(f"0x{mask:02X}")

        if dir_fields:
            best = dir_fields[0]
            self._sw_spin_dir_pos.setValue(best.byte_pos)
            self._sw_spin_dir_bit.setValue(best.bit_low)
            self._sw_combo_polarity.setCurrentIndex(0)  # assume PLUS = bit 1

        # Switch to the switch tab and auto-generate
        self._mode_tabs.setCurrentIndex(1)
        self._generate_switch()

    def _generate(self) -> None:
        if self._mode_tabs.currentIndex() == 1:
            self._generate_switch()
        else:
            self._code_edit.setPlainText(self._build_sketch())

    def _generate_switch(self) -> None:
        self._code_edit.setPlainText(self._build_switch_sketch())

    def _build_switch_sketch(self) -> str:
        pkt_len   = self._sw_spin_pkt_len.value()
        addr_pos  = self._sw_spin_addr_pos.value()
        addr_mask = self._parse_hex(self._sw_edit_addr_mask.text(), 0x0F)
        dir_pos   = self._sw_spin_dir_pos.value()
        dir_bit   = self._sw_spin_dir_bit.value()
        plus_is_1 = self._sw_combo_polarity.currentIndex() == 0
        cs_algo   = self._sw_combo_cs_algo.currentText()
        cs_pos    = self._sw_spin_cs_pos.value()

        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        cs_func = _gen_checksum_func(cs_algo, cs_pos)
        cs_call = (
            f"    g_pkt[{cs_pos}] = calcChecksum();"
            if cs_algo != "None" else
            "    // (no checksum)"
        )

        return f"""\
// =============================================================
// PIKO SmartControl Protocol Analyzer — Generated Sketch
// Device type : Switch / Accessory Decoder
// Generated   : {ts}
// Tool        : https://github.com/Shtilluz/piko-analyzer
// =============================================================
// WARNING: This code is based on EXPERIMENTALLY DISCOVERED
// packet structure. Verify all constants before operating
// real hardware. Wrong packets may damage equipment.
// =============================================================

#include <Arduino.h>

// ---- Discovered packet constants ----
const uint8_t PKT_LEN      = {pkt_len};    // total packet length, bytes

const uint8_t SW_ADDR_BYTE = {addr_pos};   // byte position of switch address
const uint8_t SW_ADDR_MASK = 0x{addr_mask:02X};  // address bitmask

const uint8_t SW_DIR_BYTE  = {dir_pos};   // byte position of direction bit
const uint8_t SW_DIR_BIT   = {dir_bit};   // bit number (0=LSB)
const bool    SW_PLUS_IS_1 = {'true' if plus_is_1 else 'false'};  // true: bit=1 means PLUS

const uint8_t CS_POS       = {cs_pos};   // checksum byte position (algorithm: {cs_algo})

// ---- Runtime packet buffer ----
uint8_t g_pkt[PKT_LEN];

void setup() {{
    Serial.begin(115200);
    memset(g_pkt, 0, PKT_LEN);
    Serial.println("PIKO Switch Sketch ready.");
}}

// ---- Checksum ----
{cs_func}

// ---- Throw a switch to PLUS or MINUS position ----
void throwSwitch(uint8_t address, bool plus) {{
    memset(g_pkt, 0, PKT_LEN);

    // Set address field
    g_pkt[SW_ADDR_BYTE] = (g_pkt[SW_ADDR_BYTE] & ~SW_ADDR_MASK)
                          | (address & SW_ADDR_MASK);

    // Set direction bit
    if (SW_PLUS_IS_1 ? plus : !plus)
        g_pkt[SW_DIR_BYTE] |=  (1 << SW_DIR_BIT);
    else
        g_pkt[SW_DIR_BYTE] &= ~(1 << SW_DIR_BIT);

    // Checksum
{cs_call}

    // === TODO: Replace Serial.write with your physical bus driver ===
    Serial.write(g_pkt, PKT_LEN);
}}

// ---- Example loop ----
void loop() {{
    // Cycle through switches 1–4
    for (uint8_t sw = 1; sw <= 4; sw++) {{
        throwSwitch(sw, true);   // PLUS
        delay(1000);
        throwSwitch(sw, false);  // MINUS
        delay(1000);
    }}
}}
"""

    def _build_sketch(self) -> str:
        pkt_len    = self._spin_pkt_len.value()
        addr_pos   = self._spin_addr_pos.value()
        addr_val   = self._parse_hex(self._edit_addr_val.text(), 0x03)
        speed_pos  = self._spin_speed_pos.value()
        speed_mask = self._parse_hex(self._edit_speed_mask.text(), 0x7F)
        speed_max  = self._spin_speed_max.value()
        dir_pos    = self._spin_dir_pos.value()
        dir_bit    = self._spin_dir_bit.value()
        dir_fwd1   = self._chk_dir_fwd1.isChecked()
        cs_algo    = self._combo_cs_algo.currentText()
        cs_pos     = self._spin_cs_pos.value()

        # Functions
        fn_rows = []
        for row in range(self._fn_table.rowCount()):
            bp  = self._fn_table.cellWidget(row, 0)
            bt  = self._fn_table.cellWidget(row, 1)
            chk = self._fn_table.cellWidget(row, 2)
            if chk and chk.isChecked():
                fn_rows.append((row, bp.value(), bt.value()))

        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

        fn_defs = ",\n    ".join(
            f"{{{row}, {bp}, {bt}}}  // F{row}"
            for row, bp, bt in fn_rows
        ) or "// no functions defined"

        cs_func = _gen_checksum_func(cs_algo, cs_pos)
        cs_call = (
            f"    g_pkt[{cs_pos}] = calcChecksum();"
            if cs_algo != "None" else
            f"    // (no checksum)"
        )

        return f"""\
// =============================================================
// PIKO SmartControl Protocol Analyzer — Generated Sketch
// Generated : {ts}
// Tool      : https://github.com/Shtilluz/piko-analyzer
// =============================================================
// WARNING: This code is based on EXPERIMENTALLY DISCOVERED
// packet structure. Verify all constants before operating
// real hardware. Wrong packets may damage equipment.
// =============================================================

#include <Arduino.h>

// ---- Discovered packet constants (edit if needed) ----
const uint8_t PKT_LEN    = {pkt_len};      // total packet length, bytes
const uint8_t ADDR_POS   = {addr_pos};       // decoder address byte position
const uint8_t ADDR_VAL   = 0x{addr_val:02X};     // decoder address value

const uint8_t SPEED_POS  = {speed_pos};       // speed field byte position
const uint8_t SPEED_MASK = 0x{speed_mask:02X};     // speed bitmask within the byte
const uint8_t SPEED_MAX  = {speed_max};     // maximum speed value

const uint8_t DIR_POS    = {dir_pos};       // direction byte position
const uint8_t DIR_BIT    = {dir_bit};       // direction bit number (0=LSB)
const bool    DIR_FWD_1  = {'true' if dir_fwd1 else 'false'};  // true: bit=1 means FORWARD

const uint8_t CS_POS     = {cs_pos};       // checksum byte position (algorithm: {cs_algo})

// ---- Functions table: {{fn_num, byte_pos, bit_pos}} ----
struct FnDef {{ uint8_t fn; uint8_t byte_pos; uint8_t bit_pos; }};
const FnDef FUNCTIONS[] = {{
    {fn_defs}
}};
const uint8_t FN_COUNT = sizeof(FUNCTIONS) / sizeof(FUNCTIONS[0]);

// ---- Runtime state ----
uint8_t g_pkt[PKT_LEN];
uint8_t g_speed   = 0;
bool    g_forward = true;
bool    g_fn[29]  = {{}};    // F0..F28

void setup() {{
    Serial.begin(115200);
    memset(g_pkt, 0, PKT_LEN);
    g_pkt[ADDR_POS] = ADDR_VAL;
    Serial.println("PIKO Sketch ready.");
}}

// ---- Checksum ----
{cs_func}

// ---- Build packet from state and send ----
void buildAndSend() {{
    // Speed
    g_pkt[SPEED_POS] = (g_pkt[SPEED_POS] & ~SPEED_MASK) | (g_speed & SPEED_MASK);

    // Direction
    if (DIR_FWD_1 ? g_forward : !g_forward)
        g_pkt[DIR_POS] |=  (1 << DIR_BIT);
    else
        g_pkt[DIR_POS] &= ~(1 << DIR_BIT);

    // Functions
    for (uint8_t i = 0; i < FN_COUNT; i++) {{
        if (g_fn[FUNCTIONS[i].fn])
            g_pkt[FUNCTIONS[i].byte_pos] |=  (1 << FUNCTIONS[i].bit_pos);
        else
            g_pkt[FUNCTIONS[i].byte_pos] &= ~(1 << FUNCTIONS[i].bit_pos);
    }}

    // Checksum
{cs_call}

    // === TODO: Replace Serial.write with your physical bus driver ===
    // The PIKO SmartControl bus uses a specific physical layer.
    // Until you implement it, this sends the raw bytes over USB Serial
    // so you can inspect them from the PC.
    Serial.write(g_pkt, PKT_LEN);
}}

// ---- Public API ----

void setSpeed(uint8_t speed) {{
    g_speed = constrain(speed, 0, SPEED_MAX);
    buildAndSend();
}}

void setDirection(bool forward) {{
    g_forward = forward;
    buildAndSend();
}}

void setFunction(uint8_t fn, bool on) {{
    if (fn < 29) g_fn[fn] = on;
    buildAndSend();
}}

// ---- Example loop ----
void loop() {{
    // Ramp speed up then down
    for (uint8_t s = 0; s <= SPEED_MAX; s++) {{
        setSpeed(s);
        delay(100);
    }}
    delay(1000);
    for (uint8_t s = SPEED_MAX; s > 0; s--) {{
        setSpeed(s);
        delay(100);
    }}
    delay(1000);

    // Toggle direction
    setDirection(true);   delay(2000);
    setDirection(false);  delay(2000);

    // Toggle F0 (headlight)
    setFunction(0, true);   delay(1000);
    setFunction(0, false);  delay(1000);
}}
"""

    # ================================================================ #
    # Helpers                                                            #
    # ================================================================ #

    @staticmethod
    def _parse_hex(text: str, default: int) -> int:
        text = text.strip().lower().replace("0x", "")
        try:
            return int(text, 16)
        except ValueError:
            return default

    def _copy_code(self) -> None:
        text = self._code_edit.toPlainText()
        if text:
            QApplication.clipboard().setText(text)

    def _save_ino(self) -> None:
        text = self._code_edit.toPlainText()
        if not text:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, tr("Save .ino"), "piko_sketch.ino", "Arduino sketch (*.ino)"
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)


# ------------------------------------------------------------------ #
# Checksum C code snippets                                            #
# ------------------------------------------------------------------ #

def _gen_checksum_func(algo: str, cs_pos: int) -> str:
    if algo == "None":
        return "// No checksum configured."

    body_map = {
        "XOR":       f"    uint8_t cs = 0;\n    for (uint8_t i = 0; i < {cs_pos}; i++) cs ^= g_pkt[i];\n    return cs;",
        "SUM8":      f"    uint8_t cs = 0;\n    for (uint8_t i = 0; i < {cs_pos}; i++) cs += g_pkt[i];\n    return cs & 0xFF;",
        "SUM8_NEG":  f"    uint8_t cs = 0;\n    for (uint8_t i = 0; i < {cs_pos}; i++) cs += g_pkt[i];\n    return (-cs) & 0xFF;",
        "SUM8_COMP2":f"    uint8_t cs = 0;\n    for (uint8_t i = 0; i < {cs_pos}; i++) cs += g_pkt[i];\n    return (~cs + 1) & 0xFF;",
        "CRC8":      (
            f"    uint8_t cs = 0x00;\n"
            f"    for (uint8_t i = 0; i < {cs_pos}; i++) {{\n"
            f"        cs ^= g_pkt[i];\n"
            f"        for (uint8_t b = 0; b < 8; b++)\n"
            f"            cs = (cs & 0x80) ? (cs << 1) ^ 0x07 : (cs << 1);\n"
            f"    }}\n"
            f"    return cs;"
        ),
    }
    body = body_map.get(algo, "    return 0;  // unknown algorithm")
    return (
        f"uint8_t calcChecksum() {{  // algorithm: {algo}\n"
        f"{body}\n"
        f"}}"
    )
