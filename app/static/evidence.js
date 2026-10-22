/* Evidence-checklist display logic: pure functions with no DOM access, so they can be unit-tested with Node.
 *
 * Response shape consumed (from POST /api/cases/{case_id}/evidence-checklist):
 *   { case_id: number, suggested_evidence: [{ item: string, reason: string }], warning: string }
 * Nothing else is read from the response.
 */
(function (root) {
  const LABEL = "Generate Evidence Checklist";
  // Shown only if the server omits its own warning. It never claims the items are required.
  const FALLBACK_WARNING = "These are general suggestions only. Check the retailer's actual policy for what evidence it asks for.";

  // Turns the raw API response into a safe, minimal model. status: "ok" | "empty" | "invalid".
  function normalizeEvidenceResponse(data, expectedCaseId) {
    const invalid = { status: "invalid", items: [], warning: null };
    if (!data || typeof data !== "object" || !Array.isArray(data.suggested_evidence)) return invalid;
    if (expectedCaseId != null && data.case_id != null && Number(data.case_id) !== Number(expectedCaseId)) return invalid;
    const items = data.suggested_evidence
      .filter((e) => e && typeof e === "object" && typeof e.item === "string" && e.item.trim())
      .map((e) => ({ item: e.item.trim(), reason: typeof e.reason === "string" ? e.reason.trim() : "" }));
    const warning = typeof data.warning === "string" && data.warning.trim() ? data.warning.trim() : null;
    return { status: items.length ? "ok" : "empty", items, warning };
  }

  // Maps a failed request to a message a person can act on. `err` is the Error thrown by api() (may carry .status).
  function describeEvidenceError(err) {
    if (err && err.kind === "invalid") return "The server returned a response this page could not read. Please try again.";
    if (err && err.status === 404) return "This case could not be found. It may have been removed, so the case list is being refreshed.";
    if (err && err.name === "TypeError") return "Could not reach the server. Check that the app is still running, then try again.";
    return (err && err.message) ? String(err.message) : "Something went wrong. Please try again.";
  }

  function warningBlock(model, esc) {
    return `<div class="evidence-warning" role="note"><span class="evidence-warning-icon" aria-hidden="true">!</span>` +
           `<div><strong>Please note</strong><p>${esc(model.warning || FALLBACK_WARNING)}</p></div></div>`;
  }

  // `esc` escapes text for HTML (passed in so this file stays DOM-free).
  function renderEvidenceChecklist(model, caseId, esc) {
    const headingId = `evidence-heading-${Number(caseId)}`;
    let body;
    if (model.status === "ok") {
      body = `<p class="evidence-intro">Ideas for what you might gather. These are not requirements, and having them does not mean a claim will succeed.</p>` +
        `<ul class="evidence-list">${model.items.map((i) =>
          `<li class="evidence-item"><strong class="evidence-name">${esc(i.item)}</strong>` +
          (i.reason ? `<span class="evidence-reason">${esc(i.reason)}</span>` : "") + `</li>`).join("")}</ul>`;
    } else {
      body = `<p class="evidence-empty">No evidence suggestions were returned for this case. You can still check the retailer's own policy for what it asks for.</p>`;
    }
    return `<section class="evidence" aria-labelledby="${headingId}">` +
           `<h3 id="${headingId}">Suggested evidence</h3>${warningBlock(model, esc)}${body}</section>`;
  }

  function renderEvidenceError(message, esc) {
    return `<div class="evidence evidence-error" role="alert"><strong>Could not generate the evidence checklist.</strong><p>${esc(message)}</p></div>`;
  }

  function renderEvidenceLoading() {
    return `<div class="evidence evidence-loading"><span class="sr-only">Generating evidence checklist…</span>` +
           `<div class="skeleton" aria-hidden="true"></div><div class="skeleton" aria-hidden="true"></div></div>`;
  }

  // Tracks which case ids have a request running, so a second click cannot start a duplicate request.
  function createRequestGate() {
    const running = new Set();
    return {
      tryStart(id) { if (running.has(id)) return false; running.add(id); return true; },
      finish(id) { running.delete(id); },
      isRunning(id) { return running.has(id); },
    };
  }

  const api = { LABEL, FALLBACK_WARNING, createRequestGate, normalizeEvidenceResponse, describeEvidenceError,
                renderEvidenceChecklist, renderEvidenceError, renderEvidenceLoading };
  if (typeof module === "object" && module.exports) module.exports = api; else root.RGEvidence = api;
})(typeof window !== "undefined" ? window : globalThis);
