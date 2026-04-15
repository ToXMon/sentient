"""Rate limiter instance — shared across modules to avoid circular imports."""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["10/minute"],
    headers_enabled=True,
)
