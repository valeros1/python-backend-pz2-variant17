"""Простой проход от HTTP-запроса к записи результата."""

import base64
from http import HTTPStatus
import xml.etree.ElementTree as element_tree

from fastapi.testclient import TestClient

from examples.demo import SAMPLES, make_gif
from src.client import ApiClient
from src.server import Settings, create_app


def test_basic_auth_and_xml_workflow():
    app = create_app(Settings("student", "secret", True))
    with TestClient(app) as client:
        denied = client.post("/api/collect-report")
        assert denied.status_code == HTTPStatus.UNAUTHORIZED

        client.auth = ("student", "secret")
        created = client.post(
            "/api/submit-member",
            content="<member><ip>127.0.0.1</ip><locale>ru</locale>"
                    "<platform>macOS</platform></member>",
        )
        assert created.status_code == HTTPStatus.OK
        assert created.headers["content-type"].startswith("application/xml")
        member_id = element_tree.fromstring(created.content).findtext(
            "identifier")

        gif = base64.b64encode(make_gif(SAMPLES[0])).decode("ascii")
        query_xml = (f"<query><argument>{gif}</argument>"
                     f"<member>{member_id}</member>"
                     "<description>sample</description></query>")
        submitted = client.post("/api/submit-query", content=query_xml)
        assert submitted.status_code == HTTPStatus.OK
        query_id = element_tree.fromstring(submitted.content).findtext(
            "identifier")

        collected = client.post(f"/api/collect-response/{query_id}",
                                content="<filter />")
        response = element_tree.fromstring(collected.content).find("item")
        assert response.findtext("status") == "test"
        assert response.findtext("query") == query_id


def test_invalid_xml_returns_xml_error():
    app = create_app(Settings("student", "secret", True))
    with TestClient(app) as client:
        client.auth = ("student", "secret")
        result = client.post("/api/submit-member", content="<member>")
    assert result.status_code == HTTPStatus.BAD_REQUEST
    assert element_tree.fromstring(result.content).tag == "error"


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
