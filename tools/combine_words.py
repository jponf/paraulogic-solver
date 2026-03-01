#!/usr/bin/env python3
"""Combine word lists from DIEC and Paraulogic crawlers.

Merges results from diec_crawler.py and paraulogicavui_crawler.py
into a single deduplicated word list matching the data/words_v*.json format.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Final

DEFAULT_DIEC_FILE: Final = "diec_words.json"
DEFAULT_PARAULOGIC_FILE: Final = "words.json"


def normalize_word(word: str) -> list[str]:
    """Normalize a word entry, handling variants and filtering phrases.

    - "abstenir o abstindre" -> ["abstenir", "abstindre"] (split variants)
    - "a mansalva" -> [] (filter out phrases)
    - "normal" -> ["normal"]

    Returns list of valid single words.
    """
    word = word.strip()
    if not word:
        return []

    # Check for variant pattern: "word1 o word2" (Catalan "or")
    if " o " in word:
        parts = [p.strip() for p in word.split(" o ")]
        # Validate each part is a single word
        result = []
        for part in parts:
            if part and " " not in part:
                result.append(part)
        return result

    # Filter out phrases (multiple words without "o" separator)
    if " " in word:
        return []

    return [word]


def load_diec_words(path: Path) -> set[str]:
    """Load words from DIEC crawler output.

    Supports both JSON format and words-only (one per line) format.
    Normalizes entries: splits variants ("word1 o word2") and filters phrases.
    """
    words: set[str] = set()

    if not path.exists():
        print(f"Warning: DIEC file not found: {path}", file=sys.stderr)
        return words

    content = path.read_text(encoding="utf-8")

    # Try JSON format first
    try:
        data = json.loads(content)
        if "entries" in data:
            # JSON format: {"entries": [{"word": "...", "conjugations": [...]}, ...]}
            for entry in data["entries"]:
                if word := entry.get("word"):
                    words.update(normalize_word(word))
                # Also include conjugated forms if present
                if conjugations := entry.get("conjugations"):
                    for form in conjugations:
                        words.update(normalize_word(form))
        elif "words" in data:
            # Alternative format
            for word_entry in data["words"]:
                if isinstance(word_entry, list) and word_entry:
                    for w in word_entry:
                        words.update(normalize_word(w))
                elif isinstance(word_entry, str):
                    words.update(normalize_word(word_entry))
        return words
    except json.JSONDecodeError:
        pass

    # Fall back to words-only format (one per line)
    for line in content.splitlines():
        words.update(normalize_word(line))

    return words


def load_paraulogic_words(path: Path) -> set[str]:
    """Load words from Paraulogic crawler output.

    Expected format: {"words": [["word1"], ["word2"], ...]}
    Normalizes entries: splits variants ("word1 o word2") and filters phrases.
    """
    words: set[str] = set()

    if not path.exists():
        print(f"Warning: Paraulogic file not found: {path}", file=sys.stderr)
        return words

    content = path.read_text(encoding="utf-8")

    try:
        data = json.loads(content)
        if "words" in data:
            for word_entry in data["words"]:
                if isinstance(word_entry, list):
                    for w in word_entry:
                        words.update(normalize_word(w))
                elif isinstance(word_entry, str):
                    words.update(normalize_word(word_entry))
    except json.JSONDecodeError as e:
        print(f"Error parsing Paraulogic file: {e}", file=sys.stderr)

    return words


def get_root_form(group: list[str]) -> str | None:
    """Get the root form from a word group (the one without '-' prefix)."""
    for word in group:
        if not word.startswith("-"):
            return word
    return None


def load_existing_groups(path: Path) -> dict[str, list[str]]:
    """Load word groups from existing words_v*.json file.

    Returns a dict mapping root form -> full group list.
    Preserves groupings like ["-a", "dècuple"] where "dècuple" is the root.
    """
    groups: dict[str, list[str]] = {}

    if not path.exists():
        return groups

    content = path.read_text(encoding="utf-8")

    try:
        data = json.loads(content)
        if "words" in data:
            for word_entry in data["words"]:
                if isinstance(word_entry, list) and word_entry:
                    # Find the root form (without "-" prefix)
                    root = get_root_form(word_entry)
                    if root:
                        groups[root] = [w.strip() for w in word_entry]
                    else:
                        # All forms have "-", use first as key
                        groups[word_entry[0].strip()] = [w.strip() for w in word_entry]
                elif isinstance(word_entry, str):
                    word = word_entry.strip()
                    groups[word] = [word]
    except json.JSONDecodeError as e:
        print(f"Error parsing existing file: {e}", file=sys.stderr)

    return groups


def load_existing_words(path: Path) -> set[str]:
    """Load words from existing words_v*.json file (flat set)."""
    groups = load_existing_groups(path)
    words: set[str] = set()
    for group in groups.values():
        words.update(group)
    return words


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Combine word lists from DIEC and Paraulogic crawlers.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-d",
        "--diec",
        type=Path,
        default=Path(DEFAULT_DIEC_FILE),
        help="Path to DIEC crawler output file",
    )
    parser.add_argument(
        "-p",
        "--paraulogic",
        type=Path,
        default=Path(DEFAULT_PARAULOGIC_FILE),
        help="Path to Paraulogic crawler output file",
    )
    parser.add_argument(
        "-e",
        "--existing",
        type=Path,
        default=None,
        help="Path to existing words_v*.json to merge with",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Output file path (e.g., data/words_v4.json)",
    )
    parser.add_argument(
        "--diec-only",
        action="store_true",
        help="Only include words from DIEC",
    )
    parser.add_argument(
        "--paraulogic-only",
        action="store_true",
        help="Only include words from Paraulogic",
    )
    parser.add_argument(
        "--intersection",
        action="store_true",
        help="Only include words present in both sources",
    )

    args = parser.parse_args()

    # Load words from sources
    diec_words: set[str] = set()
    paraulogic_words: set[str] = set()
    existing_groups: dict[str, list[str]] = {}

    if not args.paraulogic_only:
        diec_words = load_diec_words(args.diec)
        print(f"Loaded {len(diec_words)} words from DIEC", file=sys.stderr)

    if not args.diec_only:
        paraulogic_words = load_paraulogic_words(args.paraulogic)
        print(f"Loaded {len(paraulogic_words)} words from Paraulogic", file=sys.stderr)

    if args.existing:
        existing_groups = load_existing_groups(args.existing)
        existing_all_words = set()
        for group in existing_groups.values():
            existing_all_words.update(group)
        print(
            f"Loaded {len(existing_groups)} word groups "
            f"({len(existing_all_words)} total words) from existing file",
            file=sys.stderr,
        )

    # Combine words based on mode
    if args.intersection:
        combined = diec_words & paraulogic_words
        print(f"Intersection: {len(combined)} words", file=sys.stderr)
        # For intersection, output flat (no groupings preserved)
        words_list = [[w] for w in sorted(combined)]
    elif args.diec_only:
        new_words = diec_words
        # Add new words that aren't already in existing groups (by root)
        for word in new_words:
            if word not in existing_groups:
                existing_groups[word] = [word]
        # Sort by root form and output groups
        words_list = [existing_groups[root] for root in sorted(existing_groups.keys())]
    elif args.paraulogic_only:
        new_words = paraulogic_words
        for word in new_words:
            if word not in existing_groups:
                existing_groups[word] = [word]
        words_list = [existing_groups[root] for root in sorted(existing_groups.keys())]
    else:
        # Union: merge all sources, preserving existing groupings
        new_words = diec_words | paraulogic_words
        added_count = 0
        for word in new_words:
            if word not in existing_groups:
                existing_groups[word] = [word]
                added_count += 1
        print(
            f"Union: {len(existing_groups)} unique root words "
            f"({added_count} new)",
            file=sys.stderr,
        )
        # Sort by root form and output groups
        words_list = [existing_groups[root] for root in sorted(existing_groups.keys())]

    # Write output in words_v*.json format
    output_data = {"words": words_list}

    # Ensure output directory exists
    args.output.parent.mkdir(parents=True, exist_ok=True)

    args.output.write_text(
        json.dumps(output_data, ensure_ascii=False),
        encoding="utf-8",
    )

    total_words = sum(len(group) for group in words_list)
    print(
        f"Wrote {len(words_list)} word groups ({total_words} total words) to {args.output}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
