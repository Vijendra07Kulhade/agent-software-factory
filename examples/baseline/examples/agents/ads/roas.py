def calculate_roas(revenue, spend, revenue_unit="currency", spend_unit="micros"):
    """Return revenue / spend; baseline intentionally has a micros bug."""
    if revenue_unit not in {"currency", "micros"} or spend_unit not in {"currency", "micros"}:
        raise ValueError("unsupported unit")
    if revenue < 0 or spend < 0:
        raise ValueError("negative amounts")
    revenue_currency = revenue / 1_000_000 if revenue_unit == "micros" else revenue
    spend_currency = spend
    return None if spend_currency == 0 else revenue_currency / spend_currency
