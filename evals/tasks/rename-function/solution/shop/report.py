from shop import cart


def summary(orders):
    totals = [cart.compute_total(items) for items in orders]
    return {"orders": len(totals), "revenue": sum(totals)}
