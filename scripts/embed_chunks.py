"""Precompute chunk embeddings for the Worker (worker/src/vectors.json).

Run after export_chunks.py and label_chunks.py (it embeds each chunk's labelled `enriched` text). Uses CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID if set,
otherwise the token from `wrangler login`.
"""
import json
import os
import re
import urllib.request
from pathlib import Path

MODEL = "@cf/baai/bge-small-en-v1.5"  # must match EMBED_MODEL in worker/src/index.js
root = Path(__file__).resolve().parent.parent


def credentials():
    token, account = os.environ.get("CLOUDFLARE_API_TOKEN"), os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    if not token:
        cfg = Path(os.environ["APPDATA"]) / "xdg.config" / ".wrangler" / "config" / "default.toml"
        token = re.search(r'oauth_token\s*=\s*"([^"]+)"', cfg.read_text()).group(1)
    if not account:
        req = urllib.request.Request(
            "https://api.cloudflare.com/client/v4/accounts", headers={"Authorization": f"Bearer {token}"}
        )
        account = json.load(urllib.request.urlopen(req))["result"][0]["id"]
    return token, account


def embed(token, account, texts):
    req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{MODEL}",
        data=json.dumps({"text": texts}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    return json.load(urllib.request.urlopen(req))["result"]["data"]


if __name__ == "__main__":
    chunks = json.loads((root / "worker" / "src" / "chunks.json").read_text(encoding="utf-8"))
    token, account = credentials()
    vectors = []
    for i in range(0, len(chunks), 8):
        vectors += embed(token, account, [c["enriched"] for c in chunks[i : i + 8]])
    assert len(vectors) == len(chunks)
    out = root / "worker" / "src" / "vectors.json"
    out.write_text(json.dumps([[round(x, 6) for x in v] for v in vectors]), encoding="utf-8")
    print(f"wrote {len(vectors)} vectors of dim {len(vectors[0])} to {out}")

    # One vector per label question and "about" line (label_chunks.py), each tagged with its chunk's
    # index: a student's question is matched against similar questions, not only against the
    # section's wording, which is what keeps retrieval steady when a question is reworded.
    phrases = [(i, p) for i, c in enumerate(chunks) if c.get("label") for p in [c["label"]["about"], *c["label"]["questions"]]]
    qvecs = []
    for j in range(0, len(phrases), 50):
        qvecs += embed(token, account, [p for _, p in phrases[j : j + 50]])
    out = root / "worker" / "src" / "question_vectors.json"
    out.write_text(json.dumps([[i, [round(x, 5) for x in v]] for (i, _), v in zip(phrases, qvecs)]), encoding="utf-8")
    print(f"wrote {len(qvecs)} question vectors to {out}")
