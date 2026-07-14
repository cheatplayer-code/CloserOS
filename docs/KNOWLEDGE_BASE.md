# Knowledge Base (NOPQ)

This document describes tenant-isolated knowledge ingestion, indexing, and
retrieval implemented for NOPQ.

## Domain and persistence objects

Primary tables/repositories:

- `knowledge_documents`
- `knowledge_document_versions`
- `knowledge_chunks`
- `knowledge_chunk_terms`

Supporting encryption storage:

- `encrypted_contents` kinds:
  - `knowledge_document`
  - `knowledge_chunk`

## Lifecycle

1. Upload encrypted document content.
2. Create draft version record.
3. Approve version.
4. Enqueue `knowledge.index` outbox job.
5. Worker decrypts document, chunks content, encrypts chunk content.
6. Worker builds tenant-keyed lexical term index.
7. Version is marked `indexed`.
8. Retrieval can use active/indexed chunks only.

## Indexing details

- Deterministic Unicode tokenization (NFKC + casefold).
- Tokens include Unicode letters and decimal digits (RU/KZ/EN).
- Stop-word filtering for English, Russian, and Kazakh after normalization.
- HMAC-SHA256 term digests over `TERM_INDEX_VERSION:token` with tenant search key.
- Explicit index version `v1-unicode-term-v1` (and search key version
  `v1-unicode-search-v1`). Do not mix digests from prior ASCII-only indexes.
- Reindex strategy: re-approve or enqueue `knowledge.index` for each active
  document version after upgrading; old digests will not match new queries.
- Weighted terms in basis points.
- Indexed chunks are revocable per version.

## Retrieval details

`KnowledgeRetrievalService`:

- accepts tenant + query + analysis context;
- builds query term digests with tenant key;
- runs ranked lexical search on active/indexed rows only;
- decrypts chunk content with
  `ContentAccessPurpose.KNOWLEDGE_RETRIEVAL`;
- returns cited results (chunk ID, source code, version, kind, weight);
- appends `knowledge.retrieval.completed` audit metadata.

## Security constraints

- retrieval is always tenant-scoped;
- no cross-tenant index or cache key sharing;
- only metadata is logged/audited;
- decrypted chunk text is never persisted as plaintext in retrieval tables.

## Current limitations

- lexical ranking only (no vector embedding retrieval in NOPQ);
- no public HTTP knowledge routes are exposed in `apps/api` yet;
- `message.analyze` worker orchestration remains a follow-up phase.

