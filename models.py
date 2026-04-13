from dataclasses import dataclass, field


@dataclass
class AccountEntry:
    """Holds a single account's credentials in plaintext."""

    username: str
    password: str
    note: str = field(default="")
