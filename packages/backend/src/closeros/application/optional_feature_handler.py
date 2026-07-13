"""Controlled permanent failure for disabled optional production features."""

from __future__ import annotations

from closeros.domain.outbox import OutboxErrorCode, OutboxJob


class OptionalFeatureDisabledHandlerError(Exception):
    def __init__(self) -> None:
        self.error_code = OutboxErrorCode.UNSUPPORTED_OPERATION
        self.permanent = True
        super().__init__("optional feature is disabled")


class OptionalFeatureDisabledHandler:
    """Permanent controlled failure when a disabled feature job arrives unexpectedly."""

    async def handle(self, *, job: OutboxJob) -> None:
        _ = job
        raise OptionalFeatureDisabledHandlerError()


__all__ = [
    "OptionalFeatureDisabledHandler",
    "OptionalFeatureDisabledHandlerError",
]
