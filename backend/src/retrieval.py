"""Finding the sections that answer a question.

Each kind of source is ranked three ways and the rankings are fused (reciprocal rank fusion):
BM25 keyword search, embedding similarity, and a cross-encoder reranker. A section that several
rankings place high wins, so no single model's quirks with a wording decide the answer.

PC141 sections are also matched on the questions their label says they answer (see
scripts/labels.py), which keeps retrieval steady when a student rewords a question. On 101
rewordings of the course eval questions (data/paraphrase_eval.json) this finds the right section
in the top 5 for 100 of them.
"""
import asyncio
import json
import math
import re
from collections import Counter
from operator import mul
from pathlib import Path

PC141_TOP_N = 5  # sections the model reads from the course documents
LAURIER_TOP_N = 3  # and from Laurier pages
LAURIER_POOL = 10  # Laurier sections the reranker scores
LAURIER_PER_PAGE = 2  # so one long page can't crowd out the others
LAURIER_MIN_RERANK = 0.01  # below this the reranker says the section is unrelated

# "Laurier" is on every university page, so in a question it only favours sections that happen to
# say it (a policy's "Purpose", the lab manual's parking-space example).
STOPWORDS = set(
    "a an and are as at be by can do does for from has have how i if in is it its me my of on or our so that the their them "
    "then there these this to was we what when where which who why will with you your laurier wlu wilfrid".split()
)

# Students' words -> the words the course documents and Laurier pages use. Added to the search
# query only; the model still sees the original question.
SYNONYMS = [
    (r"\b(chat ?gpt|copilot|gemini|claude|gen ?ai|generative|llms?|ai)\b", "AI-based systems, generative AI tools"),
    (r"\b(sick|ill|flu|covid|doctor)\b", "illness, medical documentation"),
    (r"\b(miss|missed|missing|skip|skipped|absent|absence)\b", "absence, attendance, make-up"),
    (r"\b(phones?|laptops?|tablets?|devices?|smart ?watch)\b", "digital devices"),
    (r"\b(cheat|cheating|copy|copied|copying)\b", "plagiarism, academic misconduct"),
    (r"\b(hand in|turn in|upload|submit|submission)\b", "submit, Dropbox, MyLearningSpace"),
    (r"\blate\b", "late submission deduction"),
    (r"\b(counts? as|considered|means?|meaning|defined?|definitions?)\b", "definitions, defined, includes"),
    (r"\b(marks?|marking|graded)\b", "grade, grading"),
    (r"\b(prof|professor|teacher|ta|contact)\b", "instructor, IA, email"),
]


def expand_query(question):
    extra = [words for pattern, words in SYNONYMS if re.search(pattern, question, re.I)]
    return f"{question} ({'; '.join(extra)})" if extra else question


def stem(word):
    """Light suffix stripping, so "missed"/"missing" match "miss" and "labs" matches "lab"."""
    if len(word) <= 3 or re.search(r"\d", word):
        return word
    s = word
    if s.endswith("ies") and len(s) > 4:
        s = s[:-3] + "y"
    elif s.endswith("sses"):
        s = s[:-2]
    elif re.search(r"(ch|sh|x|z)es$", s):
        s = s[:-2]
    elif s.endswith("ing") and len(s) > 5:
        s = s[:-3]
    elif s.endswith("ed") and len(s) > 4:
        s = s[:-2]
    elif s.endswith("s") and not re.search(r"(ss|us|is)$", s):
        s = s[:-1]
    if s != word and re.search(r"([bdgmnprt])\1$", s):
        s = s[:-1]  # "submitt" -> "submit"
    return s


def tokenize(text):
    return [stem(t) for t in re.findall(r"\w+", text.lower()) if t not in STOPWORDS]


class BM25:
    """Okapi BM25 keyword ranking over a fixed list of texts."""

    def __init__(self, texts, k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        self.docs = [Counter(tokenize(t)) for t in texts]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg_length = sum(self.lengths) / max(len(self.docs), 1)
        self.df = Counter(word for d in self.docs for word in d)

    def rank(self, query):
        """[(index, score)] best first, only texts that share a word with the query."""
        n = len(self.docs)
        words = set(tokenize(query))
        scored = []
        for i, (doc, length) in enumerate(zip(self.docs, self.lengths)):
            score = 0.0
            for w in words:
                if f := doc.get(w):
                    idf = math.log((n - self.df[w] + 0.5) / (self.df[w] + 0.5) + 1)
                    score += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * length / self.avg_length))
            if score > 0:
                scored.append((i, score))
        return sorted(scored, key=lambda x: -x[1])


