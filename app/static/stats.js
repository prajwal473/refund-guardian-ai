/* Pure dashboard logic (no DOM access) so it can be unit-tested with Node as well as run in the browser. */
(function (root) {
  const ACTIVE_STATUSES = ["new", "in_progress", "waiting_for_user"];
  const isActive = (c) => ACTIVE_STATUSES.includes(c.status);

  // Whole calendar days from `today` to the YYYY-MM-DD string. Negative = already passed. null = unusable.
  function daysUntil(dateStr, today) {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(dateStr || "");
    if (!m) return null;
    const target = new Date(+m[1], +m[2] - 1, +m[3]);
    const now = today || new Date();
    const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    return Math.round((target - start) / 86400000);
  }

  // A deadline only counts as "confirmed" if the user said they checked the window against the retailer's policy.
  const isConfirmed = (c) => c.policy_confirmed === true;

  function computeStats(cases, today) {
    const stats = { total: cases.length, active: 0, resolved: 0,
                    dueSoonConfirmed: 0, dueSoonUnconfirmed: 0, overdueConfirmed: 0, overdueUnconfirmed: 0 };
    for (const c of cases) {
      if (!isActive(c)) { stats.resolved++; continue; }
      stats.active++;
      const n = daysUntil(c.deadline, today);
      if (n === null) continue;
      const tag = isConfirmed(c) ? "Confirmed" : "Unconfirmed";
      if (n < 0) stats["overdue" + tag]++;                 // overdue is never "due in 7 days"
      else if (n <= 7) stats["dueSoon" + tag]++;
    }
    return stats;
  }

  const api = { ACTIVE_STATUSES, isActive, isConfirmed, daysUntil, computeStats };
  if (typeof module === "object" && module.exports) module.exports = api; else root.RGStats = api;
})(typeof window !== "undefined" ? window : globalThis);
