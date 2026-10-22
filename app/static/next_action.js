/* "Next Best Action" logic: deterministic rules over the case that openCase() already loaded.
 * Pure functions with no DOM access and no network calls, so they can be unit-tested with Node.
 * It never calls an AI service and never states or invents retailer policy. Deadlines are described as
 * "confirmed by you" or "unconfirmed" - never as verified, because nothing in this app verifies a policy.
 */
(function (root) {
  const ACTIVE = ["new", "in_progress", "waiting_for_user"];
  const CLOSED = ["resolved", "closed"];
  const ACTION_LABELS = {
    draft: "Generate support draft",
    evidence: "Generate Evidence Checklist",
    eligibility: "Analyze Eligibility",
    followup: "Add follow-up",
    reopen: "Reopen case",
    new_case: "New Refund Claim",
  };
  const TONE_LABELS = { urgent: "Urgent", warn: "Needs attention", info: "Suggested", done: "No action needed" };

  // Strict YYYY-MM-DD -> Date at local midnight, or null if absent, malformed, or not a real calendar date.
  function parseDay(value) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(typeof value === "string" ? value.trim() : "");
    if (!m) return null;
    const d = new Date(+m[1], +m[2] - 1, +m[3]);
    return d.getFullYear() === +m[1] && d.getMonth() === +m[2] - 1 && d.getDate() === +m[3] ? d : null;
  }
  // Whole calendar days from `today` to `value` (negative = already passed); null if unreadable.
  function daysFromToday(value, today) {
    const d = parseDay(value);
    if (!d) return null;
    const now = today || new Date();
    return Math.round((d - new Date(now.getFullYear(), now.getMonth(), now.getDate())) / 86400000);
  }
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  function relative(n) {
    if (n === 0) return "today";
    if (n === 1) return "tomorrow";
    if (n === -1) return "yesterday";
    return n > 0 ? `in ${plural(n, "day")}` : `${plural(-n, "day")} ago`;
  }
  const statusLabel = (s) => String(s ?? "").replaceAll("_", " ");
  const text = (v) => (typeof v === "string" ? v.trim() : "");

  // Which details are too incomplete or unreadable to base a recommendation on.
  function missingCoreInfo(c, today) {
    const problems = [];
    if (!text(c.product_name)) problems.push("product name");
    if (!text(c.retailer)) problems.push("retailer");
    const n = daysFromToday(c.purchase_date, today);
    if (n === null) problems.push("purchase date (YYYY-MM-DD)");
    else if (n > 0) problems.push("purchase date (it is in the future)");
    if (text(c.issue_description).length < 5) problems.push("issue description");
    return problems;
  }

  // How the deadline should be described. Never uses the word "verified" for a deadline.
  function describeDeadline(c, today) {
    const n = daysFromToday(c.deadline, today);
    const closed = CLOSED.includes(c.status);
    if (n === null) {
      return { kind: "none", days: null, label: "No deadline established", date: null, relative: null,
               detail: c.deadline ? "A deadline is stored on this case but it could not be read." : "No return window is recorded for this case, so no deadline can be calculated." };
    }
    const confirmed = c.policy_confirmed === true;
    const base = { days: n, date: c.deadline.trim(), relative: relative(n) };
    if (closed) {
      return { ...base, kind: "closed", label: "Not tracked (case " + statusLabel(c.status) + ")",
               detail: confirmed ? "Date from a window you confirmed yourself. It is no longer tracked because the case is finished."
                                 : "Date from a window you entered but never confirmed. It is no longer tracked because the case is finished." };
    }
    if (confirmed) {
      return { ...base, kind: "confirmed", label: "Confirmed by you",
               detail: "You stated that you checked this window against the retailer's own policy. Refund Guardian has not verified it." };
    }
    return { ...base, kind: "unconfirmed", label: "Unconfirmed deadline",
             detail: "Based on a window you entered. You have not confirmed it against the retailer's own policy, and Refund Guardian does not verify retailer policies, so treat it as an estimate." };
  }

  function action(name, primary) { return { action: name, label: ACTION_LABELS[name], primary: !!primary }; }

  // options: { today?: Date, followups?: [{due_date, note, done}] }  -> recommendation model
  function recommendNextAction(c, options) {
    c = c || {};
    const today = (options && options.today) || new Date();
    const followups = Array.isArray(options && options.followups) ? options.followups : [];
    const pending = followups.filter((f) => f && !f.done && parseDay(f.due_date))
                             .sort((a, b) => a.due_date.localeCompare(b.due_date));
    const hasFollowup = followups.length > 0;
    const deadline = describeDeadline(c, today);
    const n = deadline.days;
    const dateText = deadline.date ? `${deadline.date} (${deadline.relative})` : "";
    const add = (list, name, primary) => list.push(action(name, primary));
    const model = (id, tone, title, summary, reasons, actions) => ({ id, tone, toneLabel: TONE_LABELS[tone], title, summary, reasons, deadline, actions });

    // 1. Finished cases: nothing to do.
    if (CLOSED.includes(c.status)) {
      return model("closed", "done", "No action needed right now", `This case is marked ${statusLabel(c.status)}.`, [
        `The status is ${statusLabel(c.status)}, so deadlines are no longer tracked.`,
        "If the problem comes back, you can reopen this case or start a new one.",
      ], [action("reopen", false)]);
    }

    // 2. Not enough reliable information to say anything useful.
    const missing = missingCoreInfo(c, today);
    if (missing.length) {
      return model("incomplete", "warn", "Complete the missing case details", `These details are missing or unreadable: ${missing.join(", ")}.`, [
        "Without them, deadlines and eligibility cannot be assessed reliably.",
        "Existing cases cannot be edited yet (only status and notes can change), so create a new case with the corrected details.",
      ], [action("new_case", true)]);
    }

    const optionalFollowup = (list) => { if (!hasFollowup) add(list, "followup", false); };

    // 3-5. Deadlines the user has confirmed.
    if (deadline.kind === "confirmed" && n < 0) {
      const actions = [action("draft", true), action("eligibility"), action("evidence")]; optionalFollowup(actions);
      return model("overdue_confirmed", "urgent", "Your confirmed window has passed - ask about other options",
        `You confirmed a window that ended on ${dateText}.`, [
          "A passed return window does not necessarily rule out other remedies, such as warranty or defective-product coverage. Whether any apply depends on the retailer's terms and the rules where you live, which Refund Guardian does not check.",
          "A written message gives you a record of what you asked and when.",
          "Analyze Eligibility lists the points worth raising.",
        ], actions);
    }
    if (deadline.kind === "confirmed" && n <= 3) {
      const actions = [action("draft", true), action("evidence")]; optionalFollowup(actions);
      return model("imminent_confirmed", "urgent", n === 0 ? "Last day of your confirmed window - contact the retailer today" : `Your confirmed window ends in ${plural(n, "day")} - contact the retailer now`,
        `The window you confirmed ends on ${dateText}.`, [
          "You confirmed this window yourself; Refund Guardian has not verified it, so re-check the retailer's policy if you are unsure.",
          "A message sent before the date leaves a record of when you asked.",
          "Have your receipt and photos of the problem ready.",
        ], actions);
    }
    if (deadline.kind === "confirmed" && n <= 7) {
      const actions = [action("evidence", true), action("draft")]; optionalFollowup(actions);
      return model("approaching_confirmed", "warn", "Your confirmed window ends this week - prepare your claim",
        `The window you confirmed ends on ${dateText}.`, [
          "There is still time, but little of it. Gathering evidence first makes the message to the retailer quicker to write.",
          "You confirmed this window yourself; Refund Guardian has not verified it.",
        ], actions);
    }

    // 6. A deadline exists but the user never confirmed the window.
    if (deadline.kind === "unconfirmed") {
      const soon = n <= 7;
      const actions = [action("eligibility", true), action("draft"), action("evidence")]; optionalFollowup(actions);
      return model("unconfirmed_deadline", soon ? "warn" : "info",
        n < 0 ? "Check whether this deadline has already passed" : "Check the retailer's policy before relying on this date",
        `The date ${dateText} comes from a window you entered, not one you confirmed.`, [
          "Refund Guardian does not look up or verify retailer policies, so this date is an estimate, not an established deadline.",
          n < 0 ? "If the window you entered is right, it may already have ended, so it is worth checking the policy promptly."
                : soon ? "If the window you entered is right, it ends soon, so check the policy first."
                       : "Checking the policy now avoids surprises later.",
          "To record a confirmed window, create a new case with the confirmation box ticked (existing cases cannot be edited yet).",
        ], actions);
    }

    // 7. No usable deadline at all.
    if (deadline.kind === "none") {
      const actions = [action("draft", true), action("evidence"), action("eligibility")]; optionalFollowup(actions);
      return model("no_deadline", "info", "Find out the return window", "No return window is recorded, so no deadline can be calculated.", [
        "Without a window, Refund Guardian cannot tell how much time you have.",
        "Check the retailer's return and warranty policy, or ask the retailer. The support draft asks them to explain the applicable process.",
      ], actions);
    }

    // 8-9. Confirmed deadline more than a week away: use the case status to pick the next step.
    if (c.status === "waiting_for_user") {
      const actions = [action("draft", true), action("evidence")]; optionalFollowup(actions);
      return model("waiting_for_user", "warn", "This case is waiting on you", `The case is marked waiting for user. Your confirmed window ends on ${dateText}.`, [
        "That status means the next step is yours.",
        "A reply, or the evidence the retailer asked for, moves the case forward.",
      ], actions);
    }
    if (c.status === "in_progress") {
      if (!hasFollowup) {
        return model("schedule_followup", "info", "Schedule a follow-up so this does not stall", `The case is in progress and has no follow-up scheduled. Your confirmed window ends on ${dateText}.`, [
          "A dated reminder helps you chase the retailer if you hear nothing.",
          "You confirmed the window yourself; Refund Guardian has not verified it.",
        ], [action("followup", true), action("draft"), action("evidence")]);
      }
      const next = pending[0] ? `Your next follow-up is on ${pending[0].due_date}.` : "A follow-up is already scheduled.";
      return model("follow_up", "info", "Follow up if you have not heard back", `The case is in progress. ${next}`, [
        "If the retailer has not replied, a polite follow-up message keeps the case moving.",
        `Your confirmed window ends on ${dateText}.`,
      ], [action("draft", true), action("evidence")]);
    }
    const actions = [action("evidence", true), action("draft"), action("eligibility")]; optionalFollowup(actions);
    return model("gather_evidence", "info", "Gather your evidence while there is time", `Your confirmed window ends on ${dateText}.`, [
      "Having the receipt, photos and any earlier messages ready makes the first message to the retailer easier to write.",
      "You confirmed the window yourself; Refund Guardian has not verified it.",
    ], actions);
  }

  // `esc` escapes text for HTML (passed in so this file stays DOM-free). Every model string is escaped.
  function renderNextAction(model, caseId, esc) {
    const headingId = `nba-heading-${Number(caseId)}`;
    const d = model.deadline;
    const dateLine = d.date ? `<span class="nba-dl-date">${esc(d.date)} · ${esc(d.relative)}</span>` : "";
    const buttons = model.actions.map((a) =>
      `<button type="button" class="nba-btn${a.primary ? " nba-btn-primary" : ""}" data-nba-action="${esc(a.action)}">${esc(a.label)}</button>`).join("");
    return `<section class="nba nba-${esc(model.tone)}" aria-labelledby="${headingId}">` +
      `<div class="nba-head"><span class="eyebrow">NEXT BEST ACTION</span><span class="nba-tone">${esc(model.toneLabel)}</span></div>` +
      `<h3 id="${headingId}">${esc(model.title)}</h3>` +
      `<p class="nba-summary">${esc(model.summary)}</p>` +
      `<div class="nba-deadline nba-deadline-${esc(d.kind)}"><span class="nba-dl-label">${esc(d.label)}</span>${dateLine}<p>${esc(d.detail)}</p></div>` +
      `<h4>Why this is suggested</h4><ul class="nba-reasons">${model.reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>` +
      (buttons ? `<div class="nba-actions" role="group" aria-label="Suggested actions">${buttons}</div>` : "") +
      `<p class="nba-note">A rule-based suggestion from the details saved on this case. It does not check any retailer policy and does not predict or guarantee a refund.</p>` +
      `</section>`;
  }

  const api = { ACTION_LABELS, TONE_LABELS, parseDay, daysFromToday, describeDeadline, missingCoreInfo,
                recommendNextAction, renderNextAction };
  if (typeof module === "object" && module.exports) module.exports = api; else root.RGNextAction = api;
})(typeof window !== "undefined" ? window : globalThis);