def rrf(rankings, k=60):
    """Reciprocal rank fusion of several rankings of (index, score); returns indices best first."""
    fused = Counter()
    for ranking in rankings:
        for rank, (i, _) in enumerate(ranking):
            fused[i] += 1 / (k + rank + 1)
    return [i for i, _ in fused.most_common()]


def by_similarity(query_vector, vectors):
    """[(index, score)] best first. Stored vectors are unit length, so a dot product ranks by cosine."""
    scores = [sum(map(mul, query_vector, v)) for v in vectors]
    return sorted(enumerate(scores), key=lambda x: -x[1])


class Corpus:
    """The sections built by scripts/build_corpus.py, with their search indexes."""

    def __init__(self, data_dir):
        load = lambda name: json.loads((Path(data_dir) / name).read_text(encoding="utf-8"))
        self.chunks = load("corpus.json")
        vectors = load("vectors.json")
        self.course = [i for i, c in enumerate(self.chunks) if c["kind"] == "pc141"]
        self.laurier = [i for i, c in enumerate(self.chunks) if c["kind"] == "laurier"]
        self.course_bm25 = BM25([self.chunks[i]["search_text"] for i in self.course])
        self.laurier_bm25 = BM25([self.chunks[i]["search_text"] for i in self.laurier])
        self.course_vectors = [vectors[i] for i in self.course]
        self.laurier_vectors = [vectors[i] for i in self.laurier]
        # A section's label questions, matched on their own: its best-matching question counts.
        position = {chunk: n for n, chunk in enumerate(self.course)}
        self.questions = [(position[i], v) for i, v in load("question_vectors.json")]

    def question_ranking(self, query_vector):
        best = {}
        for n, v in self.questions:
            best[n] = max(best.get(n, -1.0), sum(map(mul, query_vector, v)))
        return sorted(best.items(), key=lambda x: -x[1])

    async def search_course(self, query, query_vector, models):
        """The best PC141 sections: every section is reranked (there are few), then the reranker's
        order is fused with the keyword, vector and label-question rankings."""
        rankings = [self.course_bm25.rank(query), by_similarity(query_vector, self.course_vectors), self.question_ranking(query_vector)]
        pool = rrf(rankings)
        scores = await models.rerank(query, [self.chunks[self.course[n]]["search_text"] for n in pool])
        reranked = sorted(zip(pool, scores), key=lambda x: -x[1])
        score_of = dict(reranked)
        best = rrf([reranked, *rankings])[:PC141_TOP_N]
        return [{**self.chunks[self.course[n]], "score": score_of[n]} for n in best]

    async def search_laurier(self, query, query_vector, models):
        """The best Laurier sections: keyword and vector rankings fused, at most two per page,
        then the reranker picks the few it judges related."""
        fused = rrf([self.laurier_bm25.rank(query)[:50], by_similarity(query_vector, self.laurier_vectors)[:50]])
        pool, per_page = [], Counter()
        for n in fused:
            page = self.chunks[self.laurier[n]]["id"].split("#")[0]
            if per_page[page] < LAURIER_PER_PAGE:
                per_page[page] += 1
                pool.append(n)
            if len(pool) == LAURIER_POOL:
                break
        texts = [self.chunks[self.laurier[n]]["search_text"] for n in pool]
        reranked = sorted(zip(pool, await models.rerank(query, texts)), key=lambda x: -x[1])
        return [{**self.chunks[self.laurier[n]], "score": s} for n, s in reranked if s >= LAURIER_MIN_RERANK][:LAURIER_TOP_N]

    async def search(self, question, models):
        """Numbered sources for the prompt: PC141 sections first, then Laurier sections."""
        query = expand_query(question)
        [query_vector] = await models.embed([query])
        course, laurier = await asyncio.gather(self.search_course(query, query_vector, models), self.search_laurier(query, query_vector, models))
        return [{"n": n, **s} for n, s in enumerate(with_intros(self, course) + laurier, start=1)]


def with_intros(corpus, found):
    """An announcement's opening text ("Labs are held on alternate weeks in Room N2089") is context
    for every subsection under it, so the best-ranked subsection carries it as `intro`."""
    seen = {c["id"] for c in found}
    out = []
    for c in found:
        top, *rest = c["section"].split(" > ")
        parent = rest and next((p for p in corpus.chunks if p.get("file") == c["file"] and p["section"] == top), None)
        if parent and parent["id"] not in seen:
            seen.add(parent["id"])
            c = {**c, "intro": parent["text"]}
        out.append(c)
    return out
