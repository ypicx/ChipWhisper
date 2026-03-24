from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from ..extension_packs import CatalogRegistry, load_catalog
from .retrieval_index import ensure_retrieval_index, search_retrieval_index
from .state import RetrievedChunk


_TOKEN_RE = re.compile(r"[A-Za-z0-9_+-]+")
_MAX_CONTENT_CHARS = 2200


@dataclass(frozen=True)
class RetrievalQuery:
    chips: tuple[str, ...]
    boards: tuple[str, ...]
    modules: tuple[str, ...]
    mcu_family: str
    terms: tuple[str, ...]

    def to_filter_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if self.chips:
            payload["chip_names"] = list(self.chips)
        if self.boards:
            payload["board_names"] = list(self.boards)
        if self.modules:
            payload["module_names"] = list(self.modules)
        if self.mcu_family:
            payload["mcu_family"] = self.mcu_family
        if self.terms:
            payload["terms"] = list(self.terms)
        return payload


def retrieve_relevant_chunks(
    user_input: str,
    repo_root: str | Path,
    packs_dir: str | Path | None = None,
    active_project_dir: str | Path | None = None,
    limit: int = 6,
) -> tuple[List[RetrievedChunk], Dict[str, Any]]:
    repo_path = Path(repo_root).resolve()
    registry = load_catalog(packs_dir)
    query = _build_query(user_input, registry, repo_path, active_project_dir)
    base_corpus, corpus_key = _build_base_corpus_with_key(repo_path, registry)
    ensure_retrieval_index(repo_path, corpus_key, base_corpus)

    indexed_candidates = search_retrieval_index(
        repo_path,
        _hybrid_query_terms(query),
        max(limit * 6, 18),
        mcu_family=query.mcu_family,
        chip_names=query.chips,
        board_names=query.boards,
        module_names=query.modules,
    )
    current_chunks = _current_project_chunks(Path(active_project_dir)) if active_project_dir else []

    if indexed_candidates:
        candidate_chunks = _dedupe_chunks(
            [
                *[chunk for chunk in indexed_candidates if _metadata_matches(chunk.get("metadata", {}), query)],
                *[chunk for chunk in current_chunks if _metadata_matches(chunk.get("metadata", {}), query)],
            ]
        )
    else:
        corpus = [*base_corpus, *current_chunks]
        candidate_chunks = [chunk for chunk in corpus if _metadata_matches(chunk.get("metadata", {}), query)]

    query_terms = _hybrid_query_terms(query)
    doc_freq = _document_frequency(candidate_chunks, query_terms)
    avg_doc_len = _average_doc_length(candidate_chunks)
    total_docs = max(len(candidate_chunks), 1)

    scored: List[RetrievedChunk] = []
    for chunk in candidate_chunks:
        score = _score_chunk(chunk, query, query_terms, doc_freq, total_docs, avg_doc_len)
        if score <= 0:
            continue
        entry = dict(chunk)
        entry["score"] = round(score, 3)
        scored.append(entry)

    scored.sort(key=lambda item: (float(item.get("score", 0.0)), str(item.get("source", ""))), reverse=True)
    return scored[:limit], query.to_filter_dict()


def render_retrieved_context(chunks: Sequence[RetrievedChunk]) -> str:
    lines: List[str] = []
    for index, chunk in enumerate(chunks, start=1):
        metadata = chunk.get("metadata", {})
        labels = []
        doc_type = str(metadata.get("doc_type", "")).strip()
        if doc_type:
            labels.append(doc_type)
        module_name = str(metadata.get("module_name", "")).strip()
        if module_name:
            labels.append(module_name)
        board_name = str(metadata.get("board_name", "")).strip()
        if board_name:
            labels.append(board_name)
        chip_name = str(metadata.get("chip_name", "")).strip()
        if chip_name:
            labels.append(chip_name)
        header = f"[{index}] {chunk.get('source', '')}"
        if labels:
            header += " | " + " | ".join(labels)
        lines.append(header)
        lines.append(str(chunk.get("content", "")).strip())
        lines.append("")
    return "\n".join(line for line in lines if line is not None).strip()


