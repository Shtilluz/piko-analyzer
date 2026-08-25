"""
Charts panel — time-series and distribution plots.
"""

from __future__ import annotations

from collections import deque

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox,
)

from analyzer.i18n    import tr, on_language_changed
from analyzer.models  import PacketRecord, ByteStats
from analyzer         import config


class ChartsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._byte_pos   = 0
        self._last_records:     list[PacketRecord] = []
        self._last_byte_stats:  list[ByteStats]    = []
        self._last_ordered:     list[bytes]         = []

        self._build_ui()
        on_language_changed(lambda _: self._on_lang_changed())

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        ctrl = QHBoxLayout()
        self._lbl_bytepos = QLabel()
        ctrl.addWidget(self._lbl_bytepos)
        self._byte_spin = QSpinBox()
        self._byte_spin.setMinimum(0)
        self._byte_spin.setMaximum(31)
        self._byte_spin.setValue(0)
        self._byte_spin.valueChanged.connect(self._on_byte_pos_changed)
        ctrl.addWidget(self._byte_spin)
        ctrl.addStretch()
        layout.addLayout(ctrl)

        self._fig = Figure(figsize=(8, 5), tight_layout=True)
        self._canvas = FigureCanvasQTAgg(self._fig)
        layout.addWidget(self._canvas)

        self._ax_freq  = self._fig.add_subplot(2, 2, 1)
        self._ax_byte  = self._fig.add_subplot(2, 2, 2)
        self._ax_len   = self._fig.add_subplot(2, 2, 3)
        self._ax_dist  = self._fig.add_subplot(2, 2, 4)

        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self._lbl_bytepos.setText(tr("Byte position:"))
        self._draw_empty()

    def _on_lang_changed(self) -> None:
        self.retranslate_ui()
        if self._last_records or self._last_byte_stats:
            self.update_data(
                self._last_records, self._last_byte_stats, self._last_ordered
            )

    def _on_byte_pos_changed(self, value: int) -> None:
        self._byte_pos = value

    def update_data(
        self,
        records:      list[PacketRecord],
        byte_stats:   list[ByteStats],
        ordered_pkts: list[bytes],
    ) -> None:
        self._last_records    = records
        self._last_byte_stats = byte_stats
        self._last_ordered    = ordered_pkts

        self._draw_freq(records)
        self._draw_byte_over_time(ordered_pkts)
        self._draw_len_over_time(ordered_pkts)
        self._draw_distribution(byte_stats)
        self._canvas.draw_idle()

    # ---- Drawing ----

    def _draw_empty(self) -> None:
        for ax, title in (
            (self._ax_freq, tr("Top packets by count")),
            (self._ax_byte, f"BYTE 0 {tr('Byte value distribution')}"),
            (self._ax_len,  tr("Packet length over time")),
            (self._ax_dist, tr("Byte value distribution")),
        ):
            ax.cla()
            ax.set_title(title, fontsize=9)
            ax.text(0.5, 0.5, tr("No data"), transform=ax.transAxes,
                    ha="center", va="center", color="grey")
        self._canvas.draw_idle()

    def _draw_freq(self, records: list[PacketRecord]) -> None:
        ax = self._ax_freq
        ax.cla()
        ax.set_title(tr("Top packets by count"), fontsize=9)
        if not records:
            return
        top    = records[:10]
        labels = [r.hex_str[:14] for r in top]
        counts = [r.count for r in top]
        y_pos  = range(len(top))
        ax.barh(y_pos, counts, color="steelblue")
        ax.set_yticks(list(y_pos))
        ax.set_yticklabels(labels, fontsize=7)
        ax.invert_yaxis()
        ax.set_xlabel(tr("Count"), fontsize=8)

    def _draw_byte_over_time(self, ordered_pkts: list[bytes]) -> None:
        ax  = self._ax_byte
        pos = self._byte_pos
        ax.cla()
        ax.set_title(
            f"BYTE {pos} — {tr('Byte value distribution')} "
            f"({tr('Packet #')} {config.CHART_WINDOW_SAMPLES})",
            fontsize=9
        )
        window = ordered_pkts[-config.CHART_WINDOW_SAMPLES:]
        vals   = [p[pos] for p in window if pos < len(p)]
        if not vals:
            ax.text(0.5, 0.5, tr("No data for this byte position"),
                    transform=ax.transAxes, ha="center", va="center", color="grey")
            return
        ax.plot(vals, linewidth=0.8, color="darkorange")
        ax.set_ylabel(tr("Value (hex)"), fontsize=8)
        ax.set_xlabel(tr("Packet #"), fontsize=8)
        ax.yaxis.set_major_formatter(
            lambda val, _: f"{int(val):02X}" if 0 <= val <= 255 else ""
        )

    def _draw_len_over_time(self, ordered_pkts: list[bytes]) -> None:
        ax = self._ax_len
        ax.cla()
        ax.set_title(tr("Packet length over time"), fontsize=9)
        window = ordered_pkts[-config.CHART_WINDOW_SAMPLES:]
        if not window:
            return
        ax.plot([len(p) for p in window], linewidth=0.8, color="seagreen")
        ax.set_ylabel(tr("Bytes"), fontsize=8)
        ax.set_xlabel(tr("Packet #"), fontsize=8)

    def _draw_distribution(self, byte_stats: list[ByteStats]) -> None:
        ax  = self._ax_dist
        pos = self._byte_pos
        ax.cla()
        ax.set_title(f"BYTE {pos} — {tr('Byte value distribution')}", fontsize=9)
        if not byte_stats or pos >= len(byte_stats):
            ax.text(0.5, 0.5, tr("No data"), transform=ax.transAxes,
                    ha="center", va="center", color="grey")
            return
        bs = byte_stats[pos]
        if not bs.value_counts:
            return
        sorted_vals = sorted(bs.value_counts.items())
        xs = [v for v, _ in sorted_vals]
        ys = [c for _, c in sorted_vals]
        ax.bar(xs, ys, color="mediumpurple")
        ax.set_xlabel(tr("Value (hex)"), fontsize=8)
        ax.set_ylabel(tr("Count"), fontsize=8)
        ax.xaxis.set_major_formatter(
            lambda val, _: f"{int(val):02X}" if 0 <= val <= 255 else ""
        )
