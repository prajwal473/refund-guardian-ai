const $ = (s) => document.querySelector(s);
const form = $("#caseForm");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

async function api(url, options={}) {
  const res = await fetch(url, {headers:{"Content-Type":"application/json"}, ...options});
  const data = await res.json().catch(()=>({detail:"Unexpected response"}));
  if(!res.ok) {
    const d = data.detail;
    // FastAPI validation errors arrive as a list of {msg, loc} objects
    throw new Error(typeof d === "string" ? d : Array.isArray(d) ? d.map(x => x.msg).join("; ") : "Request failed");
  }
  return data;
}

/* ---------- UI helpers (presentation only) ---------- */
const { isActive, isConfirmed, daysUntil, computeStats } = window.RGStats;
const statusLabel = (s) => String(s ?? "").replaceAll("_", " ");
const money = (c) => `${esc(c.currency)} ${Number(c.purchase_price).toFixed(2)}`;
const badge = (status) => `<span class="badge badge-${esc(status)}">${esc(statusLabel(status))}</span>`;

function deadlineChip(c) {
  if (!c.deadline) return '<span class="dl dl-unknown">Unknown — verify policy</span>';
  if (!isActive(c)) return `<span class="dl dl-muted">${esc(c.deadline)}</span>`;
  const n = daysUntil(c.deadline);
  if (n === null) return `<span class="dl">${esc(c.deadline)}</span>`;
  let text = `in ${n} days`;
  if (n < 0) text = `${-n} day${n === -1 ? "" : "s"} past`;
  else if (n === 0) text = "today";
  else if (n === 1) text = "tomorrow";
  if (!isConfirmed(c)) {
    // Not an established deadline: the user has not confirmed the window against the retailer's policy.
    return `<span class="dl dl-unconfirmed" title="Based on a window you entered but have not confirmed against the retailer's own policy">${esc(c.deadline)} · ${text} · unconfirmed</span>`;
  }
  let cls = "dl-ok";
  if (n < 0) { cls = "dl-bad"; text = `overdue by ${-n} day${n === -1 ? "" : "s"}`; }
  else if (n <= 3) cls = "dl-bad";
  else if (n <= 7) cls = "dl-warn";
  return `<span class="dl ${cls}">${esc(c.deadline)} · ${text}</span>`;
}

let toastTimer;
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 3200);
}

/* ---------- New claim drawer ---------- */
function openDrawer() {
  $("#claimDrawer").classList.add("open");
  $("#drawerOverlay").classList.add("open");
  $("#claimDrawer").setAttribute("aria-hidden", "false");
  setTimeout(() => form.elements.product_name.focus(), 250);
}
function closeDrawer() {
  $("#claimDrawer").classList.remove("open");
  $("#drawerOverlay").classList.remove("open");
  $("#claimDrawer").setAttribute("aria-hidden", "true");
}
document.addEventListener("click", (e) => { if (e.target.closest(".js-open-drawer")) openDrawer(); });
$("#closeDrawer").addEventListener("click", closeDrawer);
$("#drawerOverlay").addEventListener("click", closeDrawer);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });

document.querySelectorAll(".nav-link").forEach(a => a.addEventListener("click", () => {
  document.querySelectorAll(".nav-link").forEach(x => x.classList.remove("active"));
  a.classList.add("active");
}));

