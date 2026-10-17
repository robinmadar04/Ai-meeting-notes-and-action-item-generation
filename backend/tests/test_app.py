from io import BytesIO
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from docx import Document
from reportlab.pdfgen import canvas
import httpx
from pypdf import PdfReader
from app.db import Base
from app.main import app, db_session
from app.schemas import GeneratedNotes, GenerateInput
from app import ai


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    def override_db():
        db = TestingSession()
        try: yield db
        finally: db.close()
    app.dependency_overrides[db_session] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


def sample_notes(data):
    return GeneratedNotes(meeting_title="Planning", summary="The team planned launch tasks.", key_points=["Launch timeline reviewed"], decisions=[{"decision":"Publish Friday","evidence":"Let's publish Friday"}], action_items=[{"task":"Prepare release checklist","owner":"Sam","deadline":"2026-11-01","priority":"high","evidence":"Sam will prepare it"}], unresolved_questions=[])


def test_generate_persists_notes_and_action_items(client, monkeypatch):
    monkeypatch.setattr("app.main.generate_notes", sample_notes)
    result = client.post("/api/meetings/generate", json={"title":"Launch planning","meeting_date":"2026-10-16","transcript":"Sam will prepare it. Let's publish Friday."})
    assert result.status_code == 200
    meeting = result.json()
    assert meeting["summary"] == "The team planned launch tasks."
    assert meeting["action_items"][0]["owner"] == "Sam"
    assert meeting["action_items"][0]["deadline"] == "2026-11-01"
    assert client.get(f"/api/meetings/{meeting['id']}").status_code == 200


def test_edits_search_and_delete_are_persisted(client, monkeypatch):
    monkeypatch.setattr("app.main.generate_notes", sample_notes)
    meeting = client.post("/api/meetings/generate", json={"transcript":"Transcript about launch"}).json()
    action = meeting["action_items"][0]
    patched = client.patch(f"/api/action-items/{action['id']}", json={"owner":"Taylor","status":"completed","priority":"medium"})
    assert patched.status_code == 200 and patched.json()["owner"] == "Taylor"
    client.patch(f"/api/meetings/{meeting['id']}", json={"title":"Release sync","summary":"Updated recap"})
    assert client.get("/api/meetings?q=checklist").json()["total"] == 1
    assert client.get("/api/meetings?q=Release%20sync").json()["total"] == 1
    assert client.delete(f"/api/meetings/{meeting['id']}").status_code == 204
    assert client.get("/api/meetings").json()["total"] == 0


