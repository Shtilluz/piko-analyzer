"""
Main application window.
"""

from __future__ import annotations

import os
import time
from datetime import datetime

from PySide6.QtCore    import Qt, QTimer, Slot
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QGroupBox, QTabWidget,
    QSplitter, QStatusBar, QFileDialog, QMessageBox,
)

from analyzer              import config
from analyzer.i18n         import tr, set_language, on_language_changed, LANGUAGES
from analyzer.models       import RawEdge
from analyzer.serial_reader import SerialThread, list_ports
from analyzer.packet_parser import EdgeAccumulator, RingBuffer
from analyzer.statistics    import PacketStats
from analyzer.transition_analysis import TransitionTracker
from analyzer.action_recorder     import ActionRecorder
from analyzer.checksum_analysis   import find_checksum_candidates
from analyzer.bit_analysis        import compute_byte_stats, compute_bit_stats
from analyzer.session             import SessionManager

from analyzer.gui.packet_table      import PacketTableWidget
from analyzer.gui.byte_analysis     import ByteAnalysisWidget
from analyzer.gui.bit_analysis_view import BitAnalysisWidget
from analyzer.gui.action_view       import ActionWidget
from analyzer.gui.charts            import ChartsWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(tr("PIKO SmartControl Protocol Analyzer"))
        self.resize(1280, 800)

        self._serial_thread: SerialThread | None = None
        self._packet_stats   = PacketStats()
        self._transitions    = TransitionTracker()
        self._edge_buf       = RingBuffer()
        self._edge_accum     = EdgeAccumulator()
        self._edge_accum.on_packet(self._on_parsed_packet)
        self._capture_start  = 0.0
        self._session_mgr    = SessionManager()
        self._action_rec     = ActionRecorder(config.ACTION_FILE)
        self._checksum_cache: list = []
        self._ordered_pkts: list[bytes] = []

        self._build_ui()
        self._setup_refresh_timer()
        self._refresh_ports()

        on_language_changed(self._retranslate_ui)

    # ================================================================ #
    # UI construction                                                    #
    # ================================================================ #

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 6)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter)

        left = QWidget()
        left.setMinimumWidth(260)
        left.setMaximumWidth(320)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self._grp_serial  = self._build_serial_group()
        self._grp_stats   = self._build_stats_group()
        self._grp_actions = self._build_actions_group()

        left_layout.addWidget(self._grp_serial)
        left_layout.addWidget(self._grp_stats)
        left_layout.addWidget(self._grp_actions)
        left_layout.addStretch()
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 0, 0, 0)

        self._packet_table = PacketTableWidget()
        right_layout.addWidget(self._packet_table, 2)

        self._tabs = QTabWidget()
        right_layout.addWidget(self._tabs, 3)

        self._byte_view   = ByteAnalysisWidget()
        self._bit_view    = BitAnalysisWidget()
        self._action_view = ActionWidget(self._action_rec)
        self._charts_view = ChartsWidget()

        self._tabs.addTab(self._byte_view,   tr("Byte Analysis"))
        self._tabs.addTab(self._bit_view,    tr("Bit Analysis"))
        self._tabs.addTab(self._action_view, tr("Actions"))
        self._tabs.addTab(self._charts_view, tr("Charts"))

        # Checksum tab
        self._checksum_label = QLabel(tr("No data yet."))
        self._checksum_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._checksum_label.setWordWrap(True)
        cs_wrapper = QWidget()
        cs_layout  = QVBoxLayout(cs_wrapper)
        self._btn_run_cs = QPushButton(tr("Run Checksum Analysis"))
        self._btn_run_cs.clicked.connect(self._run_checksum)
        cs_layout.addWidget(self._btn_run_cs)
        cs_layout.addWidget(self._checksum_label)
        cs_layout.addStretch()
        self._tabs.addTab(cs_wrapper, tr("Checksum"))

        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage(tr("Ready"))

        self._build_menu()

    def _build_serial_group(self) -> QGroupBox:
        grp = QGroupBox(tr("Serial"))
        layout = QVBoxLayout(grp)

        row1 = QHBoxLayout()
        self._lbl_port = QLabel(tr("Port:"))
        row1.addWidget(self._lbl_port)
        self._port_combo = QComboBox()
        self._port_combo.setMinimumWidth(100)
        row1.addWidget(self._port_combo)
        btn_refresh = QPushButton("↺")
        btn_refresh.setFixedWidth(28)
        btn_refresh.clicked.connect(self._refresh_ports)
        row1.addWidget(btn_refresh)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        self._lbl_baud = QLabel(tr("Baud:"))
        row2.addWidget(self._lbl_baud)
        self._baud_combo = QComboBox()
        for b in ["9600", "57600", "115200", "230400", "500000", "1000000"]:
            self._baud_combo.addItem(b)
        self._baud_combo.setCurrentText(str(config.DEFAULT_BAUDRATE))
        row2.addWidget(self._baud_combo)
        layout.addLayout(row2)

        btn_row = QHBoxLayout()
        self._btn_connect    = QPushButton(tr("Connect"))
        self._btn_disconnect = QPushButton(tr("Disconnect"))
        self._btn_disconnect.setEnabled(False)
        self._btn_connect.clicked.connect(self._connect)
        self._btn_disconnect.clicked.connect(self._disconnect)
        btn_row.addWidget(self._btn_connect)
        btn_row.addWidget(self._btn_disconnect)
        layout.addLayout(btn_row)

        return grp

    def _build_stats_group(self) -> QGroupBox:
        grp = QGroupBox(tr("Statistics"))
        layout = QVBoxLayout(grp)

        self._lbl_packets  = QLabel(tr("Packets: 0"))
        self._lbl_unique   = QLabel(tr("Unique: 0"))
        self._lbl_duration = QLabel(tr("Duration: 00:00:00"))
        self._lbl_dropped  = QLabel(tr("Dropped: 0"))

        for lbl in (self._lbl_packets, self._lbl_unique,
                    self._lbl_duration, self._lbl_dropped):
            layout.addWidget(lbl)

        return grp

    def _build_actions_group(self) -> QGroupBox:
        grp = QGroupBox(tr("Quick Actions"))
        layout = QVBoxLayout(grp)

        self._btn_raw_cap = QPushButton(tr("Start Raw Capture"))
        self._btn_raw_cap.clicked.connect(self._start_raw_capture)
        layout.addWidget(self._btn_raw_cap)

        self._btn_reset = QPushButton(tr("Reset Statistics"))
        self._btn_reset.clicked.connect(self._reset_stats)
        layout.addWidget(self._btn_reset)

        return grp

    def _build_menu(self) -> None:
        mb = self.menuBar()
        mb.clear()

        # File menu
        self._menu_file = mb.addMenu(tr("File"))
        self._act_save   = self._menu_file.addAction(tr("Save Session"), self._save_session)
        self._act_csv    = self._menu_file.addAction(tr("Export CSV…"),  self._export_csv)
        self._menu_file.addSeparator()
        self._act_quit   = self._menu_file.addAction(tr("Quit"), self.close)

        # Capture menu
        self._menu_capture = mb.addMenu(tr("Capture"))
        self._act_reset  = self._menu_capture.addAction(tr("Reset Statistics"), self._reset_stats)
        self._act_rawcap = self._menu_capture.addAction(tr("Start Raw Capture"), self._start_raw_capture)
        self._act_stop   = self._menu_capture.addAction(tr("Stop Capture"), self._stop_capture)

        # Language menu
        self._menu_lang = mb.addMenu(tr("Language"))
        for code, name in LANGUAGES.items():
            action = self._menu_lang.addAction(name)
            action.setData(code)
            action.triggered.connect(lambda checked=False, c=code: self._change_language(c))

    # ================================================================ #
    # Retranslation (live language switch)                               #
    # ================================================================ #

    def _retranslate_ui(self, _lang: str = "") -> None:
        self.setWindowTitle(tr("PIKO SmartControl Protocol Analyzer"))

        # Serial group
        self._grp_serial.setTitle(tr("Serial"))
        self._lbl_port.setText(tr("Port:"))
        self._lbl_baud.setText(tr("Baud:"))
        self._btn_connect.setText(tr("Connect"))
        self._btn_disconnect.setText(tr("Disconnect"))

        # Stats group
        self._grp_stats.setTitle(tr("Statistics"))
        self._grp_actions.setTitle(tr("Quick Actions"))
        self._btn_raw_cap.setText(tr("Start Raw Capture"))
        self._btn_reset.setText(tr("Reset Statistics"))

        # Static stat labels (dynamic ones are updated in _refresh_ui)
        self._lbl_dropped.setText(tr("Dropped: 0"))

        # Tabs
        self._tabs.setTabText(0, tr("Byte Analysis"))
        self._tabs.setTabText(1, tr("Bit Analysis"))
        self._tabs.setTabText(2, tr("Actions"))
        self._tabs.setTabText(3, tr("Charts"))
        self._tabs.setTabText(4, tr("Checksum"))

        # Checksum tab button
        self._btn_run_cs.setText(tr("Run Checksum Analysis"))

        # Rebuild menu with new language
        self._build_menu()

        # Forward to child widgets
        self._packet_table.retranslate_ui()
        self._byte_view.retranslate_ui()
        self._bit_view.retranslate_ui()
        self._action_view.retranslate_ui()
        self._charts_view.retranslate_ui()

    def _change_language(self, code: str) -> None:
        set_language(code)   # fires on_language_changed callbacks

    # ================================================================ #
    # Timer & refresh                                                    #
    # ================================================================ #

    def _setup_refresh_timer(self) -> None:
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(config.GUI_REFRESH_MS)
        self._refresh_timer.timeout.connect(self._refresh_ui)
        self._refresh_timer.start()

    def _refresh_ui(self) -> None:
        total   = self._packet_stats.total_count
        unique  = self._packet_stats.unique_count
        records = self._packet_stats.records_by_count()

        if self._capture_start > 0:
            elapsed = time.monotonic() - self._capture_start
            h = int(elapsed // 3600)
            m = int((elapsed % 3600) // 60)
            s = int(elapsed % 60)
            self._lbl_duration.setText(
                tr("Duration: {h}:{m}:{s}",
                   h=f"{h:02d}", m=f"{m:02d}", s=f"{s:02d}")
            )

        self._lbl_packets.setText(tr("Packets: {total}", total=f"{total:,}"))
        self._lbl_unique.setText(tr("Unique: {unique}",  unique=f"{unique:,}"))

        self._packet_table.update_records(records, total)

        weighted = [(r.data, r.count) for r in records]
        if weighted:
            byte_stats = compute_byte_stats(weighted)
            bit_stats  = compute_bit_stats(weighted)
            self._byte_view.update_stats(byte_stats)
            self._bit_view.update_stats(bit_stats)
            self._charts_view.update_data(records, byte_stats, self._ordered_pkts)

        self._action_view.refresh()

    # ================================================================ #
    # Serial connection                                                  #
    # ================================================================ #

    def _refresh_ports(self) -> None:
        current = self._port_combo.currentText()
        self._port_combo.clear()
        for p in list_ports():
            self._port_combo.addItem(p)
        idx = self._port_combo.findText(current)
        if idx >= 0:
            self._port_combo.setCurrentIndex(idx)

    def _connect(self) -> None:
        port     = self._port_combo.currentText()
        baudrate = int(self._baud_combo.currentText())
        if not port:
            QMessageBox.warning(self, tr("No port"), tr("Please select a serial port."))
            return
        self._serial_thread = SerialThread(port, baudrate, parent=self)
        self._serial_thread.edge_received.connect(self._on_edge)
        self._serial_thread.packet_received.connect(self._on_pkt_line)
        self._serial_thread.stat_received.connect(self._on_stat)
        self._serial_thread.connected.connect(self._on_connected)
        self._serial_thread.disconnected.connect(self._on_disconnected)
        self._serial_thread.status_message.connect(self._on_status_msg)
        self._serial_thread.start()

    def _disconnect(self) -> None:
        if self._serial_thread:
            self._edge_accum.flush_now()
            self._serial_thread.stop()
            self._serial_thread = None

    # ================================================================ #
    # Serial slots                                                       #
    # ================================================================ #

    @Slot(str)
    def _on_connected(self, port: str) -> None:
        self._btn_connect.setEnabled(False)
        self._btn_disconnect.setEnabled(True)
        self._capture_start = time.monotonic()
        self.statusBar().showMessage(tr("Connected: {port}", port=port))

    @Slot(str)
    def _on_disconnected(self, reason: str) -> None:
        self._btn_connect.setEnabled(True)
        self._btn_disconnect.setEnabled(False)
        self._capture_start = 0.0
        self.statusBar().showMessage(tr("Disconnected: {reason}", reason=reason))

    @Slot(str)
    def _on_status_msg(self, msg: str) -> None:
        self.statusBar().showMessage(msg, 3000)

    @Slot(RawEdge)
    def _on_edge(self, edge: RawEdge) -> None:
        self._edge_buf.append(edge)
        self._edge_accum.feed(edge)

    @Slot(int, bytes)
    def _on_pkt_line(self, timestamp_us: int, data: bytes) -> None:
        self._on_parsed_packet(timestamp_us, data, [])

    @Slot(int, int)
    def _on_stat(self, rx: int, dropped: int) -> None:
        self._lbl_dropped.setText(
            tr("Dropped (Arduino): {dropped}", dropped=f"{dropped:,}")
        )

    def _on_parsed_packet(self, timestamp_us: int, data: bytes, raw_edges: list) -> None:
        if not data:
            return
        self._packet_stats.add_packet(timestamp_us, data)
        self._transitions.feed_packet(data)
        self._action_rec.feed_packet(data)
        self._ordered_pkts.append(data)
        if len(self._ordered_pkts) > config.LIVE_RING_SIZE:
            self._ordered_pkts = self._ordered_pkts[-config.LIVE_RING_SIZE:]

    # ================================================================ #
    # Capture controls                                                   #
    # ================================================================ #

    def _start_raw_capture(self) -> None:
        if self._serial_thread:
            self._serial_thread.send_command("RAW")
        self._capture_start = time.monotonic()
        self.statusBar().showMessage(tr("Raw capture started"))

    def _stop_capture(self) -> None:
        if self._serial_thread:
            self._serial_thread.send_command("STOP")
            self._edge_accum.flush_now()
        self.statusBar().showMessage(tr("Capture stopped"))

    def _reset_stats(self) -> None:
        self._packet_stats.reset()
        self._transitions.reset()
        self._ordered_pkts.clear()
        self._edge_buf.clear()
        if self._serial_thread:
            self._serial_thread.send_command("RST")
        self.statusBar().showMessage(tr("Statistics reset"))

    # ================================================================ #
    # Checksum                                                           #
    # ================================================================ #

    def _run_checksum(self) -> None:
        records  = self._packet_stats.records_by_count()
        weighted = [(r.data, r.count) for r in records]
        if not weighted:
            self._checksum_label.setText(tr("No packets captured yet."))
            return

        candidates = find_checksum_candidates(
            weighted,
            algorithms=config.CHECKSUM_ALGORITHMS,
            min_match_pct=50.0,
        )
        self._checksum_cache = candidates

        if not candidates:
            self._checksum_label.setText(
                tr("No checksum candidates found (all algorithms < 50% match).")
            )
            return

        lines = [
            tr("<b>Checksum Candidates</b><br>"),
            "<table>",
            f"<tr><th>{tr('Algorithm')}</th>"
            f"<th>{tr('Byte pos')}</th>"
            f"<th>{tr('Match %')}</th></tr>",
        ]
        for c in candidates[:20]:
            lines.append(
                f"<tr><td>{c.algorithm}</td>"
                f"<td>{c.byte_position}</td>"
                f"<td>{c.match_pct:.1f}%</td></tr>"
            )
        lines.append("</table>")
        self._checksum_label.setText("\n".join(lines))

    # ================================================================ #
    # Session / export                                                   #
    # ================================================================ #

    def _save_session(self) -> None:
        records    = self._packet_stats.records_by_count()
        weighted   = [(r.data, r.count) for r in records]
        byte_stats = compute_byte_stats(weighted)
        bit_stats  = compute_bit_stats(weighted)
        if not self._checksum_cache and weighted:
            self._checksum_cache = find_checksum_candidates(
                weighted, algorithms=config.CHECKSUM_ALGORITHMS
            )
        elapsed = (
            time.monotonic() - self._capture_start
            if self._capture_start > 0 else 0.0
        )
        path = self._session_mgr.save(
            packet_stats        = self._packet_stats,
            byte_stats          = byte_stats,
            bit_stats           = bit_stats,
            transition_tracker  = self._transitions,
            action_recorder     = self._action_rec,
            checksum_candidates = self._checksum_cache,
            port                = self._port_combo.currentText(),
            duration_s          = elapsed,
        )
        QMessageBox.information(self, tr("Session saved"),
                                tr("Saved to:\n{path}", path=path))

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, tr("Export CSV…"), "", "CSV files (*.csv)"
        )
        if path:
            self._session_mgr.export_csv(self._packet_stats, path)
            QMessageBox.information(self, tr("Exported"),
                                    tr("Exported to:\n{path}", path=path))
