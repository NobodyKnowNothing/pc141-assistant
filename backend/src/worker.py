"""The Cloudflare Worker: HTTP in and out, and Workers AI as the models.

This is the only file that knows it runs on Cloudflare. POST / with {"question": "..."} returns
the checked answer and its sources; add "retrieveOnly": true to get only the sources (no answer
model call, used by scripts/evaluate.py).
"""
import json
import time
from pathlib import Path

from js import Object
from pyodide.ffi import JsException, to_js
from workers import Response, WorkerEntrypoint

from assistant import answer
from models import OutOfQuota
from retrieval import Corpus

EMBED_MODEL = "@cf/baai/bge-small-en-v1.5"
RERANK_MODEL = "@cf/baai/bge-reranker-base"
ANSWER_MODEL = "@cf/google/gemma-4-26b-a4b-it"

CORPUS = Corpus(Path(__file__).parent / "data")  # loaded once per Worker instance
LOCAL_ORIGINS = ["http://localhost:8000", "http://127.0.0.1:8000"]


class WorkersAI:
    """models.Models on Workers AI."""

    def __init__(self, ai):
        self.ai = ai

    async def run(self, model, inputs):
        try:
            result = await self.ai.run(model, to_js(inputs, dict_converter=Object.fromEntries))
        except JsException as e:
            # Error 4006: the account's daily free allowance (10,000 neurons) is used up.
            if "4006" in str(e) or "daily free allocation" in str(e):
                raise OutOfQuota(str(e)) from e
            raise
        return result.to_py()

    async def embed(self, texts):
        return (await self.run(EMBED_MODEL, {"text": texts, "pooling": "mean"}))["data"]

    async def rerank(self, query, texts):
        if not texts:
            return []
        ranked = (await self.run(RERANK_MODEL, {"query": query, "contexts": [{"text": t} for t in texts], "top_k": len(texts)}))["response"]
        scores = [0.0] * len(texts)
        for r in ranked:
            scores[r["id"]] = r["score"]
        return scores

    async def generate(self, system, user, schema):
        inputs = {
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "answer", "schema": schema}},
            "temperature": 0.1,
            "max_tokens": 1200,
            "chat_template_kwargs": {"enable_thinking": False},  # thinking would spend the token allowance
        }
        try:
            result = await self.run(ANSWER_MODEL, inputs)
        except OutOfQuota:
            raise
        except JsException:
            result = await self.run(ANSWER_MODEL, inputs)  # one retry for a transient model error
        return result.get("response") or result["choices"][0]["message"]["content"]


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        origin = request.headers.get("Origin")
        allowed = [self.env.ALLOWED_ORIGIN, *LOCAL_ORIGINS]
        headers = {
            "Access-Control-Allow-Origin": origin if origin in allowed else self.env.ALLOWED_ORIGIN,
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Vary": "Origin",
            "Content-Type": "application/json",
        }
        reply = lambda body, status=200: Response(json.dumps(body), status=status, headers=headers)

        if request.method == "OPTIONS":
            return Response(None, status=204, headers=headers)
        if origin and origin not in allowed:
            return reply({"error": "Origin not allowed"}, 403)
        if request.method != "POST":
            return reply({"error": 'POST a JSON body: {"question": "..."}'}, 405)
        try:
            body = json.loads(await request.text())
            question = body["question"].strip()
            assert 0 < len(question) <= 500
        except (ValueError, KeyError, TypeError, AttributeError, AssertionError):
            return reply({"error": "question must be a non-empty string of at most 500 characters"}, 400)

        start = time.time()
        log = {"question": question}
        try:
            out = await answer(question, CORPUS, WorkersAI(self.env.AI), retrieve_only=body.get("retrieveOnly") is True)
            log.update(status=out.get("status", "retrieved"), sources=[[s["n"], s.get("file") or s.get("url"), s["section"], round(s["score"], 4)] for s in out["sources"]])
            return reply(out)
        except OutOfQuota as e:
            log["error"] = str(e)
            return reply({"error": "daily_limit", "detail": str(e)}, 429)
        except Exception as e:  # a model call failed
            log["error"] = str(e)
            return reply({"error": "Upstream model error", "detail": str(e)}, 502)
        finally:
            log["ms"] = round((time.time() - start) * 1000)
            print(json.dumps(log))  # one line per question, searchable in Workers Logs
