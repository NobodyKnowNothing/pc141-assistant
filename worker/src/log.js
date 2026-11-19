// One structured line per question, for Workers Logs (wrangler.jsonc "observability"). It records
// what retrieval returned and how it was ranked, so a missed answer can be traced from the dashboard
// without re-running the question. Source texts are left out to keep the line small.

const round = (x) => (typeof x === "number" ? Math.round(x * 1e4) / 1e4 : x);
const clip = (s, n = 120) => (typeof s === "string" && s.length > n ? `${s.slice(0, n)}…` : s);

export function retrievalLog(req, out, { ms, error } = {}) {
  const line = {
    event: "ask",
    question: req.question,
    mode: req.mode,
    scope: req.scope,
    ...((req.sections?.lab || req.sections?.tutorial) && { sections: req.sections }),
    ...(req.retrieveOnly && { retrieveOnly: true }),
    ...(req.cache === false && { skipCache: true }),
    ms,
  };
  if (error) return { ...line, error: clip(error, 300) };
  const sources = out.sources || [];
  return {
    ...line,
    ...(out.cached && { cached: true, cachedAt: out.cachedAt }),
    ...(out.shared && { shared: true }),
    status: out.status,
    cited: { pc141: out.pc141?.length ?? 0, laurier: out.laurier?.length ?? 0 },
    ...(out.unverified && { unverified: clip(out.unverified, 200) }),
    sourceCount: { pc141: sources.filter((s) => s.kind === "pc141").length, laurier: sources.filter((s) => s.kind === "laurier").length },
    sources: sources.map((s) => ({
      n: s.n,
      kind: s.kind,
      ...(s.kind === "pc141" ? { file: s.file } : { page: s.page, ...(s.viaIndex && { viaIndex: true }), ...(s.viaSearch && { viaSearch: true }) }),
      section: clip(s.section),
      score: round(s.score),
    })),
    laurierPages: (out.laurierPages || []).map((p) => ({ id: p.id, ...(p.viaIndex && { viaIndex: true }), ...(p.viaSearch && { viaSearch: true }), ...(p.error && { error: clip(p.error, 200) }) })),
    linkCount: out.laurierLinks?.length ?? 0,
    ...(out.llm && { llm: out.llm }),
    ...(out.unreadable && { unreadable: true }),
    timings: out.cached ? { cacheMs: out.timings?.cacheMs } : out.timings,
  };
}
