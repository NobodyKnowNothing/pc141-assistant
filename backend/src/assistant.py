"""Answering a question: find the sources, have the model write cited claims, check every claim."""
from prompt import RESPONSE_SCHEMA, SYSTEM_PROMPT, user_message
from verify import parse_reply, verify_answer


def public_source(s):
    """What the API returns about a source: enough to cite and link it."""
    fields = ["n", "id", "kind", "title", "section", "text", "score"]
    fields += ["file", "pages", "intro"] if s["kind"] == "pc141" else ["publisher", "authority", "revised", "url"]
    return {k: s[k] for k in fields if s.get(k) is not None}


async def answer(question, corpus, models, retrieve_only=False):
    """{status, pc141, laurier, unverified, sources}. With retrieve_only, just the sources."""
    sources = await corpus.search(question, models)
    out = {"sources": [public_source(s) for s in sources]}
    if retrieve_only:
        return out
    if not sources:
        return {**out, "status": "not_found", "pc141": [], "laurier": [], "unverified": "None of the PC141 documents or Laurier pages covers this question."}
    reply = parse_reply(await models.generate(SYSTEM_PROMPT, user_message(question, sources), RESPONSE_SCHEMA))
    if reply is None:
        return {**out, "status": "not_found", "pc141": [], "laurier": [], "unverified": "The model returned an unreadable answer."}
    return {**out, **verify_answer(reply, sources)}
