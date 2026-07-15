"""Apply the reviewed S1 permanent DeepSeek integration patch.

This one-shot script is executed only by the temporary branch workflow and is
removed before the pull request is opened.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")
    print(f"updated {path}")


def replace_once(path: str, old: str, new: str, label: str) -> None:
    content = read(path)
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: {label}: expected 1 match, found {count}")
    write(path, content.replace(old, new, 1))


# ---------------------------------------------------------------------------
# Typed API configuration.
# ---------------------------------------------------------------------------

replace_once(
    "apps/api/src/closeros_api/settings.py",
    "from dataclasses import dataclass\n",
    "from dataclasses import dataclass, field\n",
    "dataclass field import",
)
replace_once(
    "apps/api/src/closeros_api/settings.py",
    '_PRODUCTION = "production"\n',
    '_PRODUCTION = "production"\n_DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com/"\n',
    "DeepSeek base URL constant",
)
replace_once(
    "apps/api/src/closeros_api/settings.py",
    "    ingestion_service_id: UUID\n",
    dedent(
        """\
            ingestion_service_id: UUID
            ai_external_calls_enabled: bool = False
            deepseek_api_key: str | None = field(default=None, repr=False)
            deepseek_base_url: str = _DEFAULT_DEEPSEEK_BASE_URL
            deepseek_model: str | None = None
        """
    ),
    "AI settings fields",
)
replace_once(
    "apps/api/src/closeros_api/settings.py",
    "        ingestion_service_id = _ingestion_service_id_from_env(app_env=app_env)\n\n        return cls(\n",
    dedent(
        """\
                ingestion_service_id = _ingestion_service_id_from_env(app_env=app_env)
                ai_external_calls_enabled = _boolean_from_env(
                    variable_name="AI_EXTERNAL_CALLS_ENABLED",
                    default=False,
                )
                deepseek_api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip() or None
                deepseek_base_url = _https_base_url_from_env(
                    variable_name="DEEPSEEK_BASE_URL",
                    default=_DEFAULT_DEEPSEEK_BASE_URL,
                )
                deepseek_model = os.environ.get("DEEPSEEK_MODEL", "").strip() or None

                return cls(
        """
    ),
    "load AI settings",
)
replace_once(
    "apps/api/src/closeros_api/settings.py",
    "            ingestion_service_id=ingestion_service_id,\n        )\n",
    dedent(
        """\
                    ingestion_service_id=ingestion_service_id,
                    ai_external_calls_enabled=ai_external_calls_enabled,
                    deepseek_api_key=deepseek_api_key,
                    deepseek_base_url=deepseek_base_url,
                    deepseek_model=deepseek_model,
                )
        """
    ),
    "return AI settings",
)
replace_once(
    "apps/api/src/closeros_api/settings.py",
    "    def validate_for_runtime(self) -> None:\n        if self.is_development:\n",
    "    def validate_for_runtime(self) -> None:\n        _validate_external_ai_settings(self)\n        if self.is_development:\n",
    "validate external AI before environment branch",
)
replace_once(
    "apps/api/src/closeros_api/settings.py",
    "\ndef _secret_from_env(\n",
    dedent(
        """\

        def _boolean_from_env(*, variable_name: str, default: bool) -> bool:
            raw_value = os.environ.get(variable_name, "").strip().lower()
            if not raw_value:
                return default
            if raw_value in {"1", "true", "yes", "on"}:
                return True
            if raw_value in {"0", "false", "no", "off"}:
                return False
            raise ApiConfigurationError(
                f"{variable_name} must be one of true/false, 1/0, yes/no, or on/off"
            )


        def _https_base_url_from_env(*, variable_name: str, default: str) -> str:
            raw_value = os.environ.get(variable_name, "").strip() or default
            parsed = urlparse(raw_value)
            if parsed.scheme != "https":
                raise ApiConfigurationError(f"{variable_name} must use https")
            if not parsed.netloc:
                raise ApiConfigurationError(f"{variable_name} must include a host")
            if parsed.username is not None or parsed.password is not None:
                raise ApiConfigurationError(f"{variable_name} must not contain credentials")
            if parsed.query or parsed.fragment:
                raise ApiConfigurationError(f"{variable_name} must not contain query or fragment")
            return raw_value if raw_value.endswith("/") else f"{raw_value}/"


        def _validate_external_ai_settings(settings: ApiSettings) -> None:
            if not settings.ai_external_calls_enabled:
                return
            if settings.deepseek_api_key is None:
                raise ApiConfigurationError(
                    "AI_EXTERNAL_CALLS_ENABLED requires DEEPSEEK_API_KEY"
                )
            if settings.deepseek_model is None:
                raise ApiConfigurationError(
                    "AI_EXTERNAL_CALLS_ENABLED requires DEEPSEEK_MODEL"
                )
            parsed = urlparse(settings.deepseek_base_url)
            if parsed.scheme != "https" or not parsed.netloc:
                raise ApiConfigurationError(
                    "AI_EXTERNAL_CALLS_ENABLED requires a valid HTTPS DEEPSEEK_BASE_URL"
                )


        def _secret_from_env(
        """
    ),
    "AI settings helpers",
)

# ---------------------------------------------------------------------------
# Permanent API provider composition.
# ---------------------------------------------------------------------------

replace_once(
    "apps/api/src/closeros_api/composition.py",
    "from closeros.application.synthetic_ai_provider import SyntheticAiProvider\n",
    "",
    "remove hard-coded synthetic provider import",
)
replace_once(
    "apps/api/src/closeros_api/composition.py",
    "from closeros_api.observability_router import ProductionReadinessProbe, RuntimeReadinessProbe\nfrom closeros_api.settings import ApiSettings\n",
    "from closeros_api.observability_router import ProductionReadinessProbe, RuntimeReadinessProbe\nfrom closeros_api.reply_ai_runtime import build_reply_ai_runtime\nfrom closeros_api.settings import ApiSettings\n",
    "reply AI runtime import",
)
replace_once(
    "apps/api/src/closeros_api/composition.py",
    dedent(
        """\
                reply_suggestion_service = (
                    override_values.reply_suggestion_service
                    or ReplySuggestionService(
                        uow_factory=integrated_port_factory,
                        content_encryption=content_encryption,
                        outbound_message_service=outbound_message_service,
                        clock=clock,
                        ai_provider=SyntheticAiProvider(),
                        uuid_factory=uuid_factory,
                    )
                )
        """
    ),
    dedent(
        """\
                reply_ai_runtime = build_reply_ai_runtime(settings)
                reply_suggestion_service = (
                    override_values.reply_suggestion_service
                    or ReplySuggestionService(
                        uow_factory=integrated_port_factory,
                        content_encryption=content_encryption,
                        outbound_message_service=outbound_message_service,
                        clock=clock,
                        ai_provider=reply_ai_runtime.provider,
                        ai_credential_resolver=reply_ai_runtime.credential_resolver,
                        model_code=reply_ai_runtime.model_code,
                        uuid_factory=uuid_factory,
                    )
                )
        """
    ),
    "wire configured reply AI runtime",
)

# ---------------------------------------------------------------------------
# Reply service model selection and actual provider metadata persistence.
# ---------------------------------------------------------------------------

replace_once(
    "packages/backend/src/closeros/application/reply_suggestion_service.py",
    "from closeros.application.ai_ports import AiCredentialResolver, AiProvider, ProviderRequest\n",
    "from closeros.application.ai_ports import (\n    AiCredentialResolver,\n    AiProvider,\n    ProviderRequest,\n    ProviderResult,\n)\n",
    "ProviderResult import",
)
replace_once(
    "packages/backend/src/closeros/application/reply_suggestion_service.py",
    '_DEFAULT_MODEL = "deepseek-chat"\n_DEFAULT_PROVIDER_CODE = AiProviderCode.SYNTHETIC\n',
    '_DEFAULT_MODEL = "synthetic-reply-v1"\n',
    "remove deprecated hard-coded model and provider default",
)
replace_once(
    "packages/backend/src/closeros/application/reply_suggestion_service.py",
    dedent(
        """\
        def _provider_storage_code(provider_code: AiProviderCode) -> str:
            if provider_code is AiProviderCode.OPENAI_COMPATIBLE:
                return "openai"
            return "local"


        class ReplySuggestionService:
        """
    ),
    dedent(
        """\
        def _provider_storage_code(provider_code: AiProviderCode) -> str:
            if provider_code is AiProviderCode.OPENAI_COMPATIBLE:
                return "openai"
            return "local"


        def _apply_provider_result_metadata(
            *,
            run: ReplySuggestionRun,
            provider_result: ProviderResult,
        ) -> ReplySuggestionRun:
            usage = provider_result.usage
            cost_status = ReplyCostStatus.UNKNOWN
            estimated_cost_microunits: int | None = None
            if provider_result.provider_code is AiProviderCode.SYNTHETIC:
                cost_status = ReplyCostStatus.NOT_APPLICABLE
            elif usage is not None and usage.estimated_cost_microunits > 0:
                cost_status = ReplyCostStatus.KNOWN
                estimated_cost_microunits = usage.estimated_cost_microunits

            return replace(
                run,
                provider_code=_provider_storage_code(provider_result.provider_code),
                model_code=provider_result.model_code,
                input_tokens=None if usage is None else usage.input_tokens,
                output_tokens=None if usage is None else usage.output_tokens,
                latency_milliseconds=None if usage is None else usage.latency_milliseconds,
                cost_status=cost_status,
                estimated_cost_microunits=estimated_cost_microunits,
            )


        class ReplySuggestionService:
        """
    ),
    "provider result metadata helper",
)
replace_once(
    "packages/backend/src/closeros/application/reply_suggestion_service.py",
    dedent(
        """\
                ai_provider: AiProvider | None = None,
                ai_credential_resolver: AiCredentialResolver | None = None,
                uuid_factory: _UuidFactory | None = None,
            ) -> None:
        """
    ),
    dedent(
        """\
                ai_provider: AiProvider | None = None,
                ai_credential_resolver: AiCredentialResolver | None = None,
                model_code: str | None = _DEFAULT_MODEL,
                uuid_factory: _UuidFactory | None = None,
            ) -> None:
        """
    ),
    "configurable model constructor parameter",
)
replace_once(
    "packages/backend/src/closeros/application/reply_suggestion_service.py",
    "        self._ai_credential_resolver = ai_credential_resolver\n        self._uuid_factory = uuid_factory or uuid4\n",
    dedent(
        """\
                self._ai_credential_resolver = ai_credential_resolver
                normalized_model_code: str | None = None
                if model_code is not None:
                    normalized_model_code = model_code.strip()
                    if not normalized_model_code:
                        raise ValueError("model_code must be non-empty when configured")
                self._model_code = normalized_model_code
                self._uuid_factory = uuid_factory or uuid4
        """
    ),
    "normalize configured model",
)
replace_once(
    "packages/backend/src/closeros/application/reply_suggestion_service.py",
    dedent(
        """\
                    provider_code = _DEFAULT_PROVIDER_CODE
                    if self._ai_provider is not None:
                        provider_code = self._ai_provider.provider_code

                    run = ReplySuggestionRun(
        """
    ),
    dedent(
        """\
                    provider_code: AiProviderCode | None = None
                    if self._ai_provider is not None:
                        provider_code = self._ai_provider.provider_code
                    model_code = self._model_code

                    run = ReplySuggestionRun(
        """
    ),
    "optional provider and model initialization",
)
replace_once(
    "packages/backend/src/closeros/application/reply_suggestion_service.py",
    "                provider_code=_provider_storage_code(provider_code),\n                model_code=_DEFAULT_MODEL,\n",
    dedent(
        """\
                        provider_code=(
                            None
                            if provider_code is None
                            else _provider_storage_code(provider_code)
                        ),
                        model_code=model_code,
        """
    ),
    "initial run provider and model metadata",
)
replace_once(
    "packages/backend/src/closeros/application/reply_suggestion_service.py",
    "        if self._ai_provider is None:\n",
    "        if self._ai_provider is None or provider_code is None or model_code is None:\n",
    "fail closed without configured provider or model",
)
replace_once(
    "packages/backend/src/closeros/application/reply_suggestion_service.py",
    "            model_code=_DEFAULT_MODEL,\n",
    "            model_code=model_code,\n",
    "provider request configured model",
)
replace_once(
    "packages/backend/src/closeros/application/reply_suggestion_service.py",
    dedent(
        """\
                except Exception:
                    return await self._finalize_failed(
                        tenant_id=tenant_id,
                        run_id=run_id,
                        failure_code=ReplyFailureCode.PROVIDER_FAILURE,
                        input_digest=input_digest,
                        audit_context=audit_context,
                        actor_id=context.user.id,
                    )

                try:
        """
    ),
    dedent(
        """\
                except Exception:
                    return await self._finalize_failed(
                        tenant_id=tenant_id,
                        run_id=run_id,
                        failure_code=ReplyFailureCode.PROVIDER_FAILURE,
                        input_digest=input_digest,
                        audit_context=audit_context,
                        actor_id=context.user.id,
                    )

                if (
                    provider_result.provider_code is not provider_code
                    or provider_result.purpose is not AiPurpose.REPLY_SUGGESTION
                ):
                    return await self._finalize_failed(
                        tenant_id=tenant_id,
                        run_id=run_id,
                        failure_code=ReplyFailureCode.OUTPUT_INVALID,
                        input_digest=input_digest,
                        audit_context=audit_context,
                        actor_id=context.user.id,
                    )

                try:
        """
    ),
    "validate provider result identity",
)
replace_once(
    "packages/backend/src/closeros/application/reply_suggestion_service.py",
    dedent(
        """\
                    completed_run = replace(
                        current_run,
                        status=ReplySuggestionStatus.COMPLETED,
                        customer_state=validated.customer_state,
                        next_best_action=validated.next_best_action,
                        escalation_reason=validated.escalation,
                        input_digest=input_digest,
                        output_digest=validated.output_digest,
                        input_tokens=None if usage is None else usage.input_tokens,
                        output_tokens=None if usage is None else usage.output_tokens,
                        latency_milliseconds=None if usage is None else usage.latency_milliseconds,
                        cost_status=ReplyCostStatus.UNKNOWN,
                        estimated_cost_microunits=None,
                        updated_at=completed_at,
                        completed_at=completed_at,
                    )
        """
    ),
    dedent(
        """\
                    completed_run = replace(
                        current_run,
                        status=ReplySuggestionStatus.COMPLETED,
                        customer_state=validated.customer_state,
                        next_best_action=validated.next_best_action,
                        escalation_reason=validated.escalation,
                        input_digest=input_digest,
                        output_digest=validated.output_digest,
                        updated_at=completed_at,
                        completed_at=completed_at,
                    )
                    completed_run = _apply_provider_result_metadata(
                        run=completed_run,
                        provider_result=provider_result,
                    )
        """
    ),
    "persist actual provider result metadata",
)

# ---------------------------------------------------------------------------
# Current model names and opt-in live smoke.
# ---------------------------------------------------------------------------

replace_once(
    "tests/test_openai_compatible_adapter.py",
    '        model_code="deepseek-chat",\n',
    '        model_code="deepseek-v4-flash",\n',
    "current DeepSeek model in adapter tests",
)
replace_once(
    "tests/test_reply_suggestion_live_deepseek.py",
    '        base_url="https://api.deepseek.com",\n',
    '        base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),\n',
    "configurable live smoke base URL",
)
replace_once(
    "tests/test_reply_suggestion_live_deepseek.py",
    '        model_code="deepseek-chat",\n',
    '        model_code=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),\n',
    "current live smoke model",
)

# ---------------------------------------------------------------------------
# Environment examples and operator documentation.
# ---------------------------------------------------------------------------

replace_once(
    ".env.example",
    dedent(
        """\
        # External providers are disabled by default
        DEEPSEEK_API_KEY=
        DEEPSEEK_BASE_URL=
        # Optional OpenAI-compatible endpoint for NOPQ gateway adapters.
        """
    ),
    dedent(
        """\
        # External providers are disabled by default. When enabled, the API fails
        # closed unless the key, HTTPS base URL, and model are all configured.
        AI_EXTERNAL_CALLS_ENABLED=false
        DEEPSEEK_API_KEY=
        DEEPSEEK_BASE_URL=https://api.deepseek.com/
        DEEPSEEK_MODEL=deepseek-v4-flash
        # Optional OpenAI-compatible endpoint for NOPQ gateway adapters.
        """
    ),
    "canonical external AI environment block",
)
replace_once(
    ".env.example",
    "CLOSEROS_DEV_KNOWLEDGE_SEARCH_KEY_HEX=\nAI_EXTERNAL_CALLS_ENABLED=false\n",
    "CLOSEROS_DEV_KNOWLEDGE_SEARCH_KEY_HEX=\n",
    "remove duplicate external calls flag",
)
replace_once(
    "docs/ENVIRONMENT_VARIABLES.md",
    dedent(
        """\
        | `AI_EXTERNAL_CALLS_ENABLED` | no | `false` default |
        | `DEEPSEEK_API_KEY` | if enabled | Vendor key (blank default) |
        | `DEEPSEEK_BASE_URL` | if enabled | HTTPS OpenAI-compatible base |
        | `OPENAI_COMPATIBLE_*` | optional | Alternate provider |
        | `CLOSEROS_DEV_KNOWLEDGE_SEARCH_KEY_HEX` | dev only | Deterministic dev search |
        """
    ),
    dedent(
        """\
        | `AI_EXTERNAL_CALLS_ENABLED` | no | `false` by default. The ordinary API uses deterministic synthetic replies only in development while disabled; production does not silently fall back to synthetic AI. |
        | `DEEPSEEK_API_KEY` | if enabled | Vendor key injected by the platform secret store. Hidden from settings repr and never persisted. |
        | `DEEPSEEK_BASE_URL` | if enabled | HTTPS OpenAI-compatible base. Defaults to `https://api.deepseek.com/`. Credentials, query strings, and fragments are rejected. |
        | `DEEPSEEK_MODEL` | if enabled | Explicit model code. Staging default is `deepseek-v4-flash`; deprecated aliases are not used by CloserOS defaults. |
        | `OPENAI_COMPATIBLE_*` | optional | Alternate provider variables used by other gateway paths; not the Reply Copilot source of truth. |
        | `CLOSEROS_DEV_KNOWLEDGE_SEARCH_KEY_HEX` | dev only | Deterministic dev search. |
        """
    ),
    "external AI environment documentation",
)
write(
    "docs/STAGING_DEEPSEEK.md",
    dedent(
        """\
        # Staging — DeepSeek / External AI

        CloserOS uses a provider-neutral AI gateway (ADR-0015). DeepSeek is the initial
        OpenAI-compatible provider. External calls remain disabled by default and the
        normal API now selects the live provider directly from typed configuration; no
        PowerShell monkeypatch or alternate API entry point is required.

        ## Default staging posture

        ```text
        AI_EXTERNAL_CALLS_ENABLED=false
        DEEPSEEK_API_KEY=
        DEEPSEEK_BASE_URL=https://api.deepseek.com/
        DEEPSEEK_MODEL=deepseek-v4-flash
        ```

        With external calls disabled:

        - deterministic development and CI flows use `SyntheticAiProvider`;
        - production does not silently report synthetic output as live AI;
        - policy, tenant, sanitization, and budget boundaries remain enforced;
        - no external request is made.

        ## Enabling sanctioned sandbox checks

        Only for approved operator sessions:

        1. Obtain a sandbox API key through vendor onboarding and store it only in the
           deployment platform secret store.
        2. Set `AI_EXTERNAL_CALLS_ENABLED=true` on worker and API.
        3. Set `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, and `DEEPSEEK_MODEL`.
        4. Use a current model name such as `deepseek-v4-flash` or
           `deepseek-v4-pro`; CloserOS does not default to deprecated aliases.
        5. Confirm the test tenant AI policy allows `reply.suggestion`.
        6. Run with metadata-only logging; never log prompts, model output bodies, or
           bearer keys.

        Enabling external calls with a missing key, model, or invalid non-HTTPS base
        URL fails API startup closed. It never falls back to synthetic output.

        ## Data boundary

        Only **sanitized** text may leave the jurisdiction to an external model. Raw
        encrypted message bodies, provider credentials, and unrelated tenant data never
        go to DeepSeek. Provider responses still pass strict evidence, product,
        commercial-action, PII, link, and chain-of-thought validation before candidates
        are persisted.

        Candidate selection creates an encrypted outbound **draft** only. Existing human
        approval remains mandatory; S1 does not introduce autonomous sending.

        See `docs/AI_GATEWAY.md`, `docs/PRIVACY_REDACTION.md`, `docs/REPLY_COPILOT.md`,
        and ADR-0005.

        ## Staging checklist before enabling

        - [ ] Legal/vendor review recorded
        - [ ] Tenant budget limits configured
        - [ ] Kill switch tested (`AI_EXTERNAL_CALLS_ENABLED=false`)
        - [ ] Startup failure tested with missing `DEEPSEEK_API_KEY`
        - [ ] Actual provider/model/token/latency metadata verified in
              `reply_suggestion_runs`
        - [ ] No real customer conversations in staging tenant
        - [ ] Incident contacts listed in `docs/INCIDENT_RESPONSE.md`

        ## Related variables

        Documented in `docs/ENVIRONMENT_VARIABLES.md` and `.env.example`.
        """
    ),
)
replace_once(
    "docs/REPLY_COPILOT.md",
    dedent(
        """\
        ## Cost

        `cost_status=unknown` until Block 6 pricing configuration. Do not store `0` as
        a known monetary cost.
        """
    ),
    dedent(
        """\
        ## Runtime provider selection

        - Development/CI with `AI_EXTERNAL_CALLS_ENABLED=false` uses the deterministic
          synthetic provider.
        - With external calls enabled, the ordinary API uses the configured HTTPS
          DeepSeek adapter and fails startup closed when key or model configuration is
          missing.
        - Production never silently falls back from a requested live provider to
          synthetic output.
        - Completed runs persist the provider and model actually returned by the
          provider adapter, plus token and latency metadata when available.

        ## Cost

        Synthetic usage is `not_applicable`. External cost remains `unknown` until a
        pricing calculator provides a positive estimate; zero is never stored as known
        monetary cost.
        """
    ),
    "reply provider runtime documentation",
)

# ---------------------------------------------------------------------------
# New focused runtime components and tests.
# ---------------------------------------------------------------------------

write(
    "packages/backend/src/closeros/infrastructure/configured_ai_credential_resolver.py",
    dedent(
        """\
        """In-memory resolver for a deployment-injected AI provider credential."""

        from __future__ import annotations

        from dataclasses import dataclass, field
        from uuid import UUID

        from closeros.application.ai_ports import AiCredentialResolver
        from closeros.domain.ai_analysis import AiProviderCode


        @dataclass(frozen=True, slots=True)
        class ConfiguredAiCredentialResolver(AiCredentialResolver):
            """Resolve one process-level bearer key without exposing it in repr output."""

            bearer_key: str = field(repr=False)
            provider_code: AiProviderCode = AiProviderCode.OPENAI_COMPATIBLE

            def __post_init__(self) -> None:
                if not isinstance(self.provider_code, AiProviderCode):
                    raise TypeError("provider_code must be an AiProviderCode")
                if type(self.bearer_key) is not str:
                    raise TypeError("bearer_key must be a string")
                normalized = self.bearer_key.strip()
                if not normalized:
                    raise ValueError("bearer_key must not be empty")
                object.__setattr__(self, "bearer_key", normalized)

            async def resolve_bearer_key(
                self,
                *,
                tenant_id: UUID,
                provider_code: AiProviderCode,
            ) -> str | None:
                _ = tenant_id
                if provider_code is not self.provider_code:
                    return None
                return self.bearer_key


        __all__ = ["ConfiguredAiCredentialResolver"]
        """
    ),
)
write(
    "apps/api/src/closeros_api/reply_ai_runtime.py",
    dedent(
        """\
        """Fail-closed provider selection for the synchronous Reply Copilot path."""

        from __future__ import annotations

        from dataclasses import dataclass

        from closeros.application.ai_ports import AiCredentialResolver, AiProvider
        from closeros.application.openai_compatible_adapter import OpenAICompatibleChatAdapter
        from closeros.application.synthetic_ai_provider import SyntheticAiProvider
        from closeros.domain.ai_analysis import AiProviderCode
        from closeros.infrastructure.configured_ai_credential_resolver import (
            ConfiguredAiCredentialResolver,
        )

        from closeros_api.settings import ApiConfigurationError, ApiSettings

        _SYNTHETIC_REPLY_MODEL = "synthetic-reply-v1"


        @dataclass(frozen=True, slots=True)
        class ReplyAiRuntimeConfiguration:
            provider: AiProvider | None
            credential_resolver: AiCredentialResolver | None
            model_code: str | None


        def build_reply_ai_runtime(settings: ApiSettings) -> ReplyAiRuntimeConfiguration:
            """Select deterministic, live, or disabled behavior without silent fallback."""

            if settings.ai_external_calls_enabled:
                if settings.deepseek_api_key is None:
                    raise ApiConfigurationError(
                        "AI_EXTERNAL_CALLS_ENABLED requires DEEPSEEK_API_KEY"
                    )
                if settings.deepseek_model is None:
                    raise ApiConfigurationError(
                        "AI_EXTERNAL_CALLS_ENABLED requires DEEPSEEK_MODEL"
                    )
                return ReplyAiRuntimeConfiguration(
                    provider=OpenAICompatibleChatAdapter(
                        base_url=settings.deepseek_base_url,
                        provider_code=AiProviderCode.OPENAI_COMPATIBLE,
                    ),
                    credential_resolver=ConfiguredAiCredentialResolver(
                        bearer_key=settings.deepseek_api_key,
                    ),
                    model_code=settings.deepseek_model,
                )

            if settings.is_development:
                return ReplyAiRuntimeConfiguration(
                    provider=SyntheticAiProvider(),
                    credential_resolver=None,
                    model_code=_SYNTHETIC_REPLY_MODEL,
                )

            return ReplyAiRuntimeConfiguration(
                provider=None,
                credential_resolver=None,
                model_code=None,
            )


        __all__ = ["ReplyAiRuntimeConfiguration", "build_reply_ai_runtime"]
        """
    ),
)
write(
    "tests/test_api_reply_ai_runtime.py",
    dedent(
        """\
        """Focused tests for fail-closed Reply Copilot provider selection."""

        from __future__ import annotations

        import asyncio
        import os
        from dataclasses import replace
        from unittest.mock import patch
        from uuid import uuid4

        import pytest
        from closeros.application.openai_compatible_adapter import OpenAICompatibleChatAdapter
        from closeros.application.synthetic_ai_provider import SyntheticAiProvider
        from closeros.domain.ai_analysis import AiProviderCode
        from closeros_api.reply_ai_runtime import build_reply_ai_runtime
        from closeros_api.settings import ApiConfigurationError, ApiSettings

        from tests.auth_api_support import development_api_settings, production_api_settings
        from tests.database_url_support import placeholder_database_url


        def test_disabled_development_uses_deterministic_synthetic_provider() -> None:
            settings = development_api_settings(database_url=placeholder_database_url())

            runtime = build_reply_ai_runtime(settings)

            assert isinstance(runtime.provider, SyntheticAiProvider)
            assert runtime.credential_resolver is None
            assert runtime.model_code == "synthetic-reply-v1"


        def test_disabled_production_does_not_silently_fallback_to_synthetic() -> None:
            settings = production_api_settings(database_url=placeholder_database_url())

            runtime = build_reply_ai_runtime(settings)

            assert runtime.provider is None
            assert runtime.credential_resolver is None
            assert runtime.model_code is None


        def test_enabled_runtime_uses_configured_deepseek_adapter_and_hidden_key() -> None:
            secret = "synthetic-deepseek-secret"
            settings = replace(
                development_api_settings(database_url=placeholder_database_url()),
                ai_external_calls_enabled=True,
                deepseek_api_key=secret,
                deepseek_base_url="https://api.deepseek.com/",
                deepseek_model="deepseek-v4-flash",
            )
            settings.validate_for_runtime()

            runtime = build_reply_ai_runtime(settings)

            assert isinstance(runtime.provider, OpenAICompatibleChatAdapter)
            assert runtime.provider.base_url == "https://api.deepseek.com/"
            assert runtime.provider.provider_code is AiProviderCode.OPENAI_COMPATIBLE
            assert runtime.model_code == "deepseek-v4-flash"
            assert runtime.credential_resolver is not None
            resolved = asyncio.run(
                runtime.credential_resolver.resolve_bearer_key(
                    tenant_id=uuid4(),
                    provider_code=AiProviderCode.OPENAI_COMPATIBLE,
                )
            )
            assert resolved == secret
            assert secret not in repr(runtime.credential_resolver)
            assert secret not in repr(settings)


        @pytest.mark.parametrize(
            ("changes", "message"),
            [
                ({"deepseek_api_key": None}, "DEEPSEEK_API_KEY"),
                ({"deepseek_model": None}, "DEEPSEEK_MODEL"),
                ({"deepseek_base_url": "http://api.deepseek.com/"}, "HTTPS"),
            ],
        )
        def test_enabled_runtime_configuration_fails_closed(
            changes: dict[str, object],
            message: str,
        ) -> None:
            settings = replace(
                development_api_settings(database_url=placeholder_database_url()),
                ai_external_calls_enabled=True,
                deepseek_api_key="synthetic-key",
                deepseek_base_url="https://api.deepseek.com/",
                deepseek_model="deepseek-v4-flash",
                **changes,
            )

            with pytest.raises(ApiConfigurationError, match=message):
                settings.validate_for_runtime()


        def test_from_env_rejects_ambiguous_external_ai_boolean() -> None:
            with (
                patch.dict(
                    os.environ,
                    {
                        "DATABASE_URL": placeholder_database_url(),
                        "AI_EXTERNAL_CALLS_ENABLED": "sometimes",
                    },
                    clear=True,
                ),
                pytest.raises(ApiConfigurationError, match="AI_EXTERNAL_CALLS_ENABLED"),
            ):
                ApiSettings.from_env()
        """
    ),
)
write(
    "tests/test_reply_provider_metadata.py",
    dedent(
        """\
        """Tests for persisting the provider metadata actually returned by the adapter."""

        from __future__ import annotations

        from datetime import UTC, datetime
        from uuid import uuid4

        from closeros.application.ai_ports import ProviderResult
        from closeros.application.reply_suggestion_service import (
            _apply_provider_result_metadata,
        )
        from closeros.domain.ai_analysis import AiProviderCode, AiPurpose, AiUsage
        from closeros.domain.reply_suggestion import (
            ReplyCostStatus,
            ReplySuggestionRun,
            ReplySuggestionStatus,
        )


        def _run() -> ReplySuggestionRun:
            now = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
            return ReplySuggestionRun(
                id=uuid4(),
                tenant_id=uuid4(),
                conversation_thread_id=uuid4(),
                lead_id=None,
                requested_by_user_id=uuid4(),
                status=ReplySuggestionStatus.COMPLETED,
                prompt_version="v1-reply-prompt-v1",
                rubric_version="v1-reply-rubric-v1",
                provider_code="openai",
                model_code="configured-model",
                input_tokens=None,
                output_tokens=None,
                latency_milliseconds=None,
                provider_request_id=None,
                cost_status=ReplyCostStatus.UNKNOWN,
                estimated_cost_microunits=None,
                failure_code=None,
                customer_state=None,
                next_best_action=None,
                escalation_reason=None,
                idempotency_key=None,
                input_digest=None,
                output_digest=None,
                created_at=now,
                updated_at=now,
                completed_at=now,
                version=1,
            )


        def test_external_result_replaces_configured_metadata_with_actual_values() -> None:
            result = ProviderResult(
                provider_code=AiProviderCode.OPENAI_COMPATIBLE,
                model_code="deepseek-v4-flash",
                purpose=AiPurpose.REPLY_SUGGESTION,
                output_text='{"purpose":"reply.suggestion"}',
                usage=AiUsage(
                    input_tokens=120,
                    output_tokens=45,
                    latency_milliseconds=678,
                    estimated_cost_microunits=321,
                ),
                completed_at=datetime(2026, 7, 15, 12, 0, 1, tzinfo=UTC),
            )

            updated = _apply_provider_result_metadata(run=_run(), provider_result=result)

            assert updated.provider_code == "openai"
            assert updated.model_code == "deepseek-v4-flash"
            assert updated.input_tokens == 120
            assert updated.output_tokens == 45
            assert updated.latency_milliseconds == 678
            assert updated.cost_status is ReplyCostStatus.KNOWN
            assert updated.estimated_cost_microunits == 321


        def test_synthetic_result_records_cost_as_not_applicable() -> None:
            result = ProviderResult(
                provider_code=AiProviderCode.SYNTHETIC,
                model_code="synthetic-reply-v1",
                purpose=AiPurpose.REPLY_SUGGESTION,
                output_text='{"purpose":"reply.suggestion"}',
                usage=AiUsage(
                    input_tokens=10,
                    output_tokens=20,
                    latency_milliseconds=1,
                    estimated_cost_microunits=0,
                ),
                completed_at=datetime(2026, 7, 15, 12, 0, 1, tzinfo=UTC),
            )

            updated = _apply_provider_result_metadata(run=_run(), provider_result=result)

            assert updated.provider_code == "local"
            assert updated.model_code == "synthetic-reply-v1"
            assert updated.cost_status is ReplyCostStatus.NOT_APPLICABLE
            assert updated.estimated_cost_microunits is None
        """
    ),
)

print("S1 patch applied successfully")
