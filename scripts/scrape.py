#!/usr/bin/env python3
"""Scrape Wonderschool blog articles and save clean text to docs/."""

from __future__ import annotations

import argparse
import re
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
SELECTORS = ("article", "main", ".post-content", ".entry-content", ".blog-content")
REMOVE_TAGS = ("nav", "header", "footer", "aside", "script", "style")
MIN_WORDS_OK = 200
REQUEST_DELAY_SEC = 1.5

# Lines containing any of these substrings (case-insensitive) are dropped after extract.
BOILERPLATE_LINE_PHRASES: tuple[str, ...] = (
    "Find a child care program",
    "find child care",
    "click here",
    "If you're a provider, create a listing",
    "Find a child care program that meets your needs",
)

# State-specific licensing articles. These go into docs/ and are indexed by embed.py.
LICENSING_URLS = [
    "https://www.wonderschool.com/blog/child-care-provider-resources/family-child-care-licensing-in-california",
    "https://www.wonderschool.com/blog/child-care-provider-resources/types-of-child-care-licenses-in-california",
    "https://www.wonderschool.com/blog/child-care-provider-resources/family-child-care-licensing-process-in-california",
    "https://www.wonderschool.com/blog/child-care-provider-resources/family-child-care-licensing-eligibility-in-california",
    "https://www.wonderschool.com/blog/child-care-provider-resources/family-child-care-licensing-training-requirements-in-california",
    "https://www.wonderschool.com/blog/child-care-provider-resources/family-child-care-licensing-home-requirements-in-california",
    "https://www.wonderschool.com/blog/child-care-provider-resources/texas-family-child-care-licensing-an-overview",
    "https://www.wonderschool.com/blog/child-care-provider-resources/texas-family-child-care-licensing-types-of-licenses",
    "https://www.wonderschool.com/blog/child-care-provider-resources/texas-family-child-care-licensing-licensing-process",
    "https://www.wonderschool.com/blog/child-care-provider-resources/texas-family-child-care-licensing-eligibility",
    "https://www.wonderschool.com/blog/child-care-provider-resources/texas-family-child-care-licensing-training-requirements",
    "https://www.wonderschool.com/blog/child-care-provider-resources/texas-family-child-care-licensing-home-requirements",
    "https://www.wonderschool.com/blog/child-care-provider-resources/new-york-state-child-care-licensing",
    "https://www.wonderschool.com/blog/child-care-provider-resources/new-york-family-child-care-licensing-licensing-process",
    "https://www.wonderschool.com/blog/child-care-provider-resources/new-york-family-child-care-licensing-eligibility",
    "https://www.wonderschool.com/blog/child-care-provider-resources/washington-family-child-care-licensing-types-of-licenses",
    "https://www.wonderschool.com/blog/child-care-provider-resources/washington-state-family-child-care-licensing-licensing-process",
    "https://cms.wonderschool.com/p/child-care-provider-resources/how-to-get-your-florida-child-care-license-the-wonderschool-guide/",
    "https://www.wonderschool.com/blog/child-care-provider-resources/4-steps-to-get-your-family-child-care-license-in-maryland",
    "https://www.wonderschool.com/blog/child-care-provider-resources/5-steps-to-getting-your-north-carolina-family-child-care-license",
]

# Universal business topics (LLC, pricing, zoning). Saved to docs/business/ for reference,
# intentionally NOT indexed by embed.py — see DECISIONS.md ("Business content handled via
# system prompt knowledge, not RAG").
BUSINESS_URLS = [
    "https://www.wonderschool.com/blog/child-care-provider-resources/sole-proprietorship-or-an-llc-for-your-family-child-care-business",
    "https://www.wonderschool.com/blog/child-care-provider-resources/business-license-zoning-permit-family-child-care",
    "https://www.wonderschool.com/blog/child-care-provider-resources/secure-child-care-space",
    "https://www.wonderschool.com/blog/child-care-provider-resources/tuition-pricing-strategies-for-in-home-child-care",
    "https://www.wonderschool.com/blog/child-care-provider-resources/child-care-business-earnings-calculator",
    "https://www.wonderschool.com/blog/child-care-provider-resources/child-care-cost",
]


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def url_slug(url: str) -> str:
    path = urlparse(url).path.strip("/")
    if not path:
        return "index"
    return path.split("/")[-1] or "index"


