#!/usr/bin/env python
"""Прогон контрольного набора и проверка метрик раздела 5 ТЗ.

Метрики и пороги:
  - точность ответов               >= 0.85
  - доля ответов с валидной ссылкой >= 0.95   (среди отвеченных, не отказов)
  - средняя задержка                <= 20 c
  - галлюцинации на «нет данных»     == 0      (контрольные вопросы должны давать отказ)

Запуск (из корня репозитория):
  python -m eval.run                 # in-process (бэкенд импортируется, сервер не нужен)
  python -m eval.run --api http://127.0.0.1:8765   # через HTTP API
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.prompts import NO_DATA, OFF_TOPIC  # noqa: E402

LINK_RE = re.compile(r"^https?://.+/files/.+#page=\d+$")

ACC_THRESHOLD = 0.85
LINK_THRESHOLD = 0.95
LATENCY_THRESHOLD = 20.0


def valid_link(url: str) -> bool:
    return bool(url) and bool(LINK_RE.match(url))


def is_refusal_text(text: str) -> bool:
    t = (text or "").strip()
    return t == NO_DATA or t == OFF_TOPIC


def make_asker(api: str | None):
    base = "https://qletovo.ru"
    if api:
        import requests

        def ask(q: str) -> dict:
            r = requests.post(api.rstrip("/") + "/query", json={"question": q}, timeout=90)
            r.raise_for_status()
            return r.json()

        return ask, (api or base)

    from app.config import settings
    from app.rag import answer_question

    base = settings.public_base_url or base

    def ask(q: str) -> dict:
        return answer_question(q, base)

    return ask, base


def grade(item: dict, resp: dict) -> tuple[bool, str]:
    typ = item["type"]
    status = resp.get("status")
    answer = (resp.get("answer") or "").strip()
    sources = resp.get("sources") or []

    if typ == "answerable":
        if status != "answerable":
            return False, f"ожидался ответ, получили {status}"
        low = answer.lower()
        if not any(s.lower() in low for s in item.get("expect_any", [])):
            return False, "нет ожидаемых ключевых слов"
        exp_doc = item.get("expect_doc")
        if exp_doc and not any(exp_doc.lower() in (s.get("title") or "").lower() for s in sources):
            return False, f"нет источника с '{exp_doc}'"
        if not any(valid_link(s.get("url", "")) for s in sources):
            return False, "нет валидной ссылки"
        return True, "ok"

    if typ == "refuse_nodata":
        if status == "not_found" and answer == NO_DATA:
            return True, "ok (отказ)"
        return False, f"должен был отказать (NO_DATA), получили {status}"

    if typ == "refuse_offtopic":
        if status in {"off_topic", "not_found"} and is_refusal_text(answer):
            return True, "ok (отказ)"
        return False, f"должен был отказать, получили {status}"

    return False, f"неизвестный тип {typ}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default=None, help="URL бэкенда; без него — in-process")
    parser.add_argument("--questions", default=str(Path(__file__).parent / "questions.yaml"))
    args = parser.parse_args()

    items = yaml.safe_load(Path(args.questions).read_text(encoding="utf-8"))
    ask, base = make_asker(args.api)

    results = []
    latencies = []
    for item in items:
        t0 = time.time()
        try:
            resp = ask(item["q"])
        except Exception as exc:  # noqa: BLE001
            resp = {"status": "error", "answer": f"ERROR: {exc}", "sources": []}
        dt = time.time() - t0
        latencies.append(dt)
        ok, note = grade(item, resp)
        results.append((item, resp, ok, note, dt))

    total = len(results)
    correct = sum(1 for r in results if r[2])

    answered = [r for r in results if r[1].get("status") == "answerable"]
    answered_with_link = [r for r in answered if any(valid_link(s.get("url", "")) for s in r[1].get("sources") or [])]
    nodata = [r for r in results if r[0]["type"] == "refuse_nodata"]
    hallucinations = [r for r in nodata if r[1].get("status") == "answerable"]
    offtopic = [r for r in results if r[0]["type"] == "refuse_offtopic"]
    offtopic_leak = [r for r in offtopic if r[1].get("status") == "answerable"]

    accuracy = correct / total if total else 0.0
    link_share = (len(answered_with_link) / len(answered)) if answered else 1.0
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    max_latency = max(latencies) if latencies else 0.0

    print(f"\nРежим: {'HTTP ' + args.api if args.api else 'in-process'} | base={base}\n")
    print(f"{'СТАТУС':<11} {'OK':<3} {'t,с':>5}  ВОПРОС")
    print("-" * 78)
    for item, resp, ok, note, dt in results:
        mark = "✓" if ok else "✗"
        print(f"{resp.get('status',''):<11} {mark:<3} {dt:>5.1f}  {item['q'][:46]}")
        if not ok:
            print(f"            └─ {note} | ответ: {(resp.get('answer') or '')[:70]}")

    print("\n" + "=" * 78)
    print("МЕТРИКИ")
    print("=" * 78)

    def line(name, value, ok):
        print(f"  {'✓' if ok else '✗'} {name:<46} {value}")

    acc_ok = accuracy >= ACC_THRESHOLD
    link_ok = link_share >= LINK_THRESHOLD
    lat_ok = avg_latency <= LATENCY_THRESHOLD
    hall_ok = len(hallucinations) == 0

    line(f"Точность (>= {ACC_THRESHOLD:.0%})", f"{accuracy:.0%}  ({correct}/{total})", acc_ok)
    line(f"Доля ответов с валидной ссылкой (>= {LINK_THRESHOLD:.0%})",
         f"{link_share:.0%}  ({len(answered_with_link)}/{len(answered)})", link_ok)
    line(f"Средняя задержка (<= {LATENCY_THRESHOLD:.0f}с)", f"{avg_latency:.1f}с  (макс {max_latency:.1f}с)", lat_ok)
    line("Галлюцинации на «нет данных» (== 0)", f"{len(hallucinations)}", hall_ok)
    print(f"  · отказ на off-topic: {len(offtopic) - len(offtopic_leak)}/{len(offtopic)} (утечек: {len(offtopic_leak)})")

    all_ok = acc_ok and link_ok and lat_ok and hall_ok
    print("\n" + ("РЕЗУЛЬТАТ: ВСЕ МЕТРИКИ ДОСТИГНУТЫ ✓" if all_ok else "РЕЗУЛЬТАТ: ЕСТЬ НЕДОСТИГНУТЫЕ МЕТРИКИ ✗") + "\n")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
