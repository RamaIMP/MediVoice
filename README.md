# MediVoice

Independent components in one repository. Original sibling backend/ and frontend/
are unchanged. This folder can be the root of a new GitHub repository.

## Setup

Python 3.11–3.13, uv, and Node 22 are required.
Run Python commands **from the medivoice repository root**.

```sh
uv sync --frozen
cp .env.example .env
```

Fill your provider credentials into .env locally. No secrets, virtual environments,
real patient reports, databases or logs have been migrated. You can manually reuse
your existing credentials; they are not automatically read from ../backend/.env.
Do not commit credentials. Configuration paths default to this medivoice folder.

## Console development (no LiveKit Cloud transport)

```sh
uv run --frozen python -m apps.voice_agent download-files
uv run --frozen python -m apps.voice_agent console
```

Uses the computer microphone and speaker. Requires AssemblyAI, Gemini and Groq keys,
plus the credentials for the selected TTS provider. No frontend/API server is needed.
Ctrl+C stops this process.

Development `.env.example` selects `TTS_PROVIDER=cartesia_livekit`: Cartesia Sonic 3
through LiveKit Inference, using `LIVEKIT_URL`, `LIVEKIT_API_KEY` and
`LIVEKIT_API_SECRET`. No separate Cartesia key is needed. **This consumes LiveKit
Inference credits even in console mode**, but does not connect to a LiveKit room.
`CARTESIA_MODEL` and `CARTESIA_VOICE_ID` configure its model and voice.

ElevenLabs remains available: set `TTS_PROVIDER=elevenlabs` and restart the agent
and API. Existing `ELEVENLABS_*` configuration is preserved. With this provider,
console mode does not need LiveKit credentials. Direct provider quotas still apply.
There is no automatic fallback to ElevenLabs if Cartesia fails.
The SDK may print a console-command deprecation warning.

## UI demo

### Doctor Connect: real listings, simulated booking

