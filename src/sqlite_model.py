"""Слой данных варианта 17 на SQLite и явных SQL-запросах."""

import sqlite3
import time
from pathlib import Path
from threading import RLock

from src.model import Member, ModelError, Query, ReportRow, Response


RECENT_SECONDS = 7 * 60
MEMBER_FIELDS = {"identifier", "datetime", "ip", "locale", "platform"}
QUERY_FIELDS = {"identifier", "datetime", "argument", "member",
                "description", "executing"}
RESPONSE_FIELDS = {"identifier", "datetime", "output", "status",
                   "exception", "query", "cache_hit", "duration"}


def _stamp(value: int | None) -> int:
    if value is None:
        return int(time.time())
    if type(value) is not int:
        raise ModelError("datetime: требуется целое число")
    return value


def _changes(changes: dict, allowed: dict[str, type]) -> dict:
    if not isinstance(changes, dict) or not changes:
        raise ModelError("Нужно указать изменяемые поля")
    if changes.keys() - allowed.keys():
        raise ModelError("Указано неизвестное или неизменяемое поле")
    for field, value in changes.items():
        expected = allowed[field]
        valid = (type(value) is int if expected is int
                 else isinstance(value, str))
        if not valid:
            kind = "целое число" if expected is int else "строка"
            raise ModelError(f"{field}: требуется {kind}")
    return changes


def _where(filters: dict | None, allowed: set[str],
           prefix: str = " WHERE ") -> tuple[str, list]:
    values = filters or {}
    if not isinstance(values, dict) or values.keys() - allowed:
        raise ModelError("Неизвестное поле фильтра")
    clause = " AND ".join(f"{name} = ?" for name in values)
    return (prefix + clause if clause else "", list(values.values()))


