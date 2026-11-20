"""The three model calls the assistant makes, and the one error it treats specially.

worker.py provides them with Workers AI. To run the backend on a local model server instead,
write a class with the same three methods (for example calling Ollama, vLLM or llama.cpp, with
bge-small-en-v1.5 and bge-reranker-base run locally) and pass it to assistant.answer(). Nothing
else in src/ depends on Cloudflare.
"""
from typing import Protocol


class Models(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """One vector per text, from the model that embedded the corpus (bge-small-en-v1.5,
        mean pooling; see scripts/build_corpus.py)."""

    async def rerank(self, query: str, texts: list[str]) -> list[float]:
        """A relevance score per text, in the order given (bge-reranker-base). Higher is better."""

    async def generate(self, system: str, user: str, schema: dict) -> str | dict:
        """The answer model's reply: a JSON object matching `schema`, as a dict or JSON text."""


class OutOfQuota(Exception):
    """The model provider's usage allowance is used up; the API answers 429 "try again later"."""
