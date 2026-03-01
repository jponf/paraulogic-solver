#!/usr/bin/env python3
"""Minify a JSON file for production use."""

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Minify a JSON file.")
    parser.add_argument("input", type=Path, help="Input JSON file")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Output file")

    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: file not found: {args.input}", file=sys.stderr)
        return 1

    original_size = args.input.stat().st_size

    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)

    with open(args.output, "wt", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    new_size = args.output.stat().st_size
    reduction = (1 - new_size / original_size) * 100
    print(
        f"{original_size:,} -> {new_size:,} bytes ({reduction:.1f}% smaller)",
        file=sys.stderr,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
