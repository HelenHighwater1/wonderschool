#!/usr/bin/env python3
"""Quality-check scraped article .txt files in docs/."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

# Longer names first so "New York" wins over "York", "West Virginia" over "Virginia".
US_STATE_NAMES: tuple[str, ...] = (
    "District of Columbia",
    "North Carolina",
    "North Dakota",
    "South Carolina",
    "South Dakota",
    "West Virginia",
    "New Hampshire",
    "Rhode Island",
    "Connecticut",
    "Pennsylvania",
    "Massachusetts",
    "Mississippi",
    "California",
    "Washington",
    "New Jersey",
    "New Mexico",
    "Tennessee",
    "Wisconsin",
    "Maryland",
    "Minnesota",
    "Louisiana",
    "Kentucky",
    "Michigan",
    "Missouri",
    "Nebraska",
    "Oklahoma",
    "Arkansas",
    "Colorado",
    "Delaware",
    "Illinois",
    "Indiana",
    "Kansas",
    "Montana",
    "Nevada",
    "New York",
    "Ohio",
    "Oregon",
    "Texas",
    "Utah",
    "Virginia",
    "Alabama",
    "Alaska",
    "Arizona",
    "Florida",
    "Georgia",
    "Hawaii",
    "Idaho",
    "Iowa",
    "Maine",
    "Wyoming",
    "Vermont",
)

NAV_NOISE_PHRASES: tuple[str, ...] = (
    "find a child care program",
    "find child care",
    "start a childcare program",
    "start a child care program",
    "join us today",
    "subscribe to our newsletter",
    "sign up for our newsletter",
    "cookie policy",
    "privacy policy",
    "all rights reserved",
)

# Dollar amounts, ratios, square footage, hour counts
RE_DOLLAR = re.compile(
    r"(?:\$|USD\s*|usd\s*)\s*\d[\d,]*(?:\.\d+)?|\d[\d,]*(?:\.\d+)?\s*(?:dollars?|USD)\b",
    re.IGNORECASE,
)
RE_RATIO = re.compile(
    r"\b\d+\s*:\s*\d+\b|\b\d+\s+in\s+\d+\b|\b\d+\s*\/\s*\d+\b(?=\s*(?:ratio|mix|split))",
    re.IGNORECASE,
)
RE_PERCENT = re.compile(r"\b\d+(?:\.\d+)?\s*%\b")
RE_SQFT = re.compile(
    r"\b\d[\d,]*(?:\.\d+)?\s*(?:sq\.?\s*ft\.?|square\s+feet|sf\b)\b",
    re.IGNORECASE,
)
RE_HOURS = re.compile(
    r"\b\d[\d,]*(?:\.\d+)?\s*(?:-|–)?\s*(?:hour|hr)s?\b|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|\d+)[\s-]*(?:hour|hr)s?\b",
    re.IGNORECASE,
)


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def strip_header(raw: str) -> tuple[str, str]:
    """Remove SOURCE / DATE_SCRAPED header; return (body, notes about parse)."""
    lines = raw.splitlines()
    if not lines:
        return "", "empty file"
    i = 0
    if lines[i].startswith("SOURCE:"):
        i += 1
    if i < len(lines) and lines[i].startswith("DATE_SCRAPED:"):
        i += 1
    if i < len(lines) and lines[i].strip() == "":
        i += 1
    body = "\n".join(lines[i:]).strip()
    return body, ""


def word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def find_states(text: str) -> list[str]:
    """Match state names with word boundaries; longer names win (e.g. West Virginia vs Virginia)."""
    lower = text.lower()
    used: list[tuple[int, int]] = []
    found: set[str] = set()
    for state in sorted(US_STATE_NAMES, key=len, reverse=True):
        pat = re.compile(r"\b" + re.escape(state.lower()) + r"\b")
        for m in pat.finditer(lower):
            s, e = m.span()
            if any(not (e <= us or s >= ue) for us, ue in used):
                continue
            used.append((s, e))
            found.add(state)
    return sorted(found, key=lambda x: x.lower())


def has_specific_numbers(text: str) -> bool:
    """True if body has dollar-like amounts, ratios, percents, sq ft, or hour counts."""
    if RE_DOLLAR.search(text):
        return True
    if RE_RATIO.search(text):
        return True
    if RE_SQFT.search(text):
        return True
    if RE_HOURS.search(text):
        return True
    if RE_PERCENT.search(text):
        return True
    return False


def detect_noise(body: str) -> tuple[bool, list[str]]:
    """Return (is_noisy, note strings)."""
    notes: list[str] = []
    lower = body.lower()

    if re.search(r"\bclick\s+here\b", lower):
        notes.append('"click here"')

    high_signal_once = frozenset(
        {
            "find a child care program",
            "find child care",
            "subscribe to our newsletter",
            "sign up for our newsletter",
        }
    )
    for phrase in NAV_NOISE_PHRASES:
        if phrase not in lower:
            continue
        count = lower.count(phrase)
        if count >= 2 or phrase in high_signal_once:
            notes.append(f"nav/boilerplate ({count}×): {phrase[:48]}")

    # Dedupe note messages
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    line_counts = Counter(lines)
    repeated = [ln for ln, c in line_counts.items() if c >= 4 and len(ln) > 20]
    if repeated:
        notes.append(f"same line repeated ≥4× ({len(repeated)} distinct)")

    # Long repeated substring (nav/footer blocks)
    if len(body) > 200:
        chunk = 48
        seen: dict[str, int] = {}
        for i in range(0, len(body) - chunk, 12):
            frag = body[i : i + chunk].lower()
            if frag.strip() and len(frag.strip()) > 30:
                seen[frag] = seen.get(frag, 0) + 1
        dup_frags = [f for f, n in seen.items() if n >= 3]
        if dup_frags:
            notes.append("long substring repeated ≥3× (possible footer/nav block)")

    # Very high duplicate line ratio
    if len(lines) > 15:
        unique_ratio = len(set(lines)) / len(lines)
        if unique_ratio < 0.35:
            notes.append("low line diversity (possible boilerplate repetition)")

    is_noisy = len(notes) > 0
    return is_noisy, notes


def rate_quality(words: int, has_nums: bool, noisy: bool) -> str:
    if noisy:
        return "NOISY"
    if words < 300 or not has_nums:
        return "THIN"
    return "GOOD"


def main() -> None:
    docs = project_root() / "docs"
    txt_files = sorted(p for p in docs.glob("*.txt") if p.name != "failed_urls.txt")

    rows: list[tuple[str, int, str, str, str, str]] = []

    for path in txt_files:
        raw = path.read_text(encoding="utf-8", errors="replace")
        body, parse_note = strip_header(raw)
        words = word_count(body)
        states = find_states(body)
        has_nums = has_specific_numbers(body)
        noisy, noise_notes = detect_noise(body)
        quality = rate_quality(words, has_nums, noisy)

        states_cell = ", ".join(states) if states else "—"
        nums_cell = "True" if has_nums else "False"
        notes_parts: list[str] = []
        if parse_note:
            notes_parts.append(parse_note)
        if noise_notes:
            notes_parts.append("; ".join(noise_notes[:3]))
        if not has_nums and quality == "THIN" and not noisy:
            notes_parts.append("no dollar/ratio/sqft/hour patterns")
        notes_cell = "; ".join(notes_parts) if notes_parts else "—"

        rows.append(
            (
                path.name,
                words,
                quality,
                states_cell,
                nums_cell,
                notes_cell,
            )
        )

    # Markdown table
    print("| Filename | Words | Quality | States Mentioned | Has Numbers | Notes |")
    print("| --- | ---: | --- | --- | --- | --- |")
    for fn, w, q, st, hn, nt in rows:
        nt_esc = nt.replace("|", "\\|")
        st_esc = st.replace("|", "\\|")
        print(f"| {fn} | {w} | {q} | {st_esc} | {hn} | {nt_esc} |")

    thin_noisy = [(r[0], r[2], r[5]) for r in rows if r[2] in ("THIN", "NOISY")]
    print()
    print("## Files rated THIN or NOISY")
    print()
    if not thin_noisy:
        print("None — all files are GOOD.")
        return

    for fn, q, notes in thin_noisy:
        if q == "NOISY":
            rec = "**Re-scrape** after tightening selectors/removals, or **remove** if the source page embeds heavy global nav in the article container."
        elif q == "THIN":
            rec = "**Re-scrape** if the live page is longer/richer (possible empty selector); otherwise **remove** or merge if the topic is intentionally short."
        else:
            rec = ""
        print(f"- **{fn}** ({q}): {notes}")
        print(f"  - Recommendation: {rec}")
        print()


if __name__ == "__main__":
    main()
