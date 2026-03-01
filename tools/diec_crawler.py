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
ACCEPCIO_ENDPOINT: Final = f"{RESULTS_ENDPOINT}/Accepcio"
VERBS_ENDPOINT: Final = f"{DIEC_BASE_URL}/Verbs"

# Catalan alphabet letters to iterate through
CATALAN_LETTERS: Final = list("abcdefghijklmnopqrstuvwxyz")

# Default delay between requests (seconds)
DEFAULT_DELAY: Final = 0.5

# Results per page (observed from the website)
RESULTS_PER_PAGE: Final = 1000

logger = logging.getLogger(__name__)


def is_valid_word(word: str) -> bool:
    """Check if a word is a valid root word (not a prefix, suffix, or punctuation).

    Filters out:
    - Prefixes: words ending with '-' (e.g., "a-", "ab-")
    - Suffixes: words starting with '-' (e.g., "-ment", "-ció")
    - Alternative notations: words containing '[' (e.g., "a- [o an-]")
    - Punctuation-only entries: words with no letters
    """
    if not word:
        return False
    # Filter out prefixes (ending with -)
    if word.endswith("-"):
        return False
    # Filter out suffixes (starting with -)
    if word.startswith("-"):
        return False
    # Filter out entries with alternative notations
    if "[" in word:
        return False
    # Filter out entries with no letters (punctuation only)
    if not any(c.isalpha() for c in word):
        return False
    return True


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


@dataclass
class VerbConjugation:
    """Conjugation data for a verb."""

    entry_id: int
    infinitive: str
    forms: set[str] = field(default_factory=set)

    def to_dict(self) -> dict:
        return {
            "id": self.entry_id,
            "infinitive": self.infinitive,
            "forms": sorted(self.forms),
        }


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