def _build_query(
    user_input: str,
    registry: CatalogRegistry,
    repo_root: Path,
    active_project_dir: str | Path | None,
) -> RetrievalQuery:
    search_text = user_input.strip()
    if active_project_dir:
        project_ir_path = Path(active_project_dir) / "project_ir.json"
        if project_ir_path.exists():
            try:
                project_ir = json.loads(project_ir_path.read_text(encoding="utf-8"))
                target = project_ir.get("target", {})
                chip_name = str(target.get("chip", "")).strip().upper()
                family = str(target.get("family", "")).strip().upper()
                if chip_name and chip_name not in search_text.upper():
                    search_text += f" {chip_name}"
                if family and family not in search_text.upper():
                    search_text += f" {family}"
            except ValueError:
                pass

    upper_text = search_text.upper()
    lower_text = search_text.lower()
    normalized_query = _normalize_search_text(lower_text)
    chips = sorted({name for name in registry.chips if name in upper_text})

    boards = sorted(
        {
            board.key
            for board in registry.boards.values()
            if _matches_named_entity(lower_text, normalized_query, board.key, board.display_name)
        }
    )
    modules = sorted(
        {
            module.key
            for module in registry.modules.values()
            if _matches_named_entity(lower_text, normalized_query, module.key, module.display_name)
        }
    )

    mcu_family = ""
    if chips:
        chip = registry.chips.get(chips[0])
        if chip is not None:
            mcu_family = chip.family.upper()
    elif boards:
        board = registry.boards.get(boards[0])
        if board is not None:
            chip = registry.chips.get(board.chip.upper())
            if chip is not None:
                mcu_family = chip.family.upper()
    else:
        family_match = re.search(r"STM32([FGHLU]\d)", upper_text)
        if family_match:
            mcu_family = f"STM32{family_match.group(1)}".upper()
        elif "STM32F1" in upper_text:
            mcu_family = "STM32F1"
        elif "STM32G4" in upper_text:
            mcu_family = "STM32G4"

    terms = tuple(
        token.lower()
        for token in _TOKEN_RE.findall(lower_text)
        if len(token) >= 2 and token.lower() not in {"stm32", "project", "board", "module"}
    )

    return RetrievalQuery(
        chips=tuple(chips),
        boards=tuple(boards),
        modules=tuple(modules),
        mcu_family=mcu_family,
        terms=terms,
    )


@lru_cache(maxsize=8)
def _build_base_corpus(repo_root: Path, packs_dir_key: str, corpus_key: str) -> tuple[RetrievedChunk, ...]:
    registry = load_catalog(packs_dir_key or None)
    chunks: List[RetrievedChunk] = []
    chunks.extend(_catalog_chunks(registry))
    chunks.extend(_pack_template_chunks(registry))
    chunks.extend(_readme_chunks(repo_root))
    chunks.extend(_docs_chunks(repo_root / "docs"))
    chunks.extend(_example_chunks(repo_root / "examples"))
    return tuple(chunks)


def _build_base_corpus_with_key(repo_root: Path, registry: CatalogRegistry) -> tuple[List[RetrievedChunk], str]:
    corpus_key = _base_corpus_signature(repo_root, registry)
    return list(_build_base_corpus(repo_root, registry.packs_dir, corpus_key)), corpus_key


def _build_corpus(
    repo_root: Path,
    registry: CatalogRegistry,
    active_project_dir: str | Path | None,
) -> List[RetrievedChunk]:
    corpus, _corpus_key = _build_base_corpus_with_key(repo_root, registry)
    if active_project_dir:
        corpus.extend(_current_project_chunks(Path(active_project_dir)))
    return corpus


