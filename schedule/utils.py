import re
from typing import Union


_EMPTY_STRINGS = frozenset({
    '', 'none', 'null', '-', '—', 'н/д', 'нет', 'n/a', 'нб',
})

_NUMBER_RE = re.compile(r'(\d+(?:[.,]\d+)?)')


def safe_int(val) -> int:
    if val is None:
        return 0
    if isinstance(val, bool):
        return int(val)
    if isinstance(val, (int, float)):
        return int(val)
    try:
        s = str(val).strip()
        if s.lower() in _EMPTY_STRINGS:
            return 0
        try:
            return int(float(s.replace(',', '.')))
        except ValueError:
            pass
        m = _NUMBER_RE.search(s)
        if m:
            return int(float(m.group(1).replace(',', '.')))
        return 0
    except (ValueError, TypeError, AttributeError):
        return 0


def safe_float(val, decimals: int = 2) -> float:
    if val is None:
        return 0.0
    if isinstance(val, bool):
        return float(int(val))
    if isinstance(val, (int, float)):
        return round(float(val), decimals)
    try:
        s = str(val).strip()
        if s.lower() in _EMPTY_STRINGS:
            return 0.0
        try:
            return round(float(s.replace(',', '.')), decimals)
        except ValueError:
            pass
        m = _NUMBER_RE.search(s)
        if m:
            return round(float(m.group(1).replace(',', '.')), decimals)
        return 0.0
    except (ValueError, TypeError, AttributeError):
        return 0.0


def safe_str(val, default: str = '') -> str:
    if val is None:
        return default
    s = str(val).strip()
    return default if s.lower() in ('none', 'null') else s