"""Production feature capability flags resolved from environment."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _is_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class ProductionFeatureCapabilities:
    """Explicit enabled/disabled state for optional production integrations."""

    whatsapp_enabled: bool
    crm_enabled: bool
    notifications_enabled: bool
    media_scanning_enabled: bool
    external_ai_enabled: bool

    def as_safe_dict(self) -> dict[str, str]:
        return {
            "whatsapp": "enabled" if self.whatsapp_enabled else "disabled",
            "crm": "enabled" if self.crm_enabled else "disabled",
            "notifications": "enabled" if self.notifications_enabled else "disabled",
            "media_scanning": "enabled" if self.media_scanning_enabled else "disabled",
            "external_ai": "enabled" if self.external_ai_enabled else "disabled",
        }


def resolve_production_feature_capabilities() -> ProductionFeatureCapabilities:
    return ProductionFeatureCapabilities(
        whatsapp_enabled=_is_enabled("WHATSAPP_ENABLED"),
        crm_enabled=_is_enabled("CRM_ENABLED"),
        notifications_enabled=_is_enabled("NOTIFICATIONS_ENABLED"),
        media_scanning_enabled=_is_enabled("CLAMAV_ENABLED")
        or _is_enabled("MEDIA_SCANNING_ENABLED"),
        external_ai_enabled=_is_enabled("AI_EXTERNAL_CALLS_ENABLED"),
    )


__all__ = [
    "ProductionFeatureCapabilities",
    "resolve_production_feature_capabilities",
]
