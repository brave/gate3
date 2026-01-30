import pytest

from .amount import Amount

# Parsing tests


@pytest.mark.parametrize(
    "input_value,expected",
    [
        (123, 123),
        (0, 0),
        (-456, -456),
        ("123", 123),
        ("0", 0),
        ("-456", -456),
        ("0x7b", 123),
        ("0x0", 0),
        ("0xff", 255),
        ("0X7B", 123),
        ("0XFF", 255),
        ("0xde0b6b3a7640000", 1000000000000000000),  # 1 ETH in wei
    ],
)
def test_parse_valid_values(input_value, expected):
    assert Amount(input_value).value == expected


@pytest.mark.parametrize(
    "input_value",
    [
        None,
        "",
        "   ",
        "abc",
        "0xZZZ",
        "-0x64",  # Negative hex strings are not supported
        "-0XFF",
    ],
)
def test_parse_invalid_returns_none(input_value):
    assert Amount(input_value).value is None


def test_parse_amount_copy():
    original = Amount(123)
    assert Amount(original).value == 123


# State check tests


@pytest.mark.parametrize(
    "input_value,expected",
    [
        (None, True),
        (0, False),
        (123, False),
    ],
)
def test_is_undefined(input_value, expected):
    assert Amount(input_value).is_undefined() is expected


@pytest.mark.parametrize(
    "input_value,expected",
    [
        (0, True),
        ("0", True),
        ("0x0", True),
        (123, False),
        (None, False),
    ],
)
def test_is_zero(input_value, expected):
    assert Amount(input_value).is_zero() is expected


@pytest.mark.parametrize(
    "input_value,is_pos,is_neg",
    [
        (123, True, False),
        (0, False, False),
        (-123, False, True),
        (None, False, False),
    ],
)
def test_is_positive_negative(input_value, is_pos, is_neg):
    amt = Amount(input_value)
    assert amt.is_positive() is is_pos
    assert amt.is_negative() is is_neg


# Arithmetic tests


@pytest.mark.parametrize(
    "a,b,expected",
    [
        (100, 50, 150),
        (100, "50", 150),
        (100, "0x32", 150),
        (100, Amount(50), 150),
    ],
)
def test_add(a, b, expected):
    assert (Amount(a) + b).value == expected


def test_radd():
    assert (50 + Amount(100)).value == 150


@pytest.mark.parametrize("a,b", [(100, None), (None, 100)])
def test_add_undefined(a, b):
    assert (Amount(a) + b).is_undefined()


@pytest.mark.parametrize(
    "a,b,expected",
    [
        (100, 30, 70),
        (100, "30", 70),
        (30, 100, -70),
    ],
)
def test_sub(a, b, expected):
    assert (Amount(a) - b).value == expected


def test_rsub():
    assert (100 - Amount(30)).value == 70


@pytest.mark.parametrize("a,b", [(100, None), (None, 100)])
def test_sub_undefined(a, b):
    assert (Amount(a) - b).is_undefined()


@pytest.mark.parametrize(
    "a,b,expected",
    [
        (100, 3, 300),
        (100, "3", 300),
    ],
)
def test_mul(a, b, expected):
    assert (Amount(a) * b).value == expected


def test_rmul():
    assert (3 * Amount(100)).value == 300


@pytest.mark.parametrize("a,b", [(100, None), (None, 100)])
def test_mul_undefined(a, b):
    assert (Amount(a) * b).is_undefined()


