"""Преобразование простых XML-документов в поля записей и обратно."""

import xml.etree.ElementTree as element_tree
from collections.abc import Mapping


class XmlError(ValueError):
    """Запрос содержит неподходящий XML."""


INTEGER_FIELDS = {"identifier", "datetime", "member", "executing",
                  "query", "cache_hit", "duration"}


def parse_fields(data: bytes, root_name: str) -> dict:
    """Прочитать плоский XML, например <member><ip>...</ip></member>."""
    try:
        root = element_tree.fromstring(data)
    except element_tree.ParseError as error:
        raise XmlError("Некорректный XML") from error
    if root.tag != root_name or root.attrib:
        raise XmlError(f"Ожидался элемент <{root_name}>")
    fields = {}
    for child in root:
        fields[child.tag] = _parse_child(child, fields)
    return fields


def _parse_child(child: element_tree.Element, fields: dict) -> str | int:
    if child.attrib or len(child) or child.tag in fields:
        raise XmlError("Поля должны быть простыми и неповторяющимися")
    value = child.text or ""
    if child.tag not in INTEGER_FIELDS:
        return value
    try:
        return int(value)
    except ValueError as error:
        raise XmlError(f"Поле {child.tag} должно быть числом") from error


def render_xml(root_name: str, records: list | tuple | Mapping) -> bytes:
    """Сформировать XML для записи, списка записей или ошибки."""
    root = element_tree.Element(root_name)
    if isinstance(records, Mapping):
        _append_fields(root, records)
    elif isinstance(records, tuple) and hasattr(records, "_asdict"):
        _append_fields(root, records._asdict())
    else:
        for record in records:
            item = element_tree.SubElement(root, "item")
            _append_fields(item, record._asdict())
    return element_tree.tostring(root, encoding="utf-8", xml_declaration=True)


def _append_fields(parent: element_tree.Element, fields: Mapping) -> None:
    for name, value in fields.items():
        child = element_tree.SubElement(parent, name)
        child.text = str(value)