def _catalog_chunks(registry: CatalogRegistry) -> List[RetrievedChunk]:
    chunks: List[RetrievedChunk] = []
    for chip in registry.chips.values():
        content = "\n".join(
            [
                f"芯片: {chip.name}",
                f"系列: {chip.family}",
                f"封装: {chip.package}",
                f"Flash/RAM: {chip.flash_kb}KB / {chip.ram_kb}KB",
                f"保留引脚: {', '.join(chip.reserved_pins)}",
            ]
        )
        chunks.append(
            {
                "content": content,
                "source": chip.definition_path or f"catalog:chip:{chip.name}",
                "score": 0.0,
                "metadata": {
                    "doc_type": "chip_def",
                    "chunk_type": "chip_summary",
                    "chip_name": chip.name,
                    "mcu_family": chip.family.upper(),
                    "source_priority": 100,
                },
            }
        )

    for board in registry.boards.values():
        board_chip = registry.chips.get(board.chip.upper())
        capability_lines = []
        for item in board.capabilities[:8]:
            name = str(item.get("display_name", "")).strip() or str(item.get("key", "")).strip()
            summary = str(item.get("summary", "")).strip()
            line = f"- {name}" if name else "-"
            if summary:
                line += f": {summary}"
            capability_lines.append(line)
        content = "\n".join(
            [
                f"板子: {board.display_name} ({board.key})",
                f"目标芯片: {board.chip}",
                f"摘要: {board.summary}",
                "能力:",
                *(capability_lines or ["- 未声明板级能力"]),
                *[f"备注: {note}" for note in board.notes[:4]],
            ]
        )
        chunks.append(
            {
                "content": content[:_MAX_CONTENT_CHARS],
                "source": board.definition_path or f"catalog:board:{board.key}",
                "score": 0.0,
                "metadata": {
                    "doc_type": "board_def",
                    "chunk_type": "board_summary",
                    "board_name": board.key,
                    "chip_name": board.chip,
                    "mcu_family": board_chip.family.upper() if board_chip else "",
                    "source_priority": 95,
                },
            }
        )

    for module in registry.modules.values():
        content = "\n".join(
            [
                f"模块: {module.display_name} ({module.key})",
                f"摘要: {module.summary}",
                f"资源请求: {', '.join(module.resource_requests) or '无'}",
                f"依赖模块: {', '.join(module.depends_on) or '无'}",
                f"HAL组件: {', '.join(module.hal_components) or '无'}",
                f"总线类型: {module.bus_kind or '无'}",
                f"地址选项: {', '.join(hex(item) for item in module.address_options) or '无'}",
                *[f"备注: {note}" for note in module.notes[:4]],
            ]
        )
        chunks.append(
            {
                "content": content[:_MAX_CONTENT_CHARS],
                "source": module.definition_path or f"catalog:module:{module.key}",
                "score": 0.0,
                "metadata": {
                    "doc_type": "module_def",
                    "chunk_type": "module_summary",
                    "module_name": module.key,
                    "module_display_name": module.display_name,
                    "source_priority": 90,
                },
            }
        )
    return chunks


def _pack_template_chunks(registry: CatalogRegistry) -> List[RetrievedChunk]:
    chunks: List[RetrievedChunk] = []
    packs_root = Path(registry.packs_dir)
    modules_root = packs_root / "modules"
    if not modules_root.exists():
        return chunks

    for module_key, module in registry.modules.items():
        module_dir = modules_root / module_key / "templates"
        if not module_dir.exists():
            continue
        for path in sorted(module_dir.rglob("*")):
            if not path.is_file():
                continue
            suffixes = {item.lower() for item in path.suffixes}
            if not suffixes.intersection({".c", ".h", ".tpl"}):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            relative_path = path.relative_to(module_dir).as_posix()
            preview = "\n".join(text.splitlines()[:80]).strip()
            if not preview:
                continue
            chunks.append(
                {
                    "content": preview[:_MAX_CONTENT_CHARS],
                    "source": str(path),
                    "score": 0.0,
                    "metadata": {
                        "doc_type": "code_snippet",
                        "chunk_type": "module_template",
                        "module_name": module_key,
                        "module_display_name": module.display_name,
                        "mcu_family": "",
                        "template_path": relative_path,
                        "source_priority": 88,
                    },
                }
            )
    return chunks


