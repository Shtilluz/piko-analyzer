"""
Serial reader — runs in a dedicated QThread so the GUI never blocks.

Responsibilities:
  - open / close the port
  - detect disconnect
  - parse Arduino line protocol (RAW: / STAT: / PKT: / PIKO: / ERR:)
  - emit Qt signals for each received item
  - count packets; pass raw data to the rest of the pipeline

Signals are the ONLY way data leaves this thread.
No heavy analysis is done here.
"""

from __future__ import annotations

import time
from typing import Optional

import serial
import serial.tools.list_ports
from PySide6.QtCore import QThread, Signal, QObject

from analyzer.models import RawEdge
from analyzer import config


class SerialWorker(QObject):
    """
    Worker that lives in a QThread.
    All heavy I/O is done in `run()`.
    """

    # Emitted for every raw edge received from Arduino
    edge_received   = Signal(RawEdge)

    # Emitted when a PKT: line arrives (hex string, e.g. "A512348001")
    packet_received = Signal(int, bytes)   # (timestamp_us, data)

    # Emitted once per second with (total_rx, dropped)
    stat_received   = Signal(int, int)

    # Connection state changes
    connected    = Signal(str)       # port name
    disconnected = Signal(str)       # reason

    # General status / info messages (for the status bar)
    status_message = Signal(str)

    # ------------------------------------------------------------------ #

    def __init__(self, port: str, baudrate: int = config.DEFAULT_BAUDRATE):
        super().__init__()
        self._port     = port
        self._baudrate = baudrate
        self._running  = False
        self._ser: Optional[serial.Serial] = None

    # ---- Public API (called from GUI thread) ----

    def stop(self) -> None:
        self._running = False

    def send_command(self, cmd: str) -> None:
        """Send a text command to Arduino (adds \\n automatically)."""
        if self._ser and self._ser.is_open:
            try:
                self._ser.write((cmd.strip() + "\n").encode())
            except serial.SerialException as exc:
                self.status_message.emit(f"Send error: {exc}")

    # ---- Main loop (runs in QThread) ----

    def run(self) -> None:
        self._running = True
        try:
            self._ser = serial.Serial(
                self._port,
                baudrate=self._baudrate,
                timeout=config.SERIAL_TIMEOUT,
            )
        except serial.SerialException as exc:
            self.disconnected.emit(str(exc))
            self._running = False
            return

        self.connected.emit(self._port)

        while self._running:
            try:
                raw_line = self._ser.readline()
            except serial.SerialException as exc:
                self.disconnected.emit(f"Read error: {exc}")
                break

            if not raw_line:
                # timeout — port still open, nothing arrived
                continue

            try:
                line = raw_line.decode("ascii", errors="replace").strip()
            except Exception:
                continue

            self._dispatch_line(line)

        # Cleanup
        try:
            if self._ser and self._ser.is_open:
                self._ser.close()
        except Exception:
            pass
        self._ser = None

    def _dispatch_line(self, line: str) -> None:
        if not line:
            return

        if line.startswith("RAW:"):
            self._parse_raw(line)
        elif line.startswith("PKT:"):
            self._parse_pkt(line)
        elif line.startswith("STAT:"):
            self._parse_stat(line)
        elif line.startswith("PIKO:") or line.startswith("OK:") or line.startswith("ERR:"):
            self.status_message.emit(line)
        # Silently ignore unrecognised lines (debug noise, etc.)

    def _parse_raw(self, line: str) -> None:
        # RAW:<timestamp_us>:<duration_us>:<level>
        parts = line.split(":")
        if len(parts) != 4:
            return
        try:
            ts  = int(parts[1])
            dur = int(parts[2])
            lvl = int(parts[3])
        except ValueError:
            return
        self.edge_received.emit(RawEdge(ts, dur, lvl))

    def _parse_pkt(self, line: str) -> None:
        # PKT:<timestamp_us>:<HEX>
        parts = line.split(":", 2)
        if len(parts) != 3:
            return
        try:
            ts = int(parts[1])
            data = bytes.fromhex(parts[2])
        except (ValueError, TypeError):
            return
        self.packet_received.emit(ts, data)

    def _parse_stat(self, line: str) -> None:
        # STAT:<rx_count>:<dropped>
        parts = line.split(":")
        if len(parts) != 3:
            return
        try:
            rx      = int(parts[1])
            dropped = int(parts[2])
        except ValueError:
            return
        self.stat_received.emit(rx, dropped)


# ------------------------------------------------------------------ #
# Thread wrapper — creates the worker and moves it into a QThread     #
# ------------------------------------------------------------------ #

class SerialThread(QThread):
    """
    Convenience wrapper: creates a SerialWorker, moves it to this thread,
    and exposes the worker's signals directly.
    """

    edge_received   = Signal(RawEdge)
    packet_received = Signal(int, bytes)
    stat_received   = Signal(int, int)
    connected       = Signal(str)
    disconnected    = Signal(str)
    status_message  = Signal(str)

    def __init__(self, port: str, baudrate: int = config.DEFAULT_BAUDRATE, parent=None):
        super().__init__(parent)
        self._worker = SerialWorker(port, baudrate)
        self._worker.moveToThread(self)

        # Forward worker signals through this thread object
        self._worker.edge_received.connect(self.edge_received)
        self._worker.packet_received.connect(self.packet_received)
        self._worker.stat_received.connect(self.stat_received)
        self._worker.connected.connect(self.connected)
        self._worker.disconnected.connect(self.disconnected)
        self._worker.status_message.connect(self.status_message)

        self.started.connect(self._worker.run)

    def stop(self) -> None:
        self._worker.stop()
        self.quit()
        self.wait(2000)

    def send_command(self, cmd: str) -> None:
        self._worker.send_command(cmd)


def list_ports() -> list[str]:
    """Return a list of available serial port names."""
    return sorted(p.device for p in serial.tools.list_ports.comports())
