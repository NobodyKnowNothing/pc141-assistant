import assert from "node:assert/strict";
import { test } from "node:test";
import chunks from "../src/chunks.json" with { type: "json" };
import vectors from "../src/vectors.json" with { type: "json" };
import { buildUserMessage, quoteFound } from "../src/answer.js";
import { BM25, expandQuery } from "../src/retrieval.js";

// scripts/label_chunks.py gives every chunk a semantic label that retrieval searches; a re-export
// without relabelling (or re-embedding) would silently drop it.
test("every course chunk has a semantic label that its searched text includes", () => {
  for (const c of chunks) {
    assert.ok(c.label?.about && c.label.questions?.length && c.label.terms?.length, `${c.id} has no label`);
    assert.ok(c.enriched.includes(`About: ${c.label.about}`), `${c.id}: enriched text lacks its label`);
  }
  assert.equal(vectors.length, chunks.length, "vectors.json is stale: run scripts/embed_chunks.py");
});

// The lab manual's marking scheme is a bare table ("In-lab Tasks 0 40") with no word a student
// would use for it; only its label connects it to the question.
test("a marking-scheme question finds the lab manual's weight table by its label", () => {
  const index = new BM25(chunks.map((c) => c.enriched));
  for (const q of ["marking scheme?", "How much are the in-lab tasks worth?"]) {
    const top = index.rank(expandQuery(q), 5).map(([i]) => chunks[i].id);
    assert.ok(top.includes("PC141labRAG#22"), `${q} -> ${top.join(", ")}`);
  }
});

test("a quote can pick table rows, each row verbatim", () => {
  const { text } = chunks.find((c) => c.id === "PC141labRAG#22");
  assert.ok(quoteFound("In-lab Questions 0 40\nIn-lab Tasks 0 40\nPost-lab Tasks 0 20", [text]));
  assert.ok(!quoteFound("In-lab Questions 0 40\nIn-lab Tasks 0 50", [text]));
});

test("the label reaches the model as an index note, outside the quotable text", () => {
  const summary = chunks.find((c) => c.id === "PC141labRAG#22");
  const msg = buildUserMessage("marking scheme?", [{ n: 1, kind: "pc141", ...summary }]);
  assert.match(msg, /\(Index note: the marking scheme for this lab[^)]*\)\nItem Number Received Weight/);
});
