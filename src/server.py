"""HTTP API варианта 17 поверх модели данных в памяти."""

import base64
import json
import secrets
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.responses import Response as HttpResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from src.model import InMemoryModel, ModelError
from src.xml_codec import XmlError, parse_fields, render_xml


@dataclass(frozen=True)
class Settings:
    username: str
    password: str
    test_mode: bool


def load_settings(path: str | Path | None = None) -> Settings:
    """Взять настройки из config.json или учебного примера."""
    chosen = Path(path) if path else Path("config.json")
    if path is None and not chosen.exists():
        chosen = Path(__file__).resolve().parent.parent / "config.example.json"
    data = json.loads(chosen.read_text(encoding="utf-8"))
    return Settings(data["username"], data["password"], data["test_mode"])


def _xml(name: str, value) -> HttpResponse:
    return HttpResponse(render_xml(name, value), media_type="application/xml")


def _required(fields: dict, *names: str) -> dict:
    missing = set(names) - fields.keys()
    if missing:
        raise XmlError(f"Не хватает поля: {sorted(missing)[0]}")
    return {name: fields[name] for name in names}


def _run_conversion(model: InMemoryModel, query_id: int,
                    gif_bytes: bytes, test_mode: bool) -> None:
    """Фоновое выполнение ранее созданной задачи Query."""
    started = time.monotonic()
    if test_mode:
        model.finish_query(query_id, "", "test", "", 0)
        return
    try:
        result = subprocess.run(
            [sys.executable, "-m", "src.converter"],
            input=gif_bytes, capture_output=True, check=False,
        )
        output = base64.b64encode(result.stdout).decode("ascii")
        error = result.stderr.decode("utf-8", errors="replace")
        status = "done" if result.returncode == 0 else "error"
    except OSError as exc:
        output, status = "", "error"
        error = str(exc)
    duration = int(time.monotonic() - started)
    model.finish_query(query_id, output, status, str(error), duration)


def create_app(settings: Settings | None = None,
               model: InMemoryModel | None = None) -> FastAPI:
    """Создать независимый экземпляр API для сервера или теста."""
    settings = settings or load_settings()
    model = model or InMemoryModel()
    app = FastAPI(title="GIF to WebM API")
    app.state.model = model
    security = HTTPBasic(auto_error=False)

    def authenticate(credentials: HTTPBasicCredentials | None =
                     Depends(security)) -> None:
        valid = credentials is not None
        if valid:
            valid = (secrets.compare_digest(credentials.username,
                                            settings.username)
                     & secrets.compare_digest(credentials.password,
                                              settings.password))
        if not valid:
            raise HTTPException(401, "Unauthorized",
                                headers={"WWW-Authenticate": "Basic"})

    @app.exception_handler(ModelError)
    @app.exception_handler(XmlError)
    async def bad_input(_request: Request, error: Exception) -> HttpResponse:
        return HttpResponse(render_xml("error", {"message": str(error)}),
                            status_code=400, media_type="application/xml")

    @app.post("/api/submit-member", dependencies=[Depends(authenticate)])
    async def submit_member(request: Request) -> HttpResponse:
        fields = parse_fields(await request.body(), "member")
        values = _required(fields, "ip", "locale", "platform")
        values["datetime"] = fields.get("datetime")
        return _xml("member", model.submit_member(**values))

    @app.get("/api/discard-member", dependencies=[Depends(authenticate)])
    def discard_member(identifier: int) -> HttpResponse:
        return _xml("member", model.discard_member(identifier))

    @app.post("/api/collect-member", dependencies=[Depends(authenticate)])
    async def collect_member(request: Request) -> HttpResponse:
        fields = parse_fields(await request.body(), "filter")
        return _xml("members", model.collect_member(fields))

    @app.post("/api/adjust-member", dependencies=[Depends(authenticate)])
    async def adjust_member(request: Request) -> HttpResponse:
        fields = parse_fields(await request.body(), "member")
        identifier = _required(fields, "identifier")["identifier"]
        del fields["identifier"]
        return _xml("member", model.adjust_member(identifier, fields))

    @app.post("/api/submit-query", dependencies=[Depends(authenticate)])
    async def submit_query(request: Request,
                           background: BackgroundTasks) -> HttpResponse:
        fields = parse_fields(await request.body(), "query")
        values = _required(fields, "argument", "member", "description")
        try:
            gif_bytes = base64.b64decode(values["argument"], validate=True)
        except (ValueError, base64.binascii.Error) as error:
            raise XmlError("argument должен содержать GIF в Base64") from error
        query = model.submit_query(**values, datetime=fields.get("datetime"))
        background.add_task(_run_conversion, model, query.identifier,
                            gif_bytes, settings.test_mode)
        return _xml("query", query)

    @app.get("/api/discard-query", dependencies=[Depends(authenticate)])
    def discard_query(identifier: int) -> HttpResponse:
        return _xml("query", model.discard_query(identifier))

    @app.post("/api/collect-query/{member}",
              dependencies=[Depends(authenticate)])
    async def collect_query(member: int, request: Request) -> HttpResponse:
        fields = parse_fields(await request.body(), "filter")
        return _xml("queries", model.collect_query(member, fields))

    @app.post("/api/adjust-query", dependencies=[Depends(authenticate)])
    async def adjust_query(request: Request) -> HttpResponse:
        fields = parse_fields(await request.body(), "query")
        identifier = _required(fields, "identifier")["identifier"]
        del fields["identifier"]
        return _xml("query", model.adjust_query(identifier, fields))

    @app.post("/api/collect-response/{query}",
              dependencies=[Depends(authenticate)])
    async def collect_response(query: int, request: Request) -> HttpResponse:
        fields = parse_fields(await request.body(), "filter")
        return _xml("responses", model.collect_response(query, fields))

    @app.post("/api/collect-report", dependencies=[Depends(authenticate)])
    def collect_report() -> HttpResponse:
        return _xml("report", model.collect_report())

    return app


app = create_app()
