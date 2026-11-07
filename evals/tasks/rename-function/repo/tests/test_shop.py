from shop.cart import calc_total
from shop.checkout import checkout


def test_total():
    assert calc_total([(2.0, 3), (1.5, 2)]) == 9.0


def test_checkout_adds_tax():
    assert checkout([(10.0, 1)]) == 12.0