For HERE, set `DOCTOR_SEARCH_PROVIDER=here` and `HERE_API_KEY` in `medivoice/.env`.
Create an app and API key in [HERE Access Manager](https://platform.here.com/).
The backend geocodes the supplied area, then searches nearby doctors/hospitals
with HERE Discover (up to two requests per search). No live test runs without a key.
Alternatively set `DOCTOR_SEARCH_PROVIDER=google` and `GOOGLE_PLACES_API_KEY`
with Places API (New) enabled and billing configured.
`DOCTOR_SEARCH_MODE=auto` is the default;
`DOCTOR_SEARCH_MODE=dummy` forces the original fictional demo. Restart the worker.
During a live conversation, ask for a doctor and supply an area/city by voice or
in the Doctor Connect search field. Only the location/search query is sent to the provider, not
the report or appointment details. Alternatively, tap **Use my location** in the
live Doctor Connect panel. Browser permission is requested only on that tap;
coordinates are sent through the worker to Google Nearby Search (5 km radius).
Denied, unavailable or timed-out location falls back to typing/speaking an area.
Mobile geolocation requires HTTPS; localhost works for desktop development.
Coordinates are not retained in appointment state. Approximate straight-line
distances are calculated from returned coordinates, not travel distances.
Date/time pickers, patient-name entry and confirmation buttons share the voice
worker's revision-checked state. Booking remains a preview, with no external send.

Missing key, missing area, empty results, timeouts or provider errors show clearly
labelled dummy listings. No automatic switch to another paid provider occurs.
Real results have addresses (Google results also have Google Maps links); they
are never plotted on the fictional map and no distance is fabricated. Embedded
maps are not integrated yet. HERE results currently use
address cards, not an embedded map. The offline text-only demo remains fictional.
Provider results stay in the conversation's memory only.

All bookings and WhatsApp messages are previews, including for real listings.
No availability is checked, contact number verified, message sent or booking made.
Before public deployment, add your publicly accessible Terms and Privacy pages
and review the selected provider's attribution and usage requirements.
Search API usage follows your provider plan; configure quotas there. Never put keys in
frontend variables or GitHub.

Stop the old frontend/API first to avoid port collisions. Start three terminals:

```sh
# Terminal 1, from medivoice/
uv run --frozen uvicorn apps.api.main:app --host 127.0.0.1 --port 8010

# Terminal 2, from medivoice/
uv run --frozen python -m apps.voice_agent dev

# Terminal 3
cd apps/frontend
npm ci
npm run dev
```

Open http://localhost:5173. UI voice requires LiveKit URL/key/secret in addition
to provider keys. It uses LiveKit Cloud transport. Mobile microphone access needs
HTTPS; the default local servers are for desktop development, not public deployment.
Use Ctrl+C in each server terminal to stop it. Closing browser tabs does not stop servers.

DEMO_MODE=true gives simulated text answers only; voice is disabled in that mode.

## Shared sample and pending integrations

### Doctor Connect without API keys

Run only the frontend with `cd apps/frontend && npm run dev`. No FastAPI server,
provider keys or billing are needed for this local flow. Open the hamburger menu,
expand Demo setup and testing, and type “I want to see a doctor nearby”. The Doctor Connect
dialog opens automatically. Select a numbered map pin/card or type “second doctor”.
Answer yes, preferred date, preferred time and patient name, then confirm the summary.
Doctor 1 previews WhatsApp, doctor 2 previews a phone call and doctor 3 previews a
booking-page handoff. All contacts, distances and map locations are fictional.
No actual calls, links, messages or appointments are made.

Optional browser speech uses SpeechRecognition when supported and explicitly
started by the user (English demo). It may use the browser vendor's remote speech
service and is not guaranteed offline. Typed replies are always available. This
local-only mode is independent of LiveKit/AssemblyAI.
Intent recognition in this key-free demo is rule-based, not LLM understanding.
In a live LiveKit session, Gemini recognises doctor-connect intent and the worker
automatically opens the same UI panel. Voice and touch share worker-owned state.
The home screen contains only report upload and starting the conversation; there
are no Doctor Connect launch controls. Finishing a report explanation does not
automatically open doctors. It opens only in response to a user care request.
Selection, date, time, patient details, review and handoff advance inside the same
panel without reconnecting LiveKit. Back to report conversation closes the panel
but keeps the call active; End voice conversation explicitly disconnects.
Say “Find a doctor”, select one by voice or tap, then answer the date/time/name
questions and confirm. The worker speaks the prompts in the conversation language.
Browser speech recognition is not used while LiveKit is connected. Live voice
requires all configured provider keys and DEMO_MODE=false, even though doctor
results are fictional. WhatsApp handoff remains a preview; no message is sent.
Dates/times are preferred free text, not validated clinic slots. State stays in
memory and clears when the panel closes; do not enter real patient information.

Implementation: apps/frontend/src/doctorConnect.js (fixture and state machine),
DoctorConnect.jsx (dialog), doctorConnect.css. The real backend doctor provider
and LLM tool implementation remain in packages/doctor_connect for future work.

Both modes load tests/fixtures/reports/sample_report.json, a fictional CBC.
REPORT_CONTEXT_PATH can point to another compatible development JSON using an
absolute path. Arbitrary OCR JSON needs mapping to contracts.ReportContext first.
Do not put real patient data in fixtures. The UI upload currently previews only;
it does not upload or extract a report. The demo greeting and UI still say sample.

- apps/frontend: existing React UI.
- apps/api: HTTP session/token/text endpoints.
- apps/voice_agent: thin entrypoint for console and LiveKit modes.
- packages/voice: STT → Gemini → Groq → Gemini → TTS and agent lifecycle.
- packages/contracts: versioned report and future tool interfaces.
- packages/shared: configuration, report loading, storage and debug logging.
- packages/knowledge: placeholder, not integrated.
- packages/doctor_connect: worker-owned fictional appointment tool; real providers pending.

## Tests

### Voice guardrails

Gemini returns a structured scope: medical, doctor_connect, conversation,
off_topic, unclear or emergency. Missing scope defaults to unclear. Off-topic
and unclear turns use fixed English/Hindi/Telugu redirects without GPT or tool
execution. Emergency routing takes priority over name collection/booking.
Tool actions are allowlisted, revision-checked and constrained by booking state.
Patient names preserve conversation language and require explicit confirmation;
doctor selection and the final date/time/name summary also require confirmation.

Generated answers pass conservative numeric checks against report findings and
a separate Gemini safety review of BOTH the English draft and translated spoken
answer. It checks matching parameters/values/units, unsupported diagnoses,
prescriptions, dose changes and injected instructions. Only literal boolean
approval releases the answer; failed/malformed reviews return a fixed safe reply.
This adds one Gemini call to generated answers. Numeric checks may over-reject
valid reformatted values or numeric general education. Semantic safety, intent,
emergency detection and injection resistance still depend on model judgement;
these are not clinical guarantees. Mocked tests check enforcement, not model
accuracy. Live multilingual safety evaluation is required before public use.
This does not add audio noise filtering, usage quotas or private logging.

```sh
uv run --frozen pytest
uv run --frozen ruff check .
cd apps/frontend
npm test
npm run build
```

Tests use mocks and the fictional fixture; no provider keys or LiveKit credits
are needed. Offline setup check: uv run --frozen python -m scripts.check_setup.
CI runs backend tests/lint and frontend tests/build separately.

## Debugging and limitations

Console logs go to debug_logs/ with intermediate text, errors and timings.
CONSOLE_DEBUG=false disables additional file/content logging. Logs contain
conversation/report data; configured secrets are redacted, but this is not
general personal-data redaction. Do not publish logs. Old run files are not
automatically deleted. This folder is in OneDrive, which may sync ignored files.

The text test API is single-turn and intentionally does not retain history or
language preference; voice maintains language within its own session. No auth,
rate limiting, real-report upload, real doctor search/booking or clinical output validation
is implemented. Do not expose this development API publicly.
