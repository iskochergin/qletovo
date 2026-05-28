#!/usr/bin/env python
"""CLI: полная пересборка векторного индекса из data/docs.

Запуск:  python -m scripts.reindex   (из корня репозитория)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.indexer import reindex_all  # noqa: E402


def main() -> None:
    stats = reindex_all()
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
