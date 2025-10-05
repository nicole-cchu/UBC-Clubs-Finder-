"""
Scrape clubs from the AMS directory and write clubs.json for the HTML.

Usage:
  pip install requests beautifulsoup4
  python scrape_amsclubs.py

Notes:
- Be gentle (there's a small delay between requests).
- This is a best-effort scraper; AMS markup may change.
- Check site policies before scraping in production.
"""
from __future__ import annotations
import json, re, time, datetime, itertools
from typing import List, Dict, Set
import requests
from bs4 import BeautifulSoup

BASE = "https://amsclubs.ca"
LIST = f"{BASE}/all-clubs/"
HEADERS = {
    "User-Agent": "UBC-Club-Indexer/1.0 (+educational demo)"
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)

def get_soup(url: str) -> BeautifulSoup:
    r = SESSION.get(url, timeout=20)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")

def find_club_links(soup):
    """
    On the list page, each card is an <a> whose text ends with 'Discover'.
    Grab those hrefs (normalize to absolute).
    """
    hrefs = set()
    for a in soup.find_all("a", href=True):
        txt = (a.get_text(" ", strip=True) or "")
        if "Discover" in txt:               # key signal on list cards
            href = a["href"]
            if href.startswith("/"):
                href = BASE + href
            # keep only site-internal, clean URL (no fragments)
            if href.startswith(BASE):
                hrefs.add(href.split("#", 1)[0])
    return sorted(hrefs)

def extract_name_from_detail(soup: BeautifulSoup) -> str:
    for tag in ("h1","h2","h3"):
        h = soup.find(tag)
        if h and h.get_text(strip=True):
            return h.get_text(strip=True)
    title = soup.find("title")
    if title:
        return re.sub(r"\s*–.*$", "", title.get_text(strip=True))
    return ""

def extract_description_from_detail(soup: BeautifulSoup) -> str:
    # Try meta description first
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        return meta["content"].strip()
    # Then the first meaningful paragraph
    for p in soup.find_all("p"):
        txt = p.get_text(" ", strip=True)
        if txt and len(txt) > 30:
            return txt
    # Fallback: any short text block
    for p in soup.find_all(["p","div","li"]):
        txt = p.get_text(" ", strip=True)
        if txt and len(txt) > 10:
            return txt
    return ""

CATEGORIES = ["Athletic","Service","Cultural","Recreational","Business","Technology","Sciences","Other"]

def guess_category(name: str, desc: str, url: str) -> str:
    t = f"{name} {desc} {url}".lower()

    if any(k in t for k in ["finance","business","consult","entrepreneur","commerce","sauder","marketing"]):
        return "Business"
    if any(k in t for k in ["code","program","developer","software","product management","pm club","data","ai","ml","robot","hackathon","tech"]):
        return "Technology"
    if any(k in t for k in ["biology","physics","chemistry","science","research","neuroscience","math","kinesiology","geology","astronomy","statistics","biochem"]):
        return "Sciences"
    if any(k in t for k in ["sport","athletic","soccer","basketball","hockey","climb","martial","yoga","dance","run","rowing","tennis","badminton","swim","ultimate","volleyball","taekwondo","muay thai"]):
        return "Athletic"
    if any(k in t for k in ["volunteer","service","outreach","charity","non-profit","fundrais","community","brigade","ems","first aid"]):
        return "Service"
    if any(k in t for k in ["culture","cultural","chinese","korean","japanese","indian","persian","filipino","vietnamese","latino","hispanic","african","arab","jewish","islamic","sikh"]):
        return "Cultural"
    if any(k in t for k in ["game","gaming","board game","anime","film","photography","recreation","outdoor","hiking","improv","music","radio","theatre","clubhouse","tabletop"]):
        return "Recreational"
    return "Other"

def parse_detail(url: str) -> Dict[str,str]:
    try:
        soup = get_soup(url)
    except Exception:
        return {"name":"", "description":"", "category":"Other"}
    name = extract_name_from_detail(soup)
    desc = extract_description_from_detail(soup)
    cat = guess_category(name, desc, url)
    return {"name": name, "description": desc, "category": cat}


def iterate_pages(max_pages: int = 50):
    """
    Walk /all-clubs/ then /all-clubs/pagenum/2,3,... until a page has no cards.
    """
    import itertools, requests
    for p in itertools.count(start=1):
        if p > max_pages:
            break
        url = LIST if p == 1 else f"{BASE}/all-clubs/pagenum/{p}/"
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code == 404:
                break
            r.raise_for_status()
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                break
            raise
        soup = BeautifulSoup(r.text, "html.parser")
        links = find_club_links(soup)
        print(f"Page {p}: found {len(links)} links")
        if not links:
            break
        yield p, links

def main():
    seen: Set[str] = set()
    clubs: List[Dict[str,str]] = []

    print("Scanning AMS directory pages…")
    for page_num, links in iterate_pages():
        print(f"Page {page_num}: {len(links)} links")
        new_links = [u for u in links if u not in seen]
        if not new_links and page_num > 1:
            break
        for url in new_links:
            seen.add(url)
            detail = parse_detail(url)
            name = detail.get("name","").strip()
            if not name:
                continue
            clubs.append({
                "name": name,
                "category": detail.get("category","Other"),
                "description": detail.get("description","").strip(),
                "url": url
            })
            time.sleep(0.5)  # be polite

    # Sort by category, then name
    clubs.sort(key=lambda c: (CATEGORIES.index(c.get("category","Other")) if c.get("category","Other") in CATEGORIES else len(CATEGORIES), c.get("name","")))

    payload = {
        "generated_from": LIST,
        "generated_at": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "clubs": clubs
    }

    with open("clubs.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(clubs)} clubs to clubs.json")

if __name__ == "__main__":
    main()
