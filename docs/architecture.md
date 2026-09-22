# Component boundaries

The UI uses FastAPI to create a sample-backed session and obtain a LiveKit token.
The worker retrieves that session's report and runs packages.voice.
Console loads the same fixture directly, without API or LiveKit Cloud transport.

Dependency direction: apps → voice/shared/contracts; voice → shared/contracts.
Knowledge and doctor-connect implementations must depend on contracts, not apps.
The frontend communicates over HTTP and LiveKit; it never receives provider keys.

ReportContext v1.0 is the integration boundary, not raw Qwen OCR output.
Knowledge extraction must map its output into findings with preserved units and
ranges. Add page provenance, uncertainty and validation rules as extraction is
implemented; coordinate schema changes through contract tests.

DoctorSearch is only a proposed interface. Tool registration, consent/location,
provider access and result handling are pending. No synthetic doctor results.

The current pipeline buffers complete model responses before TTS. Streaming,
retries and stronger output guardrails remain future work.
