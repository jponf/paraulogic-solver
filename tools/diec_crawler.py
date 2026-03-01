#!/usr/bin/env python3
"""DIEC2 Dictionary Crawler.

Extracts all words from the Diccionari de la llengua catalana (DIEC2).
https://dlc.iec.cat/
"""

import argparse
import enum
import json
import logging
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Final
from urllib.parse import urlencode

import bs4
import requests

DIEC_BASE_URL: Final = "https://dlc.iec.cat"
RESULTS_ENDPOINT: Final = f"{DIEC_BASE_URL}/Results"

# Catalan alphabet letters to iterate through
CATALAN_LETTERS: Final = list("abcdefghijklmnopqrstuvwxyz")

# Default delay between requests (seconds)
DEFAULT_DELAY: Final = 0.5

# Results per page (observed from the website)
RESULTS_PER_PAGE: Final = 1000

logger = logging.getLogger(__name__)


class Diec2SearchCondition(enum.IntEnum):
    """DIEC2 Search Condition.

    Search condition is passed using the `OperEntrada` argument.
    """

    EXACT_MATCH = 0
    STARTS_WITH = 1
    ENDS_WITH = 2
    CONTAINS = 3
    NOT_STARTS_WITH = 4
    NOT_ENDS_WITH = 5
    DOES_NOT_CONTAIN = 6


@dataclass
class DiecEntry:
    """A dictionary entry from DIEC2."""

    entry_id: int
    word: str
    grammatical_category: str | None = None
    homonym_index: int | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.entry_id,
            "word": self.word,
            "category": self.grammatical_category,
            "homonym": self.homonym_index,
        }


@dataclass
class CrawlResult:
    """Result of a crawl operation."""

    entries: list[DiecEntry] = field(default_factory=list)
    total_records: int = 0
    pages_crawled: int = 0


def build_search_url(
    query: str,
    condition: Diec2SearchCondition = Diec2SearchCondition.STARTS_WITH,
    page: int = 0,
) -> str:
    """Build a DIEC2 search URL with the given parameters."""
    params = {
        "DecEntradaText": query,
        "OperEntrada": condition.value,
        "CurrentPage": page,
        "AllInfoMorf": "False",
        "OperDef": 0,
        "OperEx": 0,
        "OperSubEntrada": 0,
        "OperAreaTematica": 0,
        "InfoMorfType": 0,
        "OperCatGram": "False",
        "AccentSen": "False",
        "refineSearch": 0,
        "Actualitzacions": "False",
    }
    return f"{RESULTS_ENDPOINT}?{urlencode(params)}"


def parse_entry_link(link: bs4.Tag) -> DiecEntry | None:
    """Parse a single entry link from the results page.

    Expected format:
    <a id="0031264" href="#" class="resultAnchor" onclick="GetDefinition('0031264')">a¹</a>
    """
    # Extract entry ID from the id attribute or onclick
    entry_id_str = link.get("id", "")
    if not entry_id_str or not isinstance(entry_id_str, str):
        onclick = link.get("onclick", "")
        if not isinstance(onclick, str):
            return None
        id_match = re.search(r"GetDefinition\(['\"](\d+)['\"]\)", onclick)
        if id_match:
            entry_id_str = id_match.group(1)

    if not entry_id_str or not isinstance(entry_id_str, str):
        return None

    entry_id = int(entry_id_str)

    # Get the word text
    word_text = link.get_text(strip=True)

    # Parse homonym index from superscript (e.g., "a¹" -> word="a", homonym=1)
    homonym_index = None
    # Unicode superscript digits: ¹²³⁴⁵⁶⁷⁸⁹⁰
    superscript_map = {"¹": 1, "²": 2, "³": 3, "⁴": 4, "⁵": 5, "⁶": 6, "⁷": 7, "⁸": 8, "⁹": 9, "⁰": 0}

    for sup_char, num in superscript_map.items():
        if sup_char in word_text:
            homonym_index = num
            word_text = word_text.replace(sup_char, "").strip()
            break

    return DiecEntry(
        entry_id=entry_id,
        word=word_text,
        grammatical_category=None,  # Not available in list view
        homonym_index=homonym_index,
    )


def parse_total_records(soup: bs4.BeautifulSoup) -> int:
    """Extract the total number of records from the results page."""
    # Look for "N registres" text anywhere in the page
    text = soup.get_text()
    match = re.search(r"(\d+)\s*registres?", text)
    if match:
        return int(match.group(1))
    return 0


def parse_results_page(html: str) -> tuple[list[DiecEntry], int]:
    """Parse a results page and extract entries.

    Returns:
        Tuple of (entries list, total records count)
    """
    soup = bs4.BeautifulSoup(html, "html.parser")

    total_records = parse_total_records(soup)

    # Find all entry links with class "resultAnchor"
    links = soup.find_all("a", class_="resultAnchor")

    entries = []
    for link in links:
        entry = parse_entry_link(link)
        if entry:
            entries.append(entry)

    return entries, total_records


