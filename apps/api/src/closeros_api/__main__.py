"""Run the development API process."""

import uvicorn


def main() -> None:
    """Start the API scaffold on the local development interface."""
    uvicorn.run("closeros_api.app:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
