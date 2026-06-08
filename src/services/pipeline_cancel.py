"""Shared pipeline cancellation exception."""


class PipelineCancelled(Exception):
    """Raised when the user requests cancellation."""
