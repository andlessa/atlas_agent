import requests
from bs4 import BeautifulSoup
    
import re
import pymupdf  # PyMuPDF


TWIKI_URL = "https://twiki.cern.ch/twiki/bin/view/AtlasPublic"
MIDDLEWARE_URL = "https://atlaspo.cern.ch/public/twiki/middleware.php"

# The public datasets use ATLAS internal group codes (EXOT, HMBS, ...).
TARGET_GROUPS = {"EXOT", "HMBS"}
TARGET_ALIASES = {"EXO": "EXOT"}


def _extract_arxiv_id(link: str) -> str | None:
    # Supports links like /abs/2401.12345, /pdf/2401.12345.pdf, with optional version.
    m = re.search(r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5})(?:v\d+)?", link)
    if m:
        return m.group(1)
    m = re.search(r"([0-9]{4}\.[0-9]{4,5})(?:v\d+)?", link)
    if m:
        return m.group(1)
    return None


def _fetch_arxiv_abstract(arxiv_id: str) -> str:
    abs_url = f"https://arxiv.org/abs/{arxiv_id}"
    resp = requests.get(abs_url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    node = soup.select_one("blockquote.abstract")
    if not node:
        return ""
    text = node.get_text(" ", strip=True)
    return re.sub(r"^Abstract:\s*", "", text, flags=re.IGNORECASE).strip()


def _looks_like_equation_noise(line: str) -> bool:
    # Equations/captions are often symbol-heavy and not sentence-like prose.
    if len(line) < 8:
        return True

    alpha = sum(ch.isalpha() for ch in line)
    if alpha < 3:
        return True

    symbol_count = sum(ch in "=<>+-*/^_{}[]|\\~" for ch in line)
    if symbol_count >= 5 and alpha / max(len(line), 1) < 0.45:
        return True

    # Many isolated numbers/tokens are usually table or equation remnants.
    tokens = line.split()
    if tokens:
        non_wordy = sum(not re.search(r"[A-Za-z]{3,}", t) for t in tokens)
        if non_wordy / len(tokens) > 0.7 and len(line) < 140:
            return True

    return False


def _clean_pdf_text(text: str) -> str:
    text = text.replace("-\n", "")
    lines = [ln.strip() for ln in text.splitlines()]

    kept: list[str] = []
    for line in lines:
        if not line:
            continue
        if re.match(r"^arXiv:\S+", line, flags=re.IGNORECASE):
            continue
        if re.match(r"^CERN-[A-Z0-9-]+$", line):
            continue
        if re.match(r"^(Figure|Fig\.?|Table)\b", line, flags=re.IGNORECASE):
            continue
        if re.match(r"^\(?\d+\)?$", line):
            continue
        if "copyright" in line.lower() or "all rights reserved" in line.lower():
            continue
        if _looks_like_equation_noise(line):
            continue
        kept.append(line)

    # Merge consecutive lines into paragraph-like text for better model context.
    merged = "\n".join(kept)
    merged = re.sub(r"\n{3,}", "\n\n", merged)
    return merged.strip()


def _slice_relevant_sections(text: str) -> str:
    # Keep from introduction onward and trim references.
    start = 0
    m_start = re.search(r"\b(1\s*[\.:]?\s*Introduction|Introduction)\b", text, flags=re.IGNORECASE)
    if m_start:
        start = m_start.start()

    end = len(text)
    m_end = re.search(r"\b(References|Bibliography|Acknowledg(e)?ments?)\b", text, flags=re.IGNORECASE)
    if m_end and m_end.start() > start:
        end = m_end.start()

    return text[start:end].strip()


def _normalise_target_groups() -> set[str]:
    groups = set(TARGET_GROUPS)
    for group in list(groups):
        groups.add(TARGET_ALIASES.get(group, group))
    return groups


def _fetch_from_publications_api(seen_ids: set, groups_to_track: set[str]) -> list[dict]:
    # The middleware returns data only for browser-like requests.
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        ),
        "Origin": "https://atlaspo.cern.ch",
        "Referer": "https://atlaspo.cern.ch/public/twiki/publications/publications.html",
    }
    resp = requests.post(
        MIDDLEWARE_URL,
        data={"to_retrieve": "publications"},
        headers=headers,
        timeout=45,
    )
    resp.raise_for_status()
    records = resp.json()

    papers = []
    for row in records:
        lead_group = (row.get("lead_group") or "").strip().upper()
        other_groups = [g.strip().upper() for g in row.get("other_groups", []) if isinstance(g, str)]
        row_groups = {lead_group, *other_groups}
        matched_groups = row_groups & groups_to_track
        if not matched_groups:
            continue

        arxiv = row.get("arxiv") or {}
        link = arxiv.get("link") if isinstance(arxiv, dict) else ""
        if not link:
            continue

        paper_id = arxiv.get("alias") or row.get("ref_code")
        if not paper_id:
            continue
        if paper_id in seen_ids:
            continue

        title = row.get("public_short_title") or row.get("short_title") or row.get("full_title") or paper_id
        papers.append(
            {
                "group": sorted(matched_groups)[0],
                "title": title,
                "link": link,
                "id": paper_id,
            }
        )
    return papers

def fetch_new_papers(seen_ids: set) -> list[dict]:
    groups_to_track = _normalise_target_groups()

    # Primary path: consume the same publication dataset as the ATLAS DataTable.
    try:
        return _fetch_from_publications_api(seen_ids, groups_to_track)
    except (requests.RequestException, ValueError) as exc:
        print(f"Publications API failed ({exc}); falling back to TWiki scan.")

    # Fallback path: legacy HTML scan of TWiki content.
    resp = requests.get(TWIKI_URL, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    papers = []
    current_group = None

    for tag in soup.find_all(["h2", "h3", "a"]):
        if tag.name in ("h2", "h3"):
            text = tag.get_text(strip=True).upper()
            current_group = next((g for g in groups_to_track if g in text), None)

        if tag.name == "a" and current_group:
            href = tag.get("href", "")
            if "arxiv.org" in href or "Results_" in href:
                paper_id = href.split("/")[-1]
                if paper_id not in seen_ids:
                    papers.append(
                        {
                            "group": current_group,
                            "title": tag.get_text(strip=True),
                            "link": href,
                            "id": paper_id,
                        }
                    )
    return papers

def get_arxiv_pdf_text(link: str) -> str | None:
    arxiv_id = _extract_arxiv_id(link)
    if not arxiv_id:
        return None

    abstract = ""
    try:
        abstract = _fetch_arxiv_abstract(arxiv_id)
    except requests.RequestException:
        pass

    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
    resp = requests.get(pdf_url, timeout=60)
    resp.raise_for_status()

    # Extract text from PDF bytes
    doc = pymupdf.open(stream=resp.content, filetype="pdf")
    text_chunks: list[str] = []
    for page in doc:
        raw = page.get_text("text")
        text_chunks.append(raw if isinstance(raw, str) else "")
    text = "\n".join(text_chunks)
    cleaned = _clean_pdf_text(text)
    focused = _slice_relevant_sections(cleaned)

    chunks = []
    if abstract:
        chunks.append(f"Abstract: {abstract}")
    chunks.append(focused)
    # Keep a compact context window with high signal-to-noise.
    return "\n\n".join(chunks)[:18000]


import json, pathlib

STATE_FILE = pathlib.Path("seen_papers.json")

def load_seen() -> set:
    if STATE_FILE.exists():
        return set(json.loads(STATE_FILE.read_text()))
    return set()

def save_seen(seen: set):
    STATE_FILE.write_text(json.dumps(sorted(seen), indent=0))