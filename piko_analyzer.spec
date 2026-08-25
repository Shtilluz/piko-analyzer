# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for PIKO SmartControl Protocol Analyzer
#
# Build (on the target platform — Windows or Linux):
#   pyinstaller piko_analyzer.spec
#
# Output:
#   dist/PIKO_Analyzer/         (folder mode — fast startup)
#   dist/PIKO_Analyzer.exe      (entry point inside the folder)

import sys
from pathlib import Path

ROOT = Path(SPECPATH)


# --------------------------------------------------------------------------- #
# Analysis                                                                     #
# --------------------------------------------------------------------------- #

a = Analysis(
    [str(ROOT / "analyzer" / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # Ship the data directory skeleton so sessions/actions can be written
        (str(ROOT / "data"),              "data"),
    ],
    hiddenimports=[
        # pyserial — list_ports backend is resolved at runtime
        "serial",
        "serial.tools",
        "serial.tools.list_ports",
        "serial.tools.list_ports_common",
        # On Windows pyserial uses a different backend than Linux
        "serial.tools.list_ports_windows",
        # matplotlib needs an explicit backend reference
        "matplotlib",
        "matplotlib.backends.backend_qtagg",
        "matplotlib.backends.backend_agg",
        # numpy/pandas internals sometimes missed by the hook
        "numpy",
        "numpy.core._multiarray_umath",
        "pandas",
        # PySide6 extras
        "PySide6.QtCore",
        "PySide6.QtWidgets",
        "PySide6.QtGui",
        "PySide6.QtPrintSupport",
        # our own subpackages
        "analyzer",
        "analyzer.gui",
        "analyzer.config",
        "analyzer.models",
        "analyzer.serial_reader",
        "analyzer.packet_parser",
        "analyzer.statistics",
        "analyzer.bit_analysis",
        "analyzer.transition_analysis",
        "analyzer.checksum_analysis",
        "analyzer.correlation",
        "analyzer.action_recorder",
        "analyzer.session",
        "analyzer.gui.main_window",
        "analyzer.gui.packet_table",
        "analyzer.gui.byte_analysis",
        "analyzer.gui.bit_analysis_view",
        "analyzer.gui.action_view",
        "analyzer.gui.charts",
    ],
    hookspath=[str(ROOT / "build_hooks")],   # custom hooks directory (may be empty)
    hooksconfig={
        "matplotlib": {
            "backends": ["qtagg"],           # ship only the Qt backend
        },
    },
    runtime_hooks=[],
    excludes=[
        # Remove unused heavy packages if present
        "tkinter",
        "wx",
        "PyQt5",
        "PyQt6",
        "IPython",
        "jupyter",
        "notebook",
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

# --------------------------------------------------------------------------- #
# One-directory executable (recommended for PySide6 — faster startup)         #
# --------------------------------------------------------------------------- #

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PIKO_Analyzer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # no black console window on Windows
    disable_windowed_traceback=False,
    # Windows-specific
    icon=str(ROOT / "assets" / "icon.ico") if (ROOT / "assets" / "icon.ico").exists() else None,
    version=str(ROOT / "assets" / "version_info.txt") if (ROOT / "assets" / "version_info.txt").exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=["vcruntime*.dll", "api-ms-*.dll"],   # don't UPX system DLLs
    name="PIKO_Analyzer",
)
