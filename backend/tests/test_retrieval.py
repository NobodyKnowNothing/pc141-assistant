import asyncio
from pathlib import Path

import pytest

from assistant import answer
from prompt import user_message
from retrieval import BM25, Corpus, expand_query, rrf, stem
from verify import quote_found

DATA = Path(__file__).resolve().parent.parent / "src" / "data"
CORPUS = Corpus(DATA)
by_id = {c["id"]: c for c in CORPUS.chunks}


class FakeModels:
    """Embeds every query as one chosen section's vector; reranks by shared words."""

    def __init__(self, like="PC141labRAG#22", reply=None):
        index = next(i for i, c in enumerate(CORPUS.chunks) if c["id"] == like)
        self.vector = CORPUS.course_vectors[CORPUS.course.index(index)] if index in CORPUS.course else CORPUS.laurier_vectors[CORPUS.laurier.index(index)]
        self.reply = reply
        self.generated = 0

    async def embed(self, texts):
        return [self.vector for _ in texts]

    async def rerank(self, query, texts):
        words = set(query.lower().split())
        return [len(words & set(t.lower().split())) / len(words) for t in texts]

    async def generate(self, system, user, schema):
        self.generated += 1
        return self.reply


def test_stemming_bm25_fusion_and_query_expansion():
    assert [stem(w) for w in ["missed", "missing", "labs", "submitted", "classes", "policies"]] == ["miss", "miss", "lab", "submit", "class", "policy"]
    bm = BM25(["Attendance and makeup policy for missed labs", "Logarithmic scale and orders of magnitude", "Plagiarism policy"])
    assert bm.rank("What if I miss a lab?")[0][0] == 0
    assert bm.rank("unrelated words") == []
    assert rrf([[(2, 9), (0, 5)], [(0, 1), (1, 0.5)]]) == [0, 2, 1]
    assert "AI-based systems" in expand_query("Can I use ChatGPT?")
    assert expand_query("When is reading week?") == "When is reading week?"


def test_the_corpus_files_agree():
    """scripts/build_corpus.py writes all three files; a partial rebuild would misalign them."""
    import json

    vectors = json.loads((DATA / "vectors.json").read_text(encoding="utf-8"))
    assert len(vectors) == len(CORPUS.chunks) and all(len(v) == 384 for v in vectors)
    assert CORPUS.questions and all(0 <= n < len(CORPUS.course) for n, _ in CORPUS.questions)
    for c in CORPUS.chunks:
        assert c["text"].strip() and c["section"] and c["title"]
        if c["kind"] == "pc141":
            assert c["label"]["about"] and c["label"]["questions"], f"{c['id']} has no label"
            assert f"About: {c['label']['about']}" in c["search_text"]
        else:
            assert c["url"].startswith("https://") and c["authority"] in {"policy", "calendar", "guidance"}


def test_a_marking_scheme_question_finds_the_lab_manuals_weight_table_by_its_label():
    """The marking scheme is a bare table ("In-lab Tasks 0 40"); only its label has the student's words."""
    for q in ["marking scheme?", "How much are the in-lab tasks worth?"]:
        top = [CORPUS.chunks[CORPUS.course[n]]["id"] for n, _ in CORPUS.course_bm25.rank(expand_query(q))[:5]]
        assert "PC141labRAG#22" in top, f"{q} -> {top}"


def test_a_quote_can_pick_table_rows_each_row_verbatim():
    text = by_id["PC141labRAG#22"]["text"]
    assert quote_found("In-lab Questions 0 40\nIn-lab Tasks 0 40\nPost-lab Tasks 0 20", [text])
    assert not quote_found("In-lab Questions 0 40\nIn-lab Tasks 0 50", [text])


def test_the_label_reaches_the_model_as_an_index_note_outside_the_quotable_text():
    msg = user_message("marking scheme?", [{"n": 1, **by_id["PC141labRAG#22"]}])
    assert "(Index note: the marking scheme for this lab" in msg
    assert ")\nItem Number Received Weight" in msg


def test_search_numbers_course_sections_first_then_related_laurier_sections():
    sources = asyncio.run(CORPUS.search("What is the penalty for plagiarism in the code of conduct?", FakeModels()))
    kinds = [s["kind"] for s in sources]
    assert kinds[:5] == ["pc141"] * 5 and set(kinds[5:]) <= {"laurier"} and 1 <= kinds.count("laurier") <= 3
    assert [s["n"] for s in sources] == list(range(1, len(sources) + 1))
    pages = [s["id"].split("#")[0] for s in sources if s["kind"] == "laurier"]
    assert all(pages.count(p) <= 2 for p in pages)


def test_laurier_sections_the_reranker_rejects_are_left_out():
    sources = asyncio.run(CORPUS.search("zzz qqq", FakeModels()))
    assert [s["kind"] for s in sources] == ["pc141"] * 5


def test_answer_checks_the_models_claims_and_retrieve_only_skips_the_model():
    reply = {"status": "answered", "pc141": [{"text": "In-lab tasks are worth 40%.", "quote": "In-lab Tasks 0 40", "sources": [1]}], "laurier": [], "unverified": ""}
    models = FakeModels(reply=reply)
    out = asyncio.run(answer("marking scheme?", CORPUS, models))
    cited = out["sources"][0]
    assert out["status"] == "answered" and out["pc141"][0]["verified"] and cited["file"] == "PC141labRAG.pdf" and "search_text" not in cited
    assert asyncio.run(answer("marking scheme?", CORPUS, models, retrieve_only=True)).keys() == {"sources"}
    assert models.generated == 1


@pytest.mark.parametrize("reply", ["not json at all", None])
def test_an_unreadable_reply_is_reported_not_guessed(reply):
    out = asyncio.run(answer("marking scheme?", CORPUS, FakeModels(reply=reply)))
    assert out["status"] == "not_found" and "unreadable" in out["unverified"]
