"""Dashboard statistics tests. The logic lives in app/static/stats.js (pure functions) and is run with
Node, so no browser or extra Python dependency is needed. Skipped when Node is not installed."""
import json
import pathlib
import shutil
import subprocess

import pytest

STATS_JS = pathlib.Path(__file__).resolve().parents[1] / "app" / "static" / "stats.js"
NODE = shutil.which("node")
SCRIPT = ("const s=require(process.argv[1]);const i=JSON.parse(require('fs').readFileSync(0,'utf8'));"
          "const t=new Date(i.today[0],i.today[1]-1,i.today[2]);"
          "console.log(JSON.stringify({stats:s.computeStats(i.cases,t),days:i.cases.map(c=>s.daysUntil(c.deadline,t))}));")


def run_stats(cases, today=(2026, 10, 21)):
    if not NODE:
        pytest.skip("node is not installed")
    out = subprocess.run([NODE, "-e", SCRIPT, str(STATS_JS)], input=json.dumps({"cases": cases, "today": list(today)}),
                         capture_output=True, text=True, timeout=30, check=True)
    return json.loads(out.stdout)


def case(deadline, confirmed=True, status="new"):
    return {"status": status, "deadline": deadline, "policy_confirmed": confirmed}


def test_overdue_cases_are_not_counted_as_due_in_7_days():
    stats = run_stats([case("2026-10-20"), case("2026-10-01"), case("2026-10-22")])["stats"]
    assert stats["dueSoonConfirmed"] == 1          # only 2026-10-22
    assert stats["overdueConfirmed"] == 2


def test_seven_day_boundary_and_today():
    cases = [case("2026-10-21"), case("2026-10-28"), case("2026-10-29"), case("2026-10-20")]
    stats = run_stats(cases)["stats"]
    assert stats["dueSoonConfirmed"] == 2          # today (0 days) and +7 days are included; +8 is not
    assert stats["overdueConfirmed"] == 1          # yesterday


def test_unconfirmed_deadlines_are_counted_separately_and_never_as_confirmed():
    stats = run_stats([case("2026-10-23", confirmed=False), case("2026-10-01", confirmed=False), case("2026-10-24")])["stats"]
    assert stats["dueSoonConfirmed"] == 1
    assert stats["dueSoonUnconfirmed"] == 1
    assert stats["overdueUnconfirmed"] == 1 and stats["overdueConfirmed"] == 0


def test_only_a_real_true_counts_as_confirmed():
    stats = run_stats([{"status": "new", "deadline": "2026-10-23", "policy_confirmed": 1},
                       {"status": "new", "deadline": "2026-10-23"}])["stats"]
    assert stats["dueSoonConfirmed"] == 0 and stats["dueSoonUnconfirmed"] == 2


def test_resolved_closed_and_missing_deadlines_are_excluded():
    cases = [case("2026-10-23", status="resolved"), case("2026-10-23", status="closed"),
             case(None), case("not-a-date"), case("2026-10-23", status="waiting_for_user")]
    stats = run_stats(cases)["stats"]
    assert stats["total"] == 5 and stats["active"] == 3 and stats["resolved"] == 2
    assert stats["dueSoonConfirmed"] == 1


def test_day_counting_across_month_and_year_boundaries():
    days = run_stats([case("2026-11-01"), case("2027-01-01"), case("2026-10-21")], today=(2026, 10, 31))["days"]
    assert days == [1, 62, -10]
