from pagination import paginate


def test_second_page():
    assert paginate(list(range(10)), 2, 3) == [3, 4, 5]
