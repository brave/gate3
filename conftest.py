"""
Root conftest.py - Test configuration for all tests.

This file is automatically discovered by pytest and runs before any tests.
It sets up the test environment by configuring environment variables
BEFORE any application code (including Settings) is imported, and holds
fixtures shared across packages.
"""

import os

import pytest

# Set environment variables BEFORE importing any app code
# This ensures Settings() loads the correct env file
os.environ["ENV_FILE"] = "env.test"


@pytest.fixture
def metric_value():
    """Read one sample from the default Prometheus registry (0.0 if unset)."""
    from prometheus_client import REGISTRY

    def read(name: str, **labels: str) -> float:
        return REGISTRY.get_sample_value(name, labels) or 0.0

    return read
