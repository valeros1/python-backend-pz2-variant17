"""Hypothesis генерирует последовательности действий через HTTP-клиент."""

import base64

from fastapi.testclient import TestClient
from hypothesis import settings, strategies as st
from hypothesis.stateful import (RuleBasedStateMachine, initialize,
                                 invariant, precondition, rule)

from examples.demo import SAMPLES, make_gif
from src.client import ApiClient, ApiError
from src.server import Settings, create_app


GIFS = (make_gif(SAMPLES[0]), make_gif(SAMPLES[1]))


class ApiMachine(RuleBasedStateMachine):
    """Независимые ожидаемые записи сверяются с состоянием сервера."""

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

    @initialize()
    def required_routes(self):
        """Каждый из десяти обработчиков вызывается в каждом прогоне."""
        member = self.add_member(1)
        assert len(self.client.collect_member()) == 1
        self.client.adjust_member(member, {"locale": "en"})
        self.members[member]["locale"] = "en"
        query = self.add_query(member)
        assert len(self.client.collect_query(member)) == 1
        self.client.adjust_query(query, {"description": "updated"})
        self.queries[query]["description"] = "updated"
        assert len(self.client.collect_response(query)) == 1
        assert len(self.client.collect_report()) == 1
        self.client.discard_query(query)
        del self.queries[query]
        self.client.discard_member(member)
        del self.members[member]
        unused = self.add_member(2)
        assert self.client.collect_member({"identifier": unused})

    @rule(number=st.integers(min_value=3, max_value=200))
    def create_member(self, number):
        self.add_member(number)

    @precondition(lambda self: bool(self.members))
    @rule(index=st.integers(min_value=0, max_value=100))
    def update_member(self, index):
        identifier = sorted(self.members)[index % len(self.members)]
        locale = "en" if self.members[identifier]["locale"] == "ru" else "ru"
        self.client.adjust_member(identifier, {"locale": locale})
        self.members[identifier]["locale"] = locale

    @precondition(lambda self: bool(self.members))
    @rule(index=st.integers(min_value=0, max_value=100))
    def create_query(self, index):
        member = sorted(self.members)[index % len(self.members)]
        self.add_query(member)

    @precondition(lambda self: bool(self.queries))
    @rule(index=st.integers(min_value=0, max_value=100))
    def update_query(self, index):
        identifier = sorted(self.queries)[index % len(self.queries)]
        description = f"changed-{index}"
        self.client.adjust_query(identifier, {"description": description})
        self.queries[identifier]["description"] = description

    @precondition(lambda self: bool(self.members))
    @rule(index=st.integers(min_value=0, max_value=100))
    def try_discard_member(self, index):
        identifier = sorted(self.members)[index % len(self.members)]
        linked = any(item["member"] == identifier
                     for item in self.queries.values())
        if linked:
            try:
                self.client.discard_member(identifier)
            except ApiError:
                return
            raise AssertionError("Связанный Member был удалён")
        self.client.discard_member(identifier)
        del self.members[identifier]

    @precondition(lambda self: bool(self.queries))
    @rule(index=st.integers(min_value=0, max_value=100))
    def discard_query(self, index):
        identifier = sorted(self.queries)[index % len(self.queries)]
        self.client.discard_query(identifier)
        del self.queries[identifier]

    @rule()
    def reject_query_without_member(self):
        try:
            self.client.submit_query(GIFS[0], 999999, "invalid")
        except ApiError as error:
            assert "HTTP 400" in str(error)
        else:
            raise AssertionError("Query без Member была создана")

    @rule()
    def read_report(self):
        arguments = dict.fromkeys(item["argument"]
                                  for item in self.queries.values())
        expected = [{"argument": argument, "cache_hit": 0,
                     "status": "test"} for argument in arguments]
        assert self.client.collect_report() == expected

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


TestApiMachine = ApiMachine.TestCase
TestApiMachine.settings = settings(max_examples=12, stateful_step_count=12,
                                   deadline=None)
