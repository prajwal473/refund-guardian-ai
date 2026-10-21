from pydantic import BaseModel, Field
from typing import Literal, Optional

CaseStatus = Literal["new", "in_progress", "waiting_for_user", "resolved", "closed"]

class CaseCreate(BaseModel):
    product_name: str = Field(min_length=1, max_length=160)
    retailer: str = Field(min_length=1, max_length=160)
    purchase_date: str = Field(description="YYYY-MM-DD")
    purchase_price: float = Field(ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    issue_description: str = Field(min_length=5, max_length=3000)
    policy_days: Optional[int] = Field(default=None, ge=0, le=3650,
        description="Only use a return window verified by the user; omitted means unknown.")
    policy_source: Optional[str] = Field(default=None, max_length=500)

class CaseUpdate(BaseModel):
    status: Optional[CaseStatus] = None
    notes: Optional[str] = Field(default=None, max_length=3000)

class FollowupCreate(BaseModel):
    due_date: str = Field(description="YYYY-MM-DD")
    note: str = Field(min_length=2, max_length=1000)

class ReceiptTextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20000)

EligibilityOutcome = Literal["potentially_eligible", "outside_known_window",
                             "needs_policy_verification", "insufficient_information"]

class EligibilityRequest(BaseModel):
    use_llm: bool = Field(default=True, description="Add an optional AI explanation if a model provider is configured.")

class EligibilityResponse(BaseModel):
    case_id: int
    outcome: EligibilityOutcome
    outcome_label: str
    explanation: str = Field(description="Deterministic, rule-based explanation. Always present.")
    policy_verified: bool
    as_of: str = Field(description="Date used for the calculation (YYYY-MM-DD).")
    deadline: Optional[str] = None
    days_remaining: Optional[int] = Field(default=None, description="Negative once the deadline has passed.")
    missing_information: list[str]
    recommended_next_steps: list[str]
    caveats: list[str]
    analysis_method: Literal["rule_based", "rule_based+llm_explanation"]
    ai_explanation: Optional[str] = None
    llm_note: Optional[str] = None