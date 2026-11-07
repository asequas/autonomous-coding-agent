def calc_total(items):
    """Sum price * quantity over (price, quantity) pairs."""
    return sum(price * quantity for price, quantity in items)
