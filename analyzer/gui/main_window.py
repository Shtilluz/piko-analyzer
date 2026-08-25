"""
Main application window.
"""

from __future__ import annotations

import os
import time

from PySide6.QtCore    import Qt, QTimer, Slot
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QGroupBox, QTabWidget,
    QSplitter, QStatusBar, QFileDialog, QMessageBox,
)

from analyzer              import config
from analyzer.i18n         import tr, set_language, on_language_changed, LANGUAGES
from analyzer.logger       import get_logger, install_qt_handler
from analyzer.version      import APP_NAME, VERSION, AUTHOR, REPO
from analyzer.models       import RawEdge
from analyzer.serial_reader import SerialThread, list_ports
from analyzer.packet_parser import EdgeAccumulator, RingBuffer
from analyzer.statistics    import PacketStats
from analyzer.transition_analysis import TransitionTracker
from analyzer.action_recorder     import ActionRecorder
from analyzer.checksum_analysis   import find_checksum_candidates
from analyzer.bit_analysis        import compute_byte_stats, compute_bit_stats
from analyzer.session             import SessionManager

from analyzer.gui.packet_table       import PacketTableWidget
from analyzer.gui.byte_analysis      import ByteAnalysisWidget
from analyzer.gui.bit_analysis_view  import BitAnalysisWidget
from analyzer.gui.action_view        import ActionWidget
from analyzer.gui.signal_finder_view import SignalFinderWidget
from analyzer.gui.charts             import ChartsWidget
from analyzer.gui.log_view           import LogViewWidget
from analyzer.gui.sketch_generator   import SketchGeneratorWidget
from analyzer.gui.help_view          import HelpViewWidget

