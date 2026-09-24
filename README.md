# MediVoice

### Your report companion—powered by voice

MediVoice brings report explanations and doctor discovery into a guided
conversation. Speak in English, Hindi or Telugu, explore report findings, and
choose nearby care through a combination of voice and simple touch controls.

The hackathon demo uses a fictional sample report and simulated appointment
requests. MediVoice is for educational report explanations, not diagnosis or
prescribing; always follow your doctor's advice.

## Highlights

- **Voice-first experience:** microphone input, spoken responses and animated
  conversation states.
- **Multilingual conversations:** application-level language handling for English,
  Hindi and Telugu.
- **Report-grounded answers:** structured report context, numeric checks and
  model-based safety review.
- **Doctor discovery:** Google Places API (New) listings with addresses, Google
  Maps links and location-based search.
- **Guided appointment preview:** select a doctor, choose a date and time, enter
  a name, and review the request.
- **Flexible development:** browser UI, microphone console and a key-free
  Doctor Connect preview.
- **Audio controls:** LiveKit background-voice cancellation for Cloud room audio,
  browser audio processing and configurable speech/interruption detection.

## How it works

1. Start with the sample report or preview a file locally. Demo answers use the
   configured sample report.
2. Ask a question by voice and hear an explanation.
3. Ask to connect with a doctor to open Doctor Connect within the conversation.
4. Select a listing, then complete separate date, time and patient-name screens.
5. Review the simulated request while keeping the voice conversation active.

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
| Speech output | Cartesia Sonic 3.6 through LiveKit Inference; selectable ElevenLabs |
| Doctor search | Google Places API (New) |
| Speech detection | Silero VAD |
| Deployment | Railway backend, Vercel frontend |

Report-answer flow:

```text
Speech → AssemblyAI → Groq routing and report reasoning
       → Grounding checks, translation and safety review → TTS
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
The default Cartesia path uses your LiveKit project's Inference access.
Google credentials are optional when using fictional doctor listings.

| Configuration | Variables |
| --- | --- |
| LiveKit | `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` |
| Speech recognition | `ASSEMBLYAI_API_KEY` |
| Groq | `GROQ_API_KEY`, `LANGUAGE_PROVIDER=groq` |
| Cartesia via LiveKit | `TTS_PROVIDER=cartesia_livekit`, model and voice ID from the example |
| Google search | `GOOGLE_PLACES_API_KEY`, `DOCTOR_SEARCH_PROVIDER=google` |
| Live voice mode | `DEMO_MODE=false` |

The example selects Cartesia Sonic 3.6 through LiveKit Inference. To use ElevenLabs,
set `TTS_PROVIDER=elevenlabs` and configure its key, model and voice ID.

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
3. Open the UI, choose **Try voice** with the sample report, wait for the ready
   message, and press **Start talking**. Allow microphone access.
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

## Report context

Both UI sessions and console mode use
[the fictional sample report](tests/fixtures/reports/sample_report.json) by default.
Set `REPORT_CONTEXT_PATH` to load another development JSON file that conforms
to `packages.contracts.ReportContext`.

## Deployment

### Railway backend

The repository includes a [Dockerfile](Dockerfile) and
[Railway configuration](railway.toml) for automatic builds.

- Deploy from the repository root with one replica.
- The container runs FastAPI and the LiveKit worker together through
  `python -m deploy.railway`, sharing the demo SQLite session store.
- Set backend credentials in Railway variables.
- Copy the non-secret model/voice settings from `.env.example` too, including
  `TTS_PROVIDER=cartesia_livekit`, `LANGUAGE_PROVIDER=groq` and `DEMO_MODE=false`
  for the default live voice setup. Local `.env` files are not deployed by Git.
- Set `FRONTEND_URL` to the exact Vercel origin without a trailing slash.
- Expose FastAPI's `PORT` (default 8080); the worker health server uses 8081.
- Use `/health` for the configured health check and test a voice session after deployment.

### Vercel frontend

- Import the repository with root directory `apps/frontend`.
- Select Vite; install with `npm ci`, build with `npm run build`, output `dist`.
- Set `VITE_API_BASE_URL=https://<your-backend>.up.railway.app` without a trailing slash.
- Redeploy after changing frontend environment variables.

After Vercel provides the frontend URL, set that exact origin as Railway's
`FRONTEND_URL` and redeploy the backend. Then test a new conversation on Vercel.

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