/* ---------- Form (existing behavior preserved) ---------- */
function formObj() { return Object.fromEntries(new FormData(form).entries()); }
$("#demoBtn").addEventListener("click", () => {
  const d = new Date(); d.setDate(d.getDate()-8);
  form.elements.product_name.value = "Wireless headphones";
  form.elements.retailer.value = "Example Electronics";
  form.elements.purchase_date.value = d.toISOString().slice(0,10);
  form.elements.purchase_price.value = "2999";
  form.elements.currency.value = "INR";
  form.elements.issue_description.value = "The headphones disconnect every few minutes during normal use.";
  form.elements.policy_days.value = "10";
  form.elements.policy_source.value = "DEMO ONLY — illustrative 10-day window, not a real retailer policy";
  form.elements.policy_confirmed.checked = false;
  $("#formMessage").textContent = "Demo data loaded. The policy window is illustrative; verify real policies before relying on a deadline.";
});
form.addEventListener("submit", async (e) => {
  e.preventDefault(); $("#formMessage").textContent = "Creating case…";
  const data = formObj();
  data.purchase_price = Number(data.purchase_price);
  data.policy_days = data.policy_days === "" ? null : Number(data.policy_days);
  data.policy_source = data.policy_source || null;
  data.policy_confirmed = form.elements.policy_confirmed.checked;
  try {
    const result = await api("/api/cases", {method:"POST",body:JSON.stringify(data)});
    $("#formMessage").textContent = `Case #${result.id} created.`;
    await loadCases(); await openCase(result.id); form.reset();
    closeDrawer();
    toast(`Case #${result.id} created.`);
  } catch(err) { $("#formMessage").textContent = err.message; }
});

/* ---------- Receipt text parser (uses existing POST /api/receipt/parse-text) ---------- */
$("#parseReceiptBtn").addEventListener("click", async () => {
  const msg = $("#receiptMessage");
  const text = $("#receiptText").value.trim();
  if (!text) { msg.textContent = "Paste some receipt text first."; return; }
  msg.textContent = "Extracting…";
  try {
    const r = await api("/api/receipt/parse-text", {method:"POST", body:JSON.stringify({text})});
    const found = [];
    for (const key of ["product_name", "retailer", "purchase_date", "purchase_price", "currency"]) {
      if (r[key] !== undefined && r[key] !== null && form.elements[key]) {
        form.elements[key].value = r[key]; found.push(key.replaceAll("_", " "));
      }
    }
    const warnings = (r.warnings || []).join(" ");
    msg.textContent = (found.length ? `Filled: ${found.join(", ")}. ` : "Nothing recognised. Use lines like “Product: …”, “Retailer: …”, “Date: YYYY-MM-DD”, “Total: …”. ") + warnings + (warnings ? " " : "") + (r.parser_note || "");
  } catch(err) { msg.textContent = err.message; }
});

$("#refreshBtn").addEventListener("click", loadCases);
$("#closeDetail").addEventListener("click", () => $("#detailPanel").classList.add("hidden"));

/* ---------- Dashboard rendering ---------- */
function renderStats(cases) {
  const set = (id, v) => { $(id).textContent = v; };
  if (!cases) { ["#statTotal", "#statActive", "#statDue", "#statResolved"].forEach(i => set(i, "–")); return; }
  const st = computeStats(cases);
  set("#statTotal", st.total);
  set("#statActive", st.active);
  set("#statDue", st.dueSoonConfirmed);          // confirmed deadlines only; overdue cases are never counted here
  set("#statResolved", st.resolved);
  const parts = ["Confirmed deadlines only"];
  if (st.dueSoonUnconfirmed) parts.push(`${st.dueSoonUnconfirmed} unconfirmed not counted`);
  const overdue = st.overdueConfirmed + st.overdueUnconfirmed;
  if (overdue) parts.push(`${overdue} past due`);
  set("#statDueSub", parts.join(" · "));
}

function renderDeadlines(cases) {
  const box = $("#deadlineList");
  const items = cases
    .filter(c => isActive(c) && c.deadline && daysUntil(c.deadline) !== null)
    .sort((a, b) => a.deadline.localeCompare(b.deadline))
    .slice(0, 6);
  if (!items.length) {
    box.innerHTML = '<div class="empty empty-rich"><div class="empty-icon">⏱</div><strong>No upcoming deadlines</strong><span>Add a return window to a case and its date will appear here.</span></div>';
    return;
  }
  box.innerHTML = items.map(c => `<div class="dl-item" data-id="${c.id}" tabindex="0" role="button"><div><div class="dl-title">${esc(c.product_name)}</div><div class="case-meta">${esc(c.retailer)} · Case #${c.id}</div></div>${deadlineChip(c)}</div>`).join("");
  if (items.some(c => !isConfirmed(c))) box.insertAdjacentHTML("beforeend", '<p class="case-meta">Dates marked <em>unconfirmed</em> come from a window you have not confirmed against the retailer’s own policy. Treat them as reminders, not entitlements.</p>');
  box.querySelectorAll("[data-id]").forEach(el => {
    el.addEventListener("click", () => openCase(Number(el.dataset.id)));
    el.addEventListener("keydown", (e) => { if (e.key === "Enter") openCase(Number(el.dataset.id)); });
  });
}