def _readme_chunks(repo_root: Path) -> List[RetrievedChunk]:
    readme = repo_root / "README.md"
    if not readme.exists():
        return []
    return _markdown_chunks(readme, doc_type="guide")


def _docs_chunks(docs_root: Path) -> List[RetrievedChunk]:
    chunks: List[RetrievedChunk] = []
    if not docs_root.exists():
        return chunks
    for path in sorted(docs_root.glob("*.md")):
        chunks.extend(_markdown_chunks(path, doc_type="guide"))
    return chunks


def _example_chunks(examples_root: Path) -> List[RetrievedChunk]:
    chunks: List[RetrievedChunk] = []
    if not examples_root.exists():
        return chunks
    for path in sorted(examples_root.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        modules = payload.get("modules", [])
        module_names = [str(item.get("kind", "")).strip() for item in modules if isinstance(item, dict)]
        content = "\n".join(
            [
                f"示例文件: {path.name}",
                f"芯片: {payload.get('chip', '')}",
                f"板子: {payload.get('board', 'chip_only')}",
                f"模块: {', '.join(module_names) or '无'}",
                *[f"需求: {item}" for item in payload.get("requirements", [])[:4]],
            ]
        )
        chip_name = str(payload.get("chip", "")).strip().upper()
        mcu_family = ""
        if chip_name.startswith("STM32F1"):
            mcu_family = "STM32F1"
        if chip_name.startswith("STM32G4"):
            mcu_family = "STM32G4"
        chunks.append(
            {
                "content": content[:_MAX_CONTENT_CHARS],
                "source": str(path),
                "score": 0.0,
                "metadata": {
                    "doc_type": "example",
                    "chunk_type": "example_request",
                    "chip_name": chip_name,
                    "board_name": str(payload.get("board", "")).strip(),
                    "module_names": module_names,
                    "mcu_family": mcu_family,
                    "source_priority": 55,
                },
            }
        )
    return chunks


def _current_project_chunks(project_dir: Path) -> List[RetrievedChunk]:
    chunks: List[RetrievedChunk] = []
    for name in ("project_ir.json", "REPORT.generated.md", "README.generated.md"):
        path = project_dir / name
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        metadata: Dict[str, Any] = {
            "doc_type": "current_project",
            "chunk_type": "project_state",
            "project_dir": str(project_dir),
            "source_priority": 85,
        }
        if path.name == "project_ir.json":
            try:
                payload = json.loads(text)
                target = payload.get("target", {})
                metadata["chip_name"] = str(target.get("chip", "")).strip().upper()
                metadata["mcu_family"] = str(target.get("family", "")).strip().upper()
                metadata["module_names"] = [
                    str(item.get("kind", "")).strip()
                    for item in payload.get("modules", [])
                    if isinstance(item, dict)
                ]
                rendered = json.dumps(
                    {
                        "target": target,
                        "modules": payload.get("modules", []),
                        "status": payload.get("status", {}),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                text = rendered
            except ValueError:
                pass
        chunks.append(
            {
                "content": text[:_MAX_CONTENT_CHARS],
                "source": str(path),
                "score": 0.0,
                "metadata": metadata,
            }
        )
    return chunks


def _markdown_chunks(path: Path, doc_type: str) -> List[RetrievedChunk]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []

    sections = _split_markdown_sections(text)
    chunks: List[RetrievedChunk] = []
    for index, section in enumerate(sections, start=1):
        content = section.strip()
        if not content:
            continue
        metadata = {
            "doc_type": doc_type,
            "chunk_type": "markdown_section",
            "source_priority": 60 if doc_type == "guide" else 50,
        }
        metadata.update(_infer_metadata_from_text(content))
        chunks.append(
            {
                "content": content[:_MAX_CONTENT_CHARS],
                "source": f"{path}#section-{index}",
                "score": 0.0,
                "metadata": metadata,
            }
        )
    return chunks


def _split_markdown_sections(text: str) -> List[str]:
    sections: List[str] = []
    current: List[str] = []
    for line in text.splitlines():
        if line.startswith("#") and current:
            sections.append("\n".join(current).strip())
            current = [line]
            continue
        current.append(line)
    if current:
        sections.append("\n".join(current).strip())
    return sections[:24]


def _infer_metadata_from_text(text: str) -> Dict[str, Any]:
    upper_text = text.upper()
    lower_text = text.lower()
    metadata: Dict[str, Any] = {}

    chip_match = re.search(r"\b(STM32[A-Z0-9]+)\b", upper_text)
    if chip_match:
        chip_name = chip_match.group(1).strip().upper()
        metadata["chip_name"] = chip_name
        family_match = re.match(r"(STM32[A-Z]\d)", chip_name)
        if family_match:
            metadata["mcu_family"] = family_match.group(1).upper()

    modules: List[str] = []
    for pattern in ("dht11", "ds18b20", "mpu6050", "ssd1306", "bh1750", "at24c02", "aht20", "ds3231", "pcf8574", "mcp4017"):
        if pattern in lower_text:
            modules.append(pattern)
    if modules:
        metadata["module_names"] = sorted(set(modules))

    if "ct117e" in lower_text:
        metadata["board_name"] = "ct117e_m4_g431"
        metadata.setdefault("mcu_family", "STM32G4")
    elif "blue pill" in lower_text:
        metadata["board_name"] = "blue_pill_f103c8"
        metadata.setdefault("mcu_family", "STM32F1")
    return metadata


def _score_chunk(
    chunk: RetrievedChunk,
    query: RetrievalQuery,
    query_terms: List[str],
    doc_freq: Dict[str, int],
    total_docs: int,
    avg_doc_len: float,
) -> float:
    metadata = chunk.get("metadata", {})
    if not _metadata_matches(metadata, query):
        return -1.0

    score = 0.0
    score += _metadata_boost(metadata, query)
    score += _source_priority_boost(metadata)
    score += _bm25_like_score(chunk, query_terms, doc_freq, total_docs, avg_doc_len)
    score += _term_overlap_score(chunk, query_terms)
    score += _phrase_score(chunk, query)
    return score


def _metadata_boost(metadata: Dict[str, Any], query: RetrievalQuery) -> float:
    score = 0.0
    doc_type = str(metadata.get("doc_type", "")).strip()
    doc_weight = {
        "module_def": 6.0,
        "board_def": 5.5,
        "chip_def": 5.0,
        "code_snippet": 4.5,
        "current_project": 4.0,
        "example": 3.0,
        "guide": 2.0,
    }.get(doc_type, 1.0)
    score += doc_weight

    module_names = set(_normalize_metadata_list(metadata.get("module_names")))
    single_module = str(metadata.get("module_name", "")).strip().lower()
    if single_module:
        module_names.add(single_module)
    if query.modules:
        matched = len(module_names.intersection({item.lower() for item in query.modules}))
        score += matched * 10.0

    board_name = str(metadata.get("board_name", "")).strip().lower()
    if query.boards and board_name and board_name in {item.lower() for item in query.boards}:
        score += 9.0

    chip_name = str(metadata.get("chip_name", "")).strip().upper()
    if query.chips and chip_name and chip_name in query.chips:
        score += 8.0

    mcu_family = str(metadata.get("mcu_family", "")).strip().upper()
    if query.mcu_family and mcu_family == query.mcu_family:
        score += 7.0
    return score


def _source_priority_boost(metadata: Dict[str, Any]) -> float:
    priority = int(metadata.get("source_priority", 0) or 0)
    return min(priority / 20.0, 6.0)


def _hybrid_query_terms(query: RetrievalQuery) -> List[str]:
    terms = set(query.terms)
    for item in query.chips:
        terms.update(_tokenize(item))
    for item in query.boards:
        terms.update(_tokenize(item))
    for item in query.modules:
        terms.update(_tokenize(item))
    if query.mcu_family:
        terms.update(_tokenize(query.mcu_family))
    return sorted(term for term in terms if len(term) >= 2)


def _document_frequency(chunks: Sequence[RetrievedChunk], query_terms: Sequence[str]) -> Dict[str, int]:
    frequency: Dict[str, int] = {}
    for term in query_terms:
        count = 0
        for chunk in chunks:
            tokens = set(_chunk_tokens(chunk))
            if term in tokens:
                count += 1
        frequency[term] = max(count, 1)
    return frequency


def _average_doc_length(chunks: Sequence[RetrievedChunk]) -> float:
    if not chunks:
        return 1.0
    total = sum(max(len(_chunk_tokens(chunk)), 1) for chunk in chunks)
    return max(total / len(chunks), 1.0)


def _bm25_like_score(
    chunk: RetrievedChunk,
    query_terms: Sequence[str],
    doc_freq: Dict[str, int],
    total_docs: int,
    avg_doc_len: float,
) -> float:
    tokens = _chunk_tokens(chunk)
    if not tokens or not query_terms:
        return 0.0

    counts = Counter(tokens)
    doc_length = max(len(tokens), 1)
    k1 = 1.2
    b = 0.75
    score = 0.0
    for term in query_terms:
        tf = counts.get(term, 0)
        if tf <= 0:
            continue
        df = max(doc_freq.get(term, 1), 1)
        idf = math.log(1.0 + (total_docs - df + 0.5) / (df + 0.5))
        numerator = tf * (k1 + 1.0)
        denominator = tf + k1 * (1.0 - b + b * (doc_length / avg_doc_len))
        score += idf * (numerator / denominator)
    return score * 3.0


def _term_overlap_score(chunk: RetrievedChunk, query_terms: Sequence[str]) -> float:
    if not query_terms:
        return 0.0
    haystack = _chunk_search_text(chunk)
    overlap = sum(1 for term in query_terms if term in haystack)
    return min(overlap * 1.25, 10.0)


def _phrase_score(chunk: RetrievedChunk, query: RetrievalQuery) -> float:
    haystack = _chunk_search_text(chunk)
    score = 0.0
    for module in query.modules:
        normalized = _normalize_search_text(module)
        if normalized and normalized in haystack:
            score += 5.0
    for board in query.boards:
        normalized = _normalize_search_text(board)
        if normalized and normalized in haystack:
            score += 4.0
    for chip in query.chips:
        normalized = _normalize_search_text(chip)
        if normalized and normalized in haystack:
            score += 4.0
    if query.mcu_family:
        normalized = _normalize_search_text(query.mcu_family)
        if normalized and normalized in haystack:
            score += 3.0
    return score


def _metadata_matches(metadata: Dict[str, Any], query: RetrievalQuery) -> bool:
    mcu_family = str(metadata.get("mcu_family", "")).strip().upper()
    if query.mcu_family and mcu_family and mcu_family != query.mcu_family:
        return False

    board_name = str(metadata.get("board_name", "")).strip().lower()
    if query.boards and board_name and board_name not in {item.lower() for item in query.boards}:
        return False

    module_names = set(_normalize_metadata_list(metadata.get("module_names")))
    single_module = str(metadata.get("module_name", "")).strip().lower()
    if single_module:
        module_names.add(single_module)
    if query.modules and module_names and not module_names.intersection({item.lower() for item in query.modules}):
        return False

    chip_name = str(metadata.get("chip_name", "")).strip().upper()
    if query.chips and chip_name and chip_name not in query.chips:
        return False
    return True


def _chunk_tokens(chunk: RetrievedChunk) -> List[str]:
    metadata = chunk.get("metadata", {})
    raw_fields = [
        str(chunk.get("content", "")).lower(),
        str(chunk.get("source", "")).lower(),
        str(metadata.get("doc_type", "")).lower(),
        str(metadata.get("chunk_type", "")).lower(),
        str(metadata.get("chip_name", "")).lower(),
        str(metadata.get("board_name", "")).lower(),
        str(metadata.get("module_name", "")).lower(),
        str(metadata.get("module_display_name", "")).lower(),
        str(metadata.get("mcu_family", "")).lower(),
        " ".join(_normalize_metadata_list(metadata.get("module_names"))),
    ]
    return _tokenize(" ".join(raw_fields))


def _chunk_search_text(chunk: RetrievedChunk) -> str:
    return _normalize_search_text(" ".join(_chunk_tokens(chunk)))


def _tokenize(text: str) -> List[str]:
    return [token.lower() for token in _TOKEN_RE.findall(text.lower()) if len(token) >= 2]


def _normalize_metadata_list(raw: Any) -> Iterable[str]:
    if not isinstance(raw, list):
        return []
    return [str(item).strip().lower() for item in raw if str(item).strip()]


def _dedupe_chunks(chunks: Sequence[RetrievedChunk]) -> List[RetrievedChunk]:
    unique: Dict[str, RetrievedChunk] = {}
    for chunk in chunks:
        key = str(chunk.get("source", "")).strip()
        if not key:
            continue
        if key not in unique:
            unique[key] = dict(chunk)
    return list(unique.values())


def _matches_named_entity(query_text: str, normalized_query: str, *candidates: str) -> bool:
    for candidate in candidates:
        text = str(candidate or "").strip().lower()
        if not text:
            continue
        if text in query_text:
            return True
        normalized = _normalize_search_text(text)
        if normalized and normalized in normalized_query:
            return True
        for alias in _candidate_aliases(text):
            if alias and alias in normalized_query:
                return True
    return False


def _normalize_search_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _candidate_aliases(text: str) -> List[str]:
    tokens = [token for token in re.split(r"[^a-z0-9]+", text.lower().replace("_", " ")) if token]
    aliases = set()
    for token in tokens:
        normalized = _normalize_search_text(token)
        if len(normalized) >= 4:
            aliases.add(normalized)
    for index in range(len(tokens) - 1):
        merged = _normalize_search_text(tokens[index] + tokens[index + 1])
        if len(merged) >= 6:
            aliases.add(merged)
    return sorted(aliases)


def _base_corpus_signature(repo_root: Path, registry: CatalogRegistry) -> str:
    entries: List[str] = []
    for path in _iter_base_corpus_files(repo_root, registry):
        try:
            stat = path.stat()
        except OSError:
            continue
        entries.append(f"{path}:{int(stat.st_mtime_ns)}:{stat.st_size}")
    digest = hashlib.sha256("\n".join(entries).encode("utf-8", errors="replace")).hexdigest()
    return digest


def _iter_base_corpus_files(repo_root: Path, registry: CatalogRegistry) -> Iterable[Path]:
    seen: set[Path] = set()
    candidates: List[Path] = []
    for loaded in registry.loaded_files:
        candidates.append(Path(loaded))
    packs_root = Path(registry.packs_dir)
    if packs_root.exists():
        candidates.extend(path for path in packs_root.rglob("*") if path.is_file())
    for path in (repo_root / "README.md",):
        if path.exists():
            candidates.append(path)
    for root in (repo_root / "docs", repo_root / "examples"):
        if root.exists():
            candidates.extend(path for path in root.rglob("*") if path.is_file())
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        yield resolved
