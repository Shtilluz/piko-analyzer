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

from analyzer.logger   import get_logger
from analyzer.version  import APP_NAME, VERSION, version_string

log = get_logger(__name__)


def main() -> None:
    log.info(f"=== {version_string()} ===")
    log.info(f"Python {sys.version}")
    log.info(f"Platform: {sys.platform}")
    log.info(f"CWD: {os.getcwd()}")

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(VERSION)

    from analyzer.gui.main_window import MainWindow
    window = MainWindow()
    window.show()

    log.info("GUI запущен, входим в event loop")
    code = app.exec()
    log.info(f"Приложение завершено, exit code={code}")
    sys.exit(code)


if __name__ == "__main__":
    main()
