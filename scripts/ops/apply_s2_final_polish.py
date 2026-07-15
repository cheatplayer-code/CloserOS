"""Apply final S2 smoke-safety and documentation polish."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: str, old: str, new: str, label: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: {label}: expected one match, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")
    print(f"updated {path}: {label}")


replace_once(
    "scripts/ops/deepseek_staging_smoke.py",
    '''def _safe_payload(payload: object) -> None:
    encoded = json.dumps(payload, sort_keys=True).lower()
    for marker in _SENSITIVE_MARKERS:
        if marker in encoded:
            raise SmokeFailure(f"unsafe field appeared in response JSON: {marker}")
''',
    '''def _safe_payload(payload: object) -> None:
    """Reject sensitive response field names without inspecting customer text values."""

    if isinstance(payload, dict):
        for raw_key, value in payload.items():
            normalized_key = str(raw_key).casefold()
            for marker in _SENSITIVE_MARKERS:
                if marker in normalized_key:
                    raise SmokeFailure(
                        f"unsafe field appeared in response JSON: {marker}"
                    )
            _safe_payload(value)
        return
    if isinstance(payload, list):
        for item in payload:
            _safe_payload(item)
''',
    "inspect sensitive keys instead of response values",
)

replace_once(
    "tests/test_deepseek_staging_smoke.py",
    '''            {
                "id": CANDIDATE_ID,
                "evidence_message_ids": [str(uuid4())],
            }
''',
    '''            {
                "id": CANDIDATE_ID,
                "text": "The word password in customer-safe candidate text is allowed.",
                "evidence_message_ids": [str(uuid4())],
            }
''',
    "cover sensitive-marker words in normal values",
)

replace_once(
    "docs/STAGING_SIGNOFF.md",
    "API-only variables:\n",
    "Cross-service staging values (set only on the service that consumes each value):\n",
    "clarify variable placement",
)
replace_once(
    "docs/STAGING_SIGNOFF.md",
    '''The API fails startup closed if the key or model is missing, or if the base URL
is not HTTPS. It never silently falls back to synthetic output in the production
runtime path.
''',
    '''The API fails startup closed if the key or model is missing, or if the base URL
is not HTTPS. It never silently falls back to synthetic output in the managed
staging runtime path.
''',
    "correct managed runtime wording",
)

print("S2 final polish applied")
