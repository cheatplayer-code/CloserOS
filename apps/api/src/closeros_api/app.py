"""Minimal API scaffold for CLS-001."""

from fastapi import FastAPI

app = FastAPI(title="CloserOS API", version="0.0.0")


@app.get("/health")
def health() -> dict[str, str]:
    """Return process health without exposing configuration or customer data."""
    return {"status": "ok"}
