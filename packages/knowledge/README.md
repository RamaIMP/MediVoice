# Report knowledge extraction experiment

## Direct Qwen vision pipeline (current test)

`qwen_pdf_to_json.py` renders each PDF page as a PNG, sends **one image per request**
to Groq's `qwen/qwen3.8-27b`, validates each page JSON, then compiles them in order
into a single `report.json`. There is no separate OCR service or final LLM merge.
No bounding boxes are requested or returned in the validated JSON.

Use the existing `GROQ_API_KEY` in the repository's ignored `.env`:

```sh
uv run --with pymupdf python -m packages.knowledge.qwen_pdf_to_json \
  /Users/ramachandra/Downloads/PL02.pdf --max-pages 2 --allow-upload
```

This tests the first two pages of the eight-page document, not the whole report.
Omit `--max-pages 2` for all pages. Outputs go to a unique ignored
`outputs/qwen-.../` directory: `page-001.png`, `page-001.json`, etc., and `report.json`.
These contain private report data and must not be committed or published.
The voice pipeline is not connected to this experiment.

### Use a completed report in MediVoice locally

The clean Qwen `report.json` can now be supplied directly to the existing voice LLM;
no CBC-only adapter is needed. Set this local, ignored environment value before
starting the API/voice worker:

```sh
REPORT_CONTEXT_PATH=packages/knowledge/outputs/qwen-<run-id>/report.json
```

For the completed eight-page test, `<run-id>` is `f39858224d73`. The API will load
that JSON when it creates a session and pass it unchanged to the voice pipeline.
The numeric guardrail uses values across all report pages. This is local-only because
the output is Git-ignored; a deployment needs a future upload/storage path rather
than a developer-machine file path.

The final `report.json` contains only patient name/age/sex, lab name/address, doctors
(once at document level), and page-linked medical tables, notes and uncertainties.
No duplicated full text, billing/ID fields, image descriptions or bounding boxes.
Previously captured metadata is supplied to subsequent requests to avoid repeating it.
Sample types, methods and printed clinical notes are preserved without repeating results.
`diagnostics.json` separately holds source/selected page counts, status, model, token
usage and timings. No final `report.json` is published for failed pages or conflicting
metadata. Keep diagnostics alongside the report to identify partial document selections.
Numeric values remain strings to retain
decimals, signs and units. Schema checks do not prove visual accuracy; review required.
Tables spanning pages stay separate. A selected subset is explicitly labelled
`selected_pages`; a failed page produces partial output and exit code 2.

There is no fixed pause by default; optionally set `--pause-seconds` for your account.
A 429 is retried once using `Retry-After` (up to 120 seconds).
Rate-limit waits show a plain-language message and retry delay in the CLI, and emit
a progress callback saved to `progress.json`. Persistent limits show a try-later
message, not a misleading network-error message. This callback is ready for future
API/UI integration; the current frontend does not yet display extraction progress.
This local pacing cannot coordinate other clients sharing the account. Other failures
stop the run without silently skipping pages; existing page JSONs remain available.
The 4,000-token output cap rejects truncated responses instead of saving invalid JSON.

Tests: `uv run pytest tests/test_knowledge_qwen.py tests/test_knowledge_ocr.py`.
Groq reference: https://console.groq.com/docs/vision

## Earlier NVIDIA OCR experiment

PDF/image → hosted Nemotron OCR v2 → Nemotron Nano Omni → one page-linked JSON.
Standalone: this does not change the API, frontend or voice agent. No model download
or GPU is required. PyMuPDF renders locally; images and OCR text are sent to NVIDIA.
Only upload reports you have permission to send.

## Run

From the `medivoice` root, add `NVIDIA_API_KEY` to your local ignored `.env` file.
The key must have access to both models. Never commit it or expose it to the frontend.
Start with one page:

```sh
uv run --with pymupdf python -m packages.knowledge.ocr_to_json \
  /Users/ramachandra/Downloads/PL02.pdf --max-pages 1 --allow-upload
```

Remove `--max-pages 1` to process the whole PDF. PNG/JPEG inputs are also accepted.
`--with pymupdf` does not change production dependencies or download model weights.
Rendering defaults to 180 DPI; `--dpi 240` gives larger images for small print.

Each run creates a unique `packages/knowledge/outputs/run-.../` folder containing
`page-001-ocr.json`, etc. (text detections without bounding boxes) and `report.json`
(all pages, text, confidence, tables/key-value pairs, warnings and measured timings).
The LLM receives only text and evidence IDs, not coordinates or confidence scores.
Without layout coordinates, ambiguous table relationships must be flagged, not guessed.
Outputs are Git-ignored and may contain sensitive data; do not publish them.
Rendered images are held in memory, not saved to disk.

To retry formatting from an original saved NVIDIA page-1 OCR response, add
`--saved-ocr path/to/original-page-001-ocr.json --max-pages 1`. This avoids another
OCR request. The OCR timing in this mode is local loading time, not inference time.
Earlier raw response files remain untouched; newly written outputs omit bounding boxes.

## Validation

Every structured cell must cite OCR detection IDs and match their text, apart from
whitespace. Schema, page number, references and table widths are validated. This
does not prove OCR correctness, table alignment or completeness: successful output
is marked `needs_review`. Compare against the source before use in report answers.
Raw OCR is retained even when formatting fails. No medical interpretation is requested.

One LLM call is made per page; Python combines pages into one JSON. Cross-page tables
remain separate to avoid speculative merging. The first failure stops the run and
saves partial output. No automatic retries. Partial documents (including deliberate
page subsets) exit with code 2. Source, selected and processed page counts are explicit.

Timings measure rendering, hosted OCR round-trip, LLM formatting/validation and total
wall time, not theoretical GPU speed. Live endpoint access still needs a valid key.

Tests (mocked; no API credits): `uv run pytest tests/test_knowledge_ocr.py`.

References:
- https://docs.nvidia.com/nim/ingestion/image-ocr/latest/use-the-api.html
- https://github.com/NVIDIA/NeMo-Retriever/blob/main/docs/docs/extraction/prerequisites-support-matrix.md
- https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-nano-omni-30b-a3b-reasoning-infer
