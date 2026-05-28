"""Headless-краулер (Playwright) для SPA-сайтов вроде letovo.ru.

letovo.ru рендерит ссылки на PDF клиентским JavaScript-ом (файлы под /storage/), поэтому
статический краулер (app/crawl.py) их не видит. Здесь страницы рендерятся в headless-Chromium,
после чего из DOM собираются ссылки на PDF; сами файлы качаются обычным requests (дедуп по sha1).

Установка браузера: python -m playwright install chromium
Запуск:            python -m app.crawl_js            (по сидам/sitemap из .env)
                   python -m app.crawl_js --pages https://letovo.ru/o-shkole/svedenia-ob-obrazovatelnoy-organizacii
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.parse
from pathlib import Path

import requests

from .config import settings
from .crawl import (
    SOURCES_FILE,
    UA,
    _collect_sitemap,
    _host_allowed,
    _load_sources,
    _safe_pdf_name,
    _save_sources,
)

# Страницы, на которых обычно лежат документы школы (приоритет при ограничении max_pages).
_DOC_HINT = re.compile(
    r"document|sveden|svedenia|polozh|prikaz|reglament|programm|obrazovan|dokument|locnpa|prav|priem",
    re.I,
)


def _build_page_list(seeds: list[str], seed_hosts: set[str], use_sitemap: bool, verify_tls: bool) -> list[str]:
    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    pages: list[str] = list(seeds)
    if use_sitemap:
        seen: set[str] = set()
        for s in seeds:
            p = urllib.parse.urlparse(s)
            root = f"{p.scheme}://{p.netloc}"
            for page in _collect_sitemap(f"{root}/sitemap.xml", session, verify_tls, seen):
                if _host_allowed(urllib.parse.urlparse(page).hostname or "", seed_hosts):
                    pages.append(page)
    # дедуп с сохранением порядка, документные страницы — вперёд
    seen_u: set[str] = set()
    ordered = []
    for u in pages:
        u = urllib.parse.urldefrag(u)[0]
        if u not in seen_u:
            seen_u.add(u)
            ordered.append(u)
    ordered.sort(key=lambda u: 0 if _DOC_HINT.search(u) else 1)
    return ordered


def _download_pdf(url, session, docs_dir, by_sha, sources, downloaded, verify_tls) -> None:
    try:
        resp = session.get(url, timeout=40, verify=verify_tls)
    except requests.RequestException:
        return
    ctype = resp.headers.get("Content-Type", "").lower()
    if resp.status_code != 200 or not resp.content:
        return
    if "application/pdf" not in ctype and not url.lower().endswith(".pdf"):
        return
    if not resp.content[:5].startswith(b"%PDF"):
        return
    sha1 = hashlib.sha1(resp.content).hexdigest()
    if sha1 in by_sha:
        local = by_sha[sha1]
    else:
        local = _safe_pdf_name(url)
        target = docs_dir / local
        if target.exists():
            local = f"{target.stem}-{sha1[:8]}.pdf"
            target = docs_dir / local
        target.write_bytes(resp.content)
        by_sha[sha1] = local
        downloaded.append({"local_name": local, "source_url": url, "sha1": sha1})
    sources[local] = {"source_url": url, "sha1": sha1}


def crawl_js(
    seeds: list[str] | None = None,
    *,
    pages: list[str] | None = None,
    max_pages: int | None = None,
    delay: float | None = None,
    headless: bool = True,
    verify_tls: bool = True,
    use_sitemap: bool = True,
    docs_dir: Path | None = None,
    page_timeout: int = 45000,
) -> dict:
    from playwright.sync_api import sync_playwright

    seeds = seeds or settings.crawl_seeds
    max_pages = max_pages or settings.crawl_max_pages
    delay = settings.crawl_delay if delay is None else delay
    docs_dir = Path(docs_dir or settings.docs_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)
    seed_hosts = {urllib.parse.urlparse(s).hostname or "" for s in seeds}
    seed_hosts.discard("")

    page_list = pages or _build_page_list(seeds, seed_hosts, use_sitemap, verify_tls)
    page_list = page_list[:max_pages]

    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    by_sha: dict[str, str] = {}
    for fp in docs_dir.glob("*.pdf"):
        by_sha[hashlib.sha1(fp.read_bytes()).hexdigest()] = fp.name
    sources = _load_sources(docs_dir)

    pdf_urls: set[str] = set()
    rendered = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(ignore_https_errors=not verify_tls, user_agent=UA)
        page = ctx.new_page()
        page.on(
            "response",
            lambda r: pdf_urls.add(r.url) if r.url.lower().split("?")[0].endswith(".pdf") else None,
        )
        for url in page_list:
            if not _host_allowed(urllib.parse.urlparse(url).hostname or "", seed_hosts):
                continue
            try:
                page.goto(url, wait_until="networkidle", timeout=page_timeout)
                page.wait_for_timeout(1200)
                hrefs = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
            except Exception:
                continue
            rendered += 1
            for h in hrefs:
                hu = urllib.parse.urldefrag(h)[0]
                if hu.lower().endswith(".pdf") and _host_allowed(urllib.parse.urlparse(hu).hostname or "", seed_hosts):
                    pdf_urls.add(hu)
            time.sleep(delay)
        browser.close()

    pdf_urls = {u for u in pdf_urls if _host_allowed(urllib.parse.urlparse(u).hostname or "", seed_hosts)}
    downloaded: list[dict] = []
    for purl in sorted(pdf_urls):
        _download_pdf(purl, session, docs_dir, by_sha, sources, downloaded, verify_tls)
        time.sleep(delay)

    _save_sources(docs_dir, sources)
    return {
        "pages_rendered": rendered,
        "pdf_links_found": len(pdf_urls),
        "pdfs_total": len(by_sha),
        "pdfs_new": len(downloaded),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Headless (Playwright) crawler for SPA sites")
    parser.add_argument("--seeds", nargs="*", default=None)
    parser.add_argument("--pages", nargs="*", default=None, help="конкретные страницы для рендера (вместо sitemap)")
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--delay", type=float, default=None)
    parser.add_argument("--no-verify", action="store_true")
    parser.add_argument("--no-sitemap", action="store_true")
    parser.add_argument("--headed", action="store_true", help="видимый браузер (отладка)")
    args = parser.parse_args()
    summary = crawl_js(
        seeds=args.seeds,
        pages=args.pages,
        max_pages=args.max_pages,
        delay=args.delay,
        verify_tls=not args.no_verify,
        use_sitemap=not args.no_sitemap,
        headless=not args.headed,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
