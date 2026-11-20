"""Give every PC141 section a semantic label, so retrieval matches what a section is *about*,
not only the words it happens to contain.

A section's own words often miss how students ask about it: the lab manual's "4 Summary" is just
a table ("Item ... Weight (%) ... In-lab Tasks 0 40"), so "marking scheme?" shares no word with it
and lexical, vector and reranker scores all pass it by. An LLM reads each section with its document
title, section path and the document's outline, and writes:

  about      what the section is and what it applies to, in plain words ("the marking scheme for
             the Estimation and Bounding lab: how each part of the lab is weighted")
  questions  questions a student might type that the section answers
  terms      everyday words and synonyms for its topic that the text itself does not use

These go into the section's search text (what BM25, the embeddings and the reranker read), and
each question gets its own vector. The model answering a question sees only `about`, marked as a
description it may not quote.

Labels are cached in data/chunk_labels.json by section content, so only new or changed sections
call the model (Gemma 4 on Workers AI, through the Cloudflare REST API). Credentials come from
CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID, or from `npx wrangler login`.
"""
import hashlib
import json
import os
import re
import urllib.request
from pathlib import Path

MODEL = "@cf/google/gemma-4-26b-a4b-it"
PROMPT_VERSION = 1  # bump when PROMPT changes, so every chunk is labelled again
CACHE = Path(__file__).resolve().parent.parent / "data" / "chunk_labels.json"

PROMPT = """You label sections of course documents for a search index used by students of PC141, a first-year physics course at Wilfrid Laurier University. Students type short, informal questions ("marking scheme?", "can I use my phone in lab", "what if I'm sick"), and the index must find the section that answers them even when the section uses different words.

You get one section with its document title, its place in the document and the document's outline. Reply with a JSON object:
- "about": one or two plain sentences saying what this section is and what it applies to (which document, lab or tutorial). Name the kind of information it holds in the words a student would use: for example a table of item weights at the end of a lab manual is "the marking scheme for this lab: how much each part of the lab is worth"; a list of allowed items is "what students may bring or use".
- "questions": 3 to 6 short questions a student might ask that this section answers, phrased the way students talk.
- "terms": 4 to 12 everyday words or synonyms for this topic that the section's text does not already use.

Rules: describe only what the section contains. Never add numbers, dates, names, rules or facts that are not in the text, and do not guess at missing details. If the section is a title page, table of contents, list of figures or other front matter, say so in "about" and give questions about finding the document only."""

SCHEMA = {
    "type": "object",
    "properties": {
        "about": {"type": "string"},
        "questions": {"type": "array", "items": {"type": "string"}},
        "terms": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["about", "questions", "terms"],
}


def credentials():
    """(API token, account id) for the Cloudflare REST API."""
    token, account = os.environ.get("CLOUDFLARE_API_TOKEN"), os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    if not token:
        config = Path(os.environ.get("APPDATA") or Path.home() / ".config") / "xdg.config" / ".wrangler" / "config" / "default.toml"
        if not config.exists():
            config = Path.home() / ".config" / ".wrangler" / "config" / "default.toml"
        token = re.search(r'oauth_token\s*=\s*"([^"]+)"', config.read_text()).group(1)
    if not account:
        req = urllib.request.Request("https://api.cloudflare.com/client/v4/accounts", headers={"Authorization": f"Bearer {token}"})
        account = json.load(urllib.request.urlopen(req))["result"][0]["id"]
    return token, account


def outline(chunks, source):
    seen = []
    for c in chunks:
        if c["file"] == source and c["section"] not in seen:
            seen.append(c["section"])
    return "\n".join(f"- {s}" for s in seen)


def cache_key(chunk):
    raw = json.dumps([MODEL, PROMPT_VERSION, chunk["title"], chunk["section"], chunk["text"]])
    return hashlib.sha256(raw.encode()).hexdigest()


def label(token, account, chunk, doc_outline):
    user = f"Document: {chunk['title']}\nSection: {chunk['section']}\n\nDocument outline:\n{doc_outline}\n\nSection text:\n{chunk['text']}"
    body = {
        "messages": [{"role": "system", "content": PROMPT}, {"role": "user", "content": user}],
        "response_format": {"type": "json_schema", "json_schema": {"name": "label", "schema": SCHEMA}},
        "temperature": 0.2,
        "max_tokens": 600,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{MODEL}",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    for attempt in range(3):
        try:
            res = json.load(urllib.request.urlopen(req, timeout=120))["result"]
            out = res.get("response") or res["choices"][0]["message"]["content"]
            out = json.loads(out) if isinstance(out, str) else out
            return {
                "about": str(out["about"]).strip(),
                "questions": [str(q).strip() for q in out["questions"] if str(q).strip()][:6],
                "terms": [str(t).strip() for t in out["terms"] if str(t).strip()][:12],
            }
        except Exception as e:  # malformed JSON or a transient model error: try again
            if attempt == 2:
                raise RuntimeError(f"{chunk['id']}: {e}") from e


def add_labels(chunks):
    """Sets each chunk's `label`, from the cache or, for a new section, from the model."""
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    creds = None
    for c in chunks:
        key = cache_key(c)
        if key not in cache:
            creds = creds or credentials()
            cache[key] = label(*creds, c, outline(chunks, c["file"]))
            CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")  # resume after a failure
            print(f"  labelled {c['id']}: {cache[key]['about'][:90]}")
        c["label"] = cache[key]
    used = {cache_key(c) for c in chunks}
    CACHE.write_text(json.dumps({k: v for k, v in cache.items() if k in used}, ensure_ascii=False, indent=1), encoding="utf-8")


def search_text(chunk):
    """What BM25, the embeddings and the reranker read: heading, label and section text."""
    lab = chunk["label"]
    return "\n".join(
        [
            f"{chunk['title']} | {chunk['section']}",
            f"About: {lab['about']}",
            f"Answers: {' '.join(lab['questions'])}",
            f"Terms: {', '.join(lab['terms'])}",
            chunk["text"],
        ]
    )
