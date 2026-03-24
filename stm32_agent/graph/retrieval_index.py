from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from .state import RetrievedChunk


def ensure_retrieval_index(
    repo_root: str | Path,
    corpus_key: str,
    chunks: Sequence[RetrievedChunk],
) -> Path | None:
    db_path = _index_path(repo_root)
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(db_path, timeout=5.0)) as connection:
            _initialize_schema(connection)
            stored_key = _get_meta(connection, "corpus_key")
            if stored_key != corpus_key:
                _rebuild_index(connection, corpus_key, chunks)
    except sqlite3.Error:
        return None
    return db_path


def search_retrieval_index(
    repo_root: str | Path,
    query_terms: Sequence[str],
    limit: int,
    *,
    mcu_family: str = "",
    chip_names: Iterable[str] | None = None,
    board_names: Iterable[str] | None = None,
    module_names: Iterable[str] | None = None,
) -> List[RetrievedChunk]:
    if not query_terms:
        return []
    db_path = _index_path(repo_root)
    if not db_path.exists():
        return []

    match_expr = _build_match_expression(query_terms)
    sql = [
        "SELECT d.content, d.source, d.metadata_json, bm25(docs_fts) AS rank",
        "FROM docs_fts",
        "JOIN docs d ON docs_fts.rowid = d.id",
        "WHERE docs_fts MATCH ?",
    ]
    params: List[Any] = [match_expr]

    if mcu_family:
        sql.append("AND (d.mcu_family = '' OR d.mcu_family = ?)")
        params.append(mcu_family.upper())

    chip_values = [str(item).strip().upper() for item in (chip_names or []) if str(item).strip()]
    if chip_values:
        placeholders = ", ".join("?" for _ in chip_values)
        sql.append(f"AND (d.chip_name = '' OR d.chip_name IN ({placeholders}))")
        params.extend(chip_values)

    board_values = [str(item).strip().lower() for item in (board_names or []) if str(item).strip()]
    if board_values:
        placeholders = ", ".join("?" for _ in board_values)
        sql.append(f"AND (d.board_name = '' OR d.board_name IN ({placeholders}))")
        params.extend(board_values)

    module_values = [str(item).strip().lower() for item in (module_names or []) if str(item).strip()]
    if module_values:
        clauses = ["d.module_name = ''", f"d.module_name IN ({', '.join('?' for _ in module_values)})"]
        params.extend(module_values)
        for module_name in module_values:
            clauses.append("d.module_names_flat LIKE ?")
            params.append(f"%|{module_name}|%")
        sql.append(f"AND ({' OR '.join(clauses)})")

    sql.append("ORDER BY rank ASC, d.source_priority DESC")
    sql.append("LIMIT ?")
    params.append(int(limit))

    try:
        with closing(sqlite3.connect(db_path, timeout=5.0)) as connection:
            rows = connection.execute("\n".join(sql), params).fetchall()
    except sqlite3.Error:
        return []

    chunks: List[RetrievedChunk] = []
    for content, source, metadata_json, rank in rows:
        try:
            metadata = json.loads(metadata_json)
        except ValueError:
            metadata = {}
        chunks.append(
            {
                "content": str(content),
                "source": str(source),
                "score": round(float(-rank), 3),
                "metadata": metadata if isinstance(metadata, dict) else {},
            }
        )
    return chunks


def _index_path(repo_root: str | Path) -> Path:
    return Path(repo_root).resolve() / ".chipwhisper_cache" / "retrieval.sqlite3"


def _initialize_schema(connection: sqlite3.Connection) -> None:
    connection.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS docs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL UNIQUE,
            content TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            chip_name TEXT NOT NULL,
            board_name TEXT NOT NULL,
            module_name TEXT NOT NULL,
            module_names_flat TEXT NOT NULL,
            mcu_family TEXT NOT NULL,
            source_priority INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    connection.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts
        USING fts5(
            content,
            source,
            chip_name,
            board_name,
            module_name,
            mcu_family,
            tokenize = 'unicode61'
        )
        """
    )
    connection.commit()


def _get_meta(connection: sqlite3.Connection, key: str) -> str:
    row = connection.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return str(row[0]) if row else ""


def _set_meta(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def _rebuild_index(connection: sqlite3.Connection, corpus_key: str, chunks: Sequence[RetrievedChunk]) -> None:
    connection.execute("DELETE FROM docs")
    connection.execute("DELETE FROM docs_fts")
    for chunk in chunks:
        metadata = dict(chunk.get("metadata", {}))
        chip_name = str(metadata.get("chip_name", "")).strip().upper()
        board_name = str(metadata.get("board_name", "")).strip().lower()
        module_name = str(metadata.get("module_name", "")).strip().lower()
        module_names = _normalize_metadata_list(metadata.get("module_names"))
        module_names_flat = "|" + "|".join(module_names) + "|" if module_names else ""
        mcu_family = str(metadata.get("mcu_family", "")).strip().upper()
        source_priority = int(metadata.get("source_priority", 0) or 0)
        cursor = connection.execute(
            """
            INSERT INTO docs(
                source, content, metadata_json, chip_name, board_name, module_name, module_names_flat, mcu_family, source_priority
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(chunk.get("source", "")),
                str(chunk.get("content", "")),
                json.dumps(metadata, ensure_ascii=False),
                chip_name,
                board_name,
                module_name,
                module_names_flat,
                mcu_family,
                source_priority,
            ),
        )
        rowid = cursor.lastrowid
        connection.execute(
            """
            INSERT INTO docs_fts(rowid, content, source, chip_name, board_name, module_name, mcu_family)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rowid,
                str(chunk.get("content", "")),
                str(chunk.get("source", "")),
                chip_name,
                board_name,
                module_name,
                mcu_family,
            ),
        )
    _set_meta(connection, "corpus_key", corpus_key)
    connection.commit()


def _build_match_expression(query_terms: Sequence[str]) -> str:
    parts = []
    for term in query_terms:
        normalized = str(term).strip()
        if not normalized:
            continue
        parts.append(f'"{normalized}"')
    return " OR ".join(parts[:16])


def _normalize_metadata_list(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        return []
    return [str(item).strip().lower() for item in raw if str(item).strip()]
