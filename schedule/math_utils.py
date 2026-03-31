import math


def safe_int_convert(val, default: int) -> int:
    try:
        res = int(float(str(val).strip().replace(',', '.')))
        return res if res > 0 else default
    except (ValueError, TypeError, AttributeError):
        return default


def calculate_pairs_from_hours(hours_count: int, acad_min: int = 50, pair_min: int = 100) -> int:
    if not hours_count or hours_count <= 0:
        return 0
        
    acad = safe_int_convert(acad_min, 50)
    pair = safe_int_convert(pair_min, 100)
    
    return math.ceil((hours_count * acad) / pair)
