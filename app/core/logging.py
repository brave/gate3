import logging

HEAD_CHARS = 4
TAIL_CHARS = 4
ELLIPSIS = "..."
HEX_PREFIX = "0x"

# Query parameters that may carry wallet addresses or other user PII and must
# never be written to access logs in full.
SENSITIVE_QUERY_PARAMS = frozenset(
    {
        "wallet_address",
        "wallet_addresses",
        "recipient",
    }
)


def condense_value(value: str) -> str:
    """Shorten a sensitive value to ``head...tail`` (e.g. ``0x1234...7890``).

    A ``0x`` prefix is preserved and does not count toward the head characters,
    so EVM and Solana addresses both expose four leading and four trailing
    characters. Values too short to condense are returned unchanged; there is
    nothing meaningful to hide and the ellipsis would only add noise.
    """
    prefix = ""
    body = value
    if value.lower().startswith(HEX_PREFIX):
        prefix, body = value[:2], value[2:]

    if len(body) <= HEAD_CHARS + TAIL_CHARS + len(ELLIPSIS):
        return value
    return f"{prefix}{body[:HEAD_CHARS]}{ELLIPSIS}{body[-TAIL_CHARS:]}"


def condense_sensitive_query_params(full_path: str) -> str:
    """Condense the values of sensitive query parameters in a request path.

    Non-sensitive parameters are preserved verbatim so logs stay readable.
    """
    path, sep, query = full_path.partition("?")
    if not sep or not any(key in query for key in SENSITIVE_QUERY_PARAMS):
        return full_path

    condensed_pairs = []
    for pair in query.split("&"):
        key, eq, value = pair.partition("=")
        if eq and key in SENSITIVE_QUERY_PARAMS:
            condensed_pairs.append(f"{key}={condense_value(value)}")
        else:
            condensed_pairs.append(pair)

    return f"{path}{sep}{'&'.join(condensed_pairs)}"


class CondenseSensitiveQueryParamsFilter(logging.Filter):
    """Condenses sensitive query parameters in uvicorn access log records.

    Uvicorn emits access records whose ``args`` is a 5-tuple of
    ``(client_addr, method, full_path, http_version, status_code)``, where
    ``full_path`` includes the raw query string. We rewrite it in place so the
    downstream formatter only ever sees the shortened values.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) == 5:
            record.args = (
                args[:2] + (condense_sensitive_query_params(args[2]),) + args[3:]
            )
        return True


def install_access_log_sanitizer() -> None:
    """Attach the condensing filter to uvicorn's access logger.

    Safe to call multiple times; the filter is only installed once.
    """
    access_logger = logging.getLogger("uvicorn.access")
    if not any(
        isinstance(f, CondenseSensitiveQueryParamsFilter) for f in access_logger.filters
    ):
        access_logger.addFilter(CondenseSensitiveQueryParamsFilter())
