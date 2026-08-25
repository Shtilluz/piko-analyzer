"""
Serial reader — runs in a dedicated QThread so the GUI never blocks.

Every failure path logs a message AND emits a signal so the GUI can react.
"""

from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import QThread, Signal, QObject

from analyzer.models import RawEdge
from analyzer.logger import get_logger
from analyzer import config

log = get_logger(__name__)


def list_ports() -> list[str]:
    """Return available serial port names. Returns [] if pyserial not installed."""
    try:
        import serial.tools.list_ports
        ports = sorted(p.device for p in serial.tools.list_ports.comports())
        log.debug(f"Available ports: {ports}")
        return ports
    except Exception as exc:
        log.error(f"Cannot enumerate serial ports: {exc}")
        return []


class SerialWorker(QObject):
    """
    Worker that lives in a QThread.
    Emits signals for every event — the GUI only reacts to signals.
    """

    edge_received   = Signal(RawEdge)
    packet_received = Signal(int, bytes)    # (timestamp_us, data)
    stat_received   = Signal(int, int)      # (total_rx, dropped)
    connected       = Signal(str)           # port name
    disconnected    = Signal(str)           # reason string
    status_message  = Signal(str)           # one-liner for status bar
    raw_line        = Signal(str)           # every raw ASCII line (for log panel)

    def __init__(self, port: str, baudrate: int = config.DEFAULT_BAUDRATE):
        super().__init__()
        self._port     = port
        self._baudrate = baudrate
        self._running  = False
        self._ser      = None

    # ---- Public API (called from GUI thread via queued connection) ----

    def stop(self) -> None:
        log.info("Serial worker: stop requested")
        self._running = False

    def send_command(self, cmd: str) -> None:
        if self._ser is None:
            log.warning(f"send_command('{cmd}'): port not open")
            return
        try:
            line = (cmd.strip() + "\n").encode("ascii")
            self._ser.write(line)
            log.debug(f"→ Arduino: {cmd.strip()!r}")
        except Exception as exc:
            log.error(f"send_command('{cmd}'): {exc}")
            self.status_message.emit(f"Ошибка отправки: {exc}")

    # ---- Main loop ----

    def run(self) -> None:
        log.info(f"Serial worker started: port={self._port!r} baud={self._baudrate}")
        self._running = True

        # ---- Open port ----
        try:
            import serial
            self._ser = serial.Serial(
                self._port,
                baudrate=self._baudrate,
                timeout=config.SERIAL_TIMEOUT,
            )
            log.info(f"Port {self._port!r} opened at {self._baudrate} baud")
        except Exception as exc:
            msg = f"Не удалось открыть порт {self._port!r}: {exc}"
            log.error(msg)
            self.disconnected.emit(msg)
            self._running = False
            return

        self.connected.emit(self._port)

        # ---- Read loop ----
        consecutive_errors = 0
        bytes_received     = 0
        lines_received     = 0
        parse_errors       = 0

        while self._running:
            try:
                raw = self._ser.readline()
            except Exception as exc:
                consecutive_errors += 1
                log.error(f"Ошибка чтения (#{consecutive_errors}): {exc}")
                if consecutive_errors >= 5:
                    msg = f"Порт потерян после {consecutive_errors} ошибок: {exc}"
                    log.critical(msg)
                    self.disconnected.emit(msg)
                    break
                time.sleep(0.05)
                continue

            consecutive_errors = 0

            if not raw:
                # timeout — nothing arrived, port still open
                continue

            bytes_received += len(raw)

            try:
                line = raw.decode("ascii", errors="replace").strip()
            except Exception as exc:
                parse_errors += 1
                log.warning(f"Decode error #{parse_errors}: {exc} | raw={raw!r}")
                continue

            if not line:
                continue

            lines_received += 1
            log.debug(f"← {line}")
            self.raw_line.emit(line)

            ok = self._dispatch(line)
            if not ok:
                parse_errors += 1
                if parse_errors % 50 == 1:
                    log.warning(
                        f"Нераспознанные строки: {parse_errors} "
                        f"(последняя: {line!r}). "
                        f"Возможно, неверный бодрейт или плата не прошита."
                    )

        # ---- Cleanup ----
        log.info(
            f"Serial worker завершён. "
            f"Получено: {bytes_received} байт, {lines_received} строк, "
            f"{parse_errors} ошибок парсинга."
        )
        try:
            if self._ser and self._ser.is_open:
                self._ser.close()
                log.info(f"Порт {self._port!r} закрыт")
        except Exception as exc:
            log.warning(f"Ошибка закрытия порта: {exc}")
        self._ser = None

    def _dispatch(self, line: str) -> bool:
        """Parse one line. Returns True if recognised, False otherwise."""
        if line.startswith("RAW:"):
            return self._parse_raw(line)
        if line.startswith("PKT:"):
            return self._parse_pkt(line)
        if line.startswith("STAT:"):
            return self._parse_stat(line)
        if line.startswith(("PIKO:", "OK:", "ERR:")):
            log.info(f"Arduino: {line}")
            self.status_message.emit(line)
            return True
        return False

    def _parse_raw(self, line: str) -> bool:
        # RAW:<timestamp_us>:<duration_us>:<level>
        parts = line.split(":")
        if len(parts) != 4:
            log.debug(f"Malformed RAW line ({len(parts)} parts): {line!r}")
            return False
        try:
            ts  = int(parts[1])
            dur = int(parts[2])
            lvl = int(parts[3])
        except ValueError as exc:
            log.debug(f"RAW parse error: {exc} | {line!r}")
            return False
        if lvl not in (0, 1):
            log.debug(f"RAW level out of range: {lvl} | {line!r}")
            return False
        self.edge_received.emit(RawEdge(ts, dur, lvl))
        return True

    def _parse_pkt(self, line: str) -> bool:
        # PKT:<timestamp_us>:<HEX>
        parts = line.split(":", 2)
        if len(parts) != 3:
            log.debug(f"Malformed PKT line: {line!r}")
            return False
        try:
            ts   = int(parts[1])
            data = bytes.fromhex(parts[2])
        except (ValueError, TypeError) as exc:
            log.debug(f"PKT parse error: {exc} | {line!r}")
            return False
        if not data:
            log.debug(f"PKT with empty data: {line!r}")
            return False
        log.debug(f"PKT ts={ts} data={data.hex().upper()}")
        self.packet_received.emit(ts, data)
        return True

    def _parse_stat(self, line: str) -> bool:
        # STAT:<rx_count>:<dropped>
        parts = line.split(":")
        if len(parts) != 3:
            return False
        try:
            rx      = int(parts[1])
            dropped = int(parts[2])
        except ValueError:
            return False
        if dropped > 0:
            log.warning(f"Arduino buffer overflow: {dropped} edges dropped (total rx={rx})")
        else:
            log.debug(f"Arduino STAT: rx={rx} dropped={dropped}")
        self.stat_received.emit(rx, dropped)
        return True