def word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def extract_clean_text_from_element(element) -> str:
    """Parse a copy of the element, strip unwanted nodes, return normalized text."""
    frag = BeautifulSoup(str(element), "html.parser")
    root = frag.find(True)
    if root is None:
        return ""

    for name in REMOVE_TAGS:
        for t in root.find_all(name):
            t.decompose()
    for t in root.select(".cta, .sidebar"):
        t.decompose()

    text = root.get_text(separator="\n")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    collapsed = "\n".join(lines)
    collapsed = re.sub(r"[ \t]+", " ", collapsed)
    return collapsed.strip()


def strip_series_intro_lines(text: str) -> str:
    """Line-based fallback: drop the series intro line and the sibling-link titles that follow."""
    if not text or "this post is a part of our series" not in text.lower():
        return text
    lines = text.split("\n")
    out: list[str] = []
    skipping = False
    drops = 0
    for line in lines:
        if not skipping and "this post is a part of our series" in line.lower():
            skipping = True
            drops = 0
            continue
        if skipping:
            stripped = line.strip()
            n_words = len(stripped.split())
            ends_term = bool(stripped) and stripped[-1] in {".", "?", "!", ":"}
            looks_like_title_link = (
                drops < 12
                and stripped
                and not ends_term
                and n_words < 10
                and len(stripped) < 80
            )
            if looks_like_title_link:
                drops += 1
                continue
            skipping = False
        out.append(line)
    return "\n".join(out)


def strip_trailing_nav(text: str) -> str:
    """Drop the sitewide footer block that follows every article.

    Wonderschool articles end with a fixed sequence of nav-style headings
    ("Join Wonderschool Today", "Sign Up", "Related Content", ...) followed by
    a list of unrelated sibling-article titles. That block was polluting
    retrieval (every doc ended up containing every other doc's keywords).
    Cut everything from the first such heading to EOF.
    """
    if not text:
        return text
    triggers = ("join wonderschool today", "related content")
    out: list[str] = []
    for line in text.split("\n"):
        if line.strip().lower() in triggers:
            break
        out.append(line)
    return "\n".join(out).rstrip()


def strip_boilerplate_lines(text: str) -> str:
    """Remove any line that contains a known sitewide CTA phrase (case-insensitive)."""
    if not text:
        return text
    needles = tuple(p.lower() for p in BOILERPLATE_LINE_PHRASES)
    kept: list[str] = []
    for line in text.split("\n"):
        low = line.lower()
        if any(n in low for n in needles):
            continue
        kept.append(line)
    out = "\n".join(kept).strip()
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out


def pick_main_element(soup: BeautifulSoup):
    """Try selectors in order until one yields meaningful text."""
    for sel in SELECTORS:
        el = soup.select_one(sel)
        if el is None:
            continue
        preview = extract_clean_text_from_element(el)
        if word_count(preview) >= 10:
            return el
    body = soup.body
    if body is not None:
        return body
    return soup


def fetch_html(url: str) -> tuple[str | None, str | None]:
    """Return (html, None) on success, or (None, error_reason) on failure."""
    headers = {"User-Agent": USER_AGENT}
    try:
        r = requests.get(url, headers=headers, timeout=60)
        if not r.ok:
            return None, f"HTTP_{r.status_code}"
        return r.text, None
    except requests.RequestException as e:
        return None, f"REQUEST_FAILED ({e.__class__.__name__})"


def log_failed(docs_dir: Path, url: str, reason: str) -> None:
    path = docs_dir / "failed_urls.txt"
    line = f"{url}\t{reason}\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(line)


