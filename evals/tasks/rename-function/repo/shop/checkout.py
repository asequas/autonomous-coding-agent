from shop.cart import calc_total

TAX_RATE = 0.2


def checkout(items):
    subtotal = calc_total(items)
    return round(subtotal * (1 + TAX_RATE), 2)
