"""CopyCat API. Run: uvicorn main:app --port 8000"""
import json
import logging
import os
import re
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from postgrest.exceptions import APIError
from pydantic import BaseModel, Field
from storage3.utils import StorageException
from supabase import Client, create_client

import extractor
import generator
import make_sheet
import paper as university_paper

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

DATA = ROOT / "data"
DATA.mkdir(parents=True, exist_ok=True)
SHEET = DATA / "copycat_sheet.png"
if not SHEET.exists():
    make_sheet.create_sheet(SHEET)
MAX_UPLOAD = 15 * 1024 * 1024
SESSION_TTL = timedelta(hours=24)
SESSION_TABLE = "handwriting_sessions"
STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "copycat-glyphs")
logger = logging.getLogger(__name__)
_client: Client | None = None

app = FastAPI(title="CopyCat")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])


class GenerateRequest(BaseModel):
    session: str
    text: str = Field(min_length=1, max_length=30000)
    ink_color: Literal["blue", "black", "darkblue"] = "blue"
    paper_type: Literal["ruled", "blank", "margin", "photo"] = "ruled"
    font_size: float = Field(16, ge=10, le=36)
    jitter_level: int = Field(50, ge=0, le=100)


def _supabase() -> Client:
    global _client
    if _client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            raise HTTPException(
                503,
                "Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in backend/.env.",
            )
        try:
            _client = create_client(url, key)
        except (ValueError, RuntimeError) as exc:
            logger.exception("Could not initialize the Supabase client")
            raise HTTPException(503, "Supabase configuration is invalid.") from exc
    return _client


def _storage_path(session: str, filename: str) -> str:
    return f"{session}/{filename}"


def _cleanup_expired(client: Client) -> None:
    try:
        expired = (
            client.table(SESSION_TABLE)
            .select("id,found")
            .lt("expires_at", datetime.now(timezone.utc).isoformat())
            .execute()
            .data
        )
        for row in expired:
            paths = [_storage_path(row["id"], glyph["file"]) for glyph in row["found"]]
            paths += [_storage_path(row["id"], name) for name in ("paper.jpg", "paper.json")]
            if paths:
                client.storage.from_(STORAGE_BUCKET).remove(paths)
            client.table(SESSION_TABLE).delete().eq("id", row["id"]).execute()
    except (APIError, StorageException):
        logger.exception("Could not clean up expired Supabase handwriting sessions")
        raise HTTPException(503, "Supabase storage is temporarily unavailable. Try again shortly.")


def _session_row(client: Client, session: str) -> dict:
    if not re.fullmatch(r"[a-f0-9]{32}", session):
        raise HTTPException(404, "Your handwriting session expired. Upload your sheet again.")
    try:
        rows = (
            client.table(SESSION_TABLE)
            .select("found,missing")
            .eq("id", session)
            .gt("expires_at", datetime.now(timezone.utc).isoformat())
            .limit(1)
            .execute()
            .data
        )
    except APIError:
        logger.exception("Could not read the handwriting session from Supabase")
        raise HTTPException(503, "Supabase storage is temporarily unavailable. Try again shortly.")
    if not rows:
        raise HTTPException(404, "Your handwriting session expired. Upload your sheet again.")
    return rows[0]


def _download_glyphs(client: Client, session: str, found: list[dict], folder: Path) -> None:
    try:
        for glyph in found:
            image = client.storage.from_(STORAGE_BUCKET).download(_storage_path(session, glyph["file"]))
            (folder / glyph["file"]).write_bytes(image)
    except (APIError, StorageException):
        logger.exception("Could not download handwriting glyphs from Supabase")
        raise HTTPException(503, "Supabase storage is temporarily unavailable. Try again shortly.")


def _remove_partial_upload(client: Client, session: str, uploaded: list[str]) -> None:
    if uploaded:
        try:
            client.storage.from_(STORAGE_BUCKET).remove(uploaded)
        except StorageException:
            logger.exception("Could not roll back partially uploaded handwriting glyphs")
    try:
        client.table(SESSION_TABLE).delete().eq("id", session).execute()
    except APIError:
        logger.exception("Could not remove a partially created handwriting session")


def _download_paper(client: Client, session: str):
    try:
        image = client.storage.from_(STORAGE_BUCKET).download(_storage_path(session, "paper.jpg"))
        layout = json.loads(client.storage.from_(STORAGE_BUCKET).download(_storage_path(session, "paper.json")))
    except (APIError, StorageException, json.JSONDecodeError):
        raise HTTPException(404, "Upload a photo of your blank university assignment sheet first.")
    return image, layout


def _render(req: GenerateRequest):
    client = _supabase()
    row = _session_row(client, req.session)
    background = layout = None
    if req.paper_type == "photo":
        background, layout = _download_paper(client, req.session)
    try:
        with tempfile.TemporaryDirectory(prefix="copycat-") as temp:
            _download_glyphs(client, req.session, row["found"], Path(temp))
            return generator.render_pages(
                temp, req.text, req.ink_color, req.paper_type, req.font_size, req.jitter_level,
                background=background, layout=layout,
            )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/ready")