def write_article(docs_dir: Path, slug: str, url: str, body: str, scraped_on: str) -> Path:
    out = docs_dir / f"{slug}.txt"
    header = f"SOURCE: {url}\nDATE_SCRAPED: {scraped_on}\n\n"
    out.write_text(header + body + "\n", encoding="utf-8")
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Scrape Wonderschool articles into docs/.")
    p.add_argument(
        "--append",
        action="store_true",
        help="Do not overwrite existing .txt files; append failures to failed_urls.txt",
    )
    p.add_argument(
        "urls",
        nargs="*",
        help="URLs to scrape (default: built-in licensing + business lists)",
    )
    return p.parse_args()


def scrape_one(
    url: str, out_dir: Path, docs_dir: Path, scraped_on: str, append_mode: bool
) -> tuple[str, int, str]:
    """Fetch + clean a single URL into out_dir; return (filename, word_count, status)."""
    slug = url_slug(url)
    filename = f"{slug}.txt"
    out_path = out_dir / filename

    if append_mode and out_path.exists():
        existing = out_path.read_text(encoding="utf-8")
        parts = existing.split("\n\n", 1)
        wc_existing = word_count(parts[1]) if len(parts) > 1 else 0
        return filename, wc_existing, "SKIPPED"

    html, fetch_err = fetch_html(url)
    if html is None:
        log_failed(docs_dir, url, fetch_err or "REQUEST_FAILED")
        return filename, 0, "FAILED"

    soup = BeautifulSoup(html, "html.parser")
    main_el = pick_main_element(soup)
    body = extract_clean_text_from_element(main_el)
    body = strip_series_intro_lines(body)
    body = strip_trailing_nav(body)
    body = strip_boilerplate_lines(body)
    wc = word_count(body)

    if wc < MIN_WORDS_OK:
        log_failed(docs_dir, url, f"TOO_SHORT ({wc} words)")
        status = "TOO SHORT"
    else:
        status = "OK"

    out_dir.mkdir(parents=True, exist_ok=True)
    write_article(out_dir, slug, url, body, scraped_on)
    return filename, wc, status


def main() -> None:
    args = parse_args()
    append_mode = args.append

    root = project_root()
    docs_dir = root / "docs"
    business_dir = docs_dir / "business"
    docs_dir.mkdir(parents=True, exist_ok=True)

    if args.urls:
        # Custom URLs all land in docs/ (caller's choice). Don't touch the failed log.
        jobs: list[tuple[str, Path]] = [(u, docs_dir) for u in args.urls]
        reset_failed_log = False
    else:
        jobs = [(u, docs_dir) for u in LICENSING_URLS]
        jobs += [(u, business_dir) for u in BUSINESS_URLS]
        reset_failed_log = True

    failed_path = docs_dir / "failed_urls.txt"
    if reset_failed_log and failed_path.exists():
        failed_path.unlink()

    scraped_on = date.today().isoformat()
    rows: list[tuple[str, str, int, str]] = []

    for i, (url, out_dir) in enumerate(jobs):
        if i > 0:
            time.sleep(REQUEST_DELAY_SEC)
        filename, wc, status = scrape_one(url, out_dir, docs_dir, scraped_on, append_mode)
        bucket = out_dir.relative_to(docs_dir.parent).as_posix()
        rows.append((bucket, filename, wc, status))

    # Summary table
    col_b = max((len(r[0]) for r in rows), default=4)
    col_f = max((len(r[1]) for r in rows), default=8)
    header = f"{'Bucket':<{col_b}} | {'Filename':<{col_f}} | {'Word Count':>10} | Status"
    sep = "-" * len(header)
    print(header)
    print(sep)
    for bucket, fn, wc, st in rows:
        print(f"{bucket:<{col_b}} | {fn:<{col_f}} | {wc:>10} | {st}")


if __name__ == "__main__":
    main()
