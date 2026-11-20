"""Checks every claim in the model's answer against the sources it cites.

- A claim citing no valid source is dropped.
- A claim is marked unverified when its quote is not in the cited text, or when it states a
  number, time or email the cited text doesn't contain.
- If nothing is left, the answer is "not_found"; if anything is unverified, it is "partial".

The quote check confirms the wording exists in the source. It can't catch every overstatement,
so the page shows which claims passed.
"""
import json
import re
import unicodedata

NUMBER_WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "hundred": 100}
NUMBER_WORD = re.compile(r"\b(" + "|".join(NUMBER_WORDS) + r")\b(?!['’])")  # not "one's own"
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
NUMBER = re.compile(r"\d+(?::\d\d)?")


def normalize(text):
    text = NUMBER_WORD.sub(lambda m: str(NUMBER_WORDS[m.group(1)]), text.lower())
    return re.sub(r"(\d),(\d{3})\b", r"\1\2", text)


def strip_zeros(n):
    return re.sub(r"^0+(?=\d)", "", n)


def checkable_facts(text):
    """Details a student could act on (emails, numbers, times) that the cited text must contain."""
    t = normalize(text)
    numbers = NUMBER.findall(EMAIL.sub(" ", t))
    return list(dict.fromkeys(EMAIL.findall(t) + [strip_zeros(n) for n in numbers]))


def facts_in(text):
    t = normalize(text)
    facts = set(EMAIL.findall(t))
    for n in NUMBER.findall(EMAIL.sub(" ", t)):
        facts.add(strip_zeros(n))
        facts.update(strip_zeros(part) for part in n.split(":"))
    return facts


def squash(text):
    """Letters and digits only, so PDF spacing quirks ("isbounding"), dashes and curly quotes
    don't stop a quote from matching its source."""
    return re.sub(r"[^a-z0-9@]+", "", unicodedata.normalize("NFKD", text.lower()))


def quote_found(quote, texts):
    """True when every part of the quote appears word for word in one of the texts. Parts are split
    at "...", sentence ends and line breaks, so a quote may join sentences of a numbered list, give
    them in another order, or pick rows of a table, while every sentence must still be verbatim."""
    parts = [p for p in map(squash, re.split(r"\.\.\.|…|(?<=[.!?;])\s+|\s*\n\s*", str(quote or ""))) if len(p) >= 8]
    hay = [squash(t) for t in texts]
    return bool(parts) and all(any(p in h for h in hay) for p in parts)


def parse_reply(reply):
    """The model's reply as a dict; None if it isn't readable JSON."""
    if isinstance(reply, dict):
        return reply
    try:
        parsed = json.loads(re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", str(reply)))
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def verify_answer(raw, sources):
    """{status, pc141, laurier, unverified}, with each claim marked verified or not."""
    by_n = {s["n"]: s for s in sources}
    out = {"pc141": [], "laurier": []}
    dropped = 0
    for bucket in ("pc141", "laurier"):
        for c in raw.get(bucket) if isinstance(raw.get(bucket), list) else []:
            if not isinstance(c, dict):
                continue
            text = re.sub(r"(?:\s*\[\d+(?:,\s*\d+)*\])+(?=[.!?]?\s*$)", "", str(c.get("text") or "")).strip()  # trailing [n] markers
            cited = [n for n in dict.fromkeys(_ints(c.get("sources"))) if n in by_n]
            if not text:
                continue
            if not cited:
                dropped += 1
                continue
            kinds = {by_n[n]["kind"] for n in cited}
            cited_text = [f"{by_n[n].get('intro', '')}\n{by_n[n]['text']}" for n in cited]
            quote = str(c.get("quote") or "").strip()
            # A claim lives with the kind of source it cites; one citing both goes where its quote is from.
            quoted = next((n for n, t in zip(cited, cited_text) if quote_found(quote, [t])), None)
            home = by_n[quoted]["kind"] if len(kinds) > 1 and quoted else bucket if bucket in kinds else next(iter(kinds))
            have = facts_in("\n".join(f"{by_n[n]['title']} {by_n[n]['section']} {t}" for n, t in zip(cited, cited_text)))
            missing = [f for f in checkable_facts(text) if f not in have]
            claim = {"text": text, "quote": quote, "sources": cited, "verified": True}
            if not quoted:
                claim.update(verified=False, issue="supporting quote not found in the cited section")
            elif len(kinds) > 1:
                claim.update(verified=False, issue="mixes a PC141 rule with a university rule; check both sources")
            elif missing:
                claim.update(verified=False, issue=", ".join(f'"{m}"' for m in missing) + " not found in the cited section")
            out[home].append(claim)

    claims = out["pc141"] + out["laurier"]
    unverified = str(raw.get("unverified") or "").strip()
    if re.fullmatch(r"(none|n/?a|nothing|-)?\.?", unverified, re.I):
        unverified = ""
    if dropped:
        removed = f"{dropped} statement{'s were' if dropped > 1 else ' was'} removed because {'they' if dropped > 1 else 'it'} cited no source."
        unverified = f"{unverified} {removed}".strip()
    if not claims:
        status = "not_found"
    elif raw.get("status") != "answered" or any(not c["verified"] for c in claims) or unverified:
        status = "partial"
    else:
        status = "answered"
    if status == "answered":
        unverified = ""
    if status == "not_found" and not unverified:
        unverified = "The sources found do not answer this question."
    return {"status": status, **out, "unverified": unverified}


def _ints(values):
    for v in values if isinstance(values, list) else []:
        try:
            yield int(v)
        except (TypeError, ValueError):
            pass


def answer_text(v):
    """The answer as plain text, for logs and scripts."""
    lines = lambda claims: "\n".join(f"- {c['text']} {''.join(f'[{n}]' for n in c['sources'])}{'' if c['verified'] else ' (unverified)'}" for c in claims)
    parts = []
    if v["pc141"]:
        parts.append("PC141 course rules:\n" + lines(v["pc141"]))
    if v["laurier"]:
        parts.append("Laurier university-wide:\n" + lines(v["laurier"]))
    if v["unverified"]:
        parts.append("Could not verify: " + v["unverified"])
    return "\n\n".join(parts)