def readiness():
    return {"status": "ok"}


@app.get("/api/template")
def template():
    return FileResponse(SHEET, media_type="image/png", filename="copycat_sheet.png")


@app.post("/api/upload-handwriting")
def upload_handwriting(file: UploadFile = File(...)):
    data = file.file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "Photo is larger than 15 MB.")
    client = _supabase()
    _cleanup_expired(client)
    sid = uuid.uuid4().hex

    with tempfile.TemporaryDirectory(prefix="copycat-") as temp:
        try:
            result = extractor.extract(data, temp)
        except extractor.ExtractionError as exc:
            raise HTTPException(422, str(exc)) from exc

        uploaded = []
        try:
            for glyph in result["found"]:
                path = _storage_path(sid, glyph["file"])
                image = (Path(temp) / glyph["file"]).read_bytes()
                client.storage.from_(STORAGE_BUCKET).upload(
                    path, image, {"content-type": "image/png", "upsert": "false"}
                )
                uploaded.append(path)
            client.table(SESSION_TABLE).insert(
                {
                    "id": sid,
                    "found": result["found"],
                    "missing": result["missing"],
                    "expires_at": (datetime.now(timezone.utc) + SESSION_TTL).isoformat(),
                }
            ).execute()
        except (APIError, StorageException):
            logger.exception("Could not store handwriting session in Supabase")
            _remove_partial_upload(client, sid, uploaded)
            raise HTTPException(503, "Could not save your handwriting to Supabase. Try again shortly.")

    for glyph in result["found"]:
        glyph["url"] = f"/api/files/{sid}/{glyph['file']}"
    return {"session": sid, **result}


@app.post("/api/upload-paper")
def upload_paper(session: str, file: UploadFile = File(...)):
    if not re.fullmatch(r"[a-f0-9]{32}", session):
        raise HTTPException(404, "Upload your handwriting photo before the university sheet.")
    data = file.file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "Photo is larger than 15 MB.")
    client = _supabase()
    _session_row(client, session)
    try:
        image, layout = university_paper.prepare_paper(data)
    except university_paper.PaperError as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        bucket = client.storage.from_(STORAGE_BUCKET)
        bucket.upload(_storage_path(session, "paper.jpg"), image, {"content-type": "image/jpeg", "upsert": "true"})
        bucket.upload(
            _storage_path(session, "paper.json"),
            json.dumps(layout).encode(),
            {"content-type": "application/json", "upsert": "true"},
        )
    except StorageException:
        logger.exception("Could not store the university paper in Supabase")
        raise HTTPException(503, "Could not save your university sheet. Try again shortly.")
    return {
        "detected": bool(layout["detected"]),
        "lines": len(layout["baselines"]) if layout["detected"] else 0,
        "preview": university_paper.preview_jpeg(image),
    }


@app.get("/api/paper/{session}")
def paper_photo(session: str):
    client = _supabase()
    _session_row(client, session)
    try:
        image = client.storage.from_(STORAGE_BUCKET).download(_storage_path(session, "paper.jpg"))
        layout = json.loads(client.storage.from_(STORAGE_BUCKET).download(_storage_path(session, "paper.json")))
    except (APIError, StorageException, json.JSONDecodeError):
        raise HTTPException(404, "No university sheet uploaded yet.")
    return {
        "detected": bool(layout.get("detected")),
        "lines": len(layout.get("baselines") or []) if layout.get("detected") else 0,
        "preview": university_paper.preview_jpeg(image),
    }


@app.get("/api/files/{session}/{filename}")
def handwriting_file(session: str, filename: str):
    client = _supabase()
    row = _session_row(client, session)
    if not any(glyph["file"] == filename for glyph in row["found"]):
        raise HTTPException(404, "Handwriting image not found.")
    try:
        image = client.storage.from_(STORAGE_BUCKET).download(_storage_path(session, filename))
    except (APIError, StorageException):
        logger.exception("Could not retrieve a handwriting image from Supabase")
        raise HTTPException(503, "Supabase storage is temporarily unavailable. Try again shortly.")
    return Response(image, media_type="image/png")


@app.post("/api/preview")
def preview(req: GenerateRequest):
    pages, missing = _render(req)
    return {"pages": len(pages), "images": generator.preview_images(pages), "missing": sorted(missing)}


@app.post("/api/generate-pdf")
def generate_pdf(req: GenerateRequest):
    pages, _ = _render(req)
    return Response(generator.build_pdf(pages), media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="assignment.pdf"'})


DIST = ROOT.parent / "frontend" / "dist"
if DIST.is_dir():                                   # after `npm run build`, one server does everything
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=DIST, html=True), name="web")
