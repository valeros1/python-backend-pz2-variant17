"""Hypothesis генерирует последовательности действий через HTTP-клиент."""

import base64
from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient
from hypothesis import settings, strategies as st
from hypothesis.stateful import (Bundle, RuleBasedStateMachine, invariant,
                                 multiple, rule)

from examples.demo import SAMPLES, make_gif
from src.client import ApiClient, ApiError
from src.server import Settings, create_app


GIFS = (make_gif(SAMPLES[0]), make_gif(SAMPLES[1]))


class ApiMachine(RuleBasedStateMachine):
    """Независимые ожидаемые записи сверяются с состоянием сервера."""

    member_ids = Bundle("member_ids")
    query_ids = Bundle("query_ids")

    def __init__(self):
        super().__init__()
        self.context = TestClient(create_app(Settings("u", "p", True)))
        self.http = self.context.__enter__()
        self.client = ApiClient("u", "p", transport=self.http)
        self.members = {}
        self.queries = {}
        self.next_member = 1
        self.next_query = 1

    def teardown(self):
        self.context.__exit__(None, None, None)

    def add_member(self, number):
        ip = f"10.0.0.{number}"
        result = self.client.submit_member(ip, "ru", "macOS", 1000)
        assert result["identifier"] == self.next_member
        self.members[self.next_member] = {
            "identifier": self.next_member, "datetime": 1000,
            "ip": ip, "locale": "ru", "platform": "macOS",
        }
        self.next_member += 1
        return result["identifier"]

    def add_query(self, member):
        gif = GIFS[(self.next_query - 1) % len(GIFS)]
        argument = base64.b64encode(gif).decode("ascii")
        result = self.client.submit_query(gif, member, "sample", 1000)
        assert result["identifier"] == self.next_query
        self.queries[self.next_query] = {
            "identifier": self.next_query, "datetime": 1000,
            "argument": argument, "member": member,
            "description": "sample", "executing": 0,
        }
        self.next_query += 1
        return result["identifier"]

    @rule(target=member_ids, number=st.integers(min_value=1, max_value=200))
    def create_member(self, number):
        return self.add_member(number)

    @rule(member=member_ids)
    def update_member(self, member):
        if member not in self.members:
            with pytest.raises(ApiError, match="HTTP 400"):
                self.client.adjust_member(member, {"locale": "en"})
            return
        identifier = member
        locale = "en" if self.members[identifier]["locale"] == "ru" else "ru"
        self.client.adjust_member(identifier, {"locale": locale})
        self.members[identifier]["locale"] = locale

    @rule(target=query_ids, member=member_ids)
    def create_query(self, member):
        if member not in self.members:
            with pytest.raises(ApiError, match="HTTP 400"):
                self.client.submit_query(GIFS[0], member, "sample")
            return multiple()
        return self.add_query(member)

    @rule(query=query_ids,
          description=st.text(alphabet="abc", max_size=8))
    def update_query(self, query, description):
        if query not in self.queries:
            with pytest.raises(ApiError, match="HTTP 400"):
                self.client.adjust_query(query, {"description": description})
            return
        self.client.adjust_query(query, {"description": description})
        self.queries[query]["description"] = description

    @rule(member=member_ids)
    def try_discard_member(self, member):
        linked = any(item["member"] == member
                     for item in self.queries.values())
        if member not in self.members or linked:
            with pytest.raises(ApiError, match="HTTP 400"):
                self.client.discard_member(member)
            return
        self.client.discard_member(member)
        del self.members[member]

    @rule(query=query_ids)
    def discard_query(self, query):
        if query not in self.queries:
            with pytest.raises(ApiError, match="HTTP 400"):
                self.client.discard_query(query)
            return
        self.client.discard_query(query)
        del self.queries[query]

    @rule()
    def reject_query_without_member(self):
        with pytest.raises(ApiError, match="HTTP 400"):
            self.client.submit_query(GIFS[0], 999999, "invalid")

    @rule()
    def reject_unauthorized_request(self):
        result = self.http.post("/api/collect-report", auth=None)
        assert result.status_code == HTTPStatus.UNAUTHORIZED

    @rule()
    def reject_invalid_xml(self):
        result = self.http.post("/api/submit-member", content="<member>",
                                auth=("u", "p"))
        assert result.status_code == HTTPStatus.BAD_REQUEST

    @invariant()
    def compare_all_records(self):
        actual_members = self.client.collect_member()
        assert actual_members == list(self.members.values())
        for member in self.members:
            actual_queries = self.client.collect_query(member)
            expected_queries = [item for item in self.queries.values()
                                if item["member"] == member]
            assert actual_queries == expected_queries
        for query in self.queries:
            responses = self.client.collect_response(query)
            assert len(responses) == 1
            assert responses[0]["query"] == query
            assert responses[0]["status"] == "test"
        arguments = dict.fromkeys(item["argument"]
                                  for item in self.queries.values())
        expected = [{"argument": argument, "cache_hit": 0,
                     "status": "test"} for argument in arguments]
        assert self.client.collect_report() == expected


TestApiMachine = ApiMachine.TestCase
TestApiMachine.settings = settings(max_examples=20, stateful_step_count=20,
                                   deadline=None)