def test_upload_text_pdf_docx_and_invalid_files(client):
    response = client.post("/api/meetings/upload", files={"file":("transcript.txt", b"Discussion transcript", "text/plain")})
    assert response.status_code == 200 and response.json()["transcript"] == "Discussion transcript"
    doc = Document(); doc.add_paragraph("DOCX transcript")
    docx = BytesIO(); doc.save(docx)
    response = client.post("/api/meetings/upload", files={"file":("notes.docx", docx.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
    assert response.status_code == 200 and "DOCX transcript" in response.json()["transcript"]
    pdf = BytesIO(); c = canvas.Canvas(pdf); c.drawString(50, 700, "PDF transcript"); c.save()
    response = client.post("/api/meetings/upload", files={"file":("notes.pdf", pdf.getvalue(), "application/pdf")})
    assert response.status_code == 200 and "PDF transcript" in response.json()["transcript"]
    assert client.post("/api/meetings/upload", files={"file":("empty.txt", b"", "text/plain")}).status_code == 422
    assert client.post("/api/meetings/upload", files={"file":("notes.csv", b"text", "text/csv")}).status_code == 415
    assert client.post("/api/meetings/upload", files={"file":("bad.pdf", b"not pdf", "application/pdf")}).status_code == 422


def test_pdf_export_contains_report(client, monkeypatch):
    monkeypatch.setattr("app.main.generate_notes", sample_notes)
    meeting = client.post("/api/meetings/generate", json={"transcript":"A meeting transcript"}).json()
    response = client.get(f"/api/meetings/{meeting['id']}/pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(response.content)).pages)
    assert "The team planned launch tasks." in text
    assert "Publish Friday" in text
    assert "Prepare release checklist" in text


def test_manual_action_item_can_be_created_updated_and_deleted(client, monkeypatch):
    monkeypatch.setattr("app.main.generate_notes", sample_notes)
    meeting = client.post("/api/meetings/generate", json={"transcript":"Meeting"}).json()
    action = client.post(f"/api/meetings/{meeting['id']}/action-items", json={"task":"Share minutes","owner":"Alex","priority":"low"})
    assert action.status_code == 200
    action_id = action.json()["id"]
    updated = client.patch(f"/api/action-items/{action_id}", json={"deadline":"2026-10-30","status":"in_progress"})
    assert updated.json()["deadline"] == "2026-10-30"
    assert client.delete(f"/api/action-items/{action_id}").status_code == 204


def test_ai_parses_valid_json_and_retries_invalid_output(monkeypatch):
    monkeypatch.setattr(ai.settings, "nvidia_api_key", "test-key")
    monkeypatch.setattr(ai.time, "sleep", lambda _: None)
    expected = sample_notes(None).model_dump(mode="json")
    responses = [httpx.Response(200, json={"choices":[{"message":{"content":"not json"}}]}, request=httpx.Request("POST", "https://example.test")), httpx.Response(200, json={"choices":[{"message":{"content":__import__("json").dumps(expected)}}]}, request=httpx.Request("POST", "https://example.test"))]
    calls=[]
    def post(*args, **kwargs): calls.append(kwargs); return responses.pop(0)
    monkeypatch.setattr(ai.httpx, "post", post)
    notes = ai.generate_notes(GenerateInput(transcript="Sam will prepare it."))
    assert notes.summary == expected["summary"] and len(calls) == 2
    assert calls[0]["headers"]["Authorization"] == "Bearer test-key"


def test_ai_rejects_missing_fields_bad_dates_and_http_errors(monkeypatch):
    monkeypatch.setattr(ai.settings, "nvidia_api_key", "test-key")
    monkeypatch.setattr(ai.time, "sleep", lambda _: None)
    bad = {"meeting_title":"Plan", "summary":"", "key_points":[], "decisions":[], "action_items":[{"task":"Ship", "deadline":"not-a-date"}]}
    responses = [httpx.Response(200, json={"choices":[{"message":{"content":__import__("json").dumps(bad)}}]}, request=httpx.Request("POST", "https://example.test")) for _ in range(2)]
    monkeypatch.setattr(ai.httpx, "post", lambda *a, **kw: responses.pop(0))
    with pytest.raises(RuntimeError, match="invalid structured notes"):
        ai.generate_notes(GenerateInput(transcript="A transcript"))
    monkeypatch.setattr(ai.httpx, "post", lambda *a, **kw: httpx.Response(401, request=httpx.Request("POST", "https://example.test")))
    with pytest.raises(RuntimeError, match="authentication failed"):
        ai.generate_notes(GenerateInput(transcript="A transcript"))


def test_missing_key_and_context_limit_are_clear(monkeypatch):
    monkeypatch.setattr(ai.settings, "nvidia_api_key", "")
    with pytest.raises(RuntimeError, match="NVIDIA_API_KEY"):
        ai.generate_notes(GenerateInput(transcript="A transcript"))
    monkeypatch.setattr(ai.settings, "nvidia_api_key", "test-key")
    with pytest.raises(ValueError, match="model context"):
        ai.generate_notes(GenerateInput(transcript="x" * 3_600_004))


def test_ai_retries_rate_limit_and_timeout(monkeypatch):
    monkeypatch.setattr(ai.settings, "nvidia_api_key", "test-key")
    monkeypatch.setattr(ai.time, "sleep", lambda _: None)
    good = {"choices":[{"message":{"content":__import__("json").dumps(sample_notes(None).model_dump(mode="json"))}}]}
    ok = lambda: httpx.Response(200, json=good, request=httpx.Request("POST", "https://example.test"))
    sequence = [httpx.Response(429, request=httpx.Request("POST", "https://example.test")), ok()]
    monkeypatch.setattr(ai.httpx, "post", lambda *a, **kw: sequence.pop(0))
    assert ai.generate_notes(GenerateInput(transcript="Transcript")).summary
    sequence = [httpx.TimeoutException("timeout"), ok()]
    monkeypatch.setattr(ai.httpx, "post", lambda *a, **kw: (_ for _ in ()).throw(sequence.pop(0)) if isinstance(sequence[0], Exception) else sequence.pop(0))
    assert ai.generate_notes(GenerateInput(transcript="Transcript")).summary


def test_ai_polls_nvidia_202_accepted_requests(monkeypatch):
    monkeypatch.setattr(ai.settings, "nvidia_api_key", "test-key")
    monkeypatch.setattr(ai.time, "sleep", lambda _: None)
    monkeypatch.setattr(ai.time, "monotonic", lambda: 1.0)
    pending = httpx.Response(202, json={"requestId":"123e4567-e89b-12d3-a456-426614174000"}, request=httpx.Request("POST", "https://example.test"))
    good = {"choices":[{"message":{"content":__import__("json").dumps(sample_notes(None).model_dump(mode="json"))}}]}
    complete = httpx.Response(200, json=good, request=httpx.Request("GET", "https://example.test"))
    monkeypatch.setattr(ai.httpx, "post", lambda *a, **kw: pending)
    poll_calls=[]
    def poll(url, **kwargs):
        poll_calls.append(url)
        return complete
    monkeypatch.setattr(ai.httpx, "get", poll)
    notes=ai.generate_notes(GenerateInput(transcript="Transcript"))
    assert notes.summary == "The team planned launch tasks."
    assert poll_calls == ["https://integrate.api.nvidia.com/v1/status/123e4567-e89b-12d3-a456-426614174000"]


def test_upload_size_limit_and_history_pagination(client, monkeypatch):
    monkeypatch.setattr("app.config.settings.transcript_max_size_mb", 0)
    assert client.post("/api/meetings/upload", files={"file":("transcript.txt", b"x", "text/plain")}).status_code == 413
    monkeypatch.setattr("app.config.settings.transcript_max_size_mb", 10)
    monkeypatch.setattr("app.main.generate_notes", sample_notes)
    for index in range(3):
        assert client.post("/api/meetings/generate", json={"title":f"Planning {index}","transcript":"Transcript"}).status_code == 200
    page = client.get("/api/meetings?page=2&page_size=2").json()
    assert page["total"] == 3 and len(page["items"]) == 1