class DiecCrawler:
    """Crawler for the DIEC2 dictionary."""

    def __init__(
        self,
        delay: float = DEFAULT_DELAY,
        session: requests.Session | None = None,
    ):
        self.delay = delay
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (compatible; DiecCrawler/1.0; +https://github.com/user/paraulogic-solver)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ca,en;q=0.5",
            }
        )

    def _fetch_page(self, url: str) -> str:
        """Fetch a page with rate limiting."""
        logger.debug(f"Fetching: {url}")
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        time.sleep(self.delay)
        return response.text

    def crawl_letter(
        self,
        letter: str,
        condition: Diec2SearchCondition = Diec2SearchCondition.STARTS_WITH,
    ) -> CrawlResult:
        """Crawl all entries starting with a given letter."""
        result = CrawlResult()
        page = 0
        seen_ids: set[int] = set()

        while True:
            url = build_search_url(letter, condition, page)
            try:
                html = self._fetch_page(url)
            except requests.RequestException as e:
                logger.error(f"Failed to fetch page {page} for letter '{letter}': {e}")
                break

            entries, total_records = parse_results_page(html)

            if page == 0:
                result.total_records = total_records
                logger.info(
                    f"Letter '{letter}': {total_records} total records found"
                )

            if not entries:
                break

            # Filter out duplicates
            new_entries = [e for e in entries if e.entry_id not in seen_ids]
            if not new_entries:
                # No new entries, we've seen them all
                break

            for entry in new_entries:
                seen_ids.add(entry.entry_id)
                result.entries.append(entry)

            result.pages_crawled += 1
            logger.debug(
                f"Page {page}: {len(new_entries)} new entries "
                f"(total: {len(result.entries)})"
            )

            # Check if we've got all records
            if len(result.entries) >= total_records:
                break

            page += 1

        return result

    def crawl_all(
        self,
        letters: list[str] | None = None,
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> CrawlResult:
        """Crawl all entries for all letters."""
        if letters is None:
            letters = CATALAN_LETTERS

        total_result = CrawlResult()
        seen_ids: set[int] = set()

        for i, letter in enumerate(letters):
            logger.info(f"Crawling letter '{letter}' ({i + 1}/{len(letters)})")

            if progress_callback:
                progress_callback(letter, i, len(letters))

            letter_result = self.crawl_letter(letter)

            # Deduplicate across letters
            for entry in letter_result.entries:
                if entry.entry_id not in seen_ids:
                    seen_ids.add(entry.entry_id)
                    total_result.entries.append(entry)

            total_result.pages_crawled += letter_result.pages_crawled
            logger.info(
                f"Letter '{letter}' done: {len(letter_result.entries)} entries, "
                f"total unique: {len(total_result.entries)}"
            )

        total_result.total_records = len(total_result.entries)
        return total_result


def main():
    parser = argparse.ArgumentParser(
        description="Crawl the DIEC2 dictionary to extract all words.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("diec_words.json"),
        help="Output file path",
    )
    parser.add_argument(
        "-l",
        "--letters",
        type=str,
        nargs="+",
        default=None,
        help="Specific letters to crawl (default: all a-z)",
    )
    parser.add_argument(
        "-d",
        "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help="Delay between requests in seconds",
    )
    parser.add_argument(
        "--words-only",
        action="store_true",
        help="Output only word list (one per line) instead of JSON",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (-v for INFO, -vv for DEBUG)",
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.WARNING
    if args.verbose == 1:
        log_level = logging.INFO
    elif args.verbose >= 2:
        log_level = logging.DEBUG

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        stream=sys.stderr,
    )

    # Run crawler
    crawler = DiecCrawler(delay=args.delay)

    def progress(letter: str, current: int, total: int):
        print(f"\rCrawling: {letter} ({current + 1}/{total})", end="", file=sys.stderr)

    print("Starting DIEC2 crawl...", file=sys.stderr)
    result = crawler.crawl_all(letters=args.letters, progress_callback=progress)
    print(f"\nCrawl complete: {len(result.entries)} unique entries", file=sys.stderr)

    # Write output
    if args.words_only:
        words = sorted(set(e.word for e in result.entries))
        args.output.write_text("\n".join(words) + "\n", encoding="utf-8")
        print(f"Wrote {len(words)} unique words to {args.output}", file=sys.stderr)
    else:
        data = {
            "total_entries": len(result.entries),
            "pages_crawled": result.pages_crawled,
            "entries": [e.to_dict() for e in result.entries],
        }
        args.output.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Wrote {len(result.entries)} entries to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
