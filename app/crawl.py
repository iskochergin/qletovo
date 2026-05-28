"""Вежливый краулер: обходит letovo.ru / qletovo.ru, скачивает PDF + метаданные.

- rate-limit между запросами (CRAWL_DELAY), без параллельного DDoS;
- BFS в пределах хоста сидов (и поддоменов letovo.ru);
- дедуп по sha1 содержимого;
- метаданные (source_url, заголовок ссылки) пишутся в data/docs/_sources.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.robotparser
import xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from .config import settings

UA = "LetovoDocsBot/1.0 (+internal school docs indexer)"
SOURCES_FILE = "_sources.json"


def _collect_sitemap(url: str, session: requests.Session, verify: bool, seen: set[str], depth: int = 0) -> list[str]:
    """Возвращает список URL страниц из sitemap.xml (раскрывая вложенные sitemap-индексы).

    Сайты-SPA (как letovo.ru) почти не дают ссылок в HTML, но публикуют sitemap.xml — это
    корректный и вежливый способ обнаружить все страницы и PDF-документы.
    """
    if depth > 3 or url in seen:
        return []
    seen.add(url)
    pages: list[str] = []
    try:
        resp = session.get(url, timeout=20, verify=verify)
        if resp.status_code != 200:
            return []
        root = ET.fromstring(resp.content)
    except Exception:
        return []
    for loc in root.iter():
        if not loc.tag.lower().endswith("loc") or not (loc.text or "").strip():
            continue
        target = loc.text.strip()
        if target.lower().endswith(".xml"):  # вложенный sitemap
            pages.extend(_collect_sitemap(target, session, verify, seen, depth + 1))
        else:
            pages.append(target)
    return pages


def _host_allowed(host: str, seed_hosts: set[str]) -> bool:
    host = host.lower()
    for sh in seed_hosts:
        if host == sh or host.endswith("." + sh) or sh.endswith("." + host):
            return True
        # letovo.ru ↔ www.letovo.ru ↔ qletovo.ru считаем «своими» по суффиксу letovo.ru
        if host.endswith("letovo.ru") and sh.endswith("letovo.ru"):
            return True
    return False


def _safe_pdf_name(url: str) -> str:
    path = urllib.parse.urlparse(url).path
    name = urllib.parse.unquote(Path(path).name) or "document.pdf"
    name = unicodedata.normalize("NFC", name)
    name = re.sub(r"[\\/:*?\"<>|]+", "_", name).strip()
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name


def _load_sources(docs_dir: Path) -> dict:
    fp = docs_dir / SOURCES_FILE
    if fp.exists():
        try:
            return json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_sources(docs_dir: Path, data: dict) -> None:
    (docs_dir / SOURCES_FILE).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def crawl(
    seeds: list[str] | None = None,
    *,
    max_pages: int | None = None,
    delay: float | None = None,
    verify_tls: bool = True,
    use_sitemap: bool = True,
    docs_dir: Path | None = None,
) -> dict:
    seeds = seeds or settings.crawl_seeds
    max_pages = max_pages or settings.crawl_max_pages
    delay = settings.crawl_delay if delay is None else delay
    docs_dir = Path(docs_dir or settings.docs_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)

    seed_hosts = {urllib.parse.urlparse(s).hostname or "" for s in seeds}
    seed_hosts.discard("")

    robots: dict[str, urllib.robotparser.RobotFileParser] = {}

    def can_fetch(url: str) -> bool:
        parsed = urllib.parse.urlparse(url)
        root = f"{parsed.scheme}://{parsed.netloc}"
        rp = robots.get(root)
        if rp is None:
            rp = urllib.robotparser.RobotFileParser()
            try:
                resp = requests.get(root + "/robots.txt", headers={"User-Agent": UA}, timeout=10, verify=verify_tls)
                rp.parse(resp.text.splitlines() if resp.status_code == 200 else [])
            except Exception:
                rp.parse([])
            robots[root] = rp
        try:
            return rp.can_fetch(UA, url)
        except Exception:
            return True

    session = requests.Session()
    session.headers.update({"User-Agent": UA})

    queue: deque[str] = deque(seeds)
    # Засеять очередь страницами из sitemap.xml (важно для SPA-сайтов вроде letovo.ru).
    if use_sitemap:
        sm_seen: set[str] = set()
        for s in seeds:
            p = urllib.parse.urlparse(s)
            root = f"{p.scheme}://{p.netloc}"
            for page in _collect_sitemap(f"{root}/sitemap.xml", session, verify_tls, sm_seen):
                if _host_allowed(urllib.parse.urlparse(page).hostname or "", seed_hosts):
                    queue.append(page)

    seen_urls: set[str] = set()
    by_sha: dict[str, str] = {}
    sources = _load_sources(docs_dir)
    # предзаполнить дедуп существующими файлами
    for fp in docs_dir.glob("*.pdf"):
        by_sha[hashlib.sha1(fp.read_bytes()).hexdigest()] = fp.name

    downloaded: list[dict] = []
    visited_pages = 0

    while queue and visited_pages < max_pages:
        url = queue.popleft()
        url, _frag = urllib.parse.urldefrag(url)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        host = urllib.parse.urlparse(url).hostname or ""
        if not _host_allowed(host, seed_hosts):
            continue
        if not can_fetch(url):
            continue

        try:
            resp = session.get(url, timeout=20, verify=verify_tls, allow_redirects=True)
        except requests.RequestException:
            continue
        time.sleep(delay)
        visited_pages += 1

        ctype = resp.headers.get("Content-Type", "").lower()
        is_pdf = "application/pdf" in ctype or url.lower().endswith(".pdf")

        if is_pdf and resp.status_code == 200 and resp.content:
            sha1 = hashlib.sha1(resp.content).hexdigest()
            if sha1 in by_sha:
                local = by_sha[sha1]
            else:
                local = _safe_pdf_name(url)
                target = docs_dir / local
                if target.exists():  # имя занято другим содержимым
                    local = f"{target.stem}-{sha1[:8]}.pdf"
                    target = docs_dir / local
                target.write_bytes(resp.content)
                by_sha[sha1] = local
                downloaded.append({"local_name": local, "source_url": url, "sha1": sha1})
            sources[local] = {"source_url": url, "sha1": sha1}
            continue

        if "text/html" not in ctype:
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=True):
            link = urllib.parse.urljoin(url, a["href"].strip())
            link, _ = urllib.parse.urldefrag(link)
            p = urllib.parse.urlparse(link)
            if p.scheme not in {"http", "https"}:
                continue
            if link not in seen_urls and _host_allowed(p.hostname or "", seed_hosts):
                queue.append(link)
            # запомним заголовок ссылки на PDF как кандидат source title
            if link.lower().endswith(".pdf"):
                txt = a.get_text(strip=True)
                if txt:
                    sources.setdefault(_safe_pdf_name(link), {})["link_text"] = txt[:200]

    _save_sources(docs_dir, sources)
    return {
        "pages_visited": visited_pages,
        "pdfs_total": len(by_sha),
        "pdfs_new": len(downloaded),
        "new": downloaded,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl letovo.ru/qletovo.ru for PDFs")
    parser.add_argument("--seeds", nargs="*", default=None)
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--delay", type=float, default=None)
    parser.add_argument("--no-verify", action="store_true", help="отключить проверку TLS (для self-signed qletovo.ru)")
    parser.add_argument("--no-sitemap", action="store_true", help="не засевать очередь из sitemap.xml")
    args = parser.parse_args()
    summary = crawl(
        seeds=args.seeds,
        max_pages=args.max_pages,
        delay=args.delay,
        verify_tls=not args.no_verify,
        use_sitemap=not args.no_sitemap,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
