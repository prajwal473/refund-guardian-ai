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
