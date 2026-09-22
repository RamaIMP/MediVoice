# Voice component

Shared implementation for apps.voice_agent console and dev modes.
agent.py owns LiveKit SDK integration, STT, VAD, TTS and turn lifecycle.
pipeline.py owns translation, grounded answer generation and language preference.
Each voice session owns its Pipeline; never share its mutable language state
across users. Test with pytest tests/test_agent.py tests/test_pipeline.py.
