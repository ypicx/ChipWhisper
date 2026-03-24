# Retrieval Index

ChipWhisper now uses a local persistent retrieval index for the base knowledge corpus.

## What changed

The retrieval layer is no longer pure in-memory keyword scoring for every request.

It now works in two stages:

1. `SQLite + FTS5` recalls candidate chunks from the local corpus.
2. The existing metadata filter and hybrid re-ranker score those candidates again.

This keeps the current hardware-aware retrieval behavior, while avoiding repeated full-corpus token scanning as the repo grows.

## Indexed sources

The persistent index covers the base corpus:

- `packs/chips/*.json`
- `packs/boards/*.json`
- `packs/modules/*/module.json`
- `packs/modules/*/templates/**/*`
- `docs/*.md`
- `README.md`
- `examples/*.json` when present

Current project files such as:

- `project_ir.json`
- `REPORT.generated.md`
- `README.generated.md`

are still loaded dynamically and merged in-memory on top of the indexed results.

## Storage

The local index is stored at:

```text
.chipwhisper_cache/retrieval.sqlite3
```

It is rebuilt automatically when the base corpus fingerprint changes.

## Retrieval flow

For each request:

1. Build a structured query:
   - chip
   - board
   - module
   - MCU family
   - free-form terms
2. Apply metadata-aware recall through the local index.
3. Re-apply strict metadata filtering in Python.
4. Re-rank with the existing hybrid scoring:
   - metadata boosts
   - source priority
   - BM25-like score
   - term overlap
   - phrase hits

## Why this design

This project is not a generic chat RAG system. Hardware facts are sensitive:

- STM32 family matters
- board matters
- module name matters
- pack/source priority matters

So the index is only used for fast candidate recall.
Final ranking still stays under ChipWhisper's domain-specific logic.

## Current limits

- This is local lexical retrieval, not embedding-based semantic search.
- It depends on SQLite having `FTS5` support.
- If SQLite/FTS is unavailable, retrieval falls back to the in-memory path.