class SQLiteModel:
    """Тот же интерфейс, что InMemoryModel, с хранением на диске."""

    def __init__(self, path: str | Path) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.lock = RLock()
        self.connection.execute("PRAGMA foreign_keys = ON")
        with self.connection:
            self.connection.executescript("""
                CREATE TABLE IF NOT EXISTS members (
                    identifier INTEGER PRIMARY KEY AUTOINCREMENT,
                    datetime INTEGER NOT NULL,
                    ip TEXT NOT NULL,
                    locale TEXT NOT NULL,
                    platform TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS queries (
                    identifier INTEGER PRIMARY KEY AUTOINCREMENT,
                    datetime INTEGER NOT NULL,
                    argument TEXT NOT NULL,
                    member INTEGER NOT NULL REFERENCES members(identifier)
                        ON DELETE RESTRICT,
                    description TEXT NOT NULL,
                    executing INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS responses (
                    identifier INTEGER PRIMARY KEY AUTOINCREMENT,
                    datetime INTEGER NOT NULL,
                    output TEXT NOT NULL,
                    status TEXT NOT NULL,
                    exception TEXT NOT NULL,
                    query INTEGER NOT NULL REFERENCES queries(identifier)
                        ON DELETE CASCADE,
                    cache_hit INTEGER NOT NULL,
                    duration INTEGER NOT NULL
                );
            """)

    def close(self) -> None:
        self.connection.close()

    def _find(self, table: str, identifier: int, record_type):
        if type(identifier) is not int:
            raise ModelError("identifier: требуется целое число")
        row = self.connection.execute(
            f"SELECT * FROM {table} WHERE identifier = ?", (identifier,)
        ).fetchone()
        if row is None:
            raise ModelError(f"{record_type.__name__} #{identifier} не найден")
        return record_type(**dict(row))

    def submit_member(self, ip: str, locale: str, platform: str,
                      datetime: int | None = None) -> Member:
        values = _changes({"ip": ip, "locale": locale,
                           "platform": platform},
                          {"ip": str, "locale": str, "platform": str})
        with self.lock, self.connection:
            cursor = self.connection.execute(
                "INSERT INTO members(datetime, ip, locale, platform) "
                "VALUES (?, ?, ?, ?)",
                (_stamp(datetime), values["ip"], values["locale"],
                 values["platform"]),
            )
            return self._find("members", cursor.lastrowid, Member)

    def discard_member(self, identifier: int) -> Member:
        with self.lock, self.connection:
            record = self._find("members", identifier, Member)
            try:
                self.connection.execute(
                    "DELETE FROM members WHERE identifier = ?", (identifier,)
                )
            except sqlite3.IntegrityError as error:
                raise ModelError("У Member есть связанные Query") from error
            return record

    def collect_member(self, filters: dict | None = None) -> list[Member]:
        where, values = _where(filters, MEMBER_FIELDS)
        with self.lock:
            rows = self.connection.execute(
                "SELECT * FROM members" + where + " ORDER BY identifier",
                values,
            ).fetchall()
        return [Member(**dict(row)) for row in rows]

    def adjust_member(self, identifier: int, changes: dict) -> Member:
        values = _changes(changes, {"datetime": int, "ip": str,
                                    "locale": str, "platform": str})
        with self.lock, self.connection:
            self._find("members", identifier, Member)
            assignment = ", ".join(f"{field} = ?" for field in values)
            self.connection.execute(
                f"UPDATE members SET {assignment} WHERE identifier = ?",
                [*values.values(), identifier],
            )
            return self._find("members", identifier, Member)

    def submit_query(self, argument: str, member: int, description: str,
                     datetime: int | None = None) -> Query:
        values = _changes({"argument": argument, "description": description},
                          {"argument": str, "description": str})
        with self.lock, self.connection:
            self._find("members", member, Member)
            cursor = self.connection.execute(
                "INSERT INTO queries(datetime, argument, member, "
                "description, executing) VALUES (?, ?, ?, ?, 1)",
                (_stamp(datetime), values["argument"], member,
                 values["description"]),
            )
            return self._find("queries", cursor.lastrowid, Query)

    def discard_query(self, identifier: int) -> Query:
        with self.lock, self.connection:
            record = self._find("queries", identifier, Query)
            if record.executing:
                raise ModelError("Нельзя удалить выполняемую Query")
            self.connection.execute(
                "DELETE FROM queries WHERE identifier = ?", (identifier,)
            )
            return record

    def collect_query(self, member: int,
                      filters: dict | None = None) -> list[Query]:
        where, values = _where(filters, QUERY_FIELDS, " AND ")
        with self.lock:
            self._find("members", member, Member)
            rows = self.connection.execute(
                "SELECT * FROM queries WHERE member = ?" + where
                + " ORDER BY identifier", [member, *values],
            ).fetchall()
        return [Query(**dict(row)) for row in rows]

    def adjust_query(self, identifier: int, changes: dict) -> Query:
        values = _changes(changes, {"datetime": int, "argument": str,
                                    "member": int, "description": str,
                                    "executing": int})
        with self.lock, self.connection:
            self._find("queries", identifier, Query)
            if "member" in values:
                self._find("members", values["member"], Member)
            assignment = ", ".join(f"{field} = ?" for field in values)
            self.connection.execute(
                f"UPDATE queries SET {assignment} WHERE identifier = ?",
                [*values.values(), identifier],
            )
            return self._find("queries", identifier, Query)

    def collect_response(self, query: int,
                         filters: dict | None = None) -> list[Response]:
        where, values = _where(filters, RESPONSE_FIELDS, " AND ")
        with self.lock:
            self._find("queries", query, Query)
            rows = self.connection.execute(
                "SELECT * FROM responses WHERE query = ?" + where
                + " ORDER BY identifier", [query, *values],
            ).fetchall()
        return [Response(**dict(row)) for row in rows]

    def collect_report(self, now: int | None = None) -> list[ReportRow]:
        border = _stamp(now) - RECENT_SECONDS
        with self.lock:
            rows = self.connection.execute(
                "SELECT DISTINCT q.argument, r.cache_hit, r.status "
                "FROM queries AS q FULL OUTER JOIN responses AS r "
                "ON q.identifier = r.query "
                "WHERE r.datetime >= ? "
                "ORDER BY q.identifier, r.identifier", (border,)
            ).fetchall()
        return [ReportRow(**dict(row)) for row in rows]

    def finish_query(self, query: int, output: str, status: str,
                     exception: str, duration: int,
                     datetime: int | None = None) -> Response:
        values = _changes({"output": output, "status": status,
                           "exception": exception, "duration": duration},
                          {"output": str, "status": str, "exception": str,
                           "duration": int})
        with self.lock, self.connection:
            self._find("queries", query, Query)
            cursor = self.connection.execute(
                "INSERT INTO responses(datetime, output, status, exception, "
                "query, cache_hit, duration) VALUES (?, ?, ?, ?, ?, 0, ?)",
                (_stamp(datetime), values["output"], values["status"],
                 values["exception"], query, values["duration"]),
            )
            self.connection.execute(
                "UPDATE queries SET executing = 0 WHERE identifier = ?",
                (query,),
            )
            return self._find("responses", cursor.lastrowid, Response)
