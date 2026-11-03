"""Хранилище задач преобразования в памяти для второго этапа."""

import time
from typing import NamedTuple


RECENT_SECONDS = 7 * 60


class ModelError(ValueError):
    """Операция не согласуется с текущими данными."""


class Member(NamedTuple):
    identifier: int
    datetime: int
    ip: str
    locale: str
    platform: str


class Query(NamedTuple):
    identifier: int
    datetime: int
    argument: str
    member: int
    description: str
    executing: int


class Response(NamedTuple):
    identifier: int
    datetime: int
    output: str
    status: str
    exception: str
    query: int
    cache_hit: int
    duration: int


class ReportRow(NamedTuple):
    argument: str | None
    cache_hit: int
    status: str


def _integer(value: object, name: str) -> int:
    if type(value) is not int:
        raise ModelError(f"{name}: требуется целое число")
    return value


def _text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ModelError(f"{name}: требуется строка")
    return value


def _now(value: int | None) -> int:
    return int(time.time()) if value is None else _integer(value, "datetime")


def _matching(record: tuple, filters: dict) -> bool:
    """Проверить равенство указанных полей записи."""
    unknown = filters.keys() - record._fields
    if unknown:
        raise ModelError(f"Неизвестное поле: {sorted(unknown)[0]}")
    return all(getattr(record, field) == value
               for field, value in filters.items())


class InMemoryModel:
    """Три связанные таблицы; интерфейс позже сохранится для SQLite."""

    def __init__(self) -> None:
        self.members: dict[int, Member] = {}
        self.queries: dict[int, Query] = {}
        self.responses: dict[int, Response] = {}
        self.next_ids = {"member": 1, "query": 1, "response": 1}

    def _id(self, table: str) -> int:
        identifier = self.next_ids[table]
        self.next_ids[table] += 1
        return identifier

    @staticmethod
    def _find(table: dict, identifier: int, name: str):
        _integer(identifier, "identifier")
        try:
            return table[identifier]
        except KeyError as error:
            raise ModelError(f"{name} #{identifier} не найден") from error

    def submit_member(self, ip: str, locale: str, platform: str,
                      datetime: int | None = None) -> Member:
        record = Member(self._id("member"), _now(datetime),
                        _text(ip, "ip"), _text(locale, "locale"),
                        _text(platform, "platform"))
        self.members[record.identifier] = record
        return record

    def discard_member(self, identifier: int) -> Member:
        record = self._find(self.members, identifier, "Member")
        if any(item.member == identifier for item in self.queries.values()):
            raise ModelError("У Member есть связанные Query")
        return self.members.pop(record.identifier)

    def collect_member(self, filters: dict | None = None) -> list[Member]:
        return [item for item in self.members.values()
                if _matching(item, filters or {})]

    def adjust_member(self, identifier: int, changes: dict) -> Member:
        record = self._find(self.members, identifier, "Member")
        allowed = {"datetime": int, "ip": str, "locale": str,
                   "platform": str}
        values = self._validated_changes(changes, allowed)
        updated = record._replace(**values)
        self.members[identifier] = updated
        return updated

    def submit_query(self, argument: str, member: int, description: str,
                     datetime: int | None = None) -> Query:
        self._find(self.members, member, "Member")
        record = Query(self._id("query"), _now(datetime),
                       _text(argument, "argument"), member,
                       _text(description, "description"), 1)
        self.queries[record.identifier] = record
        return record

    def discard_query(self, identifier: int) -> Query:
        record = self._find(self.queries, identifier, "Query")
        if record.executing:
            raise ModelError("Нельзя удалить выполняемую Query")
        for response_id, item in list(self.responses.items()):
            if item.query == identifier:
                del self.responses[response_id]
        return self.queries.pop(record.identifier)

    def collect_query(self, member: int,
                      filters: dict | None = None) -> list[Query]:
        self._find(self.members, member, "Member")
        return [item for item in self.queries.values()
                if item.member == member and _matching(item, filters or {})]

    def adjust_query(self, identifier: int, changes: dict) -> Query:
        record = self._find(self.queries, identifier, "Query")
        allowed = {"datetime": int, "argument": str, "member": int,
                   "description": str, "executing": int}
        values = self._validated_changes(changes, allowed)
        if "member" in values:
            self._find(self.members, values["member"], "Member")
        updated = record._replace(**values)
        self.queries[identifier] = updated
        return updated

    def collect_response(self, query: int,
                         filters: dict | None = None) -> list[Response]:
        self._find(self.queries, query, "Query")
        return [item for item in self.responses.values()
                if item.query == query and _matching(item, filters or {})]

    def collect_report(self, now: int | None = None) -> list[ReportRow]:
        """Полностью соединить Query и Response, затем отобрать ответы."""
        border = _now(now) - RECENT_SECONDS
        pairs = []
        for query in self.queries.values():
            related = [response for response in self.responses.values()
                       if response.query == query.identifier]
            if related:
                pairs.extend((query, response) for response in related)
            else:
                pairs.append((query, None))
        pairs.extend((None, response) for response in self.responses.values()
                     if response.query not in self.queries)
        rows = [ReportRow(query.argument if query is not None else None,
                          response.cache_hit, response.status)
                for query, response in pairs
                if response is not None and response.datetime >= border]
        return list(dict.fromkeys(rows))

    def finish_query(self, query: int, output: str, status: str,
                     exception: str, duration: int,
                     datetime: int | None = None) -> Response:
        """Внутренняя операция: записать результат работы конвертера."""
        current = self._find(self.queries, query, "Query")
        record = Response(self._id("response"), _now(datetime),
                          _text(output, "output"), _text(status, "status"),
                          _text(exception, "exception"), query, 0,
                          _integer(duration, "duration"))
        self.responses[record.identifier] = record
        self.queries[query] = current._replace(executing=0)
        return record

    @staticmethod
    def _validated_changes(changes: dict, allowed: dict) -> dict:
        if not isinstance(changes, dict) or not changes:
            raise ModelError("Нужно указать изменяемые поля")
        if changes.keys() - allowed.keys():
            raise ModelError("Указано неизвестное или неизменяемое поле")
        return {field: (_integer(value, field)
                        if allowed[field] is int else _text(value, field))
                for field, value in changes.items()}
