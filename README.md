# MediVoice

### Your report companion—powered by voice

MediVoice brings report explanations and doctor discovery into a guided
conversation. Speak in English or Hindi, explore report findings, and
choose nearby care through a combination of voice and simple touch controls.

The hackathon demo uses a fictional sample report and simulated appointment
requests. MediVoice is for educational report explanations, not diagnosis or
prescribing; always follow your doctor's advice.

## Highlights

- **Voice-first experience:** microphone input, spoken responses and animated
  conversation states.
- **Multilingual conversations:** application-level language handling for English,
  Hindi.
- **Hindi transcript display:** Devanagari normalization within the existing
  language-routing call, without a separate normalization request.
- **Report knowledge pipeline:** upload a medical PDF or image; MediVoice builds
  a structured, page-linked medical JSON context before the conversation starts.
- **Report-grounded answers:** voice answers use the uploaded report's tests,
  values, units, printed reference ranges and laboratory flags.
- **Doctor discovery:** Google Places API (New) listings with addresses, Google
  Maps links and location-based search.
- **Guided appointment preview:** select a doctor, choose a date and time, enter
  a name, and review the request.
- **Flexible development:** browser UI, microphone console and a key-free
  Doctor Connect preview.
- **Audio controls:** LiveKit background-voice cancellation for Cloud room audio,
  browser audio processing and configurable speech/interruption detection.

## How it works

1. Upload a medical PDF or image, or start with the fictional sample report.
2. MediVoice checks the first page, extracts each report page and creates one
   structured medical JSON context for that conversation.
3. Ask a question by voice and hear an explanation grounded in that report.
4. Ask to connect with a doctor to open Doctor Connect within the conversation.
5. Select a listing, then complete separate date, time and patient-name screens.
6. Review the simulated request while keeping the voice conversation active.

Each appointment step includes spoken guidance during LiveKit calls. Back buttons
preserve entered details, and spoken names can be confirmed before review.
Appointment previews do not send messages or reserve clinic slots.

## Technology

| Layer | Technology |
| --- | --- |
| Frontend | React, Vite |
| Backend | FastAPI, Python |
| Voice sessions | LiveKit Agents |
| Speech recognition | AssemblyAI `whisper-rt` |
| Language and report processing | Groq `openai/gpt-oss-120b` |
| Speech output | Cartesia Sonic 3.6 directly; selectable LiveKit Inference or ElevenLabs |
| Report knowledge | Qwen 3.8 vision on Groq, PyMuPDF page rendering and validated medical JSON |
| Doctor search | Google Places API (New) |
| Speech detection | Silero VAD |
| Deployment | Railway backend, Vercel frontend |

Report knowledge and answer flow:

```text
Medical PDF / image → first-page medical relevance check → page rendering
→ Qwen vision extraction → page-linked medical JSON → session context

Speech → AssemblyAI → Groq routing and report reasoning using session context
       → Grounding checks, Hindi normalization and safety review → TTS
```

Doctor requests use the appointment workflow; off-topic and unclear requests
receive guided redirects. Prompts address report grounding, diagnosis/prescribing
boundaries and prompt-injection resistance.

## Project structure

```text
apps/
  frontend/        React UI
  api/             FastAPI endpoints
  voice_agent/     LiveKit and console entrypoint
packages/
  voice/           Speech pipeline and guardrails
  knowledge/       Medical PDF/image extraction and report JSON construction
  doctor_connect/  Search and appointment workflow
  contracts/       Shared data models
  shared/          Configuration, report loading, storage and logging
tests/             Automated tests and fictional report fixtures
deploy/            Railway process launcher
```

## Getting started

Install Git, Python 3.11–3.13, uv and Node 22 (including npm).
The commands below use a macOS/Linux shell; on Windows use Git Bash or adapt the
file-copy commands for PowerShell. Live voice needs internet access and microphone
permission. On Debian/Ubuntu, install `libportaudio2` for local console audio.

### 1. Get the code

```sh
git clone https://github.com/RamaIMP/MediVoice.git
cd MediVoice
```

This folder is the repository root. Open each additional terminal in this same
folder before following the startup commands.

