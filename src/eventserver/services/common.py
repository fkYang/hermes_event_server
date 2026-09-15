def mask_identifier(value: str | None) -> str | None:
    if value is None:
        return None
    if len(value) <= 6:
        return "***"
    return f"{value[:3]}***{value[-3:]}"
