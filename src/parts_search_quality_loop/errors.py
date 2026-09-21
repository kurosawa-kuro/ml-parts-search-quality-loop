"""Public errors must never interpolate configuration or secret values."""


class FoundationError(Exception):
    """Invalid input or failed foundation operation."""
