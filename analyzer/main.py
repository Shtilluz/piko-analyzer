"""
Entry point — creates the QApplication and shows the main window.
"""

import sys
import os

# Ensure the project root is on sys.path when run as `python analyzer/main.py`
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore    import Qt

from analyzer.gui.main_window import MainWindow


def main() -> None:
    # High-DPI scaling is automatic in Qt6; the old attribute is deprecated.
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("PIKO SmartControl Protocol Analyzer")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
