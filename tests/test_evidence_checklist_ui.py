"""Frontend tests for the evidence checklist. The display logic lives in app/static/evidence.js (pure
functions) and is run with Node, so no browser or extra Python dependency is needed. The Node-based tests
are skipped if Node is not installed. These tests do NOT call the backend; the response used below is the
shape documented for POST /api/cases/{case_id}/evidence-checklist."""
import json
import pathlib
import re
import shutil
import subprocess

import pytest

STATIC = pathlib.Path(__file__).resolve().parents[1] / "app" / "static"
NODE = shutil.which("node")
SCRIPT = ("const m=require(process.argv[1]);"
          "const esc=(s)=>String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));"
          "const input=JSON.parse(require('fs').readFileSync(0,'utf8'));"
          "console.log(JSON.stringify(new Function('m','esc','input','return ('+process.argv[2]+')')(m,esc,input)));")

DOCUMENTED = {
    "case_id": 8,
    "suggested_evidence": [
        {"item": "Purchase receipt or order confirmation", "reason": "Helps establish the purchase date and product details."},
        {"item": "Description of the issue", "reason": "Helps explain the problem to the retailer."},
        {"item": "Previous communication with the retailer", "reason": "Provides context if you have already contacted support."},
    ],
    "warning": "These are general suggestions, not mandatory requirements. Check the retailer's actual policy for required evidence.",
}


def js(expression, payload=None):
    if not NODE:
        pytest.skip("node is not installed")
    out = subprocess.run([NODE, "-e", SCRIPT, str(STATIC / "evidence.js"), expression], input=json.dumps(payload),
                         capture_output=True, text=True, timeout=30, check=True)
    return json.loads(out.stdout)


def render(payload, case_id=8):
    return js(f"m.renderEvidenceChecklist(m.normalizeEvidenceResponse(input,{case_id}),{case_id},esc)", payload)


def test_documented_response_is_normalised():
    model = js("m.normalizeEvidenceResponse(input, 8)", DOCUMENTED)
    assert model["status"] == "ok"
    assert [i["item"] for i in model["items"]][0] == "Purchase receipt or order confirmation"
    assert len(model["items"]) == 3 and model["warning"].startswith("These are general suggestions")


def test_rendered_checklist_shows_every_item_reason_and_the_warning_first():
    html = render(DOCUMENTED)
    for entry in DOCUMENTED["suggested_evidence"]:
        assert entry["item"] in html and entry["reason"] in html
    assert 'role="note"' in html and "Please note" in html
    assert DOCUMENTED["warning"].replace("'", "&#39;") in html
    assert html.index('role="note"') < html.index('<ul class="evidence-list">')      # warning is seen before the list
    assert html.count('<li class="evidence-item">') == 3


def test_markup_is_accessible():
    html = render(DOCUMENTED)
    assert '<h3 id="evidence-heading-8">' in html and 'aria-labelledby="evidence-heading-8"' in html
    assert "<section" in html and "<ul" in html                                    # real list semantics
    assert 'aria-hidden="true"' in html                                           # decorative icon hidden from screen readers
    loading = js("m.renderEvidenceLoading()", None)
    assert "sr-only" in loading and "Generating evidence checklist" in loading
    assert js("m.renderEvidenceError('Boom', esc)", None).count('role="alert"') == 1


def test_empty_suggestions_show_an_empty_state_and_still_show_the_warning():
    for payload in ({**DOCUMENTED, "suggested_evidence": []},
                    {**DOCUMENTED, "suggested_evidence": [{"item": "  "}, {"reason": "no item"}, None, "text", 5]}):
        assert js("m.normalizeEvidenceResponse(input, 8)", payload)["status"] == "empty"
        html = render(payload)
        assert "No evidence suggestions were returned" in html and 'role="note"' in html and "<li" not in html


def test_unusable_responses_are_invalid():
    for payload in (None, {}, [], "ok", 5, {"case_id": 8}, {"case_id": 8, "suggested_evidence": None},
                    {"case_id": 8, "suggested_evidence": "receipt"}, {"detail": "Unexpected response"}):
        assert js("m.normalizeEvidenceResponse(input, 8)", payload)["status"] == "invalid", payload


