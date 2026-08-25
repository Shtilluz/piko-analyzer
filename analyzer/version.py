"""Single source of truth for the application version."""

VERSION       = "1.0.0"
VERSION_TUPLE = (1, 0, 0)
APP_NAME      = "PIKO SmartControl Protocol Analyzer"
AUTHOR        = "bigus400"
REPO          = "https://github.com/bigus400/piko-analyzer"

def version_string() -> str:
    return f"{APP_NAME} v{VERSION} by {AUTHOR}"
