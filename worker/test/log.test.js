import { test } from "node:test";
import assert from "node:assert/strict";
import { retrievalLog } from "../src/log.js";

const req = { question: "When is the lab report due?", mode: "full", scope: "both", sections: { lab: "L04" }, retrieveOnly: false, cache: true };

test("logs ranked sources with scores and no source text", () => {
  const out = {
    status: "partial",
    pc141: [{}],
    laurier: [],
    unverified: "x",
    sources: [
      { n: 1, kind: "pc141", file: "rules.pdf", section: "Lab reports", score: 0.123456, text: "long text" },
      { n: 2, kind: "laurier", page: "academic-calendar", viaIndex: true, section: "Deadlines", score: 0.5, text: "more" },
    ],
    laurierPages: [{ id: "site-search", error: "timeout" }],
    laurierLinks: [],
    llm: { provider: "groq", model: "m" },
    timings: { retrieveMs: 10, generateMs: 20 },
  };
  const line = retrievalLog(req, out, { ms: 31 });
  assert.equal(line.question, req.question);
  assert.deepEqual(line.sections, { lab: "L04" });
  assert.deepEqual(line.sourceCount, { pc141: 1, laurier: 1 });
  assert.deepEqual(line.sources[0], { n: 1, kind: "pc141", file: "rules.pdf", section: "Lab reports", score: 0.1235 });
  assert.equal(line.sources[1].viaIndex, true);
  assert.deepEqual(line.laurierPages, [{ id: "site-search", error: "timeout" }]);
  assert.ok(!JSON.stringify(line).includes("long text"));
});

test("marks cache hits and errors", () => {
  const hit = retrievalLog(req, { cached: true, cachedAt: "t", sources: [], timings: { cacheMs: 3, original: {} } }, { ms: 4 });
  assert.equal(hit.cached, true);
  assert.deepEqual(hit.timings, { cacheMs: 3 });
  const err = retrievalLog(req, null, { ms: 5, error: "rerank: 4006" });
  assert.equal(err.error, "rerank: 4006");
  assert.equal(err.sources, undefined);
});
