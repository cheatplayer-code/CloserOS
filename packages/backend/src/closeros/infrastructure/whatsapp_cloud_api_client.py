"""Meta WhatsApp Cloud API client using explicit versioned Graph endpoints."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from closeros.domain.whatsapp_messaging_policy import GRAPH_API_VERSION

_DEFAULT_CONNECT_TIMEOUT_SECONDS = 5.0
_DEFAULT_READ_TIMEOUT_SECONDS = 15.0
_DEFAULT_WRITE_TIMEOUT_SECONDS = 15.0
_DEFAULT_POOL_TIMEOUT_SECONDS = 5.0
_MAX_RESPONSE_BYTES = 256 * 1024


class WhatsAppCloudApiError(Exception):
    """Safe provider API failure."""


class WhatsAppCloudApiClientError(WhatsAppCloudApiError):
    """Raised when the client cannot complete a request safely."""


class WhatsAppCloudApiResponseError(WhatsAppCloudApiError):
    """Raised when the provider returns an unsafe or invalid response."""

    def __init__(self, *, error_code: str) -> None:
        self.error_code = error_code
        super().__init__("whatsapp api response error")


@dataclass(frozen=True, slots=True)
class WhatsAppSendTextRequest:
    recipient_wa_id: str
    body: str


@dataclass(frozen=True, slots=True)
class WhatsAppSendTemplateRequest:
    recipient_wa_id: str
    template_name: str
    language_code: str
    body_parameters: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WhatsAppSendResult:
    provider_message_id: str


@dataclass(frozen=True, slots=True)
class WhatsAppTemplateListItem:
    provider_template_id: str
    name: str
    language_code: str
    category: str
    approval_status: str
    component_shape: tuple[str, ...]
    parameter_count: int


@dataclass(frozen=True, slots=True)
class WhatsAppPhoneConfigResult:
    verified_name: str | None
    display_phone_number: str | None


class WhatsAppCloudApiClient:
    def __init__(
        self,
        *,
        graph_api_version: str = GRAPH_API_VERSION,
        phone_number_id: str,
        access_token: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not phone_number_id.strip().isdigit():
            raise ValueError("phone_number_id must be numeric")
        if not access_token.strip():
            raise ValueError("access_token must not be empty")
        self._base_url = f"https://graph.facebook.com/{graph_api_version.strip()}/"
        self._phone_number_id = phone_number_id.strip()
        self._access_token = access_token
        self._transport = transport
        self._timeout = httpx.Timeout(
            connect=_DEFAULT_CONNECT_TIMEOUT_SECONDS,
            read=_DEFAULT_READ_TIMEOUT_SECONDS,
            write=_DEFAULT_WRITE_TIMEOUT_SECONDS,
            pool=_DEFAULT_POOL_TIMEOUT_SECONDS,
        )

    def __repr__(self) -> str:
        return "WhatsAppCloudApiClient()"

    async def send_text(self, *, request: WhatsAppSendTextRequest) -> WhatsAppSendResult:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": request.recipient_wa_id,
            "type": "text",
            "text": {"preview_url": False, "body": request.body},
        }
        document = await self._post_messages(payload=payload)
        return WhatsAppSendResult(provider_message_id=_extract_message_id(document))

    async def send_template(self, *, request: WhatsAppSendTemplateRequest) -> WhatsAppSendResult:
        components: list[dict[str, Any]] = []
        if request.body_parameters:
            components.append(
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": parameter} for parameter in request.body_parameters
                    ],
                }
            )
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": request.recipient_wa_id,
            "type": "template",
            "template": {
                "name": request.template_name,
                "language": {"code": request.language_code},
                "components": components,
            },
        }
        document = await self._post_messages(payload=payload)
        return WhatsAppSendResult(provider_message_id=_extract_message_id(document))

    async def list_templates(self, *, waba_id: str) -> tuple[WhatsAppTemplateListItem, ...]:
        if not waba_id.strip().isdigit():
            raise WhatsAppCloudApiClientError("waba_id must be numeric")
        document = await self._request(
            method="GET",
            path=f"{waba_id.strip()}/message_templates",
            params={"limit": "100"},
        )
        data = document.get("data")
        if not isinstance(data, list):
            raise WhatsAppCloudApiResponseError(error_code="invalid_template_list")
        items: list[WhatsAppTemplateListItem] = []
        for raw_item in data[:100]:
            if not isinstance(raw_item, dict):
                continue
            items.append(_parse_template_item(raw_item))
        return tuple(items)

    async def verify_phone_config(self) -> WhatsAppPhoneConfigResult:
        document = await self._request(method="GET", path=self._phone_number_id)
        verified_name = document.get("verified_name")
        display_phone_number = document.get("display_phone_number")
        return WhatsAppPhoneConfigResult(
            verified_name=verified_name if isinstance(verified_name, str) else None,
            display_phone_number=(
                display_phone_number if isinstance(display_phone_number, str) else None
            ),
        )

    async def _post_messages(self, *, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request(
            method="POST",
            path=f"{self._phone_number_id}/messages",
            json_body=payload,
        )

    async def _request(
        self,
        *,
        method: str,
        path: str,
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self._base_url}{path.lstrip('/')}"
        headers = {"Authorization": f"Bearer {self._access_token}"}
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=self._timeout,
                follow_redirects=False,
            ) as client:
                response = await client.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json_body,
                )
        except httpx.TimeoutException as error:
            raise WhatsAppCloudApiClientError("provider timeout") from error
        except httpx.HTTPError as error:
            raise WhatsAppCloudApiClientError("provider transport error") from error

        if response.status_code >= 500:
            raise WhatsAppCloudApiClientError("provider unavailable")
        if response.status_code >= 400:
            raise WhatsAppCloudApiResponseError(error_code=f"http_{response.status_code}")

        content = response.content
        if len(content) > _MAX_RESPONSE_BYTES:
            raise WhatsAppCloudApiResponseError(error_code="response_too_large")

        try:
            document = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise WhatsAppCloudApiResponseError(error_code="invalid_json") from error

        if not isinstance(document, dict):
            raise WhatsAppCloudApiResponseError(error_code="invalid_json")
        return document


def build_client_for_connection(
    *,
    graph_api_version: str,
    phone_number_id: str,
    access_token: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> WhatsAppCloudApiClient:
    return WhatsAppCloudApiClient(
        graph_api_version=graph_api_version,
        phone_number_id=phone_number_id,
        access_token=access_token,
        transport=transport,
    )


def _extract_message_id(document: dict[str, Any]) -> str:
    messages = document.get("messages")
    if not isinstance(messages, list) or not messages:
        raise WhatsAppCloudApiResponseError(error_code="missing_message_id")
    first = messages[0]
    if not isinstance(first, dict):
        raise WhatsAppCloudApiResponseError(error_code="missing_message_id")
    message_id = first.get("id")
    if not isinstance(message_id, str) or not message_id.strip():
        raise WhatsAppCloudApiResponseError(error_code="missing_message_id")
    return message_id.strip()


def _parse_template_item(raw_item: dict[str, Any]) -> WhatsAppTemplateListItem:
    provider_template_id = raw_item.get("id")
    name = raw_item.get("name")
    language = raw_item.get("language")
    category = raw_item.get("category")
    status = raw_item.get("status")
    components = raw_item.get("components")
    if not isinstance(provider_template_id, str) or not provider_template_id.strip():
        raise WhatsAppCloudApiResponseError(error_code="invalid_template_item")
    if not isinstance(name, str) or not name.strip():
        raise WhatsAppCloudApiResponseError(error_code="invalid_template_item")
    if not isinstance(language, str) or not language.strip():
        raise WhatsAppCloudApiResponseError(error_code="invalid_template_item")
    if not isinstance(category, str) or not category.strip():
        raise WhatsAppCloudApiResponseError(error_code="invalid_template_item")
    if not isinstance(status, str) or not status.strip():
        raise WhatsAppCloudApiResponseError(error_code="invalid_template_item")
    shape: list[str] = []
    parameter_count = 0
    if isinstance(components, list):
        for component in components:
            if not isinstance(component, dict):
                continue
            component_type = component.get("type")
            if isinstance(component_type, str):
                shape.append(component_type.lower())
            if component_type == "BODY":
                text = component.get("text")
                if isinstance(text, str):
                    parameter_count = text.count("{{")
    return WhatsAppTemplateListItem(
        provider_template_id=provider_template_id.strip(),
        name=name.strip().lower(),
        language_code=language.strip(),
        category=category.strip().lower(),
        approval_status=status.strip().lower(),
        component_shape=tuple(shape) if shape else ("body",),
        parameter_count=parameter_count,
    )


__all__ = [
    "WhatsAppCloudApiClient",
    "WhatsAppCloudApiClientError",
    "WhatsAppCloudApiResponseError",
    "WhatsAppPhoneConfigResult",
    "WhatsAppSendResult",
    "WhatsAppSendTemplateRequest",
    "WhatsAppSendTextRequest",
    "WhatsAppTemplateListItem",
    "build_client_for_connection",
]
