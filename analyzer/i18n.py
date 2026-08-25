"""
Minimalist i18n system.

Usage:
    from analyzer.i18n import tr, set_language, get_language, LANGUAGES
    label = tr("Connect")          # returns translated string
    set_language("ru")             # switch language

Keys are English strings — so any missing translation falls back to the key itself.

Language change notification:
    Register a callback with on_language_changed(cb).
    The callback receives the new language code.
    GUI widgets use this to retranslate themselves live.
"""

from __future__ import annotations
from typing import Callable

# ---- Available languages ------------------------------------------------- #

LANGUAGES: dict[str, str] = {
    "en": "English",
    "ru": "Русский",
}

_current: str = "en"
_callbacks: list[Callable[[str], None]] = []

# ---- Public API ---------------------------------------------------------- #

def set_language(lang: str) -> None:
    global _current
    if lang not in LANGUAGES:
        raise ValueError(f"Unknown language: {lang!r}")
    _current = lang
    for cb in _callbacks:
        try:
            cb(lang)
        except Exception:
            pass


def get_language() -> str:
    return _current


def on_language_changed(cb: Callable[[str], None]) -> None:
    """Register a callback invoked whenever the language changes."""
    _callbacks.append(cb)


def tr(key: str, **kwargs) -> str:
    """
    Translate `key` to the current language.
    kwargs are applied with str.format() after translation.
    Falls back to the key itself if no translation exists.
    """
    text = _TRANSLATIONS.get(_current, {}).get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text


# ---- Translation tables -------------------------------------------------- #

