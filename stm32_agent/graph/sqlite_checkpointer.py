from __future__ import annotations

import random
import sqlite3
import threading
from pathlib import Path
from typing import Any, AsyncIterator, Iterator, Sequence

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_checkpoint_id,
    get_checkpoint_metadata,
)


def get_default_graph_checkpoints_path(repo_root: str | Path | None = None) -> Path:
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[2]
    return Path(repo_root).resolve() / ".chipwhisper_cache" / "langgraph_checkpoints.sqlite3"


class SQLiteCheckpointer(BaseCheckpointSaver[str]):
    def __init__(self, path: str | Path, *, serde: Any | None = None) -> None:
        super().__init__(serde=serde)
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            self.path,
            timeout=30.0,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._initialize_schema()

    def __enter__(self) -> "SQLiteCheckpointer":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool | None:
        self.close()
        return None

    async def __aenter__(self) -> "SQLiteCheckpointer":
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> bool | None:
        self.close()
        return None

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _initialize_schema(self) -> None:
        with self._lock, self._connection:
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA synchronous=NORMAL")
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    thread_id TEXT NOT NULL,
                    checkpoint_ns TEXT NOT NULL,
                    checkpoint_id TEXT NOT NULL,
                    parent_checkpoint_id TEXT,
                    checkpoint_type TEXT NOT NULL,
                    checkpoint_blob BLOB NOT NULL,
                    metadata_type TEXT NOT NULL,
                    metadata_blob BLOB NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoint_blobs (
                    thread_id TEXT NOT NULL,
                    checkpoint_ns TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    version TEXT NOT NULL,
                    value_type TEXT NOT NULL,
                    value_blob BLOB NOT NULL,
                    PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoint_writes (
                    thread_id TEXT NOT NULL,
                    checkpoint_ns TEXT NOT NULL,
                    checkpoint_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    write_idx INTEGER NOT NULL,
                    channel TEXT NOT NULL,
                    value_type TEXT NOT NULL,
                    value_blob BLOB NOT NULL,
                    task_path TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx)
                )
                """
            )

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        thread_id = str(config["configurable"]["thread_id"])
        checkpoint_ns = str(config["configurable"].get("checkpoint_ns", ""))
        checkpoint_id = get_checkpoint_id(config)
        with self._lock:
            if checkpoint_id:
                row = self._connection.execute(
                    """
                    SELECT *
                    FROM checkpoints
                    WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id = ?
                    """,
                    (thread_id, checkpoint_ns, checkpoint_id),
                ).fetchone()
                if row is None:
                    return None
                return self._row_to_checkpoint_tuple(
                    row,
                    config=config,
                    thread_id=thread_id,
                    checkpoint_ns=checkpoint_ns,
                )

            row = self._connection.execute(
                """
                SELECT *
                FROM checkpoints
                WHERE thread_id = ? AND checkpoint_ns = ?
                ORDER BY checkpoint_id DESC
                LIMIT 1
                """,
                (thread_id, checkpoint_ns),
            ).fetchone()
            if row is None:
                return None
            return self._row_to_checkpoint_tuple(
                row,
                config=None,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
            )

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        config_thread_id = str(config["configurable"]["thread_id"]) if config else ""
        config_checkpoint_ns = (
            str(config["configurable"].get("checkpoint_ns", "")) if config else None
        )
        config_checkpoint_id = get_checkpoint_id(config) if config else None
        before_checkpoint_id = get_checkpoint_id(before) if before else None

        clauses: list[str] = []
        params: list[Any] = []
        if config_thread_id:
            clauses.append("thread_id = ?")
            params.append(config_thread_id)
        if config_checkpoint_ns is not None:
            clauses.append("checkpoint_ns = ?")
            params.append(config_checkpoint_ns)
        if config_checkpoint_id:
            clauses.append("checkpoint_id = ?")
            params.append(config_checkpoint_id)
        if before_checkpoint_id:
            clauses.append("checkpoint_id < ?")
            params.append(before_checkpoint_id)

        sql = "SELECT * FROM checkpoints"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY thread_id ASC, checkpoint_ns ASC, checkpoint_id DESC"

        emitted = 0
        with self._lock:
            rows = self._connection.execute(sql, params).fetchall()
            for row in rows:
                metadata = self._load_typed(row["metadata_type"], row["metadata_blob"])
                if filter and not all(filter_value == metadata.get(filter_key) for filter_key, filter_value in filter.items()):
                    continue
                thread_id = str(row["thread_id"])
                checkpoint_ns = str(row["checkpoint_ns"])
                yield self._row_to_checkpoint_tuple(
                    row,
                    config=None,
                    thread_id=thread_id,
                    checkpoint_ns=checkpoint_ns,
                    metadata=metadata,
                )
                emitted += 1
                if limit is not None and emitted >= limit:
                    break

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        thread_id = str(config["configurable"]["thread_id"])
        checkpoint_ns = str(config["configurable"].get("checkpoint_ns", ""))
        parent_checkpoint_id = config["configurable"].get("checkpoint_id")
        checkpoint_copy = checkpoint.copy()
        channel_values = dict(checkpoint_copy.pop("channel_values", {}))

        with self._lock, self._connection:
            for channel, version in new_versions.items():
                if channel in channel_values:
                    value_type, value_blob = self.serde.dumps_typed(channel_values[channel])
                else:
                    value_type, value_blob = ("empty", b"")
                self._connection.execute(
                    """
                    INSERT OR REPLACE INTO checkpoint_blobs (
                        thread_id, checkpoint_ns, channel, version, value_type, value_blob
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        thread_id,
                        checkpoint_ns,
                        str(channel),
                        str(version),
                        str(value_type),
                        sqlite3.Binary(value_blob),
                    ),
                )

            checkpoint_type, checkpoint_blob = self.serde.dumps_typed(checkpoint_copy)
            metadata_type, metadata_blob = self.serde.dumps_typed(get_checkpoint_metadata(config, metadata))
            self._connection.execute(
                """
                INSERT OR REPLACE INTO checkpoints (
                    thread_id,
                    checkpoint_ns,
                    checkpoint_id,
                    parent_checkpoint_id,
                    checkpoint_type,
                    checkpoint_blob,
                    metadata_type,
                    metadata_blob
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    thread_id,
                    checkpoint_ns,
                    str(checkpoint["id"]),
                    str(parent_checkpoint_id) if parent_checkpoint_id else None,
                    str(checkpoint_type),
                    sqlite3.Binary(checkpoint_blob),
                    str(metadata_type),
                    sqlite3.Binary(metadata_blob),
                ),
            )

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint["id"],
            }
        }

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        thread_id = str(config["configurable"]["thread_id"])
        checkpoint_ns = str(config["configurable"].get("checkpoint_ns", ""))
        checkpoint_id = str(config["configurable"]["checkpoint_id"])

        with self._lock, self._connection:
            for index, (channel, value) in enumerate(writes):
                write_idx = WRITES_IDX_MAP.get(channel, index)
                value_type, value_blob = self.serde.dumps_typed(value)
                verb = "INSERT OR IGNORE" if write_idx >= 0 else "INSERT OR REPLACE"
                self._connection.execute(
                    f"""
                    {verb} INTO checkpoint_writes (
                        thread_id,
                        checkpoint_ns,
                        checkpoint_id,
                        task_id,
                        write_idx,
                        channel,
                        value_type,
                        value_blob,
                        task_path
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        thread_id,
                        checkpoint_ns,
                        checkpoint_id,
                        str(task_id),
                        int(write_idx),
                        str(channel),
                        str(value_type),
                        sqlite3.Binary(value_blob),
                        str(task_path or ""),
                    ),
                )

    def delete_thread(self, thread_id: str) -> None:
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM checkpoint_writes WHERE thread_id = ?", (thread_id,))
            self._connection.execute("DELETE FROM checkpoint_blobs WHERE thread_id = ?", (thread_id,))
            self._connection.execute("DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,))

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        return self.get_tuple(config)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        for item in self.list(config, filter=filter, before=before, limit=limit):
            yield item

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        return self.put(config, checkpoint, metadata, new_versions)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        self.put_writes(config, writes, task_id, task_path)

    async def adelete_thread(self, thread_id: str) -> None:
        self.delete_thread(thread_id)

    def get_next_version(self, current: str | None, channel: None) -> str:
        if current is None:
            current_version = 0
        elif isinstance(current, int):
            current_version = current
        else:
            current_version = int(str(current).split(".")[0])
        next_version = current_version + 1
        return f"{next_version:032}.{random.random():016}"

    def _row_to_checkpoint_tuple(
        self,
        row: sqlite3.Row,
        *,
        config: RunnableConfig | None,
        thread_id: str,
        checkpoint_ns: str,
        metadata: CheckpointMetadata | None = None,
    ) -> CheckpointTuple:
        checkpoint_id = str(row["checkpoint_id"])
        checkpoint = self._load_typed(row["checkpoint_type"], row["checkpoint_blob"])
        checkpoint = {
            **checkpoint,
            "channel_values": self._load_blobs(
                thread_id,
                checkpoint_ns,
                checkpoint.get("channel_versions", {}),
            ),
        }
        resolved_metadata = metadata or self._load_typed(row["metadata_type"], row["metadata_blob"])
        parent_checkpoint_id = str(row["parent_checkpoint_id"] or "").strip()
        pending_writes = self._load_writes(thread_id, checkpoint_ns, checkpoint_id)
        resolved_config = config or {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }
        return CheckpointTuple(
            config=resolved_config,
            checkpoint=checkpoint,
            metadata=resolved_metadata,
            parent_config=(
                {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": parent_checkpoint_id,
                    }
                }
                if parent_checkpoint_id
                else None
            ),
            pending_writes=pending_writes,
        )

    def _load_blobs(
        self,
        thread_id: str,
        checkpoint_ns: str,
        versions: ChannelVersions,
    ) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for channel, version in dict(versions or {}).items():
            row = self._connection.execute(
                """
                SELECT value_type, value_blob
                FROM checkpoint_blobs
                WHERE thread_id = ? AND checkpoint_ns = ? AND channel = ? AND version = ?
                """,
                (thread_id, checkpoint_ns, str(channel), str(version)),
            ).fetchone()
            if row is None:
                continue
            if str(row["value_type"]) == "empty":
                continue
            values[str(channel)] = self._load_typed(row["value_type"], row["value_blob"])
        return values

    def _load_writes(
        self,
        thread_id: str,
        checkpoint_ns: str,
        checkpoint_id: str,
    ) -> list[tuple[str, str, Any]]:
        rows = self._connection.execute(
            """
            SELECT task_id, channel, value_type, value_blob
            FROM checkpoint_writes
            WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id = ?
            ORDER BY task_id ASC, write_idx ASC
            """,
            (thread_id, checkpoint_ns, checkpoint_id),
        ).fetchall()
        return [
            (
                str(row["task_id"]),
                str(row["channel"]),
                self._load_typed(row["value_type"], row["value_blob"]),
            )
            for row in rows
        ]

    def _load_typed(self, value_type: str, payload: bytes) -> Any:
        return self.serde.loads_typed((str(value_type), bytes(payload)))
