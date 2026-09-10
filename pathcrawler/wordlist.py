"""Wordlist loading and path generation helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Tuple

from pathcrawler.errors import WordlistError
from pathcrawler.models import WordlistStats


def load_wordlist(path: str) -> Tuple[List[str], WordlistStats]:
    """Load a UTF-8 wordlist safely and return unique entries with statistics."""

    wordlist_path = Path(path)
    stats = WordlistStats(path=str(wordlist_path))

    if not wordlist_path.exists():
        raise WordlistError("Wordlist not found.")
    if not wordlist_path.is_file():
        raise WordlistError("Wordlist path is not a file.")

    entries: List[str] = []
    seen: set[str] = set()

    try:
        with wordlist_path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                stats.total_lines += 1
                entry = line.strip()
                if not entry:
                    stats.empty += 1
                    continue
                if entry.startswith("#"):
                    stats.comments += 1
                    continue
                if entry in seen:
                    stats.duplicates += 1
                    continue
                seen.add(entry)
                entries.append(entry)
    except PermissionError as exc:
        raise WordlistError("Wordlist is not readable.") from exc
    except OSError as exc:
        raise WordlistError(f"Could not read wordlist: {exc}") from exc

    stats.loaded = len(entries)
    if not entries:
        raise WordlistError("Wordlist is empty after removing comments and blanks.")

    return entries, stats


def normalize_path(path: str) -> str:
    """Normalize a wordlist entry or generated path to an absolute URL path."""

    cleaned = path.strip()
    if not cleaned:
        return "/"
    cleaned = cleaned.split("?", 1)[0].strip()
    cleaned = cleaned.strip("/")
    if not cleaned:
        return "/"
    return "/" + cleaned


def normalize_extensions(extensions: Iterable[str]) -> List[str]:
    """Normalize extension strings and remove duplicates."""

    normalized: List[str] = []
    seen: set[str] = set()
    for extension in extensions:
        ext = extension.strip().lower().lstrip(".")
        if not ext:
            continue
        if not all(ch.isalnum() for ch in ext):
            raise ValueError(f"Invalid extension: {extension}")
        if ext not in seen:
            seen.add(ext)
            normalized.append(ext)
    return normalized


def generate_paths(words: Iterable[str], extensions: Iterable[str], prefix: str = "") -> List[str]:
    """Generate unique normalized paths from words, optional extensions, and a prefix."""

    paths: List[str] = []
    seen: set[str] = set()
    base_prefix = normalize_path(prefix) if prefix else ""
    if base_prefix == "/":
        base_prefix = ""

    for word in words:
        word_path = normalize_path(word)
        if word_path == "/":
            continue
        if base_prefix:
            combined = normalize_path(base_prefix + "/" + word_path.lstrip("/"))
        else:
            combined = word_path
        candidates = [combined]
        last_segment = combined.rsplit("/", 1)[-1]
        if "." not in last_segment:
            for extension in extensions:
                candidates.append(f"{combined}.{extension}")

        for candidate in candidates:
            normalized = normalize_path(candidate)
            if normalized not in seen:
                seen.add(normalized)
                paths.append(normalized)

    return paths
