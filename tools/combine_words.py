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


def load_diec_words(path: Path) -> set[str]:
    """Load words from DIEC crawler output.

    Supports both JSON format and words-only (one per line) format.
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
            # JSON format: {"entries": [{"word": "..."}, ...]}
            for entry in data["entries"]:
                if word := entry.get("word"):
                    words.add(word.strip())
        elif "words" in data:
            # Alternative format
            for word_entry in data["words"]:
                if isinstance(word_entry, list) and word_entry:
                    for w in word_entry:
                        words.add(w.strip())
                elif isinstance(word_entry, str):
                    words.add(word_entry.strip())
        return words
    except json.JSONDecodeError:
        pass

    # Fall back to words-only format (one per line)
    for line in content.splitlines():
        line = line.strip()
        if line:
            words.add(line)

    return words


def load_paraulogic_words(path: Path) -> set[str]:
    """Load words from Paraulogic crawler output.

    Expected format: {"words": [["word1"], ["word2"], ...]}
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
                        words.add(w.strip())
                elif isinstance(word_entry, str):
                    words.add(word_entry.strip())
    except json.JSONDecodeError as e:
        print(f"Error parsing Paraulogic file: {e}", file=sys.stderr)

    return words


def load_existing_words(path: Path) -> set[str]:
    """Load words from existing words_v*.json file."""
    words: set[str] = set()

    if not path.exists():
        return words

    content = path.read_text(encoding="utf-8")

    try:
        data = json.loads(content)
        if "words" in data:
            for word_entry in data["words"]:
                if isinstance(word_entry, list):
                    for w in word_entry:
                        words.add(w.strip())
                elif isinstance(word_entry, str):
                    words.add(word_entry.strip())
    except json.JSONDecodeError as e:
        print(f"Error parsing existing file: {e}", file=sys.stderr)

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
    existing_words: set[str] = set()

    if not args.paraulogic_only:
        diec_words = load_diec_words(args.diec)
        print(f"Loaded {len(diec_words)} words from DIEC", file=sys.stderr)

    if not args.diec_only:
        paraulogic_words = load_paraulogic_words(args.paraulogic)
        print(f"Loaded {len(paraulogic_words)} words from Paraulogic", file=sys.stderr)

    if args.existing:
        existing_words = load_existing_words(args.existing)
        print(f"Loaded {len(existing_words)} words from existing file", file=sys.stderr)

    # Combine words based on mode
    if args.intersection:
        combined = diec_words & paraulogic_words
        print(f"Intersection: {len(combined)} words", file=sys.stderr)
    elif args.diec_only:
        combined = diec_words | existing_words
    elif args.paraulogic_only:
        combined = paraulogic_words | existing_words
    else:
        combined = diec_words | paraulogic_words | existing_words
        print(f"Union: {len(combined)} unique words", file=sys.stderr)

    # Sort words and format as [["word1"], ["word2"], ...]
    sorted_words = sorted(combined)
    words_list = [[w] for w in sorted_words]

    # Write output in words_v*.json format
    output_data = {"words": words_list}

    # Ensure output directory exists
    args.output.parent.mkdir(parents=True, exist_ok=True)

    args.output.write_text(
        json.dumps(output_data, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Wrote {len(sorted_words)} words to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
