from datetime import date
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import or_, func, select
from sqlalchemy.orm import Session, selectinload
from .config import settings
from .db import Base, SessionLocal, engine
from .models import Meeting, ActionItem
from .schemas import GenerateInput, MeetingOut, MeetingPatch, ActionPatch, ActionCreate, MeetingPage
from .ai import generate_notes
from .files import extract_transcript
from .pdf import build_report

app = FastAPI(title="AI Meeting Notes", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_origin, "http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])


def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def meeting_or_404(db: Session, meeting_id: int):
    meeting = db.query(Meeting).options(selectinload(Meeting.action_items)).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(404, "Meeting not found.")
    return meeting


@app.get("/api/health")
def health():
    return {"status": "ok", "ai_configured": bool(settings.nvidia_api_key)}


@app.get("/api/dashboard")
def dashboard(db: Session = Depends(db_session)):
    counts = dict(db.query(ActionItem.status, func.count(ActionItem.id)).group_by(ActionItem.status).all())
    meetings = db.query(Meeting).order_by(Meeting.updated_at.desc()).limit(6).all()
    recent = [{"id": m.id, "title": m.title, "meeting_date": m.meeting_date, "summary": m.summary, "created_at": m.created_at, "updated_at": m.updated_at, "action_count": len(m.action_items)} for m in meetings]
    return {"recent": recent, "meetings": db.query(func.count(Meeting.id)).scalar() or 0, "pending": (counts.get("pending", 0) + counts.get("in_progress", 0)), "completed": counts.get("completed", 0)}


@app.post("/api/meetings/upload")
async def upload_transcript(file: UploadFile = File(...)):
    text = await extract_transcript(file)
    return {"filename": file.filename, "transcript": text}


@app.post("/api/meetings/generate", response_model=MeetingOut)
def generate(payload: GenerateInput, db: Session = Depends(db_session)):
    transcript = payload.transcript.strip()
    if not transcript:
        raise HTTPException(422, "Transcript is required.")
    if len(transcript.encode("utf-8")) > settings.transcript_max_size_mb * 1024 * 1024:
        raise HTTPException(413, f"Transcript exceeds the {settings.transcript_max_size_mb} MB limit.")
    try:
        notes = generate_notes(payload.model_copy(update={"transcript": transcript}))
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(503 if "not configured" in str(exc) else 502, str(exc)) from exc
    meeting = Meeting(title=(payload.title.strip() or notes.meeting_title or "Untitled meeting")[:240], meeting_date=payload.meeting_date, transcript=transcript, summary=notes.summary, key_points=notes.key_points, decisions=[d.model_dump(mode="json") for d in notes.decisions], unresolved_questions=notes.unresolved_questions)
    meeting.action_items = [ActionItem(task=a.task, owner=a.owner, deadline=a.deadline, priority=a.priority, status="pending", evidence=a.evidence) for a in notes.action_items]
    db.add(meeting)
    db.commit()
    return meeting_or_404(db, meeting.id)


@app.get("/api/meetings", response_model=MeetingPage)
def list_meetings(q: str = "", page: int = Query(1, ge=1), page_size: int = Query(12, ge=1, le=50), db: Session = Depends(db_session)):
    query = db.query(Meeting)
    term = q.strip()
    if term:
        like = f"%{term}%"
        ids = select(ActionItem.meeting_id).where(ActionItem.task.ilike(like))
        query = query.filter(or_(Meeting.title.ilike(like), Meeting.summary.ilike(like), Meeting.transcript.ilike(like), Meeting.id.in_(ids)))
    total = query.count()
    meetings = query.order_by(Meeting.updated_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    items = [{"id": m.id, "title": m.title, "meeting_date": m.meeting_date, "summary": m.summary, "created_at": m.created_at, "updated_at": m.updated_at, "action_count": db.query(func.count(ActionItem.id)).filter(ActionItem.meeting_id == m.id).scalar() or 0} for m in meetings]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@app.get("/api/meetings/{meeting_id}", response_model=MeetingOut)
def get_meeting(meeting_id: int, db: Session = Depends(db_session)):
    return meeting_or_404(db, meeting_id)


@app.patch("/api/meetings/{meeting_id}", response_model=MeetingOut)
def update_meeting(meeting_id: int, patch: MeetingPatch, db: Session = Depends(db_session)):
    meeting = meeting_or_404(db, meeting_id)
    for key, value in patch.model_dump(exclude_unset=True).items():
        setattr(meeting, key, value)
    db.commit()
    return meeting_or_404(db, meeting_id)


@app.delete("/api/meetings/{meeting_id}", status_code=204)
def delete_meeting(meeting_id: int, db: Session = Depends(db_session)):
    meeting = meeting_or_404(db, meeting_id)
    db.delete(meeting)
    db.commit()
    return Response(status_code=204)


@app.post("/api/meetings/{meeting_id}/action-items")
def create_action(meeting_id: int, data: ActionCreate, db: Session = Depends(db_session)):
    meeting_or_404(db, meeting_id)
    action = ActionItem(meeting_id=meeting_id, **data.model_dump())
    db.add(action)
    db.commit()
    db.refresh(action)
    return action


@app.patch("/api/action-items/{action_id}")
def update_action(action_id: int, patch: ActionPatch, db: Session = Depends(db_session)):
    action = db.query(ActionItem).filter(ActionItem.id == action_id).first()
    if not action:
        raise HTTPException(404, "Action item not found.")
    for key, value in patch.model_dump(exclude_unset=True).items():
        setattr(action, key, value)
    db.commit()
    db.refresh(action)
    return action


@app.delete("/api/action-items/{action_id}", status_code=204)
def delete_action(action_id: int, db: Session = Depends(db_session)):
    action = db.query(ActionItem).filter(ActionItem.id == action_id).first()
    if not action:
        raise HTTPException(404, "Action item not found.")
    db.delete(action)
    db.commit()
    return Response(status_code=204)


@app.get("/api/meetings/{meeting_id}/pdf")
def meeting_pdf(meeting_id: int, db: Session = Depends(db_session)):
    meeting = meeting_or_404(db, meeting_id)
    content = build_report(meeting)
    return Response(content, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="meeting-{meeting.id}-report.pdf"'})
