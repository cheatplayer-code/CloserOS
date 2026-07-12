"""Explicit provider capability taxonomy for supported messaging features."""

from enum import StrEnum


class ProviderCapability(StrEnum):
    INBOUND_TEXT = "inbound_text"
    INTERACTIVE_REPLY = "interactive_reply"
    REACTION = "reaction"
    MESSAGE_STATUS = "message_status"
    MEDIA_REFERENCE = "media_reference"
    OUTBOUND_FREE_FORM_TEXT = "outbound_free_form_text"
    OUTBOUND_APPROVED_TEMPLATE = "outbound_approved_template"


__all__ = ["ProviderCapability"]
