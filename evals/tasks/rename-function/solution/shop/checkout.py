from shop.cart import compute_total

TAX_RATE = 0.2


def checkout(items):
    subtotal = compute_total(items)
    return round(subtotal * (1 + TAX_RATE), 2)
