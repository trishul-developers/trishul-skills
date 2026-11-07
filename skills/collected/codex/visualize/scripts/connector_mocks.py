"""Validate explicitly supplied connector fixtures for a standalone preview."""

import json
import re
from pathlib import Path
from urllib.parse import urlsplit

_MAX_JSON_BYTES = 32_768
_MAX_BINDINGS = 8
_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
_PREFIX = "<!-- vis-bindings\n"
_SUFFIX = "\n-->\n"


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _read_json(text: str, label: str):
    try:
        value = json.loads(text, object_pairs_hook=_unique_object)
        # Python accepts NaN and Infinity. The guest and binding protocol require JSON.
        json.dumps(value, allow_nan=False)
        return value
    except (ValueError, RecursionError) as error:
        raise ValueError(f"invalid {label}: {error}") from error


def _valid_interval(value, minimum: int) -> bool:
    return type(value) in (int, float) and minimum <= value <= 86_400 and value % 1 == 0


def _valid_non_tool(binding: dict[str, object]) -> bool:
    # The app rejects the entire vis-bindings header if a sibling source is malformed.
    binding_type = binding.get("type")
    if binding_type == "json":
        return set(binding) == {"type", "value"}
    if binding_type == "file":
        path = binding.get("path")
        return (
            set(binding) == {"type", "path"}
            and isinstance(path, str)
            and len(path) <= 512
            and re.fullmatch(
                r"\./(?:[A-Za-z0-9_-][A-Za-z0-9._-]*/)*[A-Za-z0-9_-][A-Za-z0-9._-]*", path
            )
            is not None
        )
    if binding_type == "library":
        file_id = binding.get("libraryFileId")
        return (
            set(binding) == {"type", "libraryFileId", "refreshIntervalSeconds"}
            and isinstance(file_id, str)
            and re.fullmatch(r"libfile_[A-Za-z0-9_-]{1,128}", file_id) is not None
            and _valid_interval(binding.get("refreshIntervalSeconds"), 15)
        )
    if binding_type == "image":
        url = binding.get("url")
        if (
            set(binding) != {"type", "url"}
            or not isinstance(url, str)
            or len(url) > 8192
            or re.search(r"[#\\\s]", url)
        ):
            return False
        parts = urlsplit(url)
        return bool(
            parts.scheme == "https"
            and parts.hostname
            and not parts.username
            and not parts.password
            and parts.port in (None, 443)
        )
    return False


def _declared_tools(fragment: str) -> dict[str, str]:
    end = fragment.find(_SUFFIX, len(_PREFIX), _MAX_JSON_BYTES)
    if not fragment.startswith(_PREFIX) or end < 0:
        raise ValueError("--connector-mocks requires a leading vis-bindings declaration")
    header = fragment[: end + len(_SUFFIX)]
    declaration = fragment[len(_PREFIX) : end]
    if len(header.encode()) > _MAX_JSON_BYTES or re.search(r"[<>]", declaration):
        raise ValueError("invalid vis-bindings header")
    bindings = _read_json(declaration, "vis-bindings")
    if not isinstance(bindings, dict) or len(bindings) > _MAX_BINDINGS:
        raise ValueError("vis-bindings must declare at most eight named bindings")
    tools = {}
    for name, binding in bindings.items():
        if (
            not _NAME.fullmatch(name)
            or name in {"constructor", "prototype"}
            or not isinstance(binding, dict)
        ):
            raise ValueError(f"invalid vis-bindings entry {name!r}")
        if binding.get("type") != "tool":
            if not _valid_non_tool(binding):
                raise ValueError(f"invalid vis-bindings entry {name!r}")
            continue
        tool = binding.get("tool")
        interval = binding.get("refreshIntervalSeconds")
        if (
            set(binding) != {"type", "tool", "arguments", "refreshIntervalSeconds"}
            or not isinstance(tool, str)
            or not 1 <= len(tool) <= 256
            or not isinstance(binding.get("arguments"), dict)
            or not _valid_interval(interval, 900)
        ):
            raise ValueError(f"invalid connector declaration for {name!r}")
        tools[name] = tool
    if not tools:
        raise ValueError("--connector-mocks requires at least one tool binding")
    return tools


def preview_connector_data(fragment: str, fixture: Path) -> str:
    tools = _declared_tools(fragment)
    if fixture.is_symlink() or not fixture.is_file() or fixture.stat().st_size > 1_000_000:
        raise ValueError("connector mock file must be a regular UTF-8 JSON file of at most 1 MB")
    mocks = _read_json(fixture.read_text(encoding="utf-8"), "connector mocks")
    if not isinstance(mocks, dict):
        raise ValueError("connector mocks must be an object keyed by binding name")  # noqa: TRY004
    if missing := sorted(tools.keys() - mocks.keys()):
        raise ValueError(f"missing connector mocks for: {', '.join(missing)}")
    if unknown := sorted(mocks.keys() - tools.keys()):
        raise ValueError(f"no declared tool binding for mock: {', '.join(unknown)}")
    values = {}
    for name, tool in tools.items():
        mock = mocks[name]
        if not isinstance(mock, dict) or set(mock) != {"tool", "value"} or mock["tool"] != tool:
            raise ValueError(f"mock {name!r} must contain tool {tool!r} and a JSON value")
        encoded = json.dumps(
            mock["value"], allow_nan=False, ensure_ascii=False, separators=(",", ":")
        )
        if len(encoded.encode()) > _MAX_JSON_BYTES:
            raise ValueError(f"mock {name!r} exceeds the 32 KiB connector result limit")
        values[name] = mock["value"]
    # Keep strings such as </script> inert inside the iframe's JSON data block.
    payload = json.dumps(values, ensure_ascii=False, separators=(",", ":")).replace("<", r"\u003c")
    return f'<script type="application/json" id="codex-connector-mocks">{payload}</script>\n'
