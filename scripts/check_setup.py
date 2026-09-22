"""Offline configuration check: never prints credentials or calls providers."""

import json

from pydantic import ValidationError

from packages.shared.settings import Settings


def readiness(config: Settings) -> dict:
    missing = config.missing()
    return {
        "voice_configured": not missing and not config.demo_mode,
        "text_configured": not config.missing(False) or config.demo_mode,
        "demo_mode": config.demo_mode,
        "missing_voice_settings": missing,
        "credentials_verified": False,
        "note": "Offline check only. Start the API and worker, then test the microphone."
        if not missing else "Add the missing settings to medivoice/.env and restart both processes.",
    }


def main() -> int:
    try:
        result = readiness(Settings())
    except ValidationError as exc:
        # Pydantic's default rendering includes input values; expose field names only.
        print(json.dumps({"invalid_settings": [".".join(map(str, e["loc"]))
                                              for e in exc.errors()]}))
        return 1
    print(json.dumps(result, indent=2))
    return 0 if result["voice_configured"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
