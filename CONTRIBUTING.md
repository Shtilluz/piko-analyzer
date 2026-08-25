# Contributing to PIKO SmartControl Protocol Analyzer

Thank you for your interest in improving this tool.

---

## Ways to contribute

- **Share capture data** — if you have packet captures from a PIKO SmartControl,
  open an issue and attach the JSON session file.  Even partial data helps.
- **Report a bug** — use the bug report template in GitHub Issues.
- **Improve analysis algorithms** — better edge-to-bit heuristics, more checksum
  algorithms, improved correlation methods.
- **Add a language** — see [Adding a language](#adding-a-language) below.
- **Improve documentation** — typos, unclear steps, missing hardware details.

---

## Ground rules

1. **Do not hardcode protocol assumptions.**
   The protocol is still unknown.  Do not add code that treats byte 0 as
   an address, byte 2 as speed, etc., unless a specific hypothesis has been
   confirmed by multiple independent experiments documented in an issue.

2. **Keep the Arduino ISR short.**
   The ISR in `piko_sniffer.ino` must complete in microseconds.
   No Serial calls, no heavy computation inside the ISR.

3. **Test your changes.**
   Run `pytest tests/ -v` before opening a PR.  New analysis logic should
   come with tests.  GUI-only changes are exempt but must not break existing tests.

4. **One concern per PR.**
   A PR that adds a new checksum algorithm and refactors the GUI is two PRs.

---

## Development setup

```bash
git clone https://github.com/bigus400/piko-analyzer.git
cd piko-analyzer

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

pytest tests/ -v                # verify baseline
python -m analyzer.main         # launch GUI
```

---

## Project layout (quick reference)

| Path | Responsibility |
|------|---------------|
| `analyzer/config.py` | All tunable constants — change here, not inline |
| `analyzer/models.py` | Pure data classes — no logic |
| `analyzer/i18n.py` | Translations — add strings here |
| `analyzer/gui/` | PySide6 widgets — each widget owns `retranslate_ui()` |
| `tests/` | pytest tests — run with `pytest tests/ -v` |
| `arduino/` | Arduino firmware — ISR must stay minimal |

---

## Adding a language

1. Open `analyzer/i18n.py`.
2. Add your language code to `LANGUAGES`:
   ```python
   LANGUAGES = {
       "en": "English",
       "ru": "Русский",
       "de": "Deutsch",   # ← new
   }
   ```
3. Add a translation dictionary `_DE = { "Connect": "Verbinden", ... }`.
4. Register it in `_TRANSLATIONS`:
   ```python
   _TRANSLATIONS = {
       "en": {},
       "ru": _RU,
       "de": _DE,   # ← new
   }
   ```
5. Add a test to `tests/test_i18n.py` — copy the `TestRussianCoverage` class,
   rename it, update the critical keys list and the Cyrillic check to match
   your script.
6. Open a PR with `[i18n]` in the title.

---

## Commit style

```
type: short description (max 72 chars)

Optional body — explain WHY, not WHAT.
```

Types: `fix`, `feat`, `test`, `docs`, `refactor`, `arduino`, `build`.

Examples:
```
feat: add CRC-16 to checksum candidates
fix: EdgeAccumulator flush_now called twice on disconnect
docs: add wiring diagram for 5 V tolerant boards
arduino: reduce ring buffer to 256 to save SRAM on Nano
```

---

## Attribution

By contributing you agree that your changes will be distributed under the
[MIT License](LICENSE).  Your name will appear in the git history.
If you make a significant contribution and would like to be listed in the
README, mention it in your PR.

---

*Questions? Open an issue — no question is too small.*
