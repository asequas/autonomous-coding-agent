from pathlib import Path

import shop.cart
from shop.checkout import checkout
from shop.report import summary

ROOT = Path(__file__).resolve().parents[1]


def test_new_name_works():
    assert shop.cart.compute_total([(2.0, 3)]) == 6.0
    assert checkout([(10.0, 1)]) == 12.0
    assert summary([[(1.0, 1)], [(2.0, 2)]]) == {"orders": 2, "revenue": 5.0}


def test_old_name_is_gone():
    assert not hasattr(shop.cart, "calc_total")
    leftovers = [
        str(p.relative_to(ROOT))
        for p in ROOT.rglob("*.py")
        if "_hidden_tests" not in p.parts and "calc_total" in p.read_text()
    ]
    assert leftovers == []
