"""Простой проход от HTTP-запроса к записи результата."""

import base64
from xml.etree import ElementTree as ET

from fastapi.testclient import TestClient

from examples.demo import SAMPLES, make_gif
from src.client import ApiClient
from src.server import Settings, create_app


def test_basic_auth_and_xml_workflow():
    app = create_app(Settings("student", "secret", True))
    with TestClient(app) as client:
        denied = client.post("/api/collect-report")
        assert denied.status_code == 401

        client.auth = ("student", "secret")
        created = client.post(
            "/api/submit-member",
            content="<member><ip>127.0.0.1</ip><locale>ru</locale>"
                    "<platform>macOS</platform></member>",
        )
        assert created.status_code == 200
        assert created.headers["content-type"].startswith("application/xml")
        member_id = ET.fromstring(created.content).findtext("identifier")

        gif = base64.b64encode(make_gif(SAMPLES[0])).decode("ascii")
        submitted = client.post(
            "/api/submit-query",
            content=f"<query><argument>{gif}</argument><member>{member_id}"
                    "</member><description>sample</description></query>",
        )
        assert submitted.status_code == 200
        query_id = ET.fromstring(submitted.content).findtext("identifier")

        collected = client.post(f"/api/collect-response/{query_id}",
                                content="<filter />")
        response = ET.fromstring(collected.content).find("item")
        assert response.findtext("status") == "test"
        assert response.findtext("query") == query_id


def test_invalid_xml_returns_xml_error():
    app = create_app(Settings("student", "secret", True))
    with TestClient(app) as client:
        client.auth = ("student", "secret")
        result = client.post("/api/submit-member", content="<member>")
    assert result.status_code == 400
    assert ET.fromstring(result.content).tag == "error"


def test_real_conversion_uses_command_line_converter():
    app = create_app(Settings("student", "secret", False))
    with TestClient(app) as transport:
        client = ApiClient("student", "secret", transport=transport)
        member = client.submit_member("127.0.0.1", "ru", "macOS")
        query = client.submit_query(make_gif(SAMPLES[1]),
                                    member["identifier"], "real conversion")
        responses = client.collect_response(query["identifier"])
        assert len(responses) == 1
        assert responses[0]["status"] == "done"
        webm = base64.b64decode(responses[0]["output"])
        assert webm.startswith(bytes.fromhex("1a45dfa3"))
