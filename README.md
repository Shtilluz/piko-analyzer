# PIKO SmartControl Protocol Analyzer

> **A hardware protocol reverse-engineering toolkit for PIKO SmartControl.**
> Captures raw signals via Arduino, decodes statistical patterns, and helps
> identify unknown protocol fields through guided experiments — without
> assuming any specific protocol format.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![PySide6](https://img.shields.io/badge/GUI-PySide6-green.svg)](https://doc.qt.io/qtforpython/)
[![Tests](https://img.shields.io/badge/Tests-112%20passed-brightgreen.svg)](tests/)

**Language / Язык:** [English](#english) · [Русский](#русский)

---

## English

### What is this?

PIKO SmartControl is a model railway hand controller. Its exact wire protocol
is undocumented. This tool helps reverse-engineer it experimentally:

1. Capture raw electrical edges from the signal line.
2. Group them into candidate packets by silence gaps.
3. Build statistical profiles of every byte and bit position.
4. Record labelled experiments ("Speed 1", "Speed 2", "F0 ON", …).
5. Auto-correlate experiment results with byte/bit values.
6. Run checksum candidates against all known algorithms.

**The tool never assumes a protocol format.** Results are always labelled
as *candidates*, *possible*, or *confidence %* — never as facts until
confirmed by multiple independent experiments.

---

### Hardware Setup

```
PIKO SmartControl
      │  (signal output pin)
      ▼
  ┌────────┐
  │ 6N137  │  optocoupler  (isolates controller from PC ground)
  └────────┘
      │  open-collector output
      │  ← 4.7 kΩ pull-up to +5 V
      ▼
  Arduino Nano — D2 (INT0, hardware interrupt)
      │
      │  USB Serial  115200 baud
      ▼
  PC running this analyzer
```

**Why 6N137?**
- Galvanic isolation protects both the controller and the Arduino.
- The 6N137 is fast enough (max ~1 Mbit/s) to not smear short pulses.
- Output is open-collector → add a 4.7 kΩ pull-up resistor to +5 V on the Arduino side.

**Pin wiring summary**

| 6N137 pin | Connect to |
|-----------|-----------|
| 1 (Anode K) | GND via 100 Ω resistor |
| 2 (Anode) | PIKO signal line via 1 kΩ series resistor |
| 3 (GND) | Arduino GND |
| 5 (Vcc) | Arduino +5 V |
| 6 (Output) | Arduino D2 + 4.7 kΩ to +5 V |
| 7 (Enable) | Arduino +5 V |
| 8 (Vcc) | Arduino +5 V |

---

### Features

| Module | What it does |
|--------|-------------|
| **Raw edge capture** | Records every signal transition with µs timestamp |
| **Packet statistics** | Counts unique byte sequences, sorted by frequency |
| **Byte analysis** | Per-position value distribution, variability label |
| **Bit analysis** | Per-bit 0/1 ratio and transition frequency |
| **Transition tracker** | Tracks value→value changes between packets |
| **Action recorder** | Baseline vs action diff with dominant packet comparison |
| **Correlation** | Pearson r between labelled numeric values and bit fields |
| **Checksum finder** | Tests XOR, SUM, CRC-8 and variants across all byte positions |
| **Charts** | Frequency, byte-over-time, length, distribution plots |
| **Session save** | Full snapshot to JSON + CSV export |
| **Bilingual UI** | English / Russian, live switch without restart |

---

### Quick Start

#### 1. Clone the repository

```bash
git clone https://github.com/bigus400/piko-analyzer.git
cd piko-analyzer
```

#### 2. Create a virtual environment and install dependencies

```bash
python -m venv venv

# Linux / macOS
source venv/bin/activate

# Windows
venv\Scripts\activate

pip install -r requirements.txt
```

#### 3. Run the tests

```bash
pytest tests/ -v
# Expected: 112 passed
```

#### 4. Flash the Arduino

- Open `arduino/piko_sniffer/piko_sniffer.ino` in the **Arduino IDE** (2.x recommended).
- Select board: **Arduino Nano**.
- Select processor: **ATmega328P** (or Old Bootloader if upload fails).
- Upload.
- Open Serial Monitor at **115200 baud** — you should see `PIKO:READY:RAW`.

#### 5. Launch the analyzer

```bash
python -m analyzer.main
```

---

### Usage Workflow

#### Step 1 — Baseline

1. Connect the Arduino USB cable.
2. In the app: select the COM port → **Connect**.
3. Leave the PIKO controller **completely idle** for 30–60 seconds.
4. Observe the **Unique Packets** table — it should stabilize.
5. Note which bytes are `CONSTANT` (sync/address bytes) and which are `VARIABLE`.

#### Step 2 — Record experiments

Go to the **Actions** tab.

| What to record | Label convention |
|----------------|-----------------|
| Speed step 0 | `speed_0` |
| Speed step 1 | `speed_1` |
| Speed step 10 | `speed_10` |
| Forward direction | `forward` |
| Reverse direction | `reverse` |
| Function 0 on | `f0_on` |
| Function 0 off | `f0_off` |

For each action:

```
1. Type the label  →  click [1. Start Baseline]
2. Wait 5 seconds without touching the controller
3. Click [2. Action Now]  →  immediately perform the action on the controller
4. Click [3. Stop & Save]
```

The tool records the **dominant packet** before and after, and shows the diff:

```
BYTE 2:  03 (00000011)  →  13 (00010011)
                              ^
                         bit 4 changed
```

#### Step 3 — Correlation

After recording at least **3 numeric experiments** (e.g. `speed_0` … `speed_5`):

- Click **Run Correlation Analysis**.
- The tool computes Pearson r between the labelled speed values and every
  bit-range in every byte.
- Results are shown as candidates with a confidence score:

```
Possible SPEED field  BYTE 2 [B4:B0]  confidence=99.8%  r=0.998 (n=6)
```

A confidence above 95% with 5+ experiments is strong evidence.
**Verify by predicting: if speed_7 should give BYTE 2 = 0x73, send speed_7
and check.**

#### Step 4 — Checksum

Click the **Checksum** tab → **Run Checksum Analysis**.

The tool tests every (algorithm × byte position) pair:

```
Checksum Candidates
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Algorithm   Byte pos   Match %
xor         4          100.0%   ← strong candidate
sum8        4           12.3%
crc8        4            8.1%
```

100% match = that byte IS the checksum of the remaining bytes with that algorithm.

#### Step 5 — Save and export

- **File → Save Session** — saves complete analysis to `data/sessions/session_YYYYMMDD_HHMMSS.json`.
- **File → Export CSV** — exports the unique packet table as CSV.

---

### Arduino Serial Protocol

The firmware speaks a simple line-based ASCII protocol.

**Arduino → PC:**

```
PIKO:READY:RAW              startup notification
RAW:<ts_us>:<dur_us>:<lvl>  one edge  (ts = micros(), lvl = 0|1)
STAT:<rx>:<dropped>         statistics, once per second
OK:RAW / OK:STOP / OK:RST  command acknowledgement
ERR:UNKNOWN:<cmd>           unknown command
```

**PC → Arduino** (newline-terminated):

```
RAW    start / resume raw edge capture  (default on boot)
STOP   pause output (ISR still runs, ring buffer fills)
RST    reset counters and clear ring buffer
```

**Why text protocol?**
Binary would be faster, but a text protocol lets you open a plain Serial
Monitor and verify the hardware is working before running the full analyzer.

---

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Python Analyzer                       │
│                                                             │
│  SerialThread (QThread)                                     │
│       │ edge_received signal                                │
│       ▼                                                     │
│  EdgeAccumulator ──► RingBuffer (100 k edges)              │
│       │ on_packet callback                                  │
│       ▼                                                     │
│  ┌────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │PacketStats │  │Transition    │  │ActionRecorder     │  │
│  │(unique map)│  │Tracker       │  │(baseline/action   │  │
│  └────────────┘  └──────────────┘  │ window + diff)    │  │
│         │               │          └───────────────────┘  │
│         ▼               ▼                    │             │
│  ┌────────────────────────────────────────────────────┐    │
│  │              GUI  (PySide6,  ~7 fps refresh)       │    │
│  │  PacketTable │ ByteAnalysis │ BitAnalysis │ Charts  │    │
│  │  ActionView  │ ChecksumTab  │ Correlation           │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

**Key design decisions:**

- Serial I/O runs in its own `QThread` — the GUI never blocks on serial reads.
- Analysis runs in the main thread, triggered by a `QTimer` at ~7 fps —
  packets can arrive at any rate without dropping GUI frames.
- `EdgeAccumulator` uses a silence-gap heuristic to detect packet boundaries.
  This heuristic may be wrong for some protocols — in that case, examine raw
  edge durations in the Charts tab and adjust `PACKET_GAP_US` in `config.py`.
- Statistics are weighted by packet count, so a packet seen 1000 times
  contributes proportionally to byte/bit histograms.

---

### Configuration

All tunable parameters are in `analyzer/config.py`:

```python
DEFAULT_BAUDRATE  = 115200    # serial speed
PACKET_GAP_US     = 5_000     # silence gap → packet boundary (µs)
MIN_PULSE_US      = 10        # ignore pulses shorter than this
LIVE_RING_SIZE    = 100_000   # max edges in live ring buffer
GUI_REFRESH_MS    = 150       # UI refresh interval (~7 fps)
MAX_UNIQUE_PACKETS = 10_000   # cap on unique packets in stats
CHECKSUM_ALGORITHMS = [...]   # algorithms to try
CORRELATION_MIN_CONFIDENCE = 0.80
```

---

### Building a Windows Executable

Prerequisites: Python 3.11+ installed on a **Windows** machine.

```bat
git clone https://github.com/bigus400/piko-analyzer.git
cd piko-analyzer
build.bat
```

`build.bat` will:
1. Create `.venv_build\`
2. Install all dependencies + PyInstaller
3. Run the test suite (build aborts on failure)
4. Build `dist\PIKO_Analyzer\PIKO_Analyzer.exe`
5. Open the output folder

The result is a self-contained folder — no Python installation needed on the target machine.

#### Automated builds via GitHub Actions

Push a version tag to trigger a Windows build in CI:

```bash
git tag v1.0.0
git push origin v1.0.0
```

The workflow (`.github/workflows/build.yml`) runs on `windows-latest`,
runs all tests, and attaches `PIKO_Analyzer_Windows.zip` to the GitHub Release.

---

### Project Structure

```
piko-analyzer/
├── arduino/
│   └── piko_sniffer/
│       └── piko_sniffer.ino      Arduino firmware (raw edge capture)
│
├── analyzer/
│   ├── config.py                 All tunable parameters
│   ├── models.py                 Pure data classes (no logic)
│   ├── i18n.py                   Translation system (EN / RU)
│   ├── serial_reader.py          QThread serial worker
│   ├── packet_parser.py          Edge → packet heuristic + ring buffer
│   ├── statistics.py             Unique packet statistics
│   ├── bit_analysis.py           Byte / bit statistics
│   ├── transition_analysis.py    Value transition tracking
│   ├── checksum_analysis.py      Checksum candidate search
│   ├── correlation.py            Pearson correlation finder
│   ├── action_recorder.py        Experiment workflow + JSON persistence
│   ├── session.py                Save / load / CSV export
│   └── gui/
│       ├── main_window.py        Main window + menus
│       ├── packet_table.py       Unique packets table
│       ├── byte_analysis.py      Per-byte statistics panel
│       ├── bit_analysis_view.py  Per-bit statistics panel
│       ├── action_view.py        Action recording + diff + correlation
│       └── charts.py             Matplotlib charts
│
├── tests/                        112 unit tests (pytest)
│
├── data/
│   ├── sessions/                 Saved session JSON files
│   └── actions.json              Recorded action experiments
│
├── assets/
│   └── version_info.txt          Windows version resource
│
├── .github/
│   └── workflows/
│       └── build.yml             GitHub Actions Windows build
│
├── piko_analyzer.spec            PyInstaller spec
├── build.bat                     Windows build script
├── build.sh                      Linux / macOS build script
├── requirements.txt
└── LICENSE                       MIT
```

---

### Running Tests

```bash
pytest tests/ -v                  # all 112 tests
pytest tests/test_checksum.py -v  # specific module
pytest tests/ -k "correlation"    # by keyword
```

---

### Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

---

### License

MIT — see [LICENSE](LICENSE).
You are free to use, modify, and distribute this software.
**You must keep the original copyright notice.**

---

---

## Русский

### Что это такое?

PIKO SmartControl — пульт управления моделями железной дороги.
Протокол его проводного интерфейса не задокументирован.
Этот инструмент помогает разобраться в нём экспериментально:

1. Захватывать сырые фронты сигнала с точностью до микросекунды.
2. Группировать их в пакеты по паузам между сигналами.
3. Строить статистику по каждому байту и биту.
4. Записывать размеченные эксперименты («Скорость 1», «Скорость 2», «F0 ВКЛ»…).
5. Автоматически искать корреляцию между экспериментами и битовыми полями.
6. Проверять кандидатов на контрольную сумму (XOR, SUM, CRC-8 и варианты).

**Инструмент никогда не предполагает формат протокола.**
Все результаты помечены как *кандидат*, *возможно* или *уверенность %* —
не как факт, пока не подтверждено несколькими независимыми экспериментами.

---

### Схема подключения

```
PIKO SmartControl
      │  (выход сигнала)
      ▼
  ┌────────┐
  │ 6N137  │  оптопара  (гальваническая развязка)
  └────────┘
      │  выход с открытым коллектором
      │  ← подтяжка 4.7 кОм к +5 В
      ▼
  Arduino Nano — D2 (INT0, аппаратное прерывание)
      │
      │  USB Serial  115200 бод
      ▼
  ПК с этой программой
```

**Назначение выводов 6N137**

| Вывод 6N137 | Подключить к |
|-------------|-------------|
| 1 (Anode K) | GND через 100 Ом |
| 2 (Anode)   | Сигнальный провод PIKO через 1 кОм |
| 3 (GND)     | GND Arduino |
| 5 (Vcc)     | +5 В Arduino |
| 6 (Output)  | D2 Arduino + 4.7 кОм к +5 В |
| 7 (Enable)  | +5 В Arduino |
| 8 (Vcc)     | +5 В Arduino |

---

### Быстрый старт

#### 1. Клонировать репозиторий

```bash
git clone https://github.com/bigus400/piko-analyzer.git
cd piko-analyzer
```

#### 2. Создать виртуальное окружение и установить зависимости

```bash
python -m venv venv

# Linux / macOS
source venv/bin/activate

# Windows
venv\Scripts\activate

pip install -r requirements.txt
```

#### 3. Запустить тесты

```bash
pytest tests/ -v
# Ожидается: 112 passed
```

#### 4. Прошить Arduino

- Открыть `arduino/piko_sniffer/piko_sniffer.ino` в **Arduino IDE** (версия 2.x).
- Плата: **Arduino Nano**.
- Процессор: **ATmega328P** (или Old Bootloader, если прошивка не загружается).
- Загрузить (Upload).
- Открыть Serial Monitor при **115200 бод** — должна появиться строка `PIKO:READY:RAW`.

#### 5. Запустить анализатор

```bash
python -m analyzer.main
```

Язык интерфейса: **Меню Language → Русский** — переключается без перезапуска.

---

### Рабочий процесс

#### Этап 1 — Baseline (фоновый сигнал)

1. Подключить USB-кабель Arduino.
2. В программе: выбрать порт → **Подключить**.
3. Не трогать контроллер PIKO 30–60 секунд.
4. Таблица «Уникальные пакеты» должна стабилизироваться.
5. Посмотреть вкладку **Анализ байтов** — выявить `ПОСТОЯННЫЙ` и `ПЕРЕМЕННЫЙ` байты.

#### Этап 2 — Запись экспериментов

Вкладка **Действия**.

| Что записывать | Метка |
|----------------|-------|
| Скорость 0 | `speed_0` |
| Скорость 1 | `speed_1` |
| Скорость 10 | `speed_10` |
| Вперёд | `forward` |
| Назад | `reverse` |
| F0 включить | `f0_on` |
| F0 выключить | `f0_off` |

Для каждого действия:

```
1. Ввести метку  →  нажать [1. Начать baseline]
2. Подождать 5 секунд без касания контроллера
3. Нажать [2. Выполнить действие]  →  сразу выполнить действие на контроллере
4. Нажать [3. Стоп и сохранить]
```

Программа показывает diff доминантных пакетов:

```
BYTE 2:  03 (00000011)  →  13 (00010011)
                              ^
                         бит 4 изменился
```

#### Этап 3 — Корреляция

После записи минимум **3 числовых экспериментов** (напр. `speed_0` … `speed_5`):

- Нажать **Запустить анализ корреляции**.
- Программа вычисляет коэффициент корреляции Пирсона между числовыми
  значениями меток и каждым диапазоном бит в каждом байте.

```
Возможное поле SPEED  BYTE 2 [B4:B0]  уверенность=99.8%  r=0.998 (n=6)
```

Уверенность выше 95% при 5+ экспериментах — весомое свидетельство.
**Верификация: предскажи значение для speed_7, отправь команду, проверь.**

#### Этап 4 — Контрольная сумма

Вкладка **Контрольная сумма** → **Запустить анализ КС**.

```
Кандидаты контрольной суммы
━━━━━━━━━━━━━━━━━━━━━━━━━━
Алгоритм   Позиция байта   Совпадений %
xor        4               100.0%   ← сильный кандидат
sum8       4                12.3%
```

100% совпадений = этот байт является контрольной суммой остальных байтов.

#### Этап 5 — Сохранение

- **Файл → Сохранить сессию** — полный снимок в `data/sessions/session_YYYYMMDD_HHMMSS.json`.
- **Файл → Экспорт CSV** — таблица уникальных пакетов в CSV.

---

### Сборка для Windows

На Windows-машине:

```bat
git clone https://github.com/bigus400/piko-analyzer.git
cd piko-analyzer
build.bat
```

Скрипт создаёт виртуальное окружение, устанавливает зависимости,
прогоняет тесты и собирает `dist\PIKO_Analyzer\PIKO_Analyzer.exe`.

Готовый exe не требует установки Python.

#### Автоматическая сборка через GitHub Actions

```bash
git tag v1.0.0
git push origin v1.0.0
```

CI собирает бинарник на Windows и прикрепляет архив к GitHub Release.

---

### Конфигурация

Файл `analyzer/config.py`:

```python
DEFAULT_BAUDRATE   = 115200   # скорость Serial
PACKET_GAP_US      = 5_000    # пауза → граница пакета (мкс)
MIN_PULSE_US       = 10       # игнорировать импульсы короче (мкс)
GUI_REFRESH_MS     = 150      # обновление GUI (~7 кадров/с)
MAX_UNIQUE_PACKETS = 10_000   # лимит уникальных пакетов в статистике
```

---

### Важные ограничения

> Это инструмент исследования, не декодер готового протокола.

- Алгоритм определения границ пакетов (`EdgeAccumulator`) использует
  эвристику — паузу в сигнале. Если протокол использует другое
  фреймирование, результаты будут неверными. В этом случае изучи
  сырые длительности импульсов на вкладке **Графики**.
- Не доверяй корреляции при менее чем 3 точках данных.
- 100% совпадение контрольной суммы — сильное, но не абсолютное
  доказательство (может быть случайным совпадением на малой выборке).
- Всегда верифицируй гипотезу предсказанием + проверкой.

---

### Лицензия

MIT — см. [LICENSE](LICENSE).
Можно свободно использовать, изменять и распространять.
**Необходимо сохранять строку с именем автора (copyright notice).**
