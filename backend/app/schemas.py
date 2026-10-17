from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Decision(BaseModel):
    decision: str = Field(min_length=1)
    evidence: str | None = None


class GeneratedAction(BaseModel):
    task: str = Field(min_length=1)
    owner: str | None = None
    deadline: date | None = None
    priority: Literal["high", "medium", "low", "unknown"] = "unknown"
    evidence: str | None = None


class GeneratedNotes(BaseModel):
    meeting_title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    key_points: list[str]
    decisions: list[Decision]
    action_items: list[GeneratedAction]
    unresolved_questions: list[str] = []


class GenerateInput(BaseModel):
    title: str = Field(default="", max_length=240)
    meeting_date: date | None = None
    transcript: str = Field(min_length=1)


class ActionPatch(BaseModel):
    task: str | None = Field(default=None, min_length=1)
    owner: str | None = None
    deadline: date | None = None
    priority: Literal["high", "medium", "low", "unknown"] | None = None
    status: Literal["pending", "in_progress", "completed"] | None = None


class ActionCreate(BaseModel):
    task: str = Field(min_length=1)
    owner: str | None = None
    deadline: date | None = None
    priority: Literal["high", "medium", "low", "unknown"] = "unknown"


class MeetingPatch(BaseModel):
    title: str | None = Field(default=None, max_length=240)
    meeting_date: date | None = None
    summary: str | None = None


class MeetingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    meeting_date: date | None
    transcript: str
    summary: str
    key_points: list[str]
    decisions: list[dict]
    unresolved_questions: list[str]
    created_at: datetime
    updated_at: datetime
    action_items: list["ActionOut"]


class ActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    meeting_id: int
    task: str
    owner: str | None
    deadline: date | None
    priority: str
    status: str
    evidence: str | None


class MeetingListItem(BaseModel):
    id: int
    title: str
    meeting_date: date | None
    summary: str
    created_at: datetime
    updated_at: datetime
    action_count: int


class MeetingPage(BaseModel):
    items: list[MeetingListItem]
    total: int
    page: int
    page_size: int
