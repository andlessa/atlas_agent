import requests
from bs4 import BeautifulSoup
    
import re, io
import fitz  # PyMuPDF


TWIKI_URL = "https://twiki.cern.ch/twiki/bin/view/AtlasPublic"
TARGET_GROUPS = {"EXO", "HMBS"}

def fetch_new_papers(seen_ids: set) -> list[dict]:
    resp = requests.get(TWIKI_URL, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    papers = []
    current_group = None

    for tag in soup.find_all(["h2", "h3", "a"]):
        # Detect group headings
        if tag.name in ("h2", "h3"):
            text = tag.get_text(strip=True)
            current_group = next((g for g in TARGET_GROUPS if g in text), None)

        # Collect paper links under the right groups
        if tag.name == "a" and current_group:
            href = tag.get("href", "")
            if "arxiv.org" in href or "Results_" in href:
                paper_id = href.split("/")[-1]
                if paper_id not in seen_ids:
                    papers.append({
                        "group": current_group,
                        "title": tag.get_text(strip=True),
                        "link": href,
                        "id": paper_id,
                    })
    return papers

def get_arxiv_pdf_text(link: str) -> str | None:
    # Normalise to arXiv abstract page, e.g. https://arxiv.org/abs/2401.12345
    arxiv_id = re.search(r"(\d{4}\.\d{4,5})", link)
    if not arxiv_id:
        return None

    pdf_url = f"https://arxiv.org/pdf/{arxiv_id.group(1)}"
    resp = requests.get(pdf_url, timeout=60)
    resp.raise_for_status()

    # Extract text from PDF bytes
    doc = fitz.open(stream=resp.content, filetype="pdf")
    text = "\n".join(page.get_text() for page in doc)
    return text[:12000]  # keep first ~12k chars — enough for intro + results    


import json, pathlib

STATE_FILE = pathlib.Path("seen_papers.json")

def load_seen() -> set:
    if STATE_FILE.exists():
        return set(json.loads(STATE_FILE.read_text()))
    return set()

def save_seen(seen: set):
    STATE_FILE.write_text(json.dumps(list(seen)))