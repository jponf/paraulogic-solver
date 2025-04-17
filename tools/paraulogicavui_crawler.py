from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import json
import multiprocessing as mp
from pathlib import Path
import re
import sys
from typing import Final, Iterator, Sequence


import requests
import requests.adapters
import tqdm
import bs4

SOLUTIONS_URL_TEMPLATE: Final = (
    "https://paraulogicavui.com/{date}-solucions-del-paraulogic-davui/"
)
SOLUTIONS_DATE_FORMAT: Final = r"%d-%m-%Y"
SOLUTIONS_RE = re.compile(r"(?:\d+\.|[1️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣8️⃣9️⃣0️⃣]+)\s+(?P<word>\S+)(?: o \S+)?")
TIME_DELTA_1D: Final = datetime.timedelta(days=1)
TIME_DELTA_365D: Final = datetime.timedelta(days=365)


class CrawlerError(Exception):
    """Base crawler exception."""


class SolutionsPageNotFound(CrawlerError):

    def __init__(
        self,
        date: datetime.date,
        url: str,
        status_code: int,
    ) -> None:
        super().__init__(
            f"solutions page not found {date} (status: {status_code} - {url})",
        )
        self.date = date
        self.url = url


class SolutionsNotFound(CrawlerError):

    def __init__(self, date: datetime.date, url: str) -> None:
        super().__init__(f"solutions not found for date {date} ({url})")
        self.date = date
        self.url = url


class CrawlerAppArgs(argparse.Namespace):
    """Crawler application arguments."""

    start_date: datetime.date
    end_date: datetime.date
    output_path: Path


def main() -> int:
    args = _parse_cli_arguments()
    dates = list(date_range(args.start_date, args.end_date))

    # Configure requests
    session = _create_requests_session()

    unique_words: set[str] = set()
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=max(mp.cpu_count(), 32),
    ) as executor:
        fetch_tasks = [
            executor.submit(fetch_solutions_for_date, date=date, session=session)
            for date in tqdm.tqdm(dates, desc="Starting tasks")
        ]

        with tqdm.tqdm(
            concurrent.futures.as_completed(fetch_tasks),
            desc="Crawling",
            total=len(fetch_tasks),
        ) as pbar:
            for future in pbar:  # tqdm.tqdm(dates, desc="Crawling"):
                try:
                    words = future.result()
                    unique_words.update(words)
                    pbar.set_postfix_str(f"# unique: {len(unique_words)}")
                except CrawlerError as err:
                    print(err)

    print("# Unique words:", len(unique_words))
    output_obj = {
        "words": [[w] for w in tqdm.tqdm(unique_words, desc="Post processing")]
    }

    with args.output_path.open("wt") as output_fh:
        json.dump(output_obj, output_fh)

    return 0


def fetch_solutions_for_date(
    date: datetime.date,
    session: requests.Session,
) -> list[str]:
    solutions_url = SOLUTIONS_URL_TEMPLATE.format(
        date=date.strftime(SOLUTIONS_DATE_FORMAT),
    )
    solutions_response = session.get(solutions_url)

    if solutions_response.status_code != 200:
        raise SolutionsPageNotFound(
            date=date,
            url=solutions_url,
            status_code=solutions_response.status_code,
        )

    solutions_bs = bs4.BeautifulSoup(solutions_response.text, "html.parser")
    solutions_div = solutions_bs.find("div", attrs={"class": "entry-content"})

    if not solutions_div:
        raise SolutionsNotFound(date=date, url=solutions_url)

    matches = SOLUTIONS_RE.finditer(solutions_div.get_text(separator="\n"))
    print(matches)
    return [m.group("word") for m in matches]


def date_range(
    start_date: datetime.date,
    end_date: datetime.date,
    *,
    include_end: bool = True,
) -> Iterator[datetime.date]:
    """Generate dates in the given [start, end] range."""
    cur = start_date
    end = end_date + TIME_DELTA_1D if include_end else end_date
    while cur < end:
        yield cur
        cur += TIME_DELTA_1D


class _CustomRetry(requests.adapters.Retry):

    def __init__(self) -> None:
        super().__init__(
            total=5,
            backoff_factor=0.1,
            status_forcelist=[500, 502, 503, 504],
        )

    def is_retry(self, method, status_code, has_retry_after=False):
        if status_code == 404:
            return False
        return super().is_retry(method, status_code, has_retry_after)


def _create_requests_session() -> requests.Session:
    session = requests.Session()
    retry_adapter = _CustomRetry()
    session.mount(
        "http://",
        requests.adapters.HTTPAdapter(max_retries=retry_adapter),
    )
    session.mount(
        "https://",
        requests.adapters.HTTPAdapter(max_retries=retry_adapter),
    )

    return session


def _parse_cli_arguments(argv: Sequence[str] | None = None) -> CrawlerAppArgs:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Crawl Paraulógic solutions.",
    )
    parser.add_argument(
        "-sd",
        "--start-date",
        default=datetime.date.today() - TIME_DELTA_365D,
        type=datetime.date.fromisoformat,
        help="Crawl solutions starting at this date [ISO format: YYYY-MM-DD].",
    )
    parser.add_argument(
        "-ed",
        "--end-date",
        default=datetime.date.today(),
        type=datetime.date.fromisoformat,
        help="Crawl solutions up to this date [ISO format: YYYY-MM-DD].",
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output_path",
        default="words.json",
        type=Path,
        help="Crawled solutions output file.",
    )

    args = parser.parse_args(argv, namespace=CrawlerAppArgs())

    if args.start_date > args.end_date:
        parser.error(
            f"start-date ({args.start_date}) cannot be after than end-date ({args.end_date})",
        )

    return args


if __name__ == "__main__":
    sys.exit(main())
