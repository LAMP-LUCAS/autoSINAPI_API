"""
Sandbox utilities for AutoSINAPI.

Provides functions to check if the application is running in sandbox mode,
which uses isolated data (tables prefixed with `sandbox_`) to avoid
polluting production data during testing.
"""

import os


def is_sandbox_mode() -> bool:
    """
    Check if the application is running in sandbox mode.
    
    Returns:
        True if AUTOSINAPI_SANDBOX=true, False otherwise.
    """
    return os.getenv("AUTOSINAPI_SANDBOX", "false").lower() == "true"


def get_sandbox_table_prefix() -> str:
    """
    Get the table name prefix for sandbox mode.
    
    Returns:
        "sandbox_" if in sandbox mode, empty string otherwise.
    """
    if is_sandbox_mode():
        return "sandbox_"
    return ""


def get_sandbox_table_name(base_name: str) -> str:
    """
    Get the full table name with sandbox prefix if applicable.
    
    Args:
        base_name: The original table name (e.g., "insumos")
    
    Returns:
        Sandbox-prefixed table name if in sandbox mode,
        original name otherwise.
    """
    return f"{get_sandbox_table_prefix()}{base_name}"


def is_data_mocking_enabled() -> bool:
    """
    Check if data mocking is enabled for tests.
    
    Returns:
        True if AUTOSINAPI_SKIP_DOWNLOAD=true, False otherwise.
    """
    return os.getenv("AUTOSINAPI_SKIP_DOWNLOAD", "false").lower() == "true"
