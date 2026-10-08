import re


def parse_compact_number(value: str | None) -> int:
    if not value:
        return 0

    normalized = value.strip().replace(",", "").upper()
    match = re.search(r"([\d.]+)\s*([KMB]|万|亿)?", normalized)
    if not match:
        return 0

    number = float(match.group(1))
    multiplier = {
        "K": 1_000,
        "M": 1_000_000,
        "B": 1_000_000_000,
        "万": 10_000,
        "亿": 100_000_000,
    }.get(match.group(2), 1)
    return int(number * multiplier)

