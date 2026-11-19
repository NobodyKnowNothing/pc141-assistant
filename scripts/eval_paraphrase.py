"""Measure how course retrieval holds up when a question is reworded.

data/paraphrase_eval.json lists, for each target section, several rewordings a student might type
(terse, informal, situational, misspelt). Each is sent as a retrieval-only request (no answer, so
only embedding and reranker calls) and scored by where the target section ranks among the course
sources returned.

    python scripts/eval_paraphrase.py                               # deployed Worker
    python scripts/eval_paraphrase.py --url http://127.0.0.1:8787 --label multivec
"""
import argparse
import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_web import DEFAULT_URL, section_hit  # noqa: E402

RESULTS = root / "results" / "paraphrase_eval.json"


def rank_of(url, item, question, mode):
    body = {"question": question, "mode": mode, "scope": "pc141", "retrieveOnly": True}
    if item.get("sections"):
        body["sections"] = item["sections"]
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json", "User-Agent": "pc141-eval/1.0"})
    for attempt in range(3):
        try:
            sources = json.load(urllib.request.urlopen(req, timeout=120))["sources"]
            break
        except Exception as e:
            if attempt == 2:
                print(f"  request failed ({e}): {question}")
                return "error"
    want = {"file": item["file"], "section": item["section"]}
    ranks = [i + 1 for i, s in enumerate(sources) if section_hit(s, want)]
    return ranks[0] if ranks else None


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--mode", default="full")
    ap.add_argument("--label", default="deployed")
    args = ap.parse_args()
    items = json.loads((root / "data" / "paraphrase_eval.json").read_text(encoding="utf-8"))
    jobs = [(it, q) for it in items for q in it["rewordings"]]
    with ThreadPoolExecutor(2) as ex:
        ranks = list(ex.map(lambda j: rank_of(args.url, j[0], j[1], args.mode), jobs))
    errors = sum(r == "error" for r in ranks)
    jobs, ranks = [j for j, r in zip(jobs, ranks) if r != "error"], [r for r in ranks if r != "error"]
    if errors:
        print(f"  {errors} requests failed and are left out")
    n = len(jobs)
    hit5 = sum(r is not None for r in ranks)
    top1 = sum(r == 1 for r in ranks)
    mrr = sum(1 / r for r in ranks if r) / n
    print(f"{args.label}: hit@5 {hit5}/{n} ({hit5 / n:.0%}), top-1 {top1}/{n} ({top1 / n:.0%}), MRR {mrr:.3f}")
    per = {}
    for (it, q), r in zip(jobs, ranks):
        per.setdefault(it["id"], []).append((q, r))
    for iid, rs in per.items():
        missed = [q for q, r in rs if r is None]
        if missed:
            print(f"  {iid} missed {len(missed)}/{len(rs)}: {missed}")
    stored = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else {}
    stored[f"{args.label}:{args.mode}"] = {"hit5": hit5, "top1": top1, "mrr": round(mrr, 4), "n": n, "ranks": {f"{it['id']}|{q}": r for (it, q), r in zip(jobs, ranks)}}
    RESULTS.write_text(json.dumps(stored, indent=1, ensure_ascii=False), encoding="utf-8")
