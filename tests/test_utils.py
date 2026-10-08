from app.crawler.utils import parse_compact_number


def test_parse_compact_number() -> None:
    assert parse_compact_number("1.2K") == 1_200
    assert parse_compact_number("3.4M") == 3_400_000
    assert parse_compact_number("2.5万") == 25_000
    assert parse_compact_number("1亿") == 100_000_000
    assert parse_compact_number(None) == 0

