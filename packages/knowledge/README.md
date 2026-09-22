# Knowledge extraction — NOT IMPLEMENTED

Owner scope: document upload processing, PDF/image parsing, Qwen calls, multi-page
merging and validation. Implement packages.contracts.models.KnowledgeExtractor.
Output: ReportContext v1.0. No dependency on LiveKit or frontend UI.
Raw OCR key_values/table JSON must be converted before the voice pipeline uses it.
Pending integration: authenticated API upload route and session report storage.
Use fictional fixtures and mocked extraction responses for tests.
