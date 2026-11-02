"""Sprachen: Texte im Code sind Englisch, _() holt die Uebersetzung der eingestellten Sprache.

Die Sprache wird beim Start aus settings.json gelesen (Standard: Englisch). Ein Wechsel gilt nach einem
Neustart, weil viele Beschriftungen schon beim Laden der Module festgelegt werden.
"""
import json
import os

LANGUAGES = [
    ("en", "English"),
    ("de", "Deutsch"),
    ("ja", "日本語"),
    ("es", "Español"),
    ("fr", "Français"),
    ("pt", "Português"),
    ("ko", "한국어"),
    ("zh", "简体中文"),
    ("tr", "Türkçe"),
    ("ru", "Русский"),
]
CODES = [c for c, _n in LANGUAGES]
DEFAULT = "en"


def _settings_path():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "Snipload", "settings.json")


def _read_language():
    forced = os.environ.get("SNIPLOAD_LANG")
    if forced in CODES:
        return forced
    try:
        with open(_settings_path(), encoding="utf-8") as f:
            code = json.load(f).get("language")
        if code in CODES:
            return code
    except Exception:
        pass
    return DEFAULT


def _load_table(code):
    if code == "en":
        return {}
    try:
        from . import locales
        return getattr(locales, "load")(code)
    except Exception:
        return {}


LANG = _read_language()
_TABLE = _load_table(LANG)


def _(text):
    """Uebersetzt einen englischen Text in die eingestellte Sprache (sonst bleibt er Englisch)."""
    return _TABLE.get(text, text) if _TABLE else text


def lang():
    return LANG


def name_of(code):
    return dict(LANGUAGES).get(code, code)


def is_cjk():
    return LANG in ("ja", "ko", "zh")