async function loadCases() {
  const list = $("#caseList");
  list.innerHTML = '<div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div>';
  try {
    const cases = await api("/api/cases");
    renderStats(cases);
    renderDeadlines(cases);
    if(!cases.length){
      list.innerHTML = '<div class="empty empty-rich"><div class="empty-icon">🛡</div><strong>No cases yet</strong><span>Load the demo or create your first refund claim.</span><button type="button" class="btn-new js-open-drawer">New Refund Claim</button></div>';
      return;
    }
    list.innerHTML = `<div class="table-wrap"><table class="claims-table"><thead><tr><th>Case</th><th>Amount</th><th>Deadline</th><th>Status</th></tr></thead><tbody>${cases.map(c=>`<tr data-id="${c.id}" tabindex="0"><td data-label="Case"><div class="case-title">${esc(c.product_name)}</div><div class="case-meta">${esc(c.retailer)} · Case #${c.id}<br>Purchased ${esc(c.purchase_date)}</div></td><td data-label="Amount">${money(c)}</td><td data-label="Deadline">${deadlineChip(c)}</td><td data-label="Status">${badge(c.status)}</td></tr>`).join("")}</tbody></table></div>`;
    list.querySelectorAll("[data-id]").forEach(el => {
      el.addEventListener("click", () => openCase(Number(el.dataset.id)));
      el.addEventListener("keydown", (e) => { if (e.key === "Enter") openCase(Number(el.dataset.id)); });
    });
  } catch(err){
    renderStats(null);
    list.innerHTML = `<div class="empty">${esc(err.message)}</div>`;
    $("#deadlineList").innerHTML = '<div class="empty">Could not load deadlines.</div>';
  }
}

/* ---------- Eligibility analysis rendering ---------- */
const ulist = (items) => items && items.length ? `<ul>${items.map(i=>`<li>${esc(i)}</li>`).join("")}</ul>` : "";
const POLICY_STATUS_TEXT = {
  user_confirmed: "Confirmed by you (not checked by Refund Guardian)",
  unconfirmed: "Not confirmed",
  missing: "No return window recorded",
  not_evaluated: "Not evaluated",
};
function renderEligibility(r) {
  const days = r.days_remaining;
  const when = days === null || days === undefined ? "" : days > 0 ? `${days} day${days===1?"":"s"} remaining` : days === 0 ? "last day" : `passed ${-days} day${days===-1?"":"s"} ago`;
  const ai = r.ai_explanation
    ? `<div class="elig-ai"><small>AI-GENERATED EXPLANATION · for readability only; the rule-based result above is what counts</small>${esc(r.ai_explanation)}</div>`
    : "";
  const note = r.llm_note ? `<p class="case-meta">${esc(r.llm_note)}</p>` : "";
  return `<div class="elig elig-${esc(r.outcome)}">
    <div class="elig-head"><h3>Eligibility analysis</h3><span class="elig-pill">${esc(r.outcome_label)}</span></div>
    <p class="elig-text">${esc(r.explanation)}</p>
    <div class="elig-facts">
      <div class="detail-box"><small>POLICY</small>${esc(POLICY_STATUS_TEXT[r.policy_status] || "Unknown")}</div>
      <div class="detail-box"><small>DEADLINE</small>${r.deadline ? esc(r.deadline) : "Not established"}${when ? `<br>${esc(when)}${r.policy_status === "user_confirmed" ? "" : " (unconfirmed)"}` : ""}</div>
      <div class="detail-box"><small>METHOD</small>${r.analysis_method === "rule_based" ? "Rule-based" : "Rule-based + AI explanation"}<br>as of ${esc(r.as_of)}</div>
    </div>
    ${ai}${note}
    ${r.missing_information.length ? `<h4>Missing or unverified information</h4>${ulist(r.missing_information)}` : ""}
    <h4>Recommended next steps</h4>${ulist(r.recommended_next_steps)}
    <h4>Caveats</h4>${ulist(r.caveats)}
  </div>`;
}

