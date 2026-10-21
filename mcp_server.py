"""Refund Guardian MCP server using Streamable HTTP.

Run separately from the web app:
    python mcp_server.py
Expected MCP endpoint: http://127.0.0.1:8001/mcp
"""
import os
from mcp.server.fastmcp import FastMCP
from app import services

services.init_db()
mcp = FastMCP("Refund Guardian", host=os.getenv("MCP_HOST", "127.0.0.1"),
              port=int(os.getenv("MCP_PORT", "8001")))

@mcp.tool()
def list_refund_cases() -> list[dict]:
    """List saved refund and warranty cases."""
    return services.list_cases()

@mcp.tool()
def create_refund_case(product_name: str, retailer: str, purchase_date: str,
                       purchase_price: float, issue_description: str,
                       currency: str = "INR", policy_days: int | None = None,
                       policy_source: str | None = None) -> dict:
    """Create a case. Supply policy_days only when the user has verified the return window.
    This records a case only; it does not contact the retailer or submit a claim."""
    return services.create_case({
        "product_name": product_name, "retailer": retailer,
        "purchase_date": purchase_date, "purchase_price": purchase_price,
        "issue_description": issue_description, "currency": currency,
        "policy_days": policy_days, "policy_source": policy_source
    })

@mcp.tool()
def draft_support_message(case_id: int) -> dict:
    """Draft a support message for user review; never sends it."""
    item = services.get_case(case_id)
    if not item:
        return {"error": f"Case {case_id} was not found."}
    return services.draft_claim(item)

@mcp.tool()
def update_case_status(case_id: int, status: str, notes: str = "") -> dict:
    """Update a case status. Allowed: new, in_progress, waiting_for_user, resolved, closed."""
    try:
        item = services.update_case(case_id, {"status": status, "notes": notes})
    except ValueError as exc:
        return {"error": str(exc)}
    return item or {"error": f"Case {case_id} was not found."}

@mcp.tool()
def schedule_followup(case_id: int, due_date: str, note: str) -> dict:
    """Save a follow-up task in the local database. This does not send a notification."""
    try:
        result = services.create_followup(case_id, due_date, note)
    except ValueError as exc:
        return {"error": str(exc)}
    return result or {"error": f"Case {case_id} was not found."}

@mcp.tool()
def analyze_refund_eligibility(case_id: int) -> dict:
    """Rule-based eligibility analysis for a saved case. Uses only the policy window and
    source the user recorded; it never guarantees a refund and does not call a model."""
    item = services.get_case(case_id)
    if not item:
        return {"error": f"Case {case_id} was not found."}
    return services.analyze_eligibility(item)

@mcp.tool()
def verify_case(case_id: int) -> dict:
    """Read back the case and follow-ups to verify persisted state."""
    item = services.get_case(case_id)
    if not item:
        return {"found": False, "case_id": case_id}
    return {"found": True, "case": item, "followups": services.list_followups(case_id)}

if __name__ == "__main__":
    mcp.run(transport="streamable-http")