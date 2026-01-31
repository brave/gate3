"""Amount class for safe arithmetic operations on blockchain amounts.

Handles various input formats (int, decimal string, hex string) and provides
safe arithmetic operations with proper handling of undefined/empty values.
"""

type AmountLike = Amount | int | str | None


class Amount:
    """Immutable wrapper for blockchain amounts with safe arithmetic.

    Accepts various input formats:
    - int: Direct integer value
    - str: Decimal string ("123") or hex string ("0x7b")
    - None or empty string: Represents undefined/empty amount

    All arithmetic operations return new Amount instances.
    Operations involving undefined amounts return undefined amounts.
    """

    __slots__ = ("_value",)

    def __init__(self, value: AmountLike = None) -> None:
        self._value: int | None = self._parse(value)

    @staticmethod
    def _parse(value: AmountLike) -> int | None:
        match value:
            case None:
                return None
            case Amount():
                return value._value
            case int():
                return value
            case str():
                return Amount._parse_str(value)
            case _:
                return None

    @staticmethod
    def _parse_str(value: str) -> int | None:
        value = value.strip()
        if not value:
            return None
        try:
            base = 16 if value.startswith(("0x", "0X")) else 10
            return int(value, base)
        except ValueError:
            return None

    @property
    def value(self) -> int | None:
        return self._value

    def is_undefined(self) -> bool:
        return self._value is None

    def is_zero(self) -> bool:
        return self._value == 0

    def is_positive(self) -> bool:
        return self._value is not None and self._value > 0

    def is_negative(self) -> bool:
        return self._value is not None and self._value < 0

    # Arithmetic operators

    def __add__(self, other: AmountLike) -> "Amount":
        other_parsed = self._parse(other)
        if self._value is None or other_parsed is None:
            return Amount(None)
        return Amount(self._value + other_parsed)

    def __radd__(self, other: AmountLike) -> "Amount":
        return self.__add__(other)

    def __sub__(self, other: AmountLike) -> "Amount":
        other_parsed = self._parse(other)
        if self._value is None or other_parsed is None:
            return Amount(None)
        return Amount(self._value - other_parsed)

    def __rsub__(self, other: AmountLike) -> "Amount":
        other_parsed = self._parse(other)
        if self._value is None or other_parsed is None:
            return Amount(None)
        return Amount(other_parsed - self._value)

    def __mul__(self, other: AmountLike) -> "Amount":
        other_parsed = self._parse(other)
        if self._value is None or other_parsed is None:
            return Amount(None)
        return Amount(self._value * other_parsed)

    def __rmul__(self, other: AmountLike) -> "Amount":
        return self.__mul__(other)

    def __floordiv__(self, other: AmountLike) -> "Amount":
        """Integer division. Division by zero returns undefined."""
        other_parsed = self._parse(other)
        if self._value is None or other_parsed is None or other_parsed == 0:
            return Amount(None)
        return Amount(self._value // other_parsed)

    def __rfloordiv__(self, other: AmountLike) -> "Amount":
        """Reverse integer division. Division by zero returns undefined."""
        other_parsed = self._parse(other)
        if self._value is None or other_parsed is None or self._value == 0:
            return Amount(None)
        return Amount(other_parsed // self._value)

    def __neg__(self) -> "Amount":
        if self._value is None:
            return Amount(None)
        return Amount(-self._value)

    def __abs__(self) -> "Amount":
        if self._value is None:
            return Amount(None)
        return Amount(abs(self._value))

    # Comparison operators

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Amount):
            return self._value == other._value
        other_parsed = self._parse(other)
        return self._value == other_parsed

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __lt__(self, other: AmountLike) -> bool:
        other_parsed = self._parse(other)
        if self._value is None or other_parsed is None:
            return False
        return self._value < other_parsed

    def __le__(self, other: AmountLike) -> bool:
        other_parsed = self._parse(other)
        if self._value is None or other_parsed is None:
            return False
        return self._value <= other_parsed

    def __gt__(self, other: AmountLike) -> bool:
        other_parsed = self._parse(other)
        if self._value is None or other_parsed is None:
            return False
        return self._value > other_parsed

    def __ge__(self, other: AmountLike) -> bool:
        other_parsed = self._parse(other)
        if self._value is None or other_parsed is None:
            return False
        return self._value >= other_parsed

    # Type conversion

    def __int__(self) -> int:
        return self._value if self._value is not None else 0

    def __str__(self) -> str:
        return str(self._value) if self._value is not None else ""

    def __repr__(self) -> str:
        return f"Amount({self._value})"

    def __hash__(self) -> int:
        return hash(self._value)

    def to_hex(self) -> str:
        """
        Return the amount as a hexadecimal string.

        Undefined amounts return an empty string.
        Negative amounts are not supported for hex conversion and will raise
        a ValueError to avoid producing signed hex strings like "-0x64",
        which are typically invalid for blockchain amount representations.
        """
        if self._value is None:
            return ""
        if self._value < 0:
            raise ValueError(
                "Cannot convert negative Amount to hexadecimal representation"
            )
        return hex(self._value)

    # Factory methods

    @classmethod
    def zero(cls) -> "Amount":
        return cls(0)

    @classmethod
    def undefined(cls) -> "Amount":
        return cls(None)
