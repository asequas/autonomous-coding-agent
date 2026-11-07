from pkg.calculator import Calculator


def evaluate(expression):
    return Calculator().evaluate(expression)


def test_modulo():
    assert evaluate("10 % 3") == 1
    assert evaluate("7 + 10 % 4") == 9


def test_power():
    assert evaluate("2 ** 10") == 1024
    assert evaluate("2 * 3 ** 2") == 18


def test_power_is_right_associative():
    assert evaluate("2 ** 3 ** 2") == 512


def test_existing_behaviour_unchanged():
    assert evaluate("2 * 3 - 8 / 2 + 5") == 7
