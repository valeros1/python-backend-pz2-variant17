"""Проверки сохранения на диске, связей и формулы отчёта."""

import pytest

from src.model import ModelError, ReportRow
from src.sqlite_model import SQLiteModel


def test_records_survive_reopening_database(tmp_path):
    path = tmp_path / "tasks.sqlite3"
    first = SQLiteModel(path)
    member = first.submit_member("127.0.0.1", "ru", "macOS", 1000)
    query = first.submit_query("GIF", member.identifier, "sample", 1000)
    first.finish_query(query.identifier, "WebM", "done", "", 2, 1580)
    first.close()

    second = SQLiteModel(path)
    assert second.collect_member()[0].identifier == member.identifier
    assert second.collect_query(member.identifier)[0].executing == 0
    assert second.collect_response(query.identifier)[0].output == "WebM"
    assert second.collect_report(now=2000) == [ReportRow("GIF", 0, "done")]
    second.close()


def test_foreign_keys_cascade_and_recent_boundary(tmp_path):
    model = SQLiteModel(tmp_path / "tasks.sqlite3")
    member = model.submit_member("127.0.0.1", "ru", "macOS", 1000)
    recent = model.submit_query("recent", member.identifier, "", 1000)
    old = model.submit_query("old", member.identifier, "", 1000)
    empty = model.submit_query("empty", member.identifier, "", 1000)
    model.finish_query(recent.identifier, "", "done", "", 0, 1580)
    model.finish_query(old.identifier, "", "done", "", 0, 1579)

    with pytest.raises(ModelError, match="связанные Query"):
        model.discard_member(member.identifier)
    assert model.collect_report(now=2000) == [ReportRow("recent", 0, "done")]
    model.discard_query(recent.identifier)
    remaining = model.connection.execute(
        "SELECT COUNT(*) FROM responses WHERE query = ?",
        (recent.identifier,),
    ).fetchone()[0]
    assert remaining == 0
    with pytest.raises(ModelError, match="выполняемую"):
        model.discard_query(empty.identifier)
    model.close()