def parse_conjugation_page(html: str) -> set[str]:
    """Parse a verb conjugation page and extract all conjugated forms.

    Returns:
        Set of all conjugated word forms.
    """
    soup = bs4.BeautifulSoup(html, "html.parser")
    forms: set[str] = set()

    # Find all conjugated forms in <span class="dm2-linia"> tags
    for span in soup.find_all("span", class_="dm2-linia"):
        # Skip tense labels (dm2-temps class)
        classes = span.get("class") or []
        if "dm2-temps" in classes:
            continue

        text = span.get_text(strip=True)
        if not text or text == "-":
            continue

        # Check for nested span with dialectal variants
        inner_span = span.find("span", class_="dm2-var")
        if inner_span:
            # Extract variants from title attribute
            inner_title = inner_span.get("title")
            if inner_title and isinstance(inner_title, str):
                variant_matches = re.findall(r"<b>([^<]+)</b>", inner_title)
                for variant in variant_matches:
                    clean_variant = variant.strip()
                    if clean_variant and clean_variant != "-":
                        forms.add(clean_variant)
            # Get the main form from inner span text
            inner_text = inner_span.get_text(strip=True)
            if inner_text and inner_text != "-":
                forms.add(inner_text)
        else:
            # No nested span, add the text directly
            if text and text != "-":
                forms.add(text)

    return forms


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

    def _post_json(self, url: str, data: dict) -> dict:
        """POST request returning JSON with rate limiting."""
        logger.debug(f"POST: {url}")
        response = self.session.post(url, data=data, timeout=30)
        response.raise_for_status()
        time.sleep(self.delay)
        return response.json()

    def fetch_entry_info(self, entry_id: int) -> dict | None:
        """Fetch entry information including whether it's a verb.

        Returns dict with keys: isVerb, idE, content, etc.
        """
        try:
            return self._post_json(
                ACCEPCIO_ENDPOINT,
                {"id": f"{entry_id:07d}", "searchParam": ""},
            )
        except requests.RequestException as e:
            logger.error(f"Failed to fetch entry info for {entry_id}: {e}")
            return None

    def fetch_conjugation(self, entry_id: int) -> set[str]:
        """Fetch all conjugated forms for a verb.

        Returns set of all conjugated word forms.
        """
        try:
            url = f"{VERBS_ENDPOINT}?IdE={entry_id:07d}"
            html = self._fetch_page(url)
            return parse_conjugation_page(html)
        except requests.RequestException as e:
            logger.error(f"Failed to fetch conjugation for {entry_id}: {e}")
            return set()

    def crawl_conjugations(
        self,
        entries: list[DiecEntry],
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> list[VerbConjugation]:
        """Crawl conjugations for all verbs in the entries list.

        First checks each entry to see if it's a verb, then fetches conjugations.
        """
        conjugations: list[VerbConjugation] = []
        verbs_found = 0

        for i, entry in enumerate(entries):
            if progress_callback:
                progress_callback(i, len(entries), entry.word)

            # Check if this entry is a verb
            info = self.fetch_entry_info(entry.entry_id)
            if not info or not info.get("isVerb"):
                continue

            verbs_found += 1
            logger.info(f"Found verb: {entry.word} (id={entry.entry_id})")

            # Fetch conjugation
            forms = self.fetch_conjugation(entry.entry_id)
            if forms:
                conjugation = VerbConjugation(
                    entry_id=entry.entry_id,
                    infinitive=entry.word,
                    forms=forms,
                )
                conjugations.append(conjugation)
                logger.debug(f"  -> {len(forms)} forms")

        logger.info(f"Found {verbs_found} verbs, {len(conjugations)} with conjugations")
        return conjugations

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
        "--include-affixes",
        action="store_true",
        help="Include prefixes, suffixes, and non-word entries (filtered by default)",
    )
    parser.add_argument(
        "--conjugations",
        action="store_true",
        help="Crawl verb conjugations (requires ~20k additional requests)",
    )
    parser.add_argument(
        "--conjugations-only",
        action="store_true",
        help="Only crawl conjugations, skip initial word list crawl (requires existing entries file)",
    )
    parser.add_argument(
        "--entries-file",
        type=Path,
        help="Use existing entries file for conjugation crawl (with --conjugations-only)",
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

    # Handle conjugations-only mode
    if args.conjugations_only:
        if not args.entries_file:
            print("Error: --entries-file required with --conjugations-only", file=sys.stderr)
            sys.exit(1)
        if not args.entries_file.exists():
            print(f"Error: entries file not found: {args.entries_file}", file=sys.stderr)
            sys.exit(1)

        # Load existing entries
        print(f"Loading entries from {args.entries_file}...", file=sys.stderr)
        with open(args.entries_file, encoding="utf-8") as f:
            data = json.load(f)
        entries = [
            DiecEntry(
                entry_id=e["id"],
                word=e["word"],
                grammatical_category=e.get("category"),
                homonym_index=e.get("homonym"),
            )
            for e in data["entries"]
        ]
        print(f"Loaded {len(entries)} entries", file=sys.stderr)
        output_entries = entries
        pages_crawled = data.get("pages_crawled", 0)
    else:
        # Normal crawl
        def progress(letter: str, current: int, total: int):
            print(f"\rCrawling: {letter} ({current + 1}/{total})", end="", file=sys.stderr)

        print("Starting DIEC2 crawl...", file=sys.stderr)
        result = crawler.crawl_all(letters=args.letters, progress_callback=progress)
        print(f"\nCrawl complete: {len(result.entries)} unique entries", file=sys.stderr)

        # Filter out prefixes, suffixes, and non-word entries (unless --include-affixes)
        if args.include_affixes:
            output_entries = result.entries
        else:
            output_entries = [e for e in result.entries if is_valid_word(e.word)]
            filtered_count = len(result.entries) - len(output_entries)
            if filtered_count > 0:
                print(
                    f"Filtered out {filtered_count} prefix/suffix/non-word entries",
                    file=sys.stderr,
                )
        pages_crawled = result.pages_crawled

    # Crawl conjugations if requested
    all_forms: set[str] = set()
    if args.conjugations or args.conjugations_only:
        def conj_progress(current: int, total: int, word: str):
            print(f"\rChecking: {word} ({current + 1}/{total})", end="", file=sys.stderr)

        print("\nCrawling verb conjugations...", file=sys.stderr)
        conjugations = crawler.crawl_conjugations(output_entries, conj_progress)
        print(f"\nFound {len(conjugations)} verbs with conjugations", file=sys.stderr)

        # Collect all conjugated forms
        for conj in conjugations:
            all_forms.update(conj.forms)
        print(f"Total unique conjugated forms: {len(all_forms)}", file=sys.stderr)

        # Write conjugations to separate file
        conj_output = args.output.with_suffix(".conjugations.json")
        conj_data = {
            "total_verbs": len(conjugations),
            "total_forms": len(all_forms),
            "verbs": [c.to_dict() for c in conjugations],
        }
        conj_output.write_text(
            json.dumps(conj_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Wrote conjugations to {conj_output}", file=sys.stderr)

    # Write main output
    if args.words_only:
        words = sorted(set(e.word for e in output_entries) | all_forms)
        args.output.write_text("\n".join(words) + "\n", encoding="utf-8")
        print(f"Wrote {len(words)} unique words to {args.output}", file=sys.stderr)
    else:
        data = {
            "total_entries": len(output_entries),
            "pages_crawled": pages_crawled,
            "entries": [e.to_dict() for e in output_entries],
        }
        if all_forms:
            data["conjugated_forms"] = sorted(all_forms)
            data["total_conjugated_forms"] = len(all_forms)
        args.output.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Wrote {len(output_entries)} entries to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
