"""
Central configuration — all tuneable parameters live here.
"""

# Serial
DEFAULT_PORT     = ""        # empty → user must select
DEFAULT_BAUDRATE = 115200
SERIAL_TIMEOUT   = 0.1       # seconds; short to keep the read thread responsive

# Ring buffer for live capture (in main process); unit: number of raw edge records
LIVE_RING_SIZE = 100_000

# GUI refresh interval in milliseconds
GUI_REFRESH_MS = 150         # ~6.7 fps — fast enough, not wasteful

# Packet gap threshold (microseconds): a silence longer than this
# is considered a possible inter-packet gap.
# Set to None to disable automatic gap detection.
PACKET_GAP_US = 5_000

# Minimum pulse duration to accept (microseconds).
# Shorter pulses from Arduino are silently ignored.
MIN_PULSE_US = 10

# Maximum number of unique packet byte-strings kept in statistics.
# Prevents unbounded memory use if the signal is noise.
MAX_UNIQUE_PACKETS = 10_000

# Session storage
SESSION_DIR = "data/sessions"

# Action recording
ACTION_FILE = "data/actions.json"

# Checksum algorithms to try (names match checksum_analysis.py implementations)
CHECKSUM_ALGORITHMS = ["xor", "sum8", "sum8_neg", "sum8_comp2", "crc8", "crc8_maxim"]

# Correlation: minimum confidence to show a candidate
CORRELATION_MIN_CONFIDENCE = 0.80

# Chart: how many recent samples to show in time-series plots
CHART_WINDOW_SAMPLES = 500
