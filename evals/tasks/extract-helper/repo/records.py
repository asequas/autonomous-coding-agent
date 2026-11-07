def format_user(user):
    name = user.get("name", "").strip().title()
    email = user.get("email", "").strip().lower()
    if not name:
        name = "Unknown"
    return f"{name} <{email}>"


def format_admin(admin):
    name = admin.get("name", "").strip().title()
    email = admin.get("email", "").strip().lower()
    if not name:
        name = "Unknown"
    return f"{name} <{email}> [admin]"
