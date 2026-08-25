#!/usr/bin/env bash
# Linux/macOS build script — mirrors build.bat logic
set -euo pipefail

VENV=".venv_build"
DIST="dist/PIKO_Analyzer"
LOG="build_log.txt"

echo ""
echo "=== PIKO Analyzer Build ==="
echo ""

# 1. Virtual environment
if [[ ! -f "$VENV/bin/python" ]]; then
    echo "[1/5] Creating virtual environment..."
    python3 -m venv "$VENV"
else
    echo "[1/5] Virtual environment already exists."
fi

# 2. Dependencies
echo "[2/5] Installing dependencies..."
"$VENV/bin/pip" install --upgrade pip --quiet
"$VENV/bin/pip" install -r requirements.txt pyinstaller --quiet

# 3. Tests
echo "[3/5] Running tests..."
"$VENV/bin/python" -m pytest tests/ -q --tb=short | tee "$LOG"

# 4. Build
echo "[4/5] Building with PyInstaller..."
"$VENV/bin/pyinstaller" piko_analyzer.spec --clean --noconfirm 2>&1 | tee -a "$LOG"

# 5. Verify
if [[ -f "$DIST/PIKO_Analyzer" ]]; then
    echo ""
    echo "============================================================"
    echo " BUILD SUCCESSFUL"
    echo " Output: $DIST/"
    echo " Size: $(du -sh "$DIST" | cut -f1)"
    echo "============================================================"
else
    echo "ERROR: Expected executable not found at $DIST/PIKO_Analyzer"
    exit 1
fi
