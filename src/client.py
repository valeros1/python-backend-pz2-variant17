"""Клиент десяти XML-методов HTTP API варианта 17."""

import base64
from xml.etree import ElementTree as ET

import httpx

from src.xml_codec import INTEGER_FIELDS, render_xml


class ApiError(RuntimeError):
    """HTTP API отклонил запрос."""


def _record(element: ET.Element) -> dict:
    result = {}
    for child in element:
        value = child.text or ""
        result[child.tag] = (int(value) if child.tag in INTEGER_FIELDS
                             else value)
    return result


class ApiClient:
    """Методы названы так же, как операции InMemoryModel."""

    def __init__(self, username: str, password: str,
                 base_url: str = "http://127.0.0.1:8000",
                 transport=None) -> None:
        self.transport = transport or httpx.Client(base_url=base_url)
        self.owns_transport = transport is None
        self.auth = (username, password)

    def close(self) -> None:
        if self.owns_transport:
            self.transport.close()

    def _call(self, method: str, path: str, root: str | None = None,
              fields: dict | None = None, params: dict | None = None):
        content = render_xml(root, fields or {}) if root else None
        response = self.transport.request(
            method, path, auth=self.auth, content=content, params=params,
            headers={"Content-Type": "application/xml"},
        )
        if response.status_code != 200:
            raise ApiError(f"HTTP {response.status_code}: {response.text}")
        document = ET.fromstring(response.content)
        if document.tag in {"members", "queries", "responses", "report"}:
            return [_record(item) for item in document.findall("item")]
        return _record(document)

    def submit_member(self, ip: str, locale: str, platform: str,
                      datetime: int | None = None) -> dict:
        fields = {"ip": ip, "locale": locale, "platform": platform}
        if datetime is not None:
            fields["datetime"] = datetime
        return self._call("POST", "/api/submit-member", "member", fields)

    def discard_member(self, identifier: int) -> dict:
        return self._call("GET", "/api/discard-member",
                          params={"identifier": identifier})

    def collect_member(self, filters: dict | None = None) -> list[dict]:
        return self._call("POST", "/api/collect-member", "filter", filters)

    def adjust_member(self, identifier: int, changes: dict) -> dict:
        return self._call("POST", "/api/adjust-member", "member",
                          {"identifier": identifier, **changes})

    def submit_query(self, gif: bytes, member: int, description: str,
                     datetime: int | None = None) -> dict:
        fields = {"argument": base64.b64encode(gif).decode("ascii"),
                  "member": member, "description": description}
        if datetime is not None:
            fields["datetime"] = datetime
        return self._call("POST", "/api/submit-query", "query", fields)

    def discard_query(self, identifier: int) -> dict:
        return self._call("GET", "/api/discard-query",
                          params={"identifier": identifier})

    def collect_query(self, member: int,
                      filters: dict | None = None) -> list[dict]:
        return self._call("POST", f"/api/collect-query/{member}",
                          "filter", filters)

    def adjust_query(self, identifier: int, changes: dict) -> dict:
        return self._call("POST", "/api/adjust-query", "query",
                          {"identifier": identifier, **changes})

    def collect_response(self, query: int,
                         filters: dict | None = None) -> list[dict]:
        return self._call("POST", f"/api/collect-response/{query}",
                          "filter", filters)

    def collect_report(self) -> list[dict]:
        return self._call("POST", "/api/collect-report")
