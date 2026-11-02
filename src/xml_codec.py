"""Преобразование простых XML-документов в поля записей и обратно."""

from collections.abc import Mapping
from xml.etree import ElementTree as ET


class XmlError(ValueError):
    """Запрос содержит неподходящий XML."""


INTEGER_FIELDS = {"identifier", "datetime", "member", "executing",
                  "query", "cache_hit", "duration"}


def parse_fields(data: bytes, root_name: str) -> dict:
    """Прочитать плоский XML, например <member><ip>...</ip></member>."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as error:
        raise XmlError("Некорректный XML") from error
    if root.tag != root_name or root.attrib:
        raise XmlError(f"Ожидался элемент <{root_name}>")
    fields = {}
    for child in root:
        if child.attrib or len(child) or child.tag in fields:
            raise XmlError("Поля должны быть простыми и неповторяющимися")
        value = child.text or ""
        if child.tag in INTEGER_FIELDS:
            try:
                value = int(value)
            except ValueError as error:
                message = f"Поле {child.tag} должно быть числом"
                raise XmlError(message) from error
        fields[child.tag] = value
    return fields


def render_xml(root_name: str, records: list | tuple | Mapping) -> bytes:
    """Сформировать XML для записи, списка записей или ошибки."""
    root = ET.Element(root_name)
    if isinstance(records, Mapping):
        _append_fields(root, records)
    elif isinstance(records, tuple) and hasattr(records, "_asdict"):
        _append_fields(root, records._asdict())
    else:
        for record in records:
            item = ET.SubElement(root, "item")
            _append_fields(item, record._asdict())
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _append_fields(parent: ET.Element, fields: Mapping) -> None:
    for name, value in fields.items():
        child = ET.SubElement(parent, name)
        child.text = str(value)
