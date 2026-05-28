#!/usr/bin/env python
"""Регидратация корпуса PDF из data/docs/_sources.json (без браузера).

`_sources.json` (создаётся краулером) хранит карту имя_файла -> {source_url, sha1}. Этот скрипт
скачивает все PDF по их source_url — удобно на сервере, где тяжёлый набор PDF не хранится в git,
но нужно восстановить корпус. После — запустите `python -m scripts.reindex`.

Запуск:  python -m scripts.fetch_sources [--no-verify]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.crawl import UA  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-verify", action="store_true")
    parser.add_argument("--delay", type=float, default=0.2)
    args = parser.parse_args()

    docs_dir = Path(settings.docs_dir)
    sources_path = docs_dir / "_sources.json"
    if not sources_path.exists():
        print("Нет data/docs/_sources.json — нечего регидрировать.")
        return
    sources = json.loads(sources_path.read_text(encoding="utf-8"))
    session = requests.Session()
    session.headers.update({"User-Agent": UA})

    fetched = skipped = failed = 0
    for local_name, meta in sources.items():
        url = (meta or {}).get("source_url")
        if not url:
            continue
        target = docs_dir / local_name
        if target.exists():
            skipped += 1
            continue
        try:
            resp = session.get(url, timeout=40, verify=not args.no_verify)
            if resp.status_code == 200 and resp.content[:5].startswith(b"%PDF"):
                target.write_bytes(resp.content)
                want = (meta or {}).get("sha1")
                got = hashlib.sha1(resp.content).hexdigest()
                fetched += 1
                if want and want != got:
                    print(f"  [warn] sha1 изменился: {local_name}")
            else:
                failed += 1
        except requests.RequestException:
            failed += 1
        time.sleep(args.delay)

    print(json.dumps({"fetched": fetched, "skipped_existing": skipped, "failed": failed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
