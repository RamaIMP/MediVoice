# Doctor Connect — live voice with fictional contacts

demo.py implements a session-local appointment state machine. Gemini's structured
translation response selects care_action/care_value from conversational intent.
Python validates stage transitions and routes to the fictional tool rather than
asking the medical model to invent doctor details. Speculative generation is off.

The worker publishes doctor_connect state on the medivoice topic. UI commands
return on medivoice.care with a revision. Only the room-bound patient can submit
commands; stale revisions resync. Console shares this flow without a visual panel.
State commits only after reply translation succeeds. No real message is sent.

Pending: implement contracts.models.DoctorSearch, location consent, Places search,
verified WhatsApp contact/link and actual appointment-page discovery. The key-free
frontend still has a separate local adapter; its IDs must match this demo fixture.