For a UI-only first look, skip Python and credential setup and use
[the key-free Doctor Connect preview](#try-doctor-connect-without-keys).

### 2. Prepare the backend

```sh
uv sync --frozen
# First setup only; preserve an existing .env.
cp .env.example .env
uv run --frozen python -m apps.voice_agent download-files
```

Add credentials to the local `.env` using [.env.example](.env.example).
Keep credentials and conversation logs out of Git.

### 3. Configure voice services

Create your own LiveKit Cloud project, AssemblyAI account and Groq account. Copy
the LiveKit project's WebSocket URL (`wss://…`), API key and secret, plus the
AssemblyAI and Groq API keys, into the matching `.env` fields. Enable access to
the selected models and ensure the accounts have available quota/credits.
The example uses a separate Cartesia account and `CARTESIA_API_KEY` for speech output.
Keep provider keys in the backend `.env` or Railway variables, never the frontend.
Google credentials are optional when using fictional doctor listings.

| Configuration | Variables |
| --- | --- |
| LiveKit | `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` |
| Speech recognition | `ASSEMBLYAI_API_KEY` |
| Groq | `GROQ_API_KEY`, `LANGUAGE_PROVIDER=groq` |
| Direct Cartesia | `TTS_PROVIDER=cartesia_direct`, `CARTESIA_API_KEY`, model and voice ID from the example |
| Google search | `GOOGLE_PLACES_API_KEY`, `DOCTOR_SEARCH_PROVIDER=google` |
| Live voice mode | `DEMO_MODE=false` |

The example selects Cartesia Sonic 3.6 directly and uses Cartesia credits, not
LiveKit Inference credits. `CARTESIA_MODEL=cartesia/sonic-3.6` works for both
Cartesia paths; the direct plugin removes the `cartesia/` prefix.
To use LiveKit Inference instead, set `TTS_PROVIDER=cartesia_livekit` and ensure
LiveKit inference credits remain. To use ElevenLabs, set `TTS_PROVIDER=elevenlabs`
and configure its key, model and voice ID. Providers do not switch automatically.

Hindi transcripts are normalized to Devanagari in the existing language-routing
call, including Romanized Hindi and confidently recognized Hindustani rendered
in Urdu script by speech recognition. The conversation panel updates the same
user turn after normalization. Numeric values are checked for changes, medical
terms and negation are preserved by the routing prompt, and patient-name
collection is never normalized. Uncertain input asks for clarification; other
languages remain subject to the language guardrail. Raw speech transcripts stay
available in private console debug logs when enabled.

For the first run, keep `FRONTEND_URL=http://localhost:5173` and set
`DOCTOR_SEARCH_MODE=dummy`. Leave `VITE_API_BASE_URL` unset locally so the Vite
proxy connects to port 8010. Check backend configuration before starting:

```sh
uv run --frozen python -m scripts.check_setup
```

For live voice, expect `voice_configured: true` and an empty
`missing_voice_settings` list. This checks presence, not validity, of credentials.

### Run the browser application

Start three terminals:

```sh
# Terminal 1: repository root
uv run --frozen uvicorn apps.api.main:app --host 127.0.0.1 --port 8010

# Terminal 2: repository root
uv run --frozen python -m apps.voice_agent dev

# Terminal 3: repository root
cd apps/frontend
npm ci
npm run dev -- --port 5173 --strictPort
```

Open http://localhost:5173. Vite proxies API requests to port 8010.
Mobile microphone and location access require HTTPS; localhost supports desktop
development. Restart the API and worker after configuration changes.

To verify the running application:

1. Open http://localhost:8010/health and check for `status: "ok"` and no missing
   voice settings.
2. Confirm the worker terminal reports that the worker is registered.
3. Open the UI, choose a medical PDF/image or **Try voice** with the sample
   report, wait for the ready message, and press **Start talking**. Allow
   microphone access.
4. Ask “Please explain my report”, then “Connect me to a doctor”.

Use **Stop talking** to end the call and Ctrl+C in all three terminals to stop
the local servers. Closing the browser alone does not stop them.

If voice is unavailable, open the menu's **Demo setup and testing**, check missing
settings, confirm `DEMO_MODE=false`, and restart both backend processes. For a
busy port, use `lsof -nP -iTCP:5173 -sTCP:LISTEN` on macOS/Linux and stop only a
process you recognise, or reuse the existing frontend.

### Run in console mode

```sh
uv run --frozen python -m apps.voice_agent console
```

Console mode uses the computer microphone and speaker without a frontend/API
server or LiveKit room. Cartesia via LiveKit still uses LiveKit Inference credits;
AssemblyAI, Groq and the selected TTS provider's usage terms apply.
Ctrl+C stops the process.

### Try Doctor Connect without keys

From the cloned repository root, run:

```sh
cd apps/frontend
npm ci
npm run dev -- --port 5173 --strictPort
```

Open http://localhost:5173, open the hamburger menu, expand **Demo setup and
testing**, enter “I want to see a doctor nearby” and click **Send question**.
Select a doctor and follow the date/time/name screens. This preview uses
fictional doctors and touch controls without Python, a backend or API keys.
The offline voice-status message is expected in this mode. Optional browser
speech input is available in English; spoken step guidance runs in live voice mode.

## Google doctor search

Enable Google Places API (New), configure billing and set:

```dotenv
DOCTOR_SEARCH_PROVIDER=google
DOCTOR_SEARCH_MODE=auto
GOOGLE_PLACES_API_KEY=your_key_here
```

Users can provide an area/city or tap **Use my location** to grant permission.
Coordinate search covers a 5 km radius and displays approximate straight-line
distances. Search sends the location/query to Google, not report or appointment
details. Results show address cards and external Google Maps links.

Labelled fictional listings keep the demo usable when live search is unavailable.
Set `DOCTOR_SEARCH_MODE=dummy` to use them explicitly. The fictional contact
previews illustrate WhatsApp, phone and appointment-page options.

## Report knowledge pipeline

MediVoice accepts medical PDFs, JPGs, PNGs and WebP images from the browser.
The API checks the first page for a medical report, renders each accepted page,
and sends one page at a time to Qwen vision. The extracted pages are combined
into a compact JSON document containing patient details, lab details, doctors,
medical tables, notes and uncertainties. The report's original page structure
is retained, so blood, urine, biochemistry, imaging and other medical report
formats can be used in the same conversation flow.

Each extracted table includes semantic column roles such as `test`, `value`,
`unit`, `reference_range` and `flag`. This lets the voice layer use report data
without depending on a particular laboratory's header names or column order.
For text-based PDFs, the page image is cross-checked against the PDF text layer
to preserve numeric separators such as `7,400` and `7.400`. When a value cannot
be read confidently, MediVoice keeps it uncertain rather than changing it.

The resulting JSON is stored with the active conversation session and is passed
to the voice pipeline as report context. Broad summaries identify printed flags
and reported out-of-range results; questions about a named test receive a
focused answer using the relevant value and reference range. The fictional
[sample report](tests/fixtures/reports/sample_report.json) remains available for
local demos and console mode.

## Deployment

### Railway backend

The repository includes a [Dockerfile](Dockerfile) and
[Railway configuration](railway.toml) for automatic builds.

- Deploy from the repository root with one replica.
- The container runs FastAPI and the LiveKit worker together through
  `python -m deploy.railway`, sharing the demo SQLite session store.
- Set backend credentials in Railway variables.
- Copy the non-secret model/voice settings from `.env.example` too, including
  `TTS_PROVIDER=cartesia_direct`, `LANGUAGE_PROVIDER=groq` and `DEMO_MODE=false`
  for the default live voice setup. Local `.env` files are not deployed by Git.
- Set `FRONTEND_URL` to the exact Vercel origin without a trailing slash.
- Expose FastAPI's `PORT` (default 8080); the worker health server uses 8081.
- Use `/health` for the configured health check and test a voice session after deployment.

For direct Cartesia speech output, configure these Railway variables alongside
the LiveKit, AssemblyAI and Groq credentials:

```dotenv
TTS_PROVIDER=cartesia_direct
CARTESIA_API_KEY=your_cartesia_key_here
CARTESIA_MODEL=cartesia/sonic-3.6
CARTESIA_VOICE_ID=9626c31c-bec5-4cca-baa8-f8ba9e84c8bc
ASSEMBLYAI_MODEL=whisper-rt
LANGUAGE_PROVIDER=groq
GROQ_MODEL=openai/gpt-oss-120b
DEMO_MODE=false
```

This sends speech synthesis directly to Cartesia; LiveKit still provides the
browser voice connection. Keep the LiveKit URL, key and secret from the same
project. An existing Railway service must have its variables updated explicitly:
changing `.env.example` in Git does not change the deployed configuration.

### Vercel frontend

- Import the repository with root directory `apps/frontend`.
- Select Vite; install with `npm ci`, build with `npm run build`, output `dist`.
- Set `VITE_API_BASE_URL=https://<your-backend>.up.railway.app` without a trailing slash.
- Redeploy after changing frontend environment variables.

After Vercel provides the frontend URL, set that exact origin as Railway's
`FRONTEND_URL` and redeploy the backend. Then test a new conversation on Vercel.

When publishing updates, push to the branch connected to both hosts (normally
`main`). Confirm Railway and Vercel deployed the intended commit; if automatic
deployment is disabled, trigger deployment manually. Reload the frontend and
start a new voice session to test the new worker and UI together. Check a report
question in each language and the guided Doctor Connect flow.

Backend secrets belong in Railway. Never put secrets in `VITE_*` variables,
which can be included in browser bundles. Hosting and provider usage are billed
separately.

## Tests and development

```sh
uv run --frozen python -m scripts.check_setup
uv run --frozen pytest
uv run --frozen ruff check .
cd apps/frontend
npm test
npm run build
```

The setup checker checks configuration without calling providers. Automated tests
use mocks and fictional fixtures. CI runs backend tests/lint and frontend tests/build.

Console debug output is written to `debug_logs/` with intermediate text, errors
and timings. Set `CONSOLE_DEBUG=false` to disable additional content/file logging.
Treat logs as sensitive and keep them private.

Develop components on separate branches and use pull requests for integration.
Include shared-contract updates and tests when changing component interfaces.