@pytest.mark.parametrize(
    "a,b,expected",
    [
        (100, 3, 33),
        (100, "4", 25),
    ],
)
def test_floordiv(a, b, expected):
    assert (Amount(a) // b).value == expected


@pytest.mark.parametrize("divisor", [0, "0"])
def test_floordiv_by_zero(divisor):
    assert (Amount(100) // divisor).is_undefined()


@pytest.mark.parametrize("a,b", [(100, None), (None, 100)])
def test_floordiv_undefined(a, b):
    assert (Amount(a) // b).is_undefined()


def test_rfloordiv():
    assert (100 // Amount(3)).value == 33


@pytest.mark.parametrize("divisor", [0, "0"])
def test_rfloordiv_by_zero(divisor):
    assert (100 // Amount(divisor)).is_undefined()


@pytest.mark.parametrize("a,b", [(100, None), (None, 100)])
def test_rfloordiv_undefined(a, b):
    assert (b // Amount(a)).is_undefined()


@pytest.mark.parametrize(
    "input_value,expected",
    [
        (100, -100),
        (-100, 100),
    ],
)
def test_neg(input_value, expected):
    assert (-Amount(input_value)).value == expected


def test_neg_undefined():
    assert (-Amount(None)).is_undefined()


@pytest.mark.parametrize(
    "input_value,expected",
    [
        (-100, 100),
        (100, 100),
    ],
)
def test_abs(input_value, expected):
    assert abs(Amount(input_value)).value == expected


def test_abs_undefined():
    assert abs(Amount(None)).is_undefined()


# Comparison tests


@pytest.mark.parametrize(
    "a,b,expected",
    [
        (100, 50, True),
        (100, 100, False),
        (100, 150, False),
        (100, None, False),
    ],
)
def test_gt(a, b, expected):
    assert (Amount(a) > b) is expected


def test_gt_undefined_lhs():
    assert (Amount(None) > 100) is False


@pytest.mark.parametrize(
    "a,b,expected",
    [
        (100, 50, True),
        (100, 100, True),
        (100, 150, False),
        (100, None, False),
    ],
)
def test_ge(a, b, expected):
    assert (Amount(a) >= b) is expected


def test_ge_undefined_lhs():
    assert (Amount(None) >= 100) is False


@pytest.mark.parametrize(
    "a,b,expected",
    [
        (50, 100, True),
        (100, 100, False),
        (150, 100, False),
        (100, None, False),
    ],
)
def test_lt(a, b, expected):
    assert (Amount(a) < b) is expected


def test_lt_undefined_lhs():
    assert (Amount(None) < 100) is False


@pytest.mark.parametrize(
    "a,b,expected",
    [
        (50, 100, True),
        (100, 100, True),
        (150, 100, False),
        (100, None, False),
    ],
)
def test_le(a, b, expected):
    assert (Amount(a) <= b) is expected


def test_le_undefined_lhs():
    assert (Amount(None) <= 100) is False


@pytest.mark.parametrize(
    "a,b,expected",
    [
        (100, 100, True),
        (100, "100", True),
        (100, "0x64", True),
        (100, Amount(100), True),
        (100, 50, False),
    ],
)
def test_eq(a, b, expected):
    assert (Amount(a) == b) is expected


def test_eq_both_none():
    assert Amount(None) == Amount(None)


def test_ne():
    assert (Amount(100) != 50) is True
    assert (Amount(100) != 100) is False


# Conversion tests


@pytest.mark.parametrize(
    "input_value,expected",
    [
        (123, 123),
        (None, 0),
    ],
)
def test_int_conversion(input_value, expected):
    assert int(Amount(input_value)) == expected


@pytest.mark.parametrize(
    "input_value,expected",
    [
        (123, "123"),
        (None, ""),
    ],
)
def test_str_conversion(input_value, expected):
    assert str(Amount(input_value)) == expected


@pytest.mark.parametrize(
    "input_value,expected",
    [
        (123, "0x7b"),
        (255, "0xff"),
        (None, ""),
    ],
)
def test_to_hex(input_value, expected):
    assert Amount(input_value).to_hex() == expected


def test_to_hex_negative_raises():
    with pytest.raises(ValueError, match="negative"):
        Amount(-100).to_hex()


# Equality and hashing tests


def test_amount_equality():
    assert Amount(100) == Amount(100)
    assert Amount(100) == Amount("100")
    assert Amount(None) == Amount(None)
    assert Amount(100) != Amount(50)


def test_hash_in_set():
    assert hash(Amount(100)) == hash(Amount(100))
    amounts = {Amount(100), Amount(100), Amount(50)}
    assert len(amounts) == 2


# Factory method tests


def test_zero():
    assert Amount.zero().value == 0
    assert Amount.zero().is_zero() is True


def test_undefined():
    assert Amount.undefined().value is None
    assert Amount.undefined().is_undefined() is True
