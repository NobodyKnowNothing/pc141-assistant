"""Measure the assistant against the deployed (or a local) backend.

    python scripts/evaluate.py retrieval                 # sources only: embedding + reranker calls
    python scripts/evaluate.py answers                   # full answers: one answer-model call each
    python scripts/evaluate.py answers --ids E1,L2,U1    # a subset, to save the daily allowance
    python scripts/evaluate.py retrieval --url http://127.0.0.1:8787

`retrieval` runs data/web_eval.json (does the expected PC141 section or Laurier page come back?)
and data/paraphrase_eval.json (101 rewordings of the course questions: where does the target
section rank?). `answers` runs data/web_eval.json and checks what the answer cites and whether its
quotes verify. Results go to results/<mode>.json; the summary is printed.
"""
import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://wlu-rag-api.nobodyknownothing.workers.dev"


class OutOfQuota(Exception):
    pass


def ask(url, question, retrieve_only):
    body = json.dumps({"question": question, "retrieveOnly": retrieve_only}).encode()
    # Cloudflare blocks Python-urllib's default user agent.
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "User-Agent": "pc141-eval/1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as res:
                return json.load(res)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise OutOfQuota from e
            if attempt == 2 or e.code < 500:
                return {"error": f"HTTP {e.code}: {e.read().decode()[:300]}"}
        except OSError as e:
            if attempt == 2:
                return {"error": str(e)}
        time.sleep(5)


def section_hit(source, want):
    return source["kind"] == "pc141" and source["file"] == want["file"] and want["section"].lower() in source["section"].lower()


def page_hit(source, want):
    """A Laurier source from one of the expected pages, given as page ids or URL fragments."""
    return source["kind"] == "laurier" and any(w == source["id"].split("#")[0] or w in source["url"] for w in want)


def check(item, r):
    """Per-question checks; None where a check doesn't apply."""
    sources = r["sources"]
    by_n = {s["n"]: s for s in sources}
    want_pc, want_ul = item.get("pc141"), item.get("laurier")
    row = {
        "pc141_retrieved": any(section_hit(s, want_pc) for s in sources) if want_pc else None,
        "laurier_retrieved": any(page_hit(s, want_ul) for s in sources) if want_ul else None,
    }
    if "status" in r:
        claims = r["pc141"] + r["laurier"]
        cited = [by_n[n] for c in claims for n in c["sources"] if n in by_n]
        unanswerable = item["group"] == "unanswerable"
        row.update(
            status=r["status"],
            pc141_cited=any(section_hit(s, want_pc) for s in cited) if want_pc else None,
            laurier_cited=any(page_hit(s, want_ul) for s in cited) if want_ul else None,
            answered=r["status"] != "not_found" if not unanswerable else None,
            refused=r["status"] == "not_found" if unanswerable else None,
            claims=len(claims),
            verified=sum(c["verified"] for c in claims),
            answer=[("" if c["verified"] else "(unverified) ") + c["text"] for c in claims] or r["unverified"],
        )
        if flagged := [{"text": c["text"], "quote": c["quote"], "issue": c.get("issue")} for c in claims if not c["verified"]]:
            row["unverified_claims"] = flagged
    row["sources"] = [f"[{s['n']}] {s['title']} > {s['section']}" for s in sources]
    return row


def tally(rows, key):
    values = [r[key] for r in rows if r.get(key) is not None]
    return f"{sum(values)}/{len(values)}" if values else "-"


def run_questions(url, items, retrieve_only):
    rows = []
    for item in items:
        start = time.time()
        r = ask(url, item["question"], retrieve_only)
        row = {"id": item["id"], "group": item["group"], "seconds": round(time.time() - start, 1)}
        row.update({"error": r["error"]} if "error" in r else check(item, r))
        rows.append(row)
        flags = " ".join(f"{k}={v}" for k, v in row.items() if k in ("pc141_retrieved", "laurier_retrieved", "pc141_cited", "laurier_cited", "refused", "status", "error") and v is not None)
        print(f"{item['id']:4} {row['seconds']:5.1f}s {flags}", flush=True)
    return rows


def run_paraphrases(url):
    items = json.loads((ROOT / "data" / "paraphrase_eval.json").read_text(encoding="utf-8"))
    ranks = {}
    for item in items:
        for q in item["rewordings"]:
            r = ask(url, q, True)
            course = [s for s in r.get("sources", []) if s["kind"] == "pc141"]
            ranks[f"{item['id']}|{q}"] = next((i for i, s in enumerate(course, 1) if section_hit(s, item)), None) if "sources" in r else "error"
    found = [v for v in ranks.values() if v != "error"]
    summary = {
        "found in top 5": f"{sum(v is not None for v in found)}/{len(found)}",
        "ranked first": f"{sum(v == 1 for v in found)}/{len(found)}",
        "MRR": round(sum(1 / v for v in found if v) / len(found), 3),
    }
    return summary, ranks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["retrieval", "answers"])
    ap.add_argument("--url", default=API)
    ap.add_argument("--ids", help="comma-separated question ids (default: all)")
    args = ap.parse_args()

    items = json.loads((ROOT / "data" / "web_eval.json").read_text(encoding="utf-8"))
    items = [i for i in items if not args.ids or i["id"] in args.ids.split(",")]
    result = {"date": date.today().isoformat(), "url": args.url}
    try:
        rows = run_questions(args.url, items, args.mode == "retrieval")
        summary = {name: tally(rows, key) for name, key in [("PC141 section retrieved", "pc141_retrieved"), ("Laurier page retrieved", "laurier_retrieved")]}
        if args.mode == "answers":
            ok = [r for r in rows if "status" in r]
            summary.update({
                "Gives an answer (answerable questions)": tally(ok, "answered"),
                "Cites the right PC141 section": tally(ok, "pc141_cited"),
                "Cites the right Laurier page": tally(ok, "laurier_cited"),
                "Says it can't verify (unanswerable questions)": tally(ok, "refused"),
                "Statements whose quote checks out": f"{sum(r['verified'] for r in ok)}/{sum(r['claims'] for r in ok)}",
                "Median seconds per answer": statistics.median(r["seconds"] for r in ok) if ok else "-",
            })
        elif not args.ids:
            summary["Rewordings"], result["paraphrase_ranks"] = run_paraphrases(args.url)
    except OutOfQuota:
        print("Stopped: the Workers AI daily allowance is used up (HTTP 429). Nothing was saved.")
        return
    result.update(summary=summary, rows=rows)
    out = ROOT / "results" / f"{args.mode}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    print()
    for name, value in summary.items():
        print(f"{name:48} {value}")
    print(f"\nsaved {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
