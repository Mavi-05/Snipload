"""Uebersetzungen. Jede Sprache ist ein Modul mit T = {Nummer: Text}; die Nummer zeigt in _keys.KEYS.

Die Module werden hier ausdruecklich importiert, damit PyInstaller sie in die exe packt.
"""
import string

from ._keys import KEYS


def _module(code):
    if code == "de":
        from . import de as m
    elif code == "ja":
        from . import ja as m
    elif code == "es":
        from . import es as m
    elif code == "fr":
        from . import fr as m
    elif code == "pt":
        from . import pt as m
    elif code == "ko":
        from . import ko as m
    elif code == "zh":
        from . import zh as m
    elif code == "tr":
        from . import tr as m
    elif code == "ru":
        from . import ru as m
    else:
        return None
    return m


def placeholders(text):
    return sorted({f for _l, f, _s, _c in string.Formatter().parse(text) if f})


def load(code):
    """{englischer Text: Uebersetzung}. Eintraege mit falschen Platzhaltern werden verworfen (bleiben Englisch),
    damit ein Tippfehler in einer Uebersetzung nie einen Absturz ausloest."""
    m = _module(code)
    if m is None:
        return {}
    out = {}
    for i, text in m.T.items():
        if 0 <= i < len(KEYS) and text:
            key = KEYS[i]
            try:
                if placeholders(key) == placeholders(text):
                    out[key] = text
            except ValueError:
                pass
    return out
