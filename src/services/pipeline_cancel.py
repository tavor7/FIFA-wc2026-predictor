"""Shared pipeline cancellation exception."""


class PipelineCancelled(Exception):
    """Raised when the user requests cancellation."""


class _PipelineCompleteEarly(Exception):
    """All steps skipped — exit the run loop immediately."""
