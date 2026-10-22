"""Tests for the "Next Best Action" panel.

The recommendation rules and the HTML rendering live in app/static/next_action.js (pure functions, no DOM),
and are run with Node, so no browser or extra Python dependency is needed. Tests that need Node are skipped
if Node is not installed. A few plain-text checks confirm the wiring in index.html and app.js.
These tests never call the backend: the panel only uses the case (and follow-ups) that openCase() already loaded.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
from datetime import date, timedelta

import pytest

STATIC = pathlib.Path(__file__).resolve().parents[1] / "app" / "static"
NODE = shutil.which("node")
SCRIPT = ("const m=require(process.argv[1]);"
          "const esc=(s)=>String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));"
          "const T=(a)=>new Date(a[0],a[1]-1,a[2],a[3]||0,a[4]||0);"
          "const input=JSON.parse(require('fs').readFileSync(0,'utf8'));"
          "console.log(JSON.stringify(new Function('m','esc','T','input','return ('+process.argv[2]+')')(m,esc,T,input)));")

TODAY = date(2026, 10, 22)
TODAY_ARGS = [2026, 10, 22]
BASE = {"id": 1, "status": "new", "product_name": "Headphones", "retailer": "Shop", "purchase_date": "2026-10-15",
        "issue_description": "Audio cuts out often", "policy_days": 30, "policy_source": "Shop returns page",
        "policy_confirmed": True, "deadline": "2026-11-14"}


def js(expression, payload=None, tz=None):
    if not NODE:
        pytest.skip("node is not installed")
    env = {**os.environ, **({"TZ": tz} if tz else {})}
    out = subprocess.run([NODE, "-e", SCRIPT, str(STATIC / "next_action.js"), expression], input=json.dumps(payload),
                         capture_output=True, text=True, timeout=60, check=True, env=env)
    return json.loads(out.stdout)


def case(offset=None, **over):
    """A case whose deadline is `offset` days from TODAY (None keeps BASE's deadline)."""
    c = {**BASE, **over}
    if offset is not None:
        c["deadline"] = (TODAY + timedelta(days=offset)).isoformat()
    return c


def recommend_all(items):
    """items: [(case, followups)] -> models (one Node call)."""
    payload = [{"c": c, "f": f, "t": TODAY_ARGS} for c, f in items]
    return js("input.map(x=>m.recommendNextAction(x.c,{today:T(x.t),followups:x.f}))", payload)


def recommend(c, followups=None):
    return recommend_all([(c, followups or [])])[0]


def primary(model):
    found = [a["action"] for a in model["actions"] if a["primary"]]
    return found[0] if found else None


def render(model, case_id=1):
    return js("m.renderNextAction(input,%d,esc)" % case_id, model)


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from strings(v)


# ---------------- the rule table ----------------
RULES = [
    # label, case, followups, expected id, tone, primary action
    ("confirmed, far away, new", case(30), [], "gather_evidence", "info", "evidence"),
    ("confirmed, 8 days", case(8), [], "gather_evidence", "info", "evidence"),
    ("confirmed, 7 days", case(7), [], "approaching_confirmed", "warn", "evidence"),
    ("confirmed, 4 days", case(4), [], "approaching_confirmed", "warn", "evidence"),
    ("confirmed, 3 days", case(3), [], "imminent_confirmed", "urgent", "draft"),
    ("confirmed, tomorrow", case(1), [], "imminent_confirmed", "urgent", "draft"),
    ("confirmed, today", case(0), [], "imminent_confirmed", "urgent", "draft"),
    ("confirmed, yesterday", case(-1), [], "overdue_confirmed", "urgent", "draft"),
    ("confirmed, long overdue", case(-40), [], "overdue_confirmed", "urgent", "draft"),
    ("unconfirmed, far away", case(30, policy_confirmed=False), [], "unconfirmed_deadline", "info", "eligibility"),
    ("unconfirmed, 5 days", case(5, policy_confirmed=False), [], "unconfirmed_deadline", "warn", "eligibility"),
    ("unconfirmed, today", case(0, policy_confirmed=False), [], "unconfirmed_deadline", "warn", "eligibility"),
    ("unconfirmed, passed", case(-3, policy_confirmed=False), [], "unconfirmed_deadline", "warn", "eligibility"),
    ("no window recorded", case(None, policy_days=None, deadline=None, policy_confirmed=False), [], "no_deadline", "info", "draft"),
    ("deadline text unreadable", case(None, deadline="not-a-date"), [], "no_deadline", "info", "draft"),
    ("waiting for user, far away", case(30, status="waiting_for_user"), [], "waiting_for_user", "warn", "draft"),
    ("waiting for user, 2 days left", case(2, status="waiting_for_user"), [], "imminent_confirmed", "urgent", "draft"),
    ("in progress, no follow-up", case(30, status="in_progress"), [], "schedule_followup", "info", "followup"),
    ("in progress, has follow-up", case(30, status="in_progress"), [{"due_date": "2026-10-30", "note": "x", "done": 0}], "follow_up", "info", "draft"),
    ("resolved", case(30, status="resolved"), [], "closed", "done", None),
    ("closed and overdue", case(-9, status="closed"), [], "closed", "done", None),
    ("resolved, even with bad data", case(30, status="resolved", issue_description=""), [], "closed", "done", None),
    ("blank issue", case(30, issue_description=""), [], "incomplete", "warn", "new_case"),
    ("future purchase date", case(30, purchase_date="2026-12-01"), [], "incomplete", "warn", "new_case"),
    ("confirmation flag must be a real boolean", case(30, policy_confirmed=1), [], "unconfirmed_deadline", "info", "eligibility"),
]


def test_rule_table():
    models = recommend_all([(c, f) for _, c, f, *_ in RULES])
    for (label, _, _, rule_id, tone, main), model in zip(RULES, models):
        assert model["id"] == rule_id, (label, model["id"])
        assert model["tone"] == tone, (label, model["tone"])
        assert primary(model) == main, (label, primary(model))


def test_deadline_day_boundaries_use_whole_calendar_days():
    ids = {off: m["id"] for off, m in zip(range(-2, 11), recommend_all([(case(o), []) for o in range(-2, 11)]))}
    assert ids[-2] == ids[-1] == "overdue_confirmed"
    assert ids[0] == ids[1] == ids[2] == ids[3] == "imminent_confirmed"
    assert ids[4] == ids[5] == ids[6] == ids[7] == "approaching_confirmed"
    assert ids[8] == ids[9] == ids[10] == "gather_evidence"


def test_time_of_day_and_daylight_saving_do_not_shift_day_counts():
    late = js("m.daysFromToday('2026-10-23', T([2026,10,22,23,59]))")
    early = js("m.daysFromToday('2026-10-23', T([2026,10,22,0,1]))")
    assert late == early == 1
    # US clocks change on 2026-03-08; the next calendar day must still be exactly 1 day away
    assert js("m.daysFromToday('2026-03-09', T([2026,3,8,12,0]))", tz="America/New_York") == 1
    assert js("m.daysFromToday('2026-11-02', T([2026,11,1,12,0]))", tz="America/New_York") == 1


# ---------------- deadline honesty ----------------
def test_unconfirmed_deadline_is_never_presented_as_confirmed():
    for model in recommend_all([(case(o, policy_confirmed=False), []) for o in (-5, 0, 3, 20)]):
        d = model["deadline"]
        assert d["kind"] == "unconfirmed" and d["label"] == "Unconfirmed deadline"
        assert "Confirmed by you" not in " ".join(strings(model))
        assert "estimate" in d["detail"] and "not confirmed" in d["detail"]


def test_confirmed_deadline_says_confirmed_by_you_and_never_verified():
    d = recommend(case(10))["deadline"]
    assert d["kind"] == "confirmed" and d["label"] == "Confirmed by you"
    assert "has not verified it" in d["detail"]


def test_no_deadline_and_closed_labels():
    none = recommend(case(None, policy_days=None, deadline=None, policy_confirmed=False))["deadline"]
    assert none["kind"] == "none" and none["label"] == "No deadline established" and none["date"] is None
    assert "No return window" in none["detail"]
    closed = recommend(case(10, status="resolved"))["deadline"]
    assert closed["kind"] == "closed" and "resolved" in closed["label"] and "no longer tracked" in closed["detail"]


def test_unreadable_deadline_values_are_treated_as_no_deadline():
    for bad in ("2026-13-45", "2026-02-30", "2026-10-22T10:00", "22/10/2026", "<img src=x onerror=alert(1)>", "", 20261022, ["2026-10-22"]):
        model = recommend(case(None, deadline=bad))
        assert model["deadline"]["kind"] == "none", bad
        assert model["id"] == "no_deadline", bad


def test_the_word_verified_is_never_used_as_a_claim_and_no_outcome_is_promised():
    grid, labels = [], []
    for status in ("new", "in_progress", "waiting_for_user", "resolved", "closed"):
        for offset in (-10, 0, 2, 6, 20, None):
            for confirmed in (True, False):
                for followups in ([], [{"due_date": "2026-11-01", "note": "x", "done": 0}]):
                    grid.append((case(offset, status=status, policy_confirmed=confirmed), followups))
    models = recommend_all(grid)
    assert len(models) == 5 * 6 * 2 * 2
    allowed = ("has not verified", "does not verify", "does not look up or verify")
    for model, html in zip(models, js("input.map(x=>m.renderNextAction(x,1,esc))", models)):
        text = " ".join(strings(model)) + " " + re.sub(r"<[^>]+>", " ", html)
        for phrase in allowed:
            text = text.replace(phrase, "")
        text = text.replace("does not predict or guarantee a refund", "")
        assert not re.search(r"verif", text, re.I), text
        assert not re.search(r"guarantee|will be refunded|you are entitled|\byou must\b|mandatory", text, re.I), text


def test_invariants_hold_for_a_wide_grid_of_cases():
    grid = [(case(o, status=s, policy_confirmed=c), []) for s in ("new", "in_progress", "waiting_for_user", "resolved", "closed")
            for o in (-30, -1, 0, 3, 4, 7, 8, 40, None) for c in (True, False)]
    for (c, _), model in zip(grid, recommend_all(grid)):
        assert model["title"] and model["summary"] and len(model["reasons"]) >= 1
        assert model["tone"] in ("urgent", "warn", "info", "done") and model["toneLabel"]
        assert sum(a["primary"] for a in model["actions"]) <= 1
        names = [a["action"] for a in model["actions"]]
        assert len(names) == len(set(names))
        assert set(names) <= {"draft", "evidence", "eligibility", "followup", "reopen", "new_case"}
        if model["tone"] == "urgent":                                         # urgency is only ever based on a confirmed date
            assert model["deadline"]["kind"] == "confirmed" and c["status"] in ("new", "in_progress", "waiting_for_user")
        if c["status"] in ("resolved", "closed"):
            assert model["tone"] == "done" and primary(model) is None and names == ["reopen"]


def test_incomplete_cases_say_what_is_missing():
    cases = [case(30, product_name=" "), case(30, retailer=None), case(30, purchase_date=""), case(30, purchase_date="soon"),
             case(30, issue_description="bad"), case(30, product_name="", retailer="", purchase_date="x", issue_description="")]
    summaries = [m["summary"] for m in recommend_all([(c, []) for c in cases])]
    for expected, summary in zip(["product name", "retailer", "purchase date", "purchase date", "issue description",
                                  "product name, retailer, purchase date"], summaries):
        assert expected in summary, (expected, summary)
    assert "cannot be edited yet" in recommend(cases[0])["reasons"][1]


def test_missing_or_garbage_input_never_throws():
    for garbage in (None, {}, [], "text", 7, {"status": None}, {"deadline": {"a": 1}}):
        model = js("m.recommendNextAction(input,{today:T([2026,10,22]),followups:'nope'})", garbage)
        assert model["id"] and model["title"]
    assert js("m.recommendNextAction({}, undefined).id") == "incomplete"


# ---------------- follow-ups ----------------
def test_followup_is_suggested_only_when_none_exist():
    without = recommend(case(2))
    assert "followup" in [a["action"] for a in without["actions"]]
    for existing in ([{"due_date": "2026-11-01", "note": "x", "done": 0}], [{"due_date": "2026-09-01", "note": "x", "done": 1}]):
        assert "followup" not in [a["action"] for a in recommend(case(2), existing)["actions"]]


def test_next_followup_date_is_shown_and_junk_followups_are_ignored():
    followups = [{"due_date": "2026-12-01", "note": "later", "done": 0}, {"due_date": "2026-10-30", "note": "sooner", "done": 0},
                 {"due_date": "2026-10-25", "note": "finished", "done": 1}, {"due_date": "garbage", "note": "x", "done": 0}, None, "text"]
    model = recommend(case(30, status="in_progress"), followups)
    assert model["id"] == "follow_up" and "2026-10-30" in model["summary"] and "2026-10-25" not in model["summary"]
    assert recommend(case(30, status="in_progress"), "nonsense")["id"] == "schedule_followup"


# ---------------- rendering ----------------
def test_rendering_is_accessible_and_complete():
    model = recommend(case(2))
    html = render(model, 7)
    assert html.startswith('<section class="nba nba-urgent" aria-labelledby="nba-heading-7">')
    assert '<h3 id="nba-heading-7">' in html and "NEXT BEST ACTION" in html and model["toneLabel"] in html
    assert html.count("<button") == len(model["actions"]) and html.count('type="button"') == len(model["actions"])
    assert html.count("nba-btn-primary") == 1 and 'role="group" aria-label="Suggested actions"' in html
    for action in model["actions"]:
        assert f'data-nba-action="{action["action"]}"' in html and action["label"] in html
    assert "<ul" in html and html.count("<li>") == len(model["reasons"])
    assert "Why this is suggested" in html and "does not check any retailer policy" in html
    assert "Unconfirmed deadline" not in html and "Confirmed by you" in html


def test_rendering_shows_the_right_deadline_block_for_each_kind():
    unconfirmed = render(recommend(case(5, policy_confirmed=False)))
    assert "nba-deadline-unconfirmed" in unconfirmed and "Unconfirmed deadline" in unconfirmed and "Confirmed by you" not in unconfirmed
    none = render(recommend(case(None, policy_days=None, deadline=None, policy_confirmed=False)))
    assert "nba-deadline-none" in none and "No deadline established" in none and "nba-dl-date" not in none
    done = render(recommend(case(5, status="closed")))
    assert "nba-deadline-closed" in done and "nba-actions" in done and "nba-btn-primary" not in done


def test_all_model_text_is_html_escaped():
    nasty = '<script>alert(1)</script><img src=x onerror=alert(2)>"\''
    model = {"id": "x", "tone": 'urgent"><script>', "toneLabel": nasty, "title": nasty, "summary": nasty, "reasons": [nasty, nasty],
             "deadline": {"kind": 'confirmed"><b>', "label": nasty, "date": nasty, "relative": nasty, "detail": nasty, "days": 1},
             "actions": [{"action": 'draft"><script>alert(3)</script>', "label": nasty, "primary": True}]}
    html = render(model, 3)
    assert "<script" not in html and "<img" not in html and "<b>" not in html
    assert "&lt;script&gt;" in html and "&quot;" in html
    assert set(re.findall(r"<([a-z0-9]+)", html)) <= {"section", "div", "span", "h3", "h4", "p", "ul", "li", "button"}


def test_case_text_from_the_database_cannot_reach_the_output():
    hostile = case(5, product_name="<script>x</script>", retailer="<img src=x onerror=alert(1)>", policy_source='"><script>',
                   issue_description="<b>bold</b> issue text", notes="<script>")
    html = render(recommend(hostile))
    assert "<script" not in html and "<img" not in html and "<b>" not in html


def test_rendered_html_adds_exactly_one_unique_id():
    html = render(recommend(case(2)), 9)
    assert re.findall(r'(?<![\w-])id="([^"]*)"', html) == ["nba-heading-9"]


# ---------------- wiring in index.html / app.js (plain text checks) ----------------
def _app_js():
    return (STATIC / "app.js").read_text(encoding="utf-8")


def _function_source(source, name):
    start = source.index(f"function {name}(")
    depth, i = 0, source.index("{", start)
    while True:
        depth += {"{": 1, "}": -1}.get(source[i], 0)
        if depth == 0:
            return source[start:i + 1]
        i += 1


def test_index_loads_the_module_before_app_js():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert html.count("/static/next_action.js") == 1
    assert html.index("/static/evidence.js") < html.index("/static/next_action.js") < html.index("/static/app.js")


def test_runner_reuses_existing_handlers_and_makes_no_requests_of_its_own():
    runner = _function_source(_app_js(), "runNextAction")
    assert "fetch(" not in runner and "api(" not in runner                      # no duplicated API calls
    assert 'case "evidence": generateEvidenceChecklist(id)' in runner            # goes through the evidence request gate
    assert "evidenceGate" not in runner and "setEvidenceBusy" not in runner      # does not meddle with the gate's state
    for existing_button in ("#draftBtn", "#eligibilityBtn", "#followBtn", "#progressBtn"):
        assert existing_button in runner
    assert "openDrawer()" in runner


def test_panel_is_built_from_the_case_and_followups_openCase_already_loaded():
    source = _app_js()
    open_case = _function_source(source, "openCase")
    assert "RGNextAction.renderNextAction(RGNextAction.recommendNextAction(c, {today: new Date(), followups}), c.id, esc)" in open_case
    assert 'querySelectorAll("[data-nba-action]")' in open_case
    # openCase still loads exactly the case and its follow-ups before rendering; the panel adds no request
    assert open_case.index("recommendNextAction") > open_case.index("/followups`")
    assert open_case.count("api(`/api/cases/${id}`)") == 1 and open_case.count("api(`/api/cases/${id}/followups`)") == 1


def test_detail_template_has_no_duplicate_ids_even_with_the_panel():
    source = _app_js()
    template = source[source.index('$("#detailContent").innerHTML = `'):]
    template = template[:template.index("`;")]
    id_attr = r'(?<![\w-])id="([^"]+)"'                                          # real id attributes, not data-case-id
    ids = re.findall(id_attr, template) + re.findall(id_attr, render(recommend(case(2)), 1))
    ids = [i for i in ids if "${" not in i]
    assert len(ids) == len(set(ids)), ids
    for required in ("draftBtn", "eligibilityBtn", "evidenceBtn", "evidenceResult", "followBtn", "progressBtn", "resolveBtn"):
        assert required in ids                                                    # existing features still in the template
