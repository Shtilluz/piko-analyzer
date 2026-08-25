"""
Tests for the i18n translation system.
"""

import pytest
import analyzer.i18n as i18n


@pytest.fixture(autouse=True)
def reset_language():
    """Restore English after each test."""
    yield
    i18n.set_language("en")
    # Clear callbacks added during tests
    i18n._callbacks.clear()


class TestBasicTranslation:
    def test_english_fallback(self):
        i18n.set_language("en")
        assert i18n.tr("Connect") == "Connect"

    def test_russian_known_key(self):
        i18n.set_language("ru")
        assert i18n.tr("Connect") == "Подключить"

    def test_missing_key_returns_key(self):
        i18n.set_language("ru")
        assert i18n.tr("SomeKeyThatDoesNotExist") == "SomeKeyThatDoesNotExist"

    def test_missing_key_english(self):
        i18n.set_language("en")
        assert i18n.tr("Anything") == "Anything"

    def test_set_and_get_language(self):
        i18n.set_language("ru")
        assert i18n.get_language() == "ru"
        i18n.set_language("en")
        assert i18n.get_language() == "en"

    def test_invalid_language_raises(self):
        with pytest.raises(ValueError):
            i18n.set_language("de")


class TestFormatting:
    def test_kwargs_applied_english(self):
        i18n.set_language("en")
        result = i18n.tr("Connected: {port}", port="COM3")
        assert result == "Connected: COM3"

    def test_kwargs_applied_russian(self):
        i18n.set_language("ru")
        result = i18n.tr("Connected: {port}", port="COM3")
        assert "COM3" in result

    def test_missing_kwarg_does_not_crash(self):
        i18n.set_language("ru")
        # Should not raise — just return partially formatted or key
        result = i18n.tr("Connected: {port}")
        assert isinstance(result, str)

    def test_packets_format(self):
        i18n.set_language("en")
        result = i18n.tr("Packets: {total}", total="1,234")
        assert "1,234" in result

        i18n.set_language("ru")
        result = i18n.tr("Packets: {total}", total="1,234")
        assert "1,234" in result


class TestCallback:
    def test_callback_fired_on_change(self):
        received = []
        i18n.on_language_changed(received.append)
        i18n.set_language("ru")
        assert received == ["ru"]
        i18n.set_language("en")
        assert received == ["ru", "en"]

    def test_callback_not_fired_on_invalid(self):
        received = []
        i18n.on_language_changed(received.append)
        with pytest.raises(ValueError):
            i18n.set_language("xx")
        assert received == []

    def test_crashing_callback_does_not_break_others(self):
        results = []

        def bad_cb(lang):
            raise RuntimeError("oops")

        def good_cb(lang):
            results.append(lang)

        i18n.on_language_changed(bad_cb)
        i18n.on_language_changed(good_cb)
        i18n.set_language("ru")
        assert results == ["ru"]


class TestLanguageList:
    def test_languages_contains_en_ru(self):
        assert "en" in i18n.LANGUAGES
        assert "ru" in i18n.LANGUAGES

    def test_language_names(self):
        assert "English" in i18n.LANGUAGES.values()
        assert "Русский" in i18n.LANGUAGES.values()


class TestRussianCoverage:
    """Spot-check that critical UI strings have Russian translations."""

    CRITICAL_KEYS = [
        "Connect",
        "Disconnect",
        "Serial",
        "Statistics",
        "Byte Analysis",
        "Bit Analysis",
        "Actions",
        "Charts",
        "Checksum",
        "Save Session",
        "Reset Statistics",
        "Run Checksum Analysis",
        "Run Correlation Analysis",
        "1. Start Baseline",
        "2. Action Now",
        "3. Stop & Save",
        "Cancel",
        "State: IDLE",
        "No data yet.",
        "CONSTANT",
        "MOSTLY_CONSTANT",
        "VARIABLE",
    ]

    @pytest.mark.parametrize("key", CRITICAL_KEYS)
    def test_has_russian(self, key):
        i18n.set_language("ru")
        translated = i18n.tr(key)
        # Translation must differ from the key (i.e. not a fallback)
        assert translated != key, f"Missing Russian translation for: {key!r}"
        # And must contain at least one Cyrillic character
        assert any("Ѐ" <= c <= "ӿ" for c in translated), (
            f"Russian translation for {key!r} has no Cyrillic: {translated!r}"
        )
