"""Tests for the i18n module."""

import pytest

from src.i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, t
from src.i18n.en import TRANSLATIONS as EN
from src.i18n.zh import TRANSLATIONS as ZH


def test_default_language_is_english():
    assert DEFAULT_LANGUAGE == "en"


def test_t_returns_english_by_default():
    result = t("new.reset")
    assert result == EN["new.reset"]


def test_t_returns_chinese_when_lang_zh():
    result = t("new.reset", lang="zh")
    assert result == ZH["new.reset"]


def test_t_falls_back_to_english_for_missing_zh_key():
    # Find a key that exists in EN but not in ZH (if any)
    en_only_keys = set(EN.keys()) - set(ZH.keys())
    if en_only_keys:
        key = next(iter(en_only_keys))
        result = t(key, lang="zh")
        assert result == EN[key]
    else:
        # All keys present in both -- just verify fallback mechanism
        # with a totally unknown key
        result = t("nonexistent.key.xyz", lang="zh")
        assert result == "nonexistent.key.xyz"


def test_t_returns_key_for_unknown_key():
    result = t("does.not.exist")
    assert result == "does.not.exist"


def test_t_with_format_kwargs():
    result = t("new.reset")
    # new.reset has no placeholders, so it should return as-is
    assert isinstance(result, str)

    # Test a key with placeholders
    result = t("status.line", dir_display="/tmp", session_status="active", cost_str="")
    assert "/tmp" in result
    assert "active" in result


def test_t_unsupported_lang_falls_back_to_english():
    result = t("new.reset", lang="fr")
    assert result == EN["new.reset"]


def test_all_en_keys_exist_in_zh():
    """Completeness check: every EN key should have a ZH translation."""
    missing = set(EN.keys()) - set(ZH.keys())
    assert missing == set(), f"Keys missing from zh translations: {missing}"


def test_supported_languages():
    assert "en" in SUPPORTED_LANGUAGES
    assert "zh" in SUPPORTED_LANGUAGES
