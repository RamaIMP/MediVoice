# Independent development and GitHub merging

Use one repository rooted at medivoice/; create feature branches and PRs.
If medivoice/ remains inside a parent repository, workflows in medivoice/.github
will not run automatically: place/adapt them at the actual repository root.

Suggested work areas:
- feature/knowledge: packages/knowledge and its tests
- feature/voice: packages/voice, apps/voice_agent and their tests
- feature/doctor-connect: packages/doctor_connect and its tests
- feature/ui-api: apps/frontend, apps/api and their tests

Shared contract changes need review from the consuming component owners. Add
backward-compatible fields where possible; explicitly version breaking changes.
Use fictional fixtures and provider mocks so branches can test independently.
Keep secrets, local databases, environments, logs and patient reports out of Git.
Run both CI jobs before merging integration changes.

All Python dependencies are declared in the root pyproject.toml and uv.lock.
Frontend dependencies are in apps/frontend/package.json and package-lock.json.
