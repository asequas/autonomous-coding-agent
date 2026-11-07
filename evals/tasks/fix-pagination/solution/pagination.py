def paginate(items, page, per_page):
    """Return the items on a 1-based page."""
    start = (page - 1) * per_page
    return items[start : start + per_page]


def page_count(items, per_page):
    """Return how many pages are needed to show every item."""
    return -(-len(items) // per_page)