log = get_logger(__name__)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{VERSION}")
        self.resize(1280, 820)

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

        # Counters for live diagnostics
        self._edges_per_tick  = 0
        self._pkts_per_tick   = 0
        self._raw_lines_total = 0
        self._last_edge_time  = 0.0   # monotonic, for stale-flush detection
        self._no_pkts_warned  = False  # warn once when edges arrive but no packets

        self._build_ui()
        self._setup_refresh_timer()
        self._refresh_ports()

        # Connect logger → log panel AFTER widget exists
        install_qt_handler(self._log_view.append_record)
        on_language_changed(self._retranslate_ui)

        log.info(f"Запуск {APP_NAME} v{VERSION} by {AUTHOR}")
        log.info(f"Репозиторий: {REPO}")
        log.info(f"Лог файл: {os.path.abspath('data/piko_analyzer.log')}")

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

        # ---- Left panel ----
        left = QWidget()
        left.setMinimumWidth(270)
        left.setMaximumWidth(330)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self._grp_serial  = self._build_serial_group()
        self._grp_stats   = self._build_stats_group()
        self._grp_diag    = self._build_diag_group()
        self._grp_actions = self._build_actions_group()

        left_layout.addWidget(self._grp_serial)
        left_layout.addWidget(self._grp_stats)
        left_layout.addWidget(self._grp_diag)
        left_layout.addWidget(self._grp_actions)
        left_layout.addStretch()
        splitter.addWidget(left)

        # ---- Right panel ----
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 0, 0, 0)

        self._packet_table = PacketTableWidget()
        right_layout.addWidget(self._packet_table, 2)

        self._tabs = QTabWidget()
        right_layout.addWidget(self._tabs, 3)

        self._byte_view          = ByteAnalysisWidget()
        self._bit_view           = BitAnalysisWidget()
        self._action_view        = ActionWidget(self._action_rec)
        self._signal_finder_view = SignalFinderWidget()
        self._charts_view        = ChartsWidget()
        self._sketch_view        = SketchGeneratorWidget()
        self._help_view          = HelpViewWidget()
        self._log_view           = LogViewWidget()

        self._tabs.addTab(self._byte_view,           tr("Byte Analysis"))   # 0
        self._tabs.addTab(self._bit_view,            tr("Bit Analysis"))    # 1
        self._tabs.addTab(self._action_view,         tr("Actions"))         # 2
        self._tabs.addTab(self._signal_finder_view,  tr("Signal Finder"))   # 3
        self._tabs.addTab(self._charts_view,         tr("Charts"))          # 4

        # Checksum tab
        cs_wrapper = QWidget()
        cs_layout  = QVBoxLayout(cs_wrapper)
        self._btn_run_cs = QPushButton(tr("Run Checksum Analysis"))
        self._btn_run_cs.setToolTip(
            "Перебрать алгоритмы контрольных сумм (XOR, SUM8, CRC8, CRC8-MAXIM, ...)\n"
            "для каждой позиции байта. Показывает байты, которые с высокой вероятностью\n"
            "являются полем контрольной суммы. Требует накопленные пакеты."
        )
        self._checksum_label = QLabel(tr("No data yet."))
        self._checksum_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._checksum_label.setWordWrap(True)
        self._checksum_label.setToolTip(
            "Результаты: алгоритм, позиция байта и процент совпадений.\n"
            "Кандидат с ≥90% совпадений скорее всего является контрольной суммой."
        )
        self._btn_run_cs.clicked.connect(self._run_checksum)
        cs_layout.addWidget(self._btn_run_cs)
        cs_layout.addWidget(self._checksum_label)
        cs_layout.addStretch()
        self._tabs.addTab(cs_wrapper,          tr("Checksum"))          # 5
        self._tabs.addTab(self._sketch_view,   tr("Sketch Generator"))  # 6
        self._tabs.addTab(self._help_view,     tr("Instructions"))      # 7
        self._tabs.addTab(self._log_view,      "Лог")                   # 8

        # Connect Signal Finder → Sketch Generator
        self._signal_finder_view.export_requested.connect(
            self._sketch_view.prefill_switch
        )

        # Tooltips for tabs
        self._tabs.setTabToolTip(0,
            "Статистика по каждой позиции байта: распределение значений,\n"
            "топ-10 значений, метка постоянства (CONSTANT / MOSTLY_CONSTANT / VARIABLE)."
        )
        self._tabs.setTabToolTip(1,
            "Детальный анализ каждого отдельного бита: как часто бит равен 0 или 1,\n"
            "как часто он меняется между пакетами (transition%). Помогает находить\n"
            "флаги, адреса и поля данных."
        )
        self._tabs.setTabToolTip(2,
            "Запись и сравнение действий контроллера.\n"
            "Схема: 1) Сбор базовой линии (покой) → 2) Отметить действие → 3) Стоп.\n"
            "Показывает какие байты изменились при выполнении действия."
        )
        self._tabs.setTabToolTip(3,
            "Автоматический поиск полей управления стрелками, светофорами, реле.\n"
            "Анализирует записанные действия и находит поля адреса и направления.\n"
            "Используйте «Быстрые метки» во вкладке Действия для записи sw_N_plus/minus."
        )
        self._tabs.setTabToolTip(4,
            "Графики: топ пакетов по частоте, динамика значения байта во времени,\n"
            "длина пакетов во времени, гистограмма распределения значений."
        )
        self._tabs.setTabToolTip(5,
            "Поиск поля контрольной суммы методом перебора алгоритмов.\n"
            "Нажмите кнопку после накопления пакетов."
        )
        self._tabs.setTabToolTip(6,
            "Генератор готового Arduino .ino скетча.\n"
            "Вкладки: Локомотив (скорость/направление/функции) и Стрелка/Аксессуар.\n"
            "Используйте «Экспорт» из Signal Finder для автозаполнения полей стрелки."
        )
        self._tabs.setTabToolTip(7,
            "Встроенная инструкция: схема подключения, порядок работы,\n"
            "интерпретация результатов, устранение неполадок."
        )
        self._tabs.setTabToolTip(8,
            "Журнал всех событий приложения в реальном времени.\n"
            "Цвета: серый=DEBUG, белый=INFO, оранжевый=WARNING, красный=ERROR.\n"
            "Здесь видны ошибки подключения, проблемы парсинга и прочая диагностика."
        )

        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)

        # ---- Status bar ----
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._status_perm = QLabel()   # permanent right-side label
        sb.addPermanentWidget(self._status_perm)
        self._set_status("Готов", permanent=f"v{VERSION}")

        self._build_menu()

    def _build_serial_group(self) -> QGroupBox:
        grp = QGroupBox(tr("Serial"))
        layout = QVBoxLayout(grp)

        row1 = QHBoxLayout()
        self._lbl_port = QLabel(tr("Port:"))
        row1.addWidget(self._lbl_port)
        self._port_combo = QComboBox()
        self._port_combo.setMinimumWidth(110)
        self._port_combo.setToolTip(
            "COM-порт, к которому подключена Arduino с прошивкой PIKO.\n"
            "Windows: COMx  |  Linux: /dev/ttyUSBx  |  Mac: /dev/tty.usbserial-x"
        )
        row1.addWidget(self._port_combo)
        self._btn_refresh = QPushButton("↺")
        self._btn_refresh.setFixedWidth(28)
        self._btn_refresh.setToolTip(
            "Обновить список доступных COM-портов.\n"
            "Нажмите после подключения USB-кабеля Arduino."
        )
        self._btn_refresh.clicked.connect(self._refresh_ports)
        row1.addWidget(self._btn_refresh)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        self._lbl_baud = QLabel(tr("Baud:"))
        row2.addWidget(self._lbl_baud)
        self._baud_combo = QComboBox()
        for b in ["9600", "57600", "115200", "230400", "500000", "1000000"]:
            self._baud_combo.addItem(b)
        self._baud_combo.setCurrentText(str(config.DEFAULT_BAUDRATE))
        self._baud_combo.setToolTip(
            "Скорость UART в бит/с. Должна совпадать с Serial.begin() в прошивке.\n"
            "По умолчанию 115200. При несовпадении строки в логе будут выглядеть как мусор."
        )
        row2.addWidget(self._baud_combo)
        layout.addLayout(row2)

        btn_row = QHBoxLayout()
        self._btn_connect    = QPushButton(tr("Connect"))
        self._btn_disconnect = QPushButton(tr("Disconnect"))
        self._btn_disconnect.setEnabled(False)
        self._btn_connect.setToolTip(
            "Открыть соединение с Arduino и начать приём сырых данных.\n"
            "Arduino должна быть подключена и прошита прошивкой PIKO."
        )
        self._btn_disconnect.setToolTip(
            "Закрыть UART-соединение.\n"
            "Все накопленные данные остаются в памяти."
        )
        self._btn_connect.clicked.connect(self._connect)
        self._btn_disconnect.clicked.connect(self._disconnect)
        btn_row.addWidget(self._btn_connect)
        btn_row.addWidget(self._btn_disconnect)
        layout.addLayout(btn_row)

        self._lbl_conn_state = QLabel("⬤ Отключено")
        self._lbl_conn_state.setStyleSheet("color: #888;")
        self._lbl_conn_state.setToolTip("Текущий статус соединения с Arduino")
        layout.addWidget(self._lbl_conn_state)

        return grp

    def _build_stats_group(self) -> QGroupBox:
        grp = QGroupBox(tr("Statistics"))
        layout = QVBoxLayout(grp)

        self._lbl_packets  = QLabel("Пакетов: 0")
        self._lbl_unique   = QLabel("Уникальных: 0")
        self._lbl_duration = QLabel("Длительность: 00:00:00")
        self._lbl_dropped  = QLabel("Потеряно (Arduino): 0")

        self._lbl_packets.setToolTip(
            "Суммарное количество принятых пакетов, включая повторяющиеся.\n"
            "Используется для расчёта процентного распределения."
        )
        self._lbl_unique.setToolTip(
            "Количество структурно различных пакетов.\n"
            "Одинаковые байтовые последовательности объединяются в одну запись."
        )
        self._lbl_duration.setToolTip(
            "Время с момента нажатия кнопки «Подключить».\n"
            "Можно использовать для расчёта частоты пакетов."
        )
        self._lbl_dropped.setToolTip(
            "Количество фронтов сигнала, потерянных из-за переполнения\n"
            "кольцевого буфера в Arduino. При больших значениях увеличьте\n"
            "скорость UART или уменьшите нагрузку на линию."
        )

        for lbl in (self._lbl_packets, self._lbl_unique,
                    self._lbl_duration, self._lbl_dropped):
            layout.addWidget(lbl)

        return grp

    def _build_diag_group(self) -> QGroupBox:
        grp = QGroupBox("Диагностика")
        layout = QVBoxLayout(grp)

        self._lbl_edges_ps  = QLabel("Фронтов/с: —")
        self._lbl_pkts_ps   = QLabel("Пакетов/с: —")
        self._lbl_raw_lines = QLabel("Строк Serial: 0")
        self._lbl_buf_size  = QLabel("Буфер фронтов: 0")

        self._lbl_edges_ps.setToolTip(
            "Количество фронтов сигнала (переходов 0→1 и 1→0) в секунду.\n"
            "Пропорционально битрейту протокола PIKO SmartControl."
        )
        self._lbl_pkts_ps.setToolTip(
            "Количество завершённых пакетов, распознанных парсером, в секунду.\n"
            "0 при активных фронтах = парсер не находит границы пакетов."
        )
        self._lbl_raw_lines.setToolTip(
            "Всего строк ASCII принято от Arduino с момента подключения.\n"
            "Форматы: RAW:ts:dur:lvl  |  PKT:ts:HEX  |  STAT:rx:dropped"
        )
        self._lbl_buf_size.setToolTip(
            "Текущее количество сырых фронтов в кольцевом буфере анализатора.\n"
            "Используется для поиска паттернов пакетов."
        )

        for lbl in (self._lbl_edges_ps, self._lbl_pkts_ps,
                    self._lbl_raw_lines, self._lbl_buf_size):
            layout.addWidget(lbl)

        return grp

    def _build_actions_group(self) -> QGroupBox:
        grp = QGroupBox(tr("Quick Actions"))
        layout = QVBoxLayout(grp)

        self._btn_raw_cap = QPushButton(tr("Start Raw Capture"))
        self._btn_raw_cap.setToolTip(
            "Отправить команду RAW на Arduino — начать передачу фронтов\n"
            "с метками времени в µс. Каждая строка: RAW:ts:dur:lvl\n"
            "где lvl=1 — нарастающий фронт, lvl=0 — спадающий."
        )
        self._btn_raw_cap.clicked.connect(self._start_raw_capture)
        layout.addWidget(self._btn_raw_cap)

        self._btn_reset = QPushButton(tr("Reset Statistics"))
        self._btn_reset.setToolTip(
            "Сбросить все накопленные данные:\n"
            "пакеты, счётчики, буфер фронтов, историю действий.\n"
            "Также отправляет RST на Arduino (сброс счётчиков платы)."
        )
        self._btn_reset.clicked.connect(self._reset_stats)
        layout.addWidget(self._btn_reset)

        return grp

    def _build_menu(self) -> None:
        mb = self.menuBar()
        mb.clear()

        self._menu_file = mb.addMenu(tr("File"))
        self._menu_file.addAction(tr("Save Session"), self._save_session)
        self._menu_file.addAction(tr("Export CSV…"),  self._export_csv)
        self._menu_file.addSeparator()
        self._menu_file.addAction(tr("Quit"), self.close)

        self._menu_capture = mb.addMenu(tr("Capture"))
        self._menu_capture.addAction(tr("Reset Statistics"),  self._reset_stats)
        self._menu_capture.addAction(tr("Start Raw Capture"), self._start_raw_capture)
        self._menu_capture.addAction(tr("Stop Capture"),      self._stop_capture)

        self._menu_lang = mb.addMenu(tr("Language"))
        for code, name in LANGUAGES.items():
            act = self._menu_lang.addAction(name)
            act.triggered.connect(lambda checked=False, c=code: set_language(c))

        self._menu_help = mb.addMenu("О программе")
        self._menu_help.addAction(
            f"{APP_NAME} v{VERSION}",
            self._show_about,
        )

    # ================================================================ #
    # Retranslation                                                      #
    # ================================================================ #

    def _retranslate_ui(self, _lang: str = "") -> None:
        self.setWindowTitle(f"{tr('PIKO SmartControl Protocol Analyzer')} v{VERSION}")
        self._grp_serial.setTitle(tr("Serial"))
        self._lbl_port.setText(tr("Port:"))
        self._lbl_baud.setText(tr("Baud:"))
        self._btn_connect.setText(tr("Connect"))
        self._btn_disconnect.setText(tr("Disconnect"))
        self._grp_stats.setTitle(tr("Statistics"))
        self._grp_actions.setTitle(tr("Quick Actions"))
        self._btn_raw_cap.setText(tr("Start Raw Capture"))
        self._btn_reset.setText(tr("Reset Statistics"))
        self._tabs.setTabText(0, tr("Byte Analysis"))
        self._tabs.setTabText(1, tr("Bit Analysis"))
        self._tabs.setTabText(2, tr("Actions"))
        self._tabs.setTabText(3, tr("Signal Finder"))
        self._tabs.setTabText(4, tr("Charts"))
        self._tabs.setTabText(5, tr("Checksum"))
        self._tabs.setTabText(6, tr("Sketch Generator"))
        self._tabs.setTabText(7, tr("Instructions"))
        self._btn_run_cs.setText(tr("Run Checksum Analysis"))
        self._build_menu()
        self._packet_table.retranslate_ui()
        self._byte_view.retranslate_ui()
        self._bit_view.retranslate_ui()
        self._action_view.retranslate_ui()
        self._signal_finder_view.retranslate_ui()
        self._charts_view.retranslate_ui()
        self._sketch_view.retranslate_ui()

    # ================================================================ #
    # Refresh timer                                                      #
    # ================================================================ #

    def _setup_refresh_timer(self) -> None:
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(config.GUI_REFRESH_MS)
        self._refresh_timer.timeout.connect(self._refresh_ui)
        self._refresh_timer.start()

    def _refresh_ui(self) -> None:
        try:
            self._refresh_stats()
            self._refresh_analysis()
            self._refresh_diag()
            self._action_view.refresh()
            self._signal_finder_view.refresh(self._action_rec.records)
        except Exception as exc:
            log.error(f"GUI refresh error: {exc}", exc_info=True)

    def _refresh_stats(self) -> None:
        total  = self._packet_stats.total_count
        unique = self._packet_stats.unique_count

        if self._capture_start > 0:
            elapsed = time.monotonic() - self._capture_start
            h = int(elapsed // 3600)
            m = int((elapsed % 3600) // 60)
            s = int(elapsed % 60)
            self._lbl_duration.setText(f"Длительность: {h:02d}:{m:02d}:{s:02d}")

        self._lbl_packets.setText(f"Пакетов: {total:,}")
        self._lbl_unique.setText(f"Уникальных: {unique:,}")
        self._packet_table.update_records(
            self._packet_stats.records_by_count(), total
        )

    def _refresh_analysis(self) -> None:
        records  = self._packet_stats.records_by_count()
        weighted = [(r.data, r.count) for r in records]
        if not weighted:
            return
        try:
            byte_stats = compute_byte_stats(weighted)
            bit_stats  = compute_bit_stats(weighted)
            self._byte_view.update_stats(byte_stats)
            self._bit_view.update_stats(bit_stats)
            self._charts_view.update_data(records, byte_stats, self._ordered_pkts)
        except Exception as exc:
            log.error(f"Ошибка анализа: {exc}", exc_info=True)

    def _refresh_diag(self) -> None:
        tick_s = config.GUI_REFRESH_MS / 1000
        rate_e = int(self._edges_per_tick / tick_s)
        rate_p = int(self._pkts_per_tick  / tick_s)
        self._lbl_edges_ps.setText(f"Фронтов/с: {rate_e:,}")
        self._lbl_pkts_ps.setText(f"Пакетов/с: {rate_p:,}")
        self._lbl_raw_lines.setText(f"Строк Serial: {self._raw_lines_total:,}")
        self._lbl_buf_size.setText(f"Буфер фронтов: {len(self._edge_buf):,}")

        # Flush stale edges: if no new edge arrived for 2× GAP, flush accumulator
        if self._last_edge_time > 0:
            stale_s = (config.PACKET_GAP_US * 2) / 1_000_000
            if (time.monotonic() - self._last_edge_time) > stale_s:
                self._edge_accum.flush_now()
                self._last_edge_time = 0.0

        # Warn once when edges arrive but no packets decoded yet
        total_edges = self._raw_lines_total
        if (not self._no_pkts_warned
                and total_edges > 200
                and self._packet_stats.total_count == 0):
            self._no_pkts_warned = True
            log.warning(
                f"Получено {total_edges} строк, но пакеты не распознаны. "
                f"Проверьте: бодрейт, есть ли сигнал на D2, правильно ли "
                f"подключён оптопар. Смотрите вкладку Лог."
            )
            self._set_status("⚠ Данные есть, пакеты не декодируются — смотрите Лог", timeout=6000)

        self._edges_per_tick = 0
        self._pkts_per_tick  = 0

    # ================================================================ #
    # Serial connection                                                  #
    # ================================================================ #

    def _refresh_ports(self) -> None:
        current = self._port_combo.currentText()
        self._port_combo.clear()
        ports = list_ports()
        if not ports:
            log.warning("Последовательные порты не найдены")
            self._port_combo.addItem("— нет портов —")
        else:
            for p in ports:
                self._port_combo.addItem(p)
            idx = self._port_combo.findText(current)
            if idx >= 0:
                self._port_combo.setCurrentIndex(idx)

    def _connect(self) -> None:
        port     = self._port_combo.currentText()
        baudrate_str = self._baud_combo.currentText()

        if not port or port.startswith("—"):
            QMessageBox.warning(self, "Нет порта",
                                "Выберите последовательный порт из списка.\n"
                                "Нажмите ↺ для обновления списка портов.")
            log.warning("Connect нажат без выбранного порта")
            return

        try:
            baudrate = int(baudrate_str)
        except ValueError:
            QMessageBox.critical(self, "Ошибка", f"Неверная скорость: {baudrate_str!r}")
            return

        log.info(f"Подключение к {port!r} @ {baudrate} baud...")
        self._set_status(f"Подключение к {port}…")
        self._btn_connect.setEnabled(False)

        try:
            self._serial_thread = SerialThread(port, baudrate, parent=self)
            self._serial_thread.edge_received.connect(self._on_edge)
            self._serial_thread.packet_received.connect(self._on_pkt_line)
            self._serial_thread.stat_received.connect(self._on_stat)
            self._serial_thread.connected.connect(self._on_connected)
            self._serial_thread.disconnected.connect(self._on_disconnected)
            self._serial_thread.status_message.connect(self._on_status_msg)
            self._serial_thread.raw_line.connect(self._on_raw_line)
            self._serial_thread.start()
            log.debug("SerialThread.start() вызван")
        except Exception as exc:
            log.error(f"Не удалось запустить SerialThread: {exc}", exc_info=True)
            QMessageBox.critical(self, "Ошибка подключения", str(exc))
            self._btn_connect.setEnabled(True)
            self._serial_thread = None

    def _disconnect(self) -> None:
        log.info("Отключение по запросу пользователя")
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
        self._lbl_conn_state.setText("⬤ Подключено")
        self._lbl_conn_state.setStyleSheet("color: #44cc44; font-weight: bold;")
        self._set_status(f"Подключено: {port}")
        log.info(f"Успешно подключено: {port}")

    @Slot(str)
    def _on_disconnected(self, reason: str) -> None:
        self._btn_connect.setEnabled(True)
        self._btn_disconnect.setEnabled(False)
        self._capture_start = 0.0
        self._lbl_conn_state.setText("⬤ Отключено")
        self._lbl_conn_state.setStyleSheet("color: #cc4444;")
        self._set_status(f"Отключено: {reason}")
        log.warning(f"Отключено: {reason}")

        if self._serial_thread:
            self._serial_thread = None

        # Show dialog for unexpected disconnects (not user-initiated)
        if reason and "stop" not in reason.lower():
            QMessageBox.warning(
                self, "Соединение потеряно",
                f"Соединение с портом прервано:\n\n{reason}\n\n"
                f"Проверьте USB-кабель и Arduino.\n"
                f"Подробности в вкладке «Лог»."
            )

    @Slot(str)
    def _on_status_msg(self, msg: str) -> None:
        self._set_status(msg, timeout=4000)

    @Slot(str)
    def _on_raw_line(self, line: str) -> None:
        self._raw_lines_total += 1

    @Slot(object)   # Signal(object) — PySide6 cannot marshal custom dataclass cross-thread
    def _on_edge(self, edge) -> None:
        self._edges_per_tick += 1
        self._last_edge_time = time.monotonic()
        self._edge_buf.append(edge)
        try:
            self._edge_accum.feed(edge)
        except Exception as exc:
            log.error(f"EdgeAccumulator.feed() error: {exc}", exc_info=True)

    @Slot(int, object)
    def _on_pkt_line(self, timestamp_us: int, data) -> None:
        self._on_parsed_packet(timestamp_us, data, [])

    @Slot(int, int)
    def _on_stat(self, rx: int, dropped: int) -> None:
        self._lbl_dropped.setText(f"Потеряно (Arduino): {dropped:,}")

    def _on_parsed_packet(self, timestamp_us: int, data: bytes, _edges: list) -> None:
        if not data:
            return
        try:
            self._pkts_per_tick += 1
            self._packet_stats.add_packet(timestamp_us, data)
            self._transitions.feed_packet(data)
            self._action_rec.feed_packet(data)
            self._ordered_pkts.append(data)
            if len(self._ordered_pkts) > config.LIVE_RING_SIZE:
                self._ordered_pkts = self._ordered_pkts[-config.LIVE_RING_SIZE:]
        except Exception as exc:
            log.error(f"Ошибка обработки пакета: {exc}", exc_info=True)

    # ================================================================ #
    # Capture controls                                                   #
    # ================================================================ #

    def _start_raw_capture(self) -> None:
        if self._serial_thread:
            self._serial_thread.send_command("RAW")
        self._capture_start = time.monotonic()
        self._set_status("Захват запущен")
        log.info("Raw capture запущен")

    def _stop_capture(self) -> None:
        if self._serial_thread:
            self._serial_thread.send_command("STOP")
            self._edge_accum.flush_now()
        self._set_status("Захват остановлен")
        log.info("Захват остановлен")

    def _reset_stats(self) -> None:
        self._packet_stats.reset()
        self._transitions.reset()
        self._ordered_pkts.clear()
        self._edge_buf.clear()
        self._raw_lines_total = 0
        if self._serial_thread:
            self._serial_thread.send_command("RST")
        self._set_status("Статистика сброшена")
        log.info("Статистика сброшена")

    # ================================================================ #
    # Checksum                                                           #
    # ================================================================ #

    def _run_checksum(self) -> None:
        records  = self._packet_stats.records_by_count()
        weighted = [(r.data, r.count) for r in records]
        if not weighted:
            self._checksum_label.setText(tr("No packets captured yet."))
            log.info("Checksum: нет пакетов")
            return

        log.info(f"Checksum analysis: {len(weighted)} уникальных пакетов…")
        try:
            candidates = find_checksum_candidates(
                weighted, algorithms=config.CHECKSUM_ALGORITHMS, min_match_pct=50.0
            )
        except Exception as exc:
            log.error(f"Checksum analysis failed: {exc}", exc_info=True)
            self._checksum_label.setText(f"Ошибка анализа: {exc}")
            return

        self._checksum_cache = candidates
        log.info(f"Checksum: найдено {len(candidates)} кандидатов")

        if not candidates:
            self._checksum_label.setText(
                tr("No checksum candidates found (all algorithms < 50% match).")
            )
            return

        lines = [
            tr("<b>Checksum Candidates</b><br>"), "<table>",
            f"<tr><th>{tr('Algorithm')}</th><th>{tr('Byte pos')}</th><th>{tr('Match %')}</th></tr>",
        ]
        for c in candidates[:20]:
            lines.append(
                f"<tr><td>{c.algorithm}</td><td>{c.byte_position}</td><td>{c.match_pct:.1f}%</td></tr>"
            )
        lines.append("</table>")
        self._checksum_label.setText("\n".join(lines))

    # ================================================================ #
    # Session / export                                                   #
    # ================================================================ #

    def _save_session(self) -> None:
        try:
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
            log.info(f"Сессия сохранена: {path}")
            QMessageBox.information(self, "Сессия сохранена", f"Сохранено:\n{path}")
        except Exception as exc:
            log.error(f"Ошибка сохранения сессии: {exc}", exc_info=True)
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить сессию:\n{exc}")

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Экспорт CSV", "", "CSV files (*.csv)"
        )
        if not path:
            return
        try:
            self._session_mgr.export_csv(self._packet_stats, path)
            log.info(f"CSV экспортирован: {path}")
            QMessageBox.information(self, "Готово", f"Сохранено:\n{path}")
        except Exception as exc:
            log.error(f"Ошибка экспорта CSV: {exc}", exc_info=True)
            QMessageBox.critical(self, "Ошибка", f"Не удалось экспортировать:\n{exc}")

    # ================================================================ #
    # Helpers                                                            #
    # ================================================================ #

    def _set_status(self, msg: str, timeout: int = 0, permanent: str = "") -> None:
        if timeout:
            self.statusBar().showMessage(msg, timeout)
        else:
            self.statusBar().showMessage(msg)
        if permanent:
            self._status_perm.setText(permanent)

    def _show_about(self) -> None:
        QMessageBox.about(
            self, f"О программе",
            f"<b>{APP_NAME}</b><br>"
            f"Версия: {VERSION}<br>"
            f"Автор: {AUTHOR}<br><br>"
            f"Инструмент для реверс-инжиниринга протокола PIKO SmartControl.<br>"
            f"Лицензия: MIT<br><br>"
            f"<a href='{REPO}'>{REPO}</a>"
        )

    def closeEvent(self, event) -> None:
        log.info("Завершение работы…")
        if self._serial_thread:
            self._edge_accum.flush_now()
            self._serial_thread.stop()
        log.info("До свидания.")
        event.accept()
