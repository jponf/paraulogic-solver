# Tools

## Setup

Create a virtual environment and install dependencies:

```bash
cd tools
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

## paraulogicavui_crawler.py

A crawler for extracting Paraulogic solutions from [paraulogicavui.com](https://paraulogicavui.com).

### Requirements

```bash
pip install beautifulsoup4 requests tqdm
```

### Usage

```bash
# Crawl last 365 days (default)
python tools/paraulogicavui_crawler.py -o words.json

# Crawl all known solutions (from earliest available date)
python tools/paraulogicavui_crawler.py -sd 2022-08-01 -o words.json

# Crawl specific date range
python tools/paraulogicavui_crawler.py -sd 2024-01-01 -ed 2024-12-31 -o words_2024.json

# Crawl from a specific start date until today
python tools/paraulogicavui_crawler.py -sd 2023-06-01 -o words.json
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `-sd, --start-date` | Start date (ISO format: YYYY-MM-DD) | 365 days ago |
| `-ed, --end-date` | End date (ISO format: YYYY-MM-DD) | today |
| `-o, --output` | Output file path | `words.json` |

### Output Format

```json
{
  "words": [
    ["paraula1"],
    ["paraula2"]
  ]
}
```

### Features

- Concurrent fetching using thread pool (up to 32 workers)
- Automatic retry on server errors (5xx)
- Progress bar with unique word count
- Deduplication of words across all dates

### Notes

- Earliest known date with solutions available: **2022-08-01**

---

## diec_crawler.py

A crawler for extracting all words from the DIEC2 (Diccionari de la llengua catalana).

### Requirements

```bash
pip install beautifulsoup4 requests
```

### Usage

```bash
# Crawl all words (a-z)
python tools/diec_crawler.py -o diec_words.json

# Crawl specific letters
python tools/diec_crawler.py -l a b c -o abc_words.json

# Output words only (one per line, sorted)
python tools/diec_crawler.py --words-only -o words.txt

# Custom delay between requests (default: 0.5s)
python tools/diec_crawler.py -d 0.3 -o output.json

# Verbose output
python tools/diec_crawler.py -v -o output.json    # INFO level
python tools/diec_crawler.py -vv -o output.json   # DEBUG level

# Crawl with verb conjugations (slow - ~20k additional requests)
python tools/diec_crawler.py --conjugations -o diec_full.json

# Crawl only conjugations using existing entries file
python tools/diec_crawler.py --conjugations-only --entries-file diec_words.json -o diec_conjugated.json
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `-o, --output` | Output file path | `diec_words.json` |
| `-l, --letters` | Specific letters to crawl | all (a-z) |
| `-d, --delay` | Delay between requests (seconds) | 0.5 |
| `--words-only` | Output word list instead of JSON | false |
| `--include-affixes` | Include prefixes/suffixes (filtered by default) | false |
| `--conjugations` | Crawl verb conjugations after word list | false |
| `--conjugations-only` | Only crawl conjugations (requires `--entries-file`) | false |
| `--entries-file` | Existing entries file for `--conjugations-only` | none |
| `-v, --verbose` | Increase verbosity | off |

### Output Formats

**JSON (default):**
```json
{
  "total_entries": 607,
  "pages_crawled": 1,
  "entries": [
    {
      "id": 84613,
      "word": "xa",
      "category": null,
      "homonym": null
    }
  ]
}
```

**JSON with conjugations (`--conjugations`):**
```json
{
  "total_entries": 19606,
  "pages_crawled": 26,
  "entries": [...],
  "conjugated_forms": ["canta", "cantava", "cantaré", ...],
  "total_conjugated_forms": 250000
}
```

Additionally creates `*.conjugations.json` with per-verb data:
```json
{
  "total_verbs": 5000,
  "total_forms": 250000,
  "verbs": [
    {
      "id": 1691,
      "infinitive": "cantar",
      "forms": ["cant", "canta", "cantada", "cantades", ...]
    }
  ]
}
```

**Words only (`--words-only`):**
```
xa
xabec
xaberniscle
...
```

### Search Conditions

The crawler uses "starts with" search by default. Available conditions in the code:

- `EXACT_MATCH` (0)
- `STARTS_WITH` (1) - default
- `ENDS_WITH` (2)
- `CONTAINS` (3)
- `NOT_STARTS_WITH` (4)
- `NOT_ENDS_WITH` (5)
- `DOES_NOT_CONTAIN` (6)

### Notes

- The DIEC2 website returns up to 1000 entries per page
- Full crawl (a-z) takes approximately 15-30 minutes with default rate limiting
- Conjugation crawl requires ~20k additional requests (~3 hours at 0.5s delay)
- Prefixes (e.g., "a-") and suffixes are filtered by default; use `--include-affixes` to keep them
- Be respectful of the server - avoid setting delay below 0.2 seconds
- Conjugations include all dialectal variants (central, valencià, balear, nord-occidental, septentrional)

---

## combine_words.py

Combines word lists from DIEC and Paraulogic crawlers into a single file matching the `data/words_v*.json` format.

### Usage

```bash
# Combine DIEC and Paraulogic results
python tools/combine_words.py -d diec_words.json -p words.json -o data/words_v4.json

# Merge with existing words file
python tools/combine_words.py -d diec_words.json -p words.json -e data/words_v3.json -o data/words_v4.json

# Only DIEC words
python tools/combine_words.py -d diec_words.json --diec-only -o data/words_v4.json

# Only Paraulogic words
python tools/combine_words.py -p words.json --paraulogic-only -o data/words_v4.json

# Intersection (words in both sources)
python tools/combine_words.py -d diec_words.json -p words.json --intersection -o data/words_v4.json
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `-d, --diec` | Path to DIEC crawler output | `diec_words.json` |
| `-p, --paraulogic` | Path to Paraulogic crawler output | `words.json` |
| `-e, --existing` | Path to existing words_v*.json to merge | none |
| `-o, --output` | Output file path (required) | - |
| `--diec-only` | Only include DIEC words | false |
| `--paraulogic-only` | Only include Paraulogic words | false |
| `--intersection` | Only words present in both sources | false |

### Output Format

```json
{"words": [["word1"], ["word2"], ["word3"]]}
```
