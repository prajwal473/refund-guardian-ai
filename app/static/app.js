const $ = (s) => document.querySelector(s);
const form = $("#caseForm");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
async function api(url, options={}) {
  const res = await fetch(url, {headers:{"Content-Type":"application/json"}, ...options});
  const data = await res.json().catch(()=>({detail:"Unexpected response"}));
  if(!res.ok) throw new Error(data.detail || "Request failed");
  return data;
}
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
  $("#formMessage").textContent = "Demo data loaded. The policy window is illustrative; verify real policies before relying on a deadline.";
});
form.addEventListener("submit", async (e) => {
  e.preventDefault(); $("#formMessage").textContent = "Creating case…";
  const data = formObj();
  data.purchase_price = Number(data.purchase_price);
  data.policy_days = data.policy_days === "" ? null : Number(data.policy_days);
  data.policy_source = data.policy_source || null;
  try {
    const result = await api("/api/cases", {method:"POST",body:JSON.stringify(data)});
    $("#formMessage").textContent = `Case #${result.id} created.`;
    await loadCases(); await openCase(result.id); form.reset();
  } catch(err) { $("#formMessage").textContent = err.message; }
});
$("#refreshBtn").addEventListener("click", loadCases);
$("#closeDetail").addEventListener("click", () => $("#detailPanel").classList.add("hidden"));
async function loadCases() {
  const list = $("#caseList"); list.innerHTML = '<div class="empty">Loading…</div>';
  try {
    const cases = await api("/api/cases");
    if(!cases.length){list.innerHTML='<div class="empty">No cases yet.<br>Load the demo or create your first case.</div>';return;}
    list.innerHTML = cases.map(c=>`<div class="case-card" data-id="${c.id}"><div class="case-title">${esc(c.product_name)} · ${esc(c.retailer)}</div><div class="case-meta">Case #${c.id} · ${esc(c.purchase_date)} · ${esc(c.currency)} ${Number(c.purchase_price).toFixed(2)}<br>Deadline: ${c.deadline ? esc(c.deadline) : "Unknown — verify policy"}</div><span class="badge">${esc(c.status.replaceAll("_"," "))}</span></div>`).join("");
    list.querySelectorAll("[data-id]").forEach(el=>el.addEventListener("click",()=>openCase(Number(el.dataset.id))));
  } catch(err){list.innerHTML=`<div class="empty">${esc(err.message)}</div>`;}
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
        <div class="detail-box"><small>DEADLINE / POLICY</small>${c.deadline ? esc(c.deadline) : "Not established — verify terms first"}\n${esc(c.policy_source || "No policy source recorded")}</div>
      </div>
      <div class="actions">
        <button id="draftBtn">Generate support draft</button>
        <button id="followBtn">Add follow-up</button>
        <button id="progressBtn">Mark in progress</button>
        <button id="resolveBtn">Mark resolved</button>
      </div>
      <div id="draftResult"></div>
      <h3>Follow-ups</h3>
      <div class="case-list">${followups.length ? followups.map(f=>`<div class="detail-box"><small>${esc(f.due_date)}</small>${esc(f.note)} · ${f.done ? "Done" : "Pending"}</div>`).join("") : '<div class="empty">No follow-ups scheduled.</div>'}</div>`;
    $("#draftBtn").onclick = async()=>{const d=await api(`/api/cases/${id}/draft`,{method:"POST"});$("#draftResult").innerHTML=`<h3>Support message draft</h3><div class="detail-box">${esc(d.draft)}</div><p class="case-meta">${esc(d.warning)}</p>`;};
    $("#followBtn").onclick = async()=>{const due=prompt("Follow-up date (YYYY-MM-DD):");if(!due)return;const note=prompt("What should you follow up on?");if(!note)return;try{await api(`/api/cases/${id}/followups`,{method:"POST",body:JSON.stringify({due_date:due,note})});await openCase(id);}catch(e){alert(e.message)}};
    $("#progressBtn").onclick = async()=>{await api(`/api/cases/${id}`,{method:"PATCH",body:JSON.stringify({status:"in_progress"})});await loadCases();await openCase(id);};
    $("#resolveBtn").onclick = async()=>{if(!confirm("Mark this case resolved? Only do this if it is actually resolved."))return;await api(`/api/cases/${id}`,{method:"PATCH",body:JSON.stringify({status:"resolved"})});await loadCases();await openCase(id);};
    $("#detailPanel").scrollIntoView({behavior:"smooth",block:"start"});
  } catch(err){alert(err.message);}
}
loadCases();
