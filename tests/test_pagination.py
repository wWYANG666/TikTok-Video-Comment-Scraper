from app.main import PAGE_SIZE, pagination


def test_pagination_uses_ten_items_per_page() -> None:
    pager = pagination(total=26, requested_page=2)

    assert PAGE_SIZE == 10
    assert pager["page"] == 2
    assert pager["pages"] == 3
    assert pager["offset"] == 10


def test_pagination_clamps_out_of_range_page() -> None:
    assert pagination(total=3, requested_page=99)["page"] == 1

