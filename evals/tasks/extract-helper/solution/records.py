def normalize_contact(record):
    name = record.get("name", "").strip().title() or "Unknown"
    email = record.get("email", "").strip().lower()
    return name, email


def format_user(user):
    name, email = normalize_contact(user)
    return f"{name} <{email}>"


def format_admin(admin):
    name, email = normalize_contact(admin)
    return f"{name} <{email}> [admin]"
