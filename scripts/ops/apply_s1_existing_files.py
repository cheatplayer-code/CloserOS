"""Apply the reviewed S1 edits to the two large source files."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: str, old: str, new: str, label: str) -> None:
    target = ROOT / path
    content = target.read_text(encoding="utf-8")
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: {label}: expected 1 match, found {count}")
    target.write_text(content.replace(old, new, 1), encoding="utf-8", newline="\n")
    print(f"updated {path}: {label}")


composition = "apps/api/src/closeros_api/composition.py"
service = "packages/backend/src/closeros/application/reply_suggestion_service.py"

replace_once(
    composition,
    "from closeros.application.synthetic_ai_provider import SyntheticAiProvider\n",
    "",
    "remove hard-coded synthetic provider import",
)
replace_once(
    composition,
    "from closeros_api.observability_router import ProductionReadinessProbe, RuntimeReadinessProbe\n"
    "from closeros_api.settings import ApiSettings\n",
    "from closeros_api.observability_router import ProductionReadinessProbe, RuntimeReadinessProbe\n"
    "from closeros_api.reply_ai_runtime import build_reply_ai_runtime\n"
    "from closeros_api.settings import ApiSettings\n",
    "import reply AI runtime selector",
)
replace_once(
    composition,
    '''        reply_suggestion_service = (
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
''',
    '''        reply_ai_runtime = build_reply_ai_runtime(settings)
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
''',
    "wire configured reply AI runtime",
)

replace_once(
    service,
    "from closeros.application.ai_ports import AiCredentialResolver, AiProvider, ProviderRequest\n",
    "from closeros.application.ai_ports import (\n"
    "    AiCredentialResolver,\n"
    "    AiProvider,\n"
    "    ProviderRequest,\n"
    "    ProviderResult,\n"
    ")\n",
    "import ProviderResult",
)
replace_once(
    service,
    '_DEFAULT_MODEL = "deepseek-chat"\n_DEFAULT_PROVIDER_CODE = AiProviderCode.SYNTHETIC\n',
    '_DEFAULT_MODEL = "synthetic-reply-v1"\n',
    "remove deprecated hard-coded model and provider default",
)
replace_once(
    service,
    '''def _provider_storage_code(provider_code: AiProviderCode) -> str:
    if provider_code is AiProviderCode.OPENAI_COMPATIBLE:
        return "openai"
    return "local"


class ReplySuggestionService:
''',
    '''def _provider_storage_code(provider_code: AiProviderCode) -> str:
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
''',
    "add actual provider metadata helper",
)
replace_once(
    service,
    '''        ai_provider: AiProvider | None = None,
        ai_credential_resolver: AiCredentialResolver | None = None,
        uuid_factory: _UuidFactory | None = None,
    ) -> None:
''',
    '''        ai_provider: AiProvider | None = None,
        ai_credential_resolver: AiCredentialResolver | None = None,
        model_code: str | None = _DEFAULT_MODEL,
        uuid_factory: _UuidFactory | None = None,
    ) -> None:
''',
    "add configured model argument",
)
replace_once(
    service,
    '''        self._ai_provider = ai_provider
        self._ai_credential_resolver = ai_credential_resolver
        self._uuid_factory = uuid_factory or uuid4
''',
    '''        self._ai_provider = ai_provider
        self._ai_credential_resolver = ai_credential_resolver
        normalized_model_code: str | None = None
        if model_code is not None:
            normalized_model_code = model_code.strip()
            if not normalized_model_code:
                raise ValueError("model_code must be non-empty when configured")
        self._model_code = normalized_model_code
        self._uuid_factory = uuid_factory or uuid4
''',
    "normalize configured model",
)
replace_once(
    service,
    '''            provider_code = _DEFAULT_PROVIDER_CODE
            if self._ai_provider is not None:
                provider_code = self._ai_provider.provider_code

            run = ReplySuggestionRun(
''',
    '''            provider_code: AiProviderCode | None = None
            if self._ai_provider is not None:
                provider_code = self._ai_provider.provider_code
            model_code = self._model_code

            run = ReplySuggestionRun(
''',
    "initialize optional provider and model",
)
replace_once(
    service,
    '''                provider_code=_provider_storage_code(provider_code),
                model_code=_DEFAULT_MODEL,
''',
    '''                provider_code=(
                    None
                    if provider_code is None
                    else _provider_storage_code(provider_code)
                ),
                model_code=model_code,
''',
    "store initial configured provider and model",
)
replace_once(
    service,
    "        if self._ai_provider is None:\n",
    "        if self._ai_provider is None or provider_code is None or model_code is None:\n",
    "fail closed without provider or model",
)
replace_once(
    service,
    "            model_code=_DEFAULT_MODEL,\n",
    "            model_code=model_code,\n",
    "send configured model",
)
replace_once(
    service,
    '''        except Exception:
            return await self._finalize_failed(
                tenant_id=tenant_id,
                run_id=run_id,
                failure_code=ReplyFailureCode.PROVIDER_FAILURE,
                input_digest=input_digest,
                audit_context=audit_context,
                actor_id=context.user.id,
            )

        try:
            validated = validate_reply_suggestion_json(
''',
    '''        except Exception:
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
            validated = validate_reply_suggestion_json(
''',
    "validate provider result identity",
)
replace_once(
    service,
    '''            completed_run = replace(
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
''',
    '''            completed_run = replace(
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
''',
    "persist actual provider metadata",
)

print("S1 source patch applied")
