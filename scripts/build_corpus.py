"""Build the assistant's corpus: every citable section of the PC141 PDFs and the Laurier pages
in sources.py, with search vectors. Writes backend/src/data/:

  corpus.json            one entry per section (text, citation, link)
  vectors.json           one embedding per section, in corpus order
  question_vectors.json  [section index, embedding] for each PC141 label question and "about" line

    python scripts/build_corpus.py            # re-fetch the Laurier pages
    python scripts/build_corpus.py --offline  # reuse the pages saved in scripts/.page_cache/

Run it when a PDF in files/ or the list in sources.py changes, and at the start of each term so the
Laurier pages are current. New PC141 sections are labelled by Gemma 4 on Workers AI (labels.py);
everything else runs locally. Embeddings use the same model as the Worker's query embeddings
(bge-small-en-v1.5, mean pooling), run on this machine with fastembed.
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

from fastembed import TextEmbedding
from fastembed.common.model_description import ModelSource, PoolingType

from labels import add_labels, search_text
from pdf_sections import pdf_sections
from sources import LAURIER_PAGES, PDFS, authority
from web_sections import page_sections, page_title, revised_date

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "backend" / "src" / "data"
PAGE_CACHE = Path(__file__).resolve().parent / ".page_cache"
USER_AGENT = "PC141-Course-Assistant/1.0 (+https://pc141-assistant.vercel.app)"


def fetch(page, offline):
    """The page's HTML, fetched politely (one request a second) and saved for --offline runs."""
    saved = PAGE_CACHE / f"{page['id']}.html"
    if offline:
        return saved.read_text(encoding="utf-8")
    time.sleep(1)
    req = urllib.request.Request(page["url"], headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as res:
        if "/404" in res.url:
            raise RuntimeError(f"{page['id']}: page has moved ({res.url})")
        html = res.read().decode("utf-8", errors="replace")
    PAGE_CACHE.mkdir(exist_ok=True)
    saved.write_text(html, encoding="utf-8")
    return html


def course_chunks():
    chunks = []
    for name, title in PDFS.items():
        for i, sec in enumerate(pdf_sections(ROOT / "files" / name), start=1):
            chunks.append({"id": f"{Path(name).stem}#{i}", "kind": "pc141", "title": title, "file": name, **sec})
    add_labels(chunks)
    for c in chunks:
        c["search_text"] = search_text(c)
    return chunks


def laurier_chunks(offline):
    chunks = []
    for page in LAURIER_PAGES:
        html = fetch(page, offline)
        title = page.get("title") or page_title(html)
        meta = {"title": title, "publisher": page["publisher"], "authority": authority(page["url"])}
        if meta["authority"] == "policy" and (revised := revised_date(html)):
            meta["revised"] = revised
        sections = page_sections(html, {"url": page["url"], "title": title})
        if not sections:
            raise RuntimeError(f"{page['id']}: no readable content at {page['url']}")
        for i, sec in enumerate(sections, start=1):
            chunks.append({"id": f"{page['id']}#{i}", "kind": "laurier", **meta, **sec, "search_text": f"{title} | {sec['section']}\n{sec['text']}"})
        print(f"  {page['id']}: {len(sections)} sections")
    return chunks


def embedder():
    # The ONNX export of bge-small-en-v1.5 at full precision, mean-pooled like Workers AI's
    # @cf/baai/bge-small-en-v1.5 (fastembed's built-in version is quantized and CLS-pooled).
    name = "bge-small-en-v1.5-mean"
    TextEmbedding.add_custom_model(model=name, pooling=PoolingType.MEAN, normalization=True, sources=ModelSource(hf="Xenova/bge-small-en-v1.5"), dim=384, model_file="onnx/model.onnx")
    model = TextEmbedding(name)
    # One text at a time: batching pads short texts, which changes their mean-pooled vectors.
    return lambda texts: [[round(float(x), 4) for x in model.embed([t]).__next__()] for t in texts]


def write(name, data):
    path = OUT / name
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    offline = "--offline" in sys.argv
    print("PC141 documents")
    corpus = course_chunks()
    print(f"  {len(corpus)} sections")
    print("Laurier pages")
    corpus += laurier_chunks(offline)
    print(f"embedding {len(corpus)} sections")
    embed = embedder()
    phrases = [(i, p) for i, c in enumerate(corpus) if c.get("label") for p in [c["label"]["about"], *c["label"]["questions"]]]
    OUT.mkdir(parents=True, exist_ok=True)
    write("corpus.json", corpus)
    write("vectors.json", embed([c["search_text"] for c in corpus]))
    write("question_vectors.json", [[i, v] for (i, _), v in zip(phrases, embed([p for _, p in phrases]))])
