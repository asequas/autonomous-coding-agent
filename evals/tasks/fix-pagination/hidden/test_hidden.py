from pagination import page_count, paginate

ITEMS = list(range(10))


def test_first_page():
    assert paginate(ITEMS, 1, 3) == [0, 1, 2]


def test_last_partial_page():
    assert paginate(ITEMS, 4, 3) == [9]


def test_page_past_the_end_is_empty():
    assert paginate(ITEMS, 5, 3) == []


def test_page_count_rounds_up():
    assert page_count(ITEMS, 3) == 4
    assert page_count(list(range(9)), 3) == 3
    assert page_count([], 3) == 0