def test_response_for_a_different_case_is_rejected():
    assert js("m.normalizeEvidenceResponse(input, 9)", DOCUMENTED)["status"] == "invalid"
    assert js("m.normalizeEvidenceResponse(input, 8)", {**DOCUMENTED, "case_id": "8"})["status"] == "ok"


def test_reason_is_optional_and_text_is_trimmed():
    payload = {"case_id": 8, "suggested_evidence": [{"item": "  Receipt  "}, {"item": "Photos", "reason": 7}], "warning": "Note"}
    model = js("m.normalizeEvidenceResponse(input, 8)", payload)
    assert [(i["item"], i["reason"]) for i in model["items"]] == [("Receipt", ""), ("Photos", "")]
    assert "evidence-reason" not in render(payload)


def test_missing_warning_falls_back_to_a_cautious_default():
    html = render({"case_id": 8, "suggested_evidence": [{"item": "Receipt", "reason": "Shows purchase."}]})
    assert 'role="note"' in html and "general suggestions only" in html and "Check the retailer" in html


def test_server_text_is_html_escaped():
    nasty = {"case_id": 8, "warning": "<b>warn</b>", "suggested_evidence": [
        {"item": "<img src=x onerror=alert(1)>", "reason": '"><script>alert(2)</script>'}]}
    html = render(nasty)
    for raw in ("<img", "<script", "<b>"):
        assert raw not in html, raw
    assert "&lt;img" in html and "&lt;script" in html
    assert "<script" not in js("m.renderEvidenceError(input, esc)", "<script>x</script>")


def test_static_copy_never_calls_the_list_mandatory_or_promises_an_outcome():
    neutral = {"case_id": 8, "warning": "Warning text.", "suggested_evidence": [{"item": "Receipt", "reason": "Shows purchase."}]}
    copy = " ".join([render(neutral), render({**neutral, "suggested_evidence": []}),
                     js("m.renderEvidenceChecklist({status:'ok',items:[{item:'A',reason:''}],warning:null},8,esc)", None)])
    assert not re.search(r"\b(must|mandatory|guarantee[sd]?|will be refunded|you need to|required to)\b", copy, re.I), copy
    assert "not requirements" in copy


def test_error_messages_are_specific():
    msg = lambda err: js("m.describeEvidenceError(input)", err)
    assert "could not be found" in msg({"status": 404, "message": "Case not found"})
    assert "Could not reach the server" in msg({"name": "TypeError", "message": "Failed to fetch"})
    assert msg({"status": 500, "message": "Evidence checklist failed."}) == "Evidence checklist failed."
    assert "could not read" in msg({"kind": "invalid"})
    assert msg({}) == "Something went wrong. Please try again."
    assert msg(None) == "Something went wrong. Please try again."


def test_request_gate_blocks_duplicates_per_case_and_reopens_after_finish():
    result = js("(()=>{const g=m.createRequestGate();const a=g.tryStart(1),b=g.tryStart(1),c=g.tryStart(2);"
                "const midway=[g.isRunning(1),g.isRunning(2)];g.finish(1);return [a,b,c,midway,g.isRunning(1),g.tryStart(1)];})()", None)
    assert result == [True, False, True, [True, True], False, True]


def test_button_label():
    assert js("m.LABEL", None) == "Generate Evidence Checklist"


# ---------------- wiring (plain text checks; no Node needed) ----------------
def test_index_loads_the_modules_before_app_js():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    order = [html.index(f'/static/{name}.js') for name in ("stats", "evidence", "app")]
    assert order == sorted(order)


def test_app_js_uses_the_documented_endpoint_with_post_and_the_gate():
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "/api/cases/${id}/evidence-checklist" in source and 'method: "POST"' in source
    assert "if (!evidenceGate.tryStart(id)) return;" in source          # the guard that stops duplicate requests
    assert "evidenceGate.finish(id)" in source and 'id="evidenceBtn"' in source
    assert "Generate Evidence Checklist" in source
