from enum import Enum


class Environment(str, Enum):
    """OAuth environment for sandbox vs production endpoints."""

    SANDBOX = "sandbox"
    PRODUCTION = "production"
