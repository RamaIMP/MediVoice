from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE / ".env", extra="ignore")
    livekit_url: str = ""
    livekit_api_key: SecretStr = SecretStr("")
    livekit_api_secret: SecretStr = SecretStr("")
    assemblyai_api_key: SecretStr = SecretStr("")
    assemblyai_model: str = "whisper-rt"
    background_voice_cancellation: bool = True
    vad_activation_threshold: float = Field(default=0.65, ge=0.1, le=0.95)
    vad_min_speech_duration: float = Field(default=0.12, ge=0.05, le=0.5)
    interruption_min_duration: float = Field(default=0.65, ge=0.2, le=2.0)
    google_places_api_key: SecretStr = SecretStr("")
    here_api_key: SecretStr = SecretStr("")
    doctor_search_provider: Literal["google", "here"] = "google"
    doctor_search_mode: Literal["auto", "dummy"] = "auto"
    gemini_api_key: SecretStr = SecretStr("")
    language_provider: Literal["groq", "gemini"] = "groq"
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_groq_fallback: bool = True
    groq_api_key: SecretStr = SecretStr("")
    groq_model: str = "openai/gpt-oss-120b"
    groq_max_completion_tokens: int = Field(default=1024, ge=256, le=4096)
    elevenlabs_api_key: SecretStr = SecretStr("")
    elevenlabs_model: str = "eleven_v3"
    elevenlabs_voice_id: str = "JBFqnCBsd6RMkjVDRZzb"
    tts_provider: Literal["elevenlabs", "cartesia_livekit"] = "elevenlabs"
    cartesia_model: str = "cartesia/sonic-3.6"
    cartesia_voice_id: str = "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"
    frontend_url: str = "http://localhost:5173"
    database_path: Path = BASE / "data" / "sessions.sqlite3"
    session_ttl_seconds: int = Field(default=3600, ge=60, le=86400)
    request_timeout_seconds: float = Field(default=25, gt=0, le=120)
    report_context_path: Path = BASE / "tests" / "fixtures" / "reports" / "sample_report.json"
    demo_mode: bool = False
    console_debug: bool = True
    console_log_dir: Path = BASE / "debug_logs"

    def missing(self, voice: bool = True, *, console: bool = False) -> list[str]:
        names = ["groq_api_key", "groq_model"]
        if self.language_provider == "gemini":
            names.append("gemini_api_key")
        if voice:
            names += ["assemblyai_api_key"]
            if self.tts_provider == "elevenlabs":
                names += ["elevenlabs_api_key", "elevenlabs_voice_id"]
            else:
                names += ["cartesia_model", "cartesia_voice_id"]
            if not console or self.tts_provider == "cartesia_livekit":
                names += ["livekit_url", "livekit_api_key", "livekit_api_secret"]
        return [name.upper() for name in names if not self._present(getattr(self, name))]

    @staticmethod
    def _present(value) -> bool:
        raw = value.get_secret_value() if isinstance(value, SecretStr) else str(value)
        return bool(raw.strip()) and not raw.lower().startswith(("your_", "replace_"))
