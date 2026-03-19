"""Internationalization (i18n) module for Claude Code Telegram Bot.

Provides the ``t(key, lang, **kwargs)`` helper that returns a translated,
format-interpolated string.  Language modules are loaded lazily on first
access.
"""

from typing import Dict, Optional

from .en import TRANSLATIONS as EN
from .zh import TRANSLATIONS as ZH

# Registry of loaded language packs.
_LANG_MAP: Dict[str, Dict[str, str]] = {
    "en": EN,
    "zh": ZH,
}

# Canonical display names (used by /lang command).
LANG_NAMES: Dict[str, str] = {
    "en": "English",
    "zh": "\u4e2d\u6587",
}

SUPPORTED_LANGUAGES = list(_LANG_MAP.keys())

DEFAULT_LANGUAGE = "en"


def t(key: str, lang: Optional[str] = None, **kwargs: object) -> str:
    """Return translated string for *key* in *lang*.

    Falls back to English when *lang* is not supported or when the key
    is missing in the requested language.  Any ``{placeholder}`` values
    in the template are interpolated from *kwargs*.

    >>> t("new.reset", "zh")
    '\u5de5\u4f5c\u968e\u6bb5\u5df2\u91cd\u7f6e\u3002\u63a5\u4e0b\u4f86\u8981\u505a\u4ec0\u9ebc\uff1f'
    >>> t("status.line", dir_display="/tmp", session_status="active", cost_str="")
    '\U0001f4c2 /tmp \u00b7 Session: active'
    """
    lang = lang or DEFAULT_LANGUAGE
    pack = _LANG_MAP.get(lang, _LANG_MAP[DEFAULT_LANGUAGE])
    template = pack.get(key)
    if template is None:
        # Fall back to English
        template = _LANG_MAP[DEFAULT_LANGUAGE].get(key, key)
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError):
            return template
    return template


def get_user_lang(context: object) -> str:
    """Extract language preference from ``context.user_data``.

    Works with ``telegram.ext.ContextTypes.DEFAULT_TYPE``.  Returns
    :data:`DEFAULT_LANGUAGE` when no preference has been stored.
    """
    user_data = getattr(context, "user_data", None)
    if user_data and isinstance(user_data, dict):
        return user_data.get("language", DEFAULT_LANGUAGE)
    return DEFAULT_LANGUAGE
