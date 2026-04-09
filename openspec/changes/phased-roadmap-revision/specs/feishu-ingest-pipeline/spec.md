## ADDED Requirements

### Requirement: Feishu document batch ingestion
The system SHALL provide an API endpoint `POST /api/ingest/feishu` that accepts a Feishu space_id and reads all documents from that space, passing each document to the extraction engine.

#### Scenario: Successful batch import from Feishu wiki
- **WHEN** a POST request is sent to `/api/ingest/feishu` with `{"space_id": "7616189322227649741"}`
- **THEN** the system reads all documents from the specified Feishu wiki space, extracts knowledge from each, creates candidate entries in the audit workflow, and returns a summary with counts of extracted entities, relations, and rules

#### Scenario: Feishu API unavailable
- **WHEN** the Feishu API returns an error or times out during batch import
- **THEN** the system returns a 502 error with details of which documents failed, and successfully processed documents are still committed

#### Scenario: Dry-run mode for preview
- **WHEN** a POST request includes `{"space_id": "...", "dry_run": true}`
- **THEN** the system extracts knowledge from all documents but does NOT commit any candidates to the database, returning the extraction results for user review

### Requirement: Single document ingestion
The system SHALL provide an API endpoint `POST /api/ingest/document` that accepts raw text content and passes it to the extraction engine.

#### Scenario: Import a single document by text
- **WHEN** a POST request is sent to `/api/ingest/document` with `{"content": "...", "source": "manual", "title": "排班规则"}`
- **THEN** the system extracts knowledge from the text and creates candidate entries in the audit workflow

### Requirement: Incremental import tracking
The system SHALL track which Feishu documents have been previously imported, skipping unchanged documents on subsequent runs.

#### Scenario: Re-import skips unchanged documents
- **WHEN** a batch import is run and some documents were previously imported with the same content hash
- **THEN** those documents are skipped, and the response indicates how many were skipped vs newly processed

#### Scenario: Changed documents are re-processed
- **WHEN** a previously imported document has been edited in Feishu (content hash differs)
- **THEN** the document is re-processed and new candidates are submitted for review
