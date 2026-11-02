"""Проверки связей и семиминутного отчёта модели."""

import pytest

from src.model import InMemoryModel, ModelError, ReportRow


def test_member_query_response_and_deletion_order():
    model = InMemoryModel()
    member = model.submit_member("127.0.0.1", "ru", "macOS", 1000)
    query = model.submit_query("GIF", member.identifier, "test", 1000)

    assert model.collect_query(member.identifier) == [query]
    with pytest.raises(ModelError, match="связанные Query"):
        model.discard_member(member.identifier)

    response = model.finish_query(query.identifier, "WebM", "done", "", 2,
                                  1010)
    assert model.collect_response(query.identifier) == [response]
    assert model.collect_query(member.identifier)[0].executing == 0
    assert model.discard_query(query.identifier).executing == 0
    assert model.responses == {}
    assert model.discard_member(member.identifier) == member


def test_report_includes_boundary_and_excludes_older_response():
    model = InMemoryModel()
    member = model.submit_member("127.0.0.1", "ru", "macOS", 1000)
    first = model.submit_query("recent", member.identifier, "", 1000)
    second = model.submit_query("old", member.identifier, "", 1000)
    model.finish_query(first.identifier, "", "done", "", 0, 1580)
    model.finish_query(second.identifier, "", "done", "", 0, 1579)

    assert model.collect_report(now=2000) == [ReportRow("recent", 0, "done")]


def test_filters_and_updates_validate_links():
    model = InMemoryModel()
    member = model.submit_member("127.0.0.1", "ru", "macOS")
    other = model.submit_member("127.0.0.2", "en", "Linux")
    assert model.collect_member({"locale": "ru"}) == [member]
    updated = model.adjust_member(member.identifier, {"locale": "en"})
    assert updated.locale == "en"
    query = model.submit_query("GIF", member.identifier, "")
    changed = model.adjust_query(query.identifier,
                                 {"member": other.identifier})
    assert changed.member == other.identifier
    with pytest.raises(ModelError, match="не найден"):
        model.adjust_query(query.identifier, {"member": 999})
