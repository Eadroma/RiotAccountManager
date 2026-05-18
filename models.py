from dataclasses import dataclass, field


@dataclass
class AccountEntry:
    """Holds a single account's credentials in plaintext."""

    username: str
    password: str
    note: str = field(default="")
    last_used: str = field(default="")  # ISO 8601, e.g. "2026-04-13T14:23:00"
    game: str = field(default="")
    group: str = field(default="")
