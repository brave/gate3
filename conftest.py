"""
Root conftest.py - Test configuration for all tests.

This file is automatically discovered by pytest and runs before any tests.
It sets up the test environment by configuring environment variables
BEFORE any application code (including Settings) is imported.
"""

import os

# Set environment variables BEFORE importing any app code
# This ensures Settings() loads the correct env file
os.environ["ENV_FILE"] = "env.test"