class SerialThread(QThread):
    """Wraps SerialWorker in a QThread. Exposes the same signals."""

    edge_received   = Signal(RawEdge)
    packet_received = Signal(int, bytes)
    stat_received   = Signal(int, int)
    connected       = Signal(str)
    disconnected    = Signal(str)
    status_message  = Signal(str)
    raw_line        = Signal(str)

    def __init__(self, port: str, baudrate: int = config.DEFAULT_BAUDRATE, parent=None):
        super().__init__(parent)
        self._worker = SerialWorker(port, baudrate)
        self._worker.moveToThread(self)

        self._worker.edge_received.connect(self.edge_received)
        self._worker.packet_received.connect(self.packet_received)
        self._worker.stat_received.connect(self.stat_received)
        self._worker.connected.connect(self.connected)
        self._worker.disconnected.connect(self.disconnected)
        self._worker.status_message.connect(self.status_message)
        self._worker.raw_line.connect(self.raw_line)

        self.started.connect(self._worker.run)

    def stop(self) -> None:
        log.info("SerialThread.stop()")
        self._worker.stop()
        self.quit()
        if not self.wait(3000):
            log.warning("SerialThread did not stop in 3 s — forcing terminate")
            self.terminate()
            self.wait(1000)

    def send_command(self, cmd: str) -> None:
        self._worker.send_command(cmd)