async function openCase(id) {
  try {
    const c = await api(`/api/cases/${id}`);
    const followups = await api(`/api/cases/${id}/followups`);
    $("#detailTitle").textContent = `#${c.id} · ${c.product_name}`;
    $("#detailPanel").classList.remove("hidden");
    $("#detailContent").innerHTML = `
      <div class="detail-grid">
        <div class="detail-box"><small>ISSUE</small>${esc(c.issue_description)}</div>
        <div class="detail-box"><small>DEADLINE / POLICY</small>${c.deadline ? esc(c.deadline) + (c.policy_confirmed ? " (confirmed by you)" : " (unconfirmed)") : "Not established — verify terms first"}\n${esc(c.policy_source || "No policy source recorded")}</div>
        <div class="detail-box"><small>PURCHASE</small>${esc(c.retailer)} · ${esc(c.purchase_date)}\n${money(c)}</div>
        <div class="detail-box"><small>STATUS</small>${badge(c.status)}</div>
      </div>
      <div class="actions">
        <button id="draftBtn">Generate support draft</button>
        <button id="eligibilityBtn">Analyze Eligibility</button>
        <button id="followBtn">Add follow-up</button>
        <button id="progressBtn">Mark in progress</button>
        <button id="resolveBtn">Mark resolved</button>
      </div>
      <div id="draftResult"></div>
      <div id="eligibilityResult" aria-live="polite"></div>
      <h3>Follow-ups</h3>
      <div class="case-list">${followups.length ? followups.map(f=>`<div class="detail-box"><small>${esc(f.due_date)}</small>${esc(f.note)} · ${f.done ? "Done" : "Pending"}</div>`).join("") : '<div class="empty">No follow-ups scheduled.</div>'}</div>`;
    $("#draftBtn").onclick = async()=>{try{const d=await api(`/api/cases/${id}/draft`,{method:"POST"});$("#draftResult").innerHTML=`<h3>Support message draft</h3><div class="detail-box">${esc(d.draft)}</div><p class="case-meta">${esc(d.warning)}</p>`;}catch(e){toast(e.message)}};
    $("#eligibilityBtn").onclick = async()=>{
      const btn=$("#eligibilityBtn"), out=$("#eligibilityResult"), label=btn.textContent;
      btn.disabled=true; btn.textContent="Analyzing…";
      out.innerHTML='<div class="elig elig-loading"><div class="skeleton"></div><div class="skeleton"></div></div>';
      try{ out.innerHTML=renderEligibility(await api(`/api/cases/${id}/eligibility`,{method:"POST",body:JSON.stringify({})})); }
      catch(e){ out.innerHTML=`<div class="elig elig-error" role="alert"><strong>Eligibility analysis failed.</strong><br>${esc(e.message)}</div>`; }
      finally{ btn.disabled=false; btn.textContent=label; }
    };
    $("#followBtn").onclick = async()=>{const due=prompt("Follow-up date (YYYY-MM-DD):");if(!due)return;const note=prompt("What should you follow up on?");if(!note)return;try{await api(`/api/cases/${id}/followups`,{method:"POST",body:JSON.stringify({due_date:due,note})});await openCase(id);toast("Follow-up scheduled.");}catch(e){alert(e.message)}};
    $("#progressBtn").onclick = async()=>{try{await api(`/api/cases/${id}`,{method:"PATCH",body:JSON.stringify({status:"in_progress"})});await loadCases();await openCase(id);}catch(e){toast(e.message)}};
    $("#resolveBtn").onclick = async()=>{if(!confirm("Mark this case resolved? Only do this if it is actually resolved."))return;try{await api(`/api/cases/${id}`,{method:"PATCH",body:JSON.stringify({status:"resolved"})});await loadCases();await openCase(id);}catch(e){toast(e.message)}};
    $("#detailPanel").scrollIntoView({behavior:"smooth",block:"start"});
  } catch(err){alert(err.message);}
}
loadCases();
