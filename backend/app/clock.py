"""Ghana uses UTC; business dates must not depend on the host timezone."""

from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc)


def today():
    return now().date()