_RU: dict[str, str] = {
    # ---- App title ----
    "PIKO SmartControl Protocol Analyzer": "PIKO SmartControl — Анализатор протокола",

    # ---- Main window panels ----
    "Serial":          "Последовательный порт",
    "Port:":           "Порт:",
    "Baud:":           "Скорость:",
    "Connect":         "Подключить",
    "Disconnect":      "Отключить",
    "Statistics":      "Статистика",
    "Quick Actions":   "Быстрые действия",
    "Start Raw Capture": "Начать захват",
    "Reset Statistics":  "Сбросить статистику",

    # ---- Stats labels ----
    "Packets: 0":      "Пакетов: 0",
    "Unique: 0":       "Уникальных: 0",
    "Duration: 00:00:00": "Длительность: 00:00:00",
    "Dropped: 0":      "Потеряно: 0",

    # ---- Dynamic stat strings (use tr() with kwargs) ----
    "Packets: {total}":       "Пакетов: {total}",
    "Unique: {unique}":       "Уникальных: {unique}",
    "Duration: {h}:{m}:{s}":  "Длительность: {h}:{m}:{s}",
    "Dropped (Arduino): {dropped}": "Потеряно (Arduino): {dropped}",

    # ---- Menu ----
    "File":           "Файл",
    "Save Session":   "Сохранить сессию",
    "Export CSV…":    "Экспорт CSV…",
    "Quit":           "Выйти",
    "Capture":        "Захват",
    "Stop Capture":   "Остановить захват",
    "Language":       "Язык",

    # ---- Status bar messages ----
    "Ready":                  "Готов",
    "Raw capture started":    "Захват запущен",
    "Capture stopped":        "Захват остановлен",
    "Statistics reset":       "Статистика сброшена",
    "Session saved":          "Сессия сохранена",
    "Exported":               "Экспортировано",
    "Connected: {port}":      "Подключено: {port}",
    "Disconnected: {reason}": "Отключено: {reason}",

    # ---- Dialogs ----
    "No port":                    "Порт не выбран",
    "Please select a serial port.": "Пожалуйста, выберите последовательный порт.",
    "Saved to:\n{path}":          "Сохранено:\n{path}",
    "Exported to:\n{path}":       "Экспортировано:\n{path}",

    # ---- Tabs ----
    "Byte Analysis": "Анализ байтов",
    "Bit Analysis":  "Анализ битов",
    "Actions":       "Действия",
    "Charts":        "Графики",
    "Checksum":      "Контрольная сумма",

    # ---- Packet table ----
    "<b>Unique Packets</b>": "<b>Уникальные пакеты</b>",
    "Packet (hex)":    "Пакет (hex)",
    "Count":           "Кол-во",
    "Last seen (us)":  "Последний (мкс)",

    # ---- Byte analysis ----
    "<b>Byte Analysis</b>": "<b>Анализ байтов</b>",
    "Value":           "Значение",
    "unique values":   "уникальных значений",
    "total":           "всего",
    "CONSTANT":        "ПОСТОЯННЫЙ",
    "MOSTLY_CONSTANT": "ПОЧТИ_ПОСТОЯННЫЙ",
    "VARIABLE":        "ПЕРЕМЕННЫЙ",

    # ---- Bit analysis ----
    "<b>Bit Analysis</b>": "<b>Анализ битов</b>",
    "bit detail":      "детализация битов",
    "%0":              "%0",
    "%1":              "%1",
    "trans%":          "перех%",

    # ---- Charts ----
    "Byte position:":                   "Позиция байта:",
    "Top packets by count":             "Топ пакетов по количеству",
    "Packet length over time":          "Длина пакета во времени",
    "Byte value distribution":          "Распределение значений байта",
    "No data":                          "Нет данных",
    "No data for this byte position":   "Нет данных для этой позиции байта",
    "Count":                            "Кол-во",
    "Bytes":                            "Байты",
    "Packet #":                         "Пакет №",
    "Value (hex)":                      "Значение (hex)",

    # ---- Action recording ----
    "Record Action":       "Запись действия",
    "Label:":              "Метка:",
    "e.g.  speed_3  or  f0_on": "напр.  speed_3  или  f0_on",
    "Note:":               "Примечание:",
    "optional description": "необязательное описание",
    "1. Start Baseline":   "1. Начать baseline",
    "2. Action Now":       "2. Выполнить действие",
    "3. Stop & Save":      "3. Стоп и сохранить",
    "Cancel":              "Отмена",

    "State: IDLE":         "Состояние: ОЖИДАНИЕ",
    "State: IDLE (cancelled)": "Состояние: ОЖИДАНИЕ (отменено)",
    "State: ERROR — enter a label first": "Ошибка: сначала введите метку",
    "State: COLLECTING BASELINE — do nothing on controller":
        "Сбор baseline — не трогайте контроллер",
    "State: RECORDING ACTION — perform the action now":
        "Запись действия — выполните действие сейчас",

    "<b>Action History &amp; Diff</b>": "<b>История действий и diff</b>",
    "Baseline dominant":  "Dominant baseline",
    "Action dominant":    "Dominant action",
    "Changed bytes":      "Изменённые байты",
    "Run Correlation Analysis": "Запустить анализ корреляции",

    "Action: {label}":           "Действие: {label}",
    "Note: {desc}":              "Примечание: {desc}",
    "Baseline dominant : {pkt}": "Dominant baseline : {pkt}",
    "Action dominant   : {pkt}": "Dominant action   : {pkt}",
    "No differences detected.":  "Различий не обнаружено.",
    "Changed bytes:":            "Изменённые байты:",
    "← changed bits":            "← изменённые биты",

    "Correlation candidates (sorted by confidence):\n":
        "Кандидаты корреляции (по убыванию уверенности):\n",
    "Possible {field} field": "Возможное поле {field}",
    "confidence={conf}":      "уверенность={conf}",
    "Need at least 3 labelled actions with numeric suffixes "
    "(e.g. speed_0, speed_1, speed_2…) to compute correlation.":
        "Нужно минимум 3 действия с числовым суффиксом "
        "(напр. speed_0, speed_1, speed_2…) для анализа корреляции.",
    "No correlation found above the confidence threshold.":
        "Корреляция выше порога уверенности не найдена.",

    # ---- Checksum panel ----
    "Run Checksum Analysis":   "Запустить анализ КС",
    "No data yet.":            "Данных пока нет.",
    "No packets captured yet.": "Пакеты ещё не захвачены.",
    "No checksum candidates found (all algorithms < 50% match).":
        "Кандидаты КС не найдены (все алгоритмы < 50% совпадений).",
    "<b>Checksum Candidates</b><br>": "<b>Кандидаты контрольной суммы</b><br>",
    "Algorithm":   "Алгоритм",
    "Byte pos":    "Позиция байта",
    "Match %":     "Совпадений %",

    # ---- Tabs (new) ----
    "Sketch Generator": "Генератор скетча",
    "Instructions":     "Инструкция",

    # ---- Sketch generator ----
    "Packet":                    "Пакет",
    "Packet length (bytes):":    "Длина пакета (байт):",
    "Decoder Address":           "Адрес декодера",
    "Byte position:":            "Позиция байта:",
    "Value (hex):":              "Значение (hex):",
    "Speed":                     "Скорость",
    "Bitmask (hex):":            "Маска битов (hex):",
    "Max value:":                "Макс. значение:",
    "Direction":                 "Направление",
    "Bit number (0=LSB):":       "Номер бита (0=LSB):",
    "Bit=1 means Forward:":      "Бит=1 означает «Вперёд»:",
    "Checksum":                  "Контрольная сумма",
    "Algorithm:":                "Алгоритм:",
    "Functions (F0–F7+)":        "Функции (F0–F7+)",
    "Byte pos":                  "Байт",
    "Bit":                       "Бит",
    "Enabled":                   "Вкл",
    "Generate Sketch":           "Сгенерировать скетч",
    "Generated Arduino sketch:": "Сгенерированный Arduino скетч:",
    "Copy":                      "Копировать",
    "Save .ino":                 "Сохранить .ino",
    "Save .ino":                 "Сохранить .ino",
}

_TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {},   # empty → key is returned as-is (English)
    "ru": _RU,
}
