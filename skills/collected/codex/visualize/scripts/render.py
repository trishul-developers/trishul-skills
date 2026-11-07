from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from html import escape
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from runpy import run_path
from urllib.parse import urlsplit

_SKILL_DIRECTORY = Path(__file__).resolve().parents[1]
_FRAGMENT_PLACEHOLDER = "<!--__INLINE_VISUALIZATION_FRAGMENT__-->"
_MAX_FRAGMENT_BYTES = 1_000_000
_DOCUMENT_ERROR = "source must be an HTML fragment, not a complete document"
_HOST_API_REFERENCE = re.compile(r"\b(?:window|globalThis)\.openai\b")
_COMPONENT_SOURCE = "https://persistent.oaistatic.com/plugins/visualize/"
_RESOURCE_SOURCES = " ".join(
    (
        "blob:",
        "data:",
        "https://cdnjs.cloudflare.com",
        "https://cdn.jsdelivr.net",
        "https://esm.sh",
        "https://fonts.bunny.net",
        "https://fonts.googleapis.com",
        "https://fonts.gstatic.com",
        "https://unpkg.com",
    ),
)
_FRAME_CSP = "; ".join(
    (
        "default-src 'none'",
        f"script-src 'unsafe-inline' 'unsafe-eval' 'wasm-unsafe-eval' {_RESOURCE_SOURCES} {_COMPONENT_SOURCE}",
        f"style-src 'unsafe-inline' {_RESOURCE_SOURCES} {_COMPONENT_SOURCE}charts/",
        f"img-src {_RESOURCE_SOURCES}",
        f"font-src {_RESOURCE_SOURCES}",
        f"media-src {_RESOURCE_SOURCES}",
        "worker-src blob:",
        "connect-src blob: data:",
        "frame-src 'none'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'none'",
    ),
)
# A srcdoc frame inherits the shell CSP, so the shell must permit resources
# which the stricter inner frame policy may load.
_SHELL_CSP = _FRAME_CSP.replace("frame-src 'none'", "frame-src 'self'")


# BEGIN SHARED CALENDAR DETECTION
_CALENDAR_ENTRY = re.compile(
    r"https://persistent\.oaistatic\.com"
    r"/plugins/visualize/widgets/[^/?#]+/(?:calendar|element)\.js(?:[?#].*)?"
)
_SCRIPT_TYPE = re.compile(r"(?:text|application)/(?:java|ecma)script")
_JS_TOKENS = re.compile(
    r"""//[^\r\n]*|/\*.*?(?:\*/|$)|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`|[\w$]+|[^\s]""",
    re.DOTALL,
)


_REGEXP_LITERAL = re.compile(r"/(?:\\[^\r\n]|\[(?:\\.|[^\]\\\r\n])*\]|[^/\[\\\r\n])+/[a-z]*")
_REGEXP_PREFIXES = frozenset("( [ { = , : ; ! ~ ? & | + - * > return throw case yield".split())


def _calendar_entry(url: str) -> bool:
    return _CALENDAR_ENTRY.fullmatch(url) is not None


def _js_tokens(source: str) -> list[str]:
    tokens: list[str] = []
    position = 0
    while match := _JS_TOKENS.search(source, position):
        token = match[0]
        position = match.end()
        if token.startswith(("//", "/*")):
            continue
        if token == "/" and (not tokens or tokens[-1] in _REGEXP_PREFIXES):
            if literal := _REGEXP_LITERAL.match(source, match.start()):
                token = literal[0]
                position = literal.end()
        tokens.append(token)
    return tokens


def _imports_calendar(source: str, *, module: bool) -> bool:
    # Only an import specifier reserves the element name. Links, comments and
    # ordinary string literals containing an example import must stay inert.
    tokens = _js_tokens(source)
    for i, token in enumerate(tokens):
        if token[0] not in ("'", '"', "`") or not _calendar_entry(token[1:-1]):
            continue
        if token[0] == "`" and "${" in token:
            continue
        if module and token[0] != "`" and i >= 1 and tokens[i - 1] in ("import", "from"):
            return True
        if (
            i >= 2
            and tokens[i - 2 : i] == ["import", "("]
            and (i == 2 or tokens[i - 3] != ".")
            and i + 1 < len(tokens)
            and tokens[i + 1] in (")", ",")
        ):
            return True
    return False


class _CalendarImportParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.found = False
        self._inert = 0
        self._inline_module: bool | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("template", "noscript", "textarea", "title"):
            self._inert += 1
        if self.found or self._inert or tag != "script":
            return
        attributes = dict(attrs)
        script_type = (attributes.get("type") or "").strip().lower()
        module = script_type == "module"
        if not module and (
            "nomodule" in attributes or (script_type and not _SCRIPT_TYPE.fullmatch(script_type))
        ):
            return
        if "src" in attributes:
            self.found = module and _calendar_entry((attributes["src"] or "").strip())
        else:
            self._inline_module = module

    def handle_data(self, data: str) -> None:
        if not self.found and self._inline_module is not None:
            self.found = _imports_calendar(data, module=self._inline_module)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._inline_module = None
        elif tag in ("template", "noscript", "textarea", "title") and self._inert:
            self._inert -= 1


def uses_bundled_calendar(fragment: str) -> bool:
    if not re.search(r"\bviz-calendar(?![-\w])", fragment, re.IGNORECASE):
        return False
    if "/plugins/visualize/widgets/" not in fragment:
        return True
    scripts = _CalendarImportParser()
    scripts.feed(fragment)
    scripts.close()
    return not scripts.found


# END SHARED CALENDAR DETECTION


class _FragmentHTMLParser(HTMLParser):
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # Older HTMLParser versions only enter text mode for script and style themselves.
        if not hasattr(HTMLParser, "RCDATA_CONTENT_ELEMENTS") and tag in {
            "title",
            "textarea",
            "xmp",
            "iframe",
            "noembed",
            "noframes",
        }:
            self.set_cdata_mode(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        super().handle_startendtag(tag, attrs)
        # The base implementation also calls handle_starttag for an empty element.
        if self.cdata_elem == tag:
            self.clear_cdata_mode()

    def parse_marked_section(self, i: int, report: bool = True) -> int:
        try:
            return super().parse_marked_section(i, report)
        except AssertionError:
            # Older parsers raise on unknown <![...]> declarations instead of consuming a comment.
            return self.parse_bogus_comment(i, report)


class _FragmentValidator(_FragmentHTMLParser):
    def close(self) -> None:
        # HTMLParser treats an unfinished start tag as text at EOF, but the wrapper can complete it.
        if self.cdata_elem is None and re.match(
            r"<(?:html|head|body)(?=[\t\n\f\r />]|$)", self.rawdata, re.IGNORECASE | re.ASCII
        ):
            raise ValueError(_DOCUMENT_ERROR)
        super().close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        super().handle_starttag(tag, attrs)
        if tag in {"html", "head", "body"}:
            raise ValueError(_DOCUMENT_ERROR)

    def handle_decl(self, decl: str) -> None:
        if decl.lower().startswith("doctype"):
            raise ValueError(_DOCUMENT_ERROR)


def _read_fragment(source: Path) -> str:
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"source must be a regular file: {source}")
    if source.stat().st_size > _MAX_FRAGMENT_BYTES:
        raise ValueError("source fragment exceeds the 1 MB size limit")
    fragment = source.read_text(encoding="utf-8")
    parser = _FragmentValidator()
    parser.feed(fragment)
    parser.close()
    return fragment


def _default_title(source: Path) -> str:
    words = source.stem.replace("-", " ").replace("_", " ").split()
    return " ".join(word.capitalize() for word in words) or "Visualization"


def calendar_script(fragment: str) -> str:
    """Install the synchronous day calendar only for fragments that use it."""
    if not uses_bundled_calendar(fragment):
        return ""
    source = (_SKILL_DIRECTORY / "assets" / "calendar.js").read_text(encoding="utf-8")
    return "<script>" + source.replace("</script", "<\\/script") + "</script>"


@dataclass(frozen=True)
class _ShareSource:
    title: str
    provider: str | None = None
    type: str | None = None
    date: str | None = None
    description: str | None = None
    url: str | None = None


@dataclass(frozen=True)
class _ShareMetadata:
    version: int
    authorName: str | None
    sources: list[_ShareSource]


class _ShareMetadataParser(_FragmentHTMLParser):
    _VOID_ELEMENTS = frozenset(
        "area base br col embed hr img input link meta param source track wbr".split()
    )
    _MATH_TEXT_ELEMENTS = frozenset({"mi", "mo", "mn", "ms", "mtext"})
    _FOREIGN_BREAKOUT_ELEMENTS = frozenset(
        (
            "b big blockquote body br center code dd div dl dt em embed h1 h2 h3 h4 h5 h6 "
            "head hr i img li listing menu meta nobr ol p pre ruby s small span strong "
            "strike sub sup table tt u ul var"
        ).split()
    )

    def __init__(self) -> None:
        super().__init__()
        self.blocks: list[str] = []
        self.active = False
        # Track only the context needed to keep HTML template contents out of the outer tree.
        self._elements: list[tuple[str, str, bool]] = []
        self._positions: dict[str, list[int]] = {}
        self._templates: list[int] = []

    def parse_starttag(self, i: int) -> int:
        end = super().parse_starttag(i)
        # SVG titles allow element children; only HTML titles use RCDATA.
        if (
            self.cdata_elem == "title"
            and self._elements
            and self._elements[-1][:2] == ("title", "svg")
        ):
            self.clear_cdata_mode()
        return end

    def _namespace(self, tag: str) -> str:
        namespace = "html"
        if self._elements:
            parent, namespace, integration = self._elements[-1]
            if (
                integration
                or (
                    namespace == "math"
                    and parent in self._MATH_TEXT_ELEMENTS
                    and tag not in {"mglyph", "malignmark"}
                )
                or (namespace == "math" and parent == "annotation-xml" and tag == "svg")
            ):
                namespace = "html"
        return tag if namespace == "html" and tag in {"svg", "math"} else namespace

    def _pop_to(self, index: int) -> None:
        while len(self._elements) > index:
            tag, namespace, _ = self._elements.pop()
            positions = self._positions[tag]
            positions.pop()
            if not positions:
                del self._positions[tag]
            if namespace == "html" and tag == "template":
                self._templates.pop()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        super().handle_starttag(tag, attrs)
        values = dict(attrs)
        namespace = self._namespace(tag)
        if namespace != "html" and (
            tag in self._FOREIGN_BREAKOUT_ELEMENTS
            or (tag == "font" and any(name in values for name in ("color", "face", "size")))
        ):
            while self._elements:
                parent, parent_namespace, integration = self._elements[-1]
                if (
                    parent_namespace == "html"
                    or integration
                    or (parent_namespace == "math" and parent in self._MATH_TEXT_ELEMENTS)
                ):
                    break
                self._pop_to(len(self._elements) - 1)
            namespace = self._namespace(tag)
        if namespace == "html" and tag == "noscript":
            # Shared exports run scripts, so HTML noscript contents are raw text.
            self.set_cdata_mode(tag)
        if namespace != "html" or tag not in self._VOID_ELEMENTS:
            encoding = next((value for name, value in attrs if name == "encoding"), None)
            integration = (namespace == "svg" and tag in {"foreignobject", "desc", "title"}) or (
                namespace == "math"
                and tag == "annotation-xml"
                and (encoding or "").lower() in {"text/html", "application/xhtml+xml"}
            )
            position = len(self._elements)
            self._positions.setdefault(tag, []).append(position)
            self._elements.append((tag, namespace, integration))
            if namespace == "html" and tag == "template":
                self._templates.append(position)
        if (
            not self._templates
            and tag == "script"
            and values.get("id") == "visualization-share-metadata"
            and values.get("type") == "application/json"
        ):
            self.blocks.append("")
            self.active = True

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"template", "noscript"} and self._namespace(tag) == "html":
            # These HTML elements are not void; a trailing slash does not close them.
            self.handle_starttag(tag, attrs)
        else:
            super().handle_startendtag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self.active = False
        positions = self._positions.get(tag)
        if positions:
            index = positions[-1]
            if not self._templates or index >= self._templates[-1]:
                self._pop_to(index)

    def handle_data(self, data: str) -> None:
        if self.active:
            self.blocks[-1] += data


def _read_share_metadata(fragment: str, metadata_path: Path | None) -> _ShareMetadata:
    parser = _ShareMetadataParser()
    parser.feed(fragment)
    if len(parser.blocks) > 1:
        raise ValueError("a visualization must have at most one share metadata block")
    if metadata_path is not None:
        if (
            metadata_path.is_symlink()
            or not metadata_path.is_file()
            or metadata_path.stat().st_size > 64 * 1024
        ):
            raise ValueError("share metadata must be a regular JSON file under 64 KiB")
        raw = metadata_path.read_text(encoding="utf-8")
    else:
        raw = parser.blocks[0] if parser.blocks else '{"version":1}'
    if len(raw.encode("utf-8")) > 64 * 1024:
        raise ValueError("share metadata exceeds 64 KiB")
    metadata = json.loads(raw)
    if (
        not isinstance(metadata, dict)
        or type(metadata.get("version")) is not int
        or metadata["version"] != 1
    ):
        raise ValueError("share metadata must be an object with version 1")
    author = metadata.get("authorName")
    if "authorName" in metadata:
        if not isinstance(author, str) or not author.strip() or len(author.strip()) > 200:
            raise ValueError("authorName must be a nonempty string under 200 characters")
        author = author.strip()
    sources = metadata.get("sources", [])
    if not isinstance(sources, list) or len(sources) > 100:
        raise ValueError("sources must be an array with at most 100 entries")
    checked_sources: list[_ShareSource] = []
    for source in sources:
        if (
            not isinstance(source, dict)
            or not isinstance(source.get("title"), str)
            or not source["title"].strip()
        ):
            raise ValueError("every source needs its actual title")
        for key, limit in (
            ("title", 300),
            ("provider", 120),
            ("type", 120),
            ("date", 120),
            ("description", 5000),
            ("url", 2000),
        ):
            if key not in source:
                continue
            value = source[key]
            if not isinstance(value, str) or len(value.strip()) > limit:
                raise ValueError(f"source {key} must be a string under {limit} characters")
            source[key] = value.strip()
        if "url" in source:
            url = urlsplit(source["url"])
            if url.scheme != "https" or not url.hostname or url.username or url.password:
                raise ValueError("source URLs must use HTTPS without credentials")
        checked_sources.append(
            _ShareSource(
                title=source["title"],
                provider=source.get("provider"),
                type=source.get("type"),
                date=source.get("date"),
                description=source.get("description"),
                url=source.get("url"),
            )
        )
    return _ShareMetadata(version=1, authorName=author, sources=checked_sources)


def _share_assets(metadata: _ShareMetadata | None, stylesheet: str) -> tuple[str, str]:
    if metadata is None:
        return "", ""
    assets = _SKILL_DIRECTORY / "assets"
    styles = (assets / "share-shell.css").read_text(encoding="utf-8")
    runtime = (
        (assets / "share-shell.js").read_text(encoding="utf-8").replace("</script", r"<\/script")
    )
    configuration = json.dumps(
        {
            "metadata": asdict(metadata),
            "labels": {
                "madeBy": "Made by {author} using {visualize}",
                "madeWith": "Made using {visualize}",
                "sources": "Sources",
                "backToChart": "Back to chart",
                "openSource": "Open source",
            },
        }
    ).replace("<", r"\u003c")
    return (
        f"<style>{stylesheet}\n{styles}</style>",
        f'<script type="application/json" id="visualization-share">{configuration}</script>\n<script>{runtime}</script>',
    )


def _mock_data(fragment: str, fixture: Path | None) -> str:
    if fixture is None:
        return ""
    helper = Path(__file__).with_name("connector_mocks.py")
    return run_path(str(helper))["preview_connector_data"](fragment, fixture)


def _render_document(
    fragment: str,
    title: str,
    metadata: _ShareMetadata | None = None,
    connector_mocks: Path | None = None,
) -> str:
    stylesheet = (_SKILL_DIRECTORY / "assets" / "visualize.css").read_text(
        encoding="utf-8",
    )
    inner_kit = (_SKILL_DIRECTORY / "assets" / "visualize.html").read_text(
        encoding="utf-8",
    )
    host_bridge = (
        (_SKILL_DIRECTORY / "assets" / "standalone-host-bridge.js")
        .read_text(
            encoding="utf-8",
        )
        .replace("</script", r"<\/script")
    )
    shell = (
        (_SKILL_DIRECTORY / "assets" / "standalone-shell.js")
        .read_text(
            encoding="utf-8",
        )
        .replace("</script", r"<\/script")
    )
    inner_html = inner_kit.replace(_FRAGMENT_PLACEHOLDER, calendar_script(fragment) + fragment)
    share_styles, share_runtime = _share_assets(metadata, stylesheet)
    mock_data = _mock_data(fragment, connector_mocks)
    document_title = escape(title)
    frame_html = f"""<!doctype html>
<html lang="en" data-visualize-standalone>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<meta http-equiv="Content-Security-Policy" content="{_FRAME_CSP}">
<title>{document_title}</title>
<style>{stylesheet}
html>body{{padding:0}}</style>
</head>
<body>
<script type="application/json" id="codex-visualization-widget-state">__CODEX_VISUALIZATION_WIDGET_STATE__</script>
{mock_data}<script>{host_bridge}</script>
{inner_html}
</body>
</html>
"""
    return f"""<!doctype html>
<html lang="en" data-visualize-standalone>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer">
<meta http-equiv="Content-Security-Policy" content="{_SHELL_CSP}">
<title>{document_title}</title>
<style>:root{{color-scheme:light dark;background:light-dark(rgb(255 255 255), rgb(24 24 24))}}html,body{{margin:0}}body{{box-sizing:border-box;padding:1rem;background:inherit}}iframe{{display:block;width:100%;height:calc(100vh - 2rem);margin:0 auto;border:0}}</style>
{share_styles}
</head>
<body>
<iframe id="codex-visualization" sandbox="allow-scripts" referrerpolicy="no-referrer" title="{document_title}" data-srcdoc="{escape(frame_html)}"></iframe>
{share_runtime}
<script>{shell}</script>
</body>
</html>
"""


def render(
    fragment_path: Path,
    title: str | None = None,
    *,
    share: bool = False,
    metadata_path: Path | None = None,
    connector_mocks: Path | None = None,
) -> str:
    fragment = _read_fragment(fragment_path)
    metadata = _read_share_metadata(fragment, metadata_path) if share else None
    return _render_document(
        fragment, title or _default_title(fragment_path), metadata, connector_mocks
    )


def export_html(
    source: Path,
    destination: Path,
    *,
    title: str | None = None,
    force: bool = False,
    share: bool = False,
    metadata_path: Path | None = None,
    connector_mocks: Path | None = None,
) -> bool:
    if destination.is_symlink():
        raise ValueError(f"destination cannot be a symbolic link: {destination}")
    if source.resolve() == destination.resolve() or (
        destination.exists() and source.samefile(destination)
    ):
        raise ValueError("source and destination must be different files")

    if connector_mocks is not None and (
        connector_mocks.resolve() == destination.resolve()
        or (destination.exists() and connector_mocks.samefile(destination))
    ):
        raise ValueError("connector mock file and destination must be different files")

    fragment = _read_fragment(source)
    metadata = _read_share_metadata(fragment, metadata_path) if share else None
    if (
        share
        and metadata_path is not None
        and (
            metadata_path.resolve() == destination.resolve()
            or (destination.exists() and metadata_path.samefile(destination))
        )
    ):
        raise ValueError("share metadata and destination must be different files")
    document = _render_document(
        fragment, title or _default_title(source), metadata, connector_mocks
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w" if force else "x", encoding="utf-8", newline="\n") as output:
        output.write(document)
    return _HOST_API_REFERENCE.search(fragment) is not None


def serve(
    source: Path,
    port: int,
    title: str | None,
    *,
    share: bool,
    metadata_path: Path | None,
    connector_mocks: Path | None = None,
) -> None:
    # Fail before opening a server for an invalid initial fragment.
    render(source, title, share=share, metadata_path=metadata_path, connector_mocks=connector_mocks)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path not in ("/", "/index.html"):
                self.send_error(404)
                return
            try:
                encoded_document = render(
                    source,
                    title,
                    share=share,
                    metadata_path=metadata_path,
                    connector_mocks=connector_mocks,
                ).encode("utf-8")
            except (OSError, UnicodeError, ValueError) as exc:
                self.send_error(500, "Cannot render current fragment", explain=str(exc))
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded_document)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(encoded_document)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"http://127.0.0.1:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render an inline visualization fragment as standalone HTML.",
    )
    parser.add_argument("fragment", type=Path, help="absolute fragment HTML path")
    parser.add_argument(
        "destination",
        type=Path,
        nargs="?",
        help="optional output HTML path",
    )
    parser.add_argument(
        "--title",
        help="document title; defaults to the fragment file name",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace the destination if it already exists",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="serve the rendered visualization locally",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="local serve port; defaults to any free port",
    )
    parser.add_argument(
        "--share",
        action="store_true",
        help="add the shared-page card, attribution, and Sources view",
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        help="optional version 1 share metadata JSON; otherwise read the fragment's explicit metadata block",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="check chart payload/import/syntax offline without rendering",
    )
    parser.add_argument(
        "--chart-state",
        action="append",
        default=[],
        metavar="FILE",
        help="with --check, validate an actual chart config in JSON (repeat for control states)",
    )
    parser.add_argument(
        "--connector-mocks",
        type=Path,
        help="preview declared tool bindings with local JSON fixtures keyed by binding name",
    )
    args = parser.parse_args(argv)
    if args.chart_state and not args.check:
        parser.error("--chart-state requires --check")
    if args.check:
        if args.serve or args.share or args.metadata is not None or args.destination is not None:
            parser.error("--check cannot be combined with export options")
        try:
            fragment = _read_fragment(args.fragment)
            _mock_data(fragment, args.connector_mocks)
            node = shutil.which("node")
            if not node:
                raise ValueError("Offline chart validation requires the host's Node runtime")
            result = subprocess.run(
                [
                    node,
                    str(_SKILL_DIRECTORY / "scripts/chart_check.mjs"),
                    "--stdin",
                    *args.chart_state,
                ],
                input=fragment,
                capture_output=True,
                text=True,
            )
            if result.returncode:
                raise ValueError(result.stderr.strip())
            sys.stderr.write(result.stderr)
            print(result.stdout.strip())
            return 0
        except (OSError, UnicodeError, ValueError) as error:
            parser.error(str(error))
    if args.metadata is not None and not args.share:
        parser.error("--metadata requires --share")
    if args.serve and args.destination is not None:
        parser.error("destination cannot be used with --serve")
    if args.destination is not None and args.destination.exists() and not args.force:
        parser.error("destination already exists; pass --force to replace it")
    if args.serve and not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")

    try:
        if args.destination is not None:
            references_host_api = export_html(
                args.fragment,
                args.destination,
                title=args.title,
                force=args.force,
                connector_mocks=args.connector_mocks,
                share=args.share,
                metadata_path=args.metadata,
            )
            if references_host_api:
                print(
                    "warning: the source references window.openai; verify APIs beyond "
                    "widgetState/setWidgetState before hosting",
                    file=sys.stderr,
                )
            print(args.destination)
        elif args.serve:
            serve(
                args.fragment,
                args.port,
                args.title,
                share=args.share,
                metadata_path=args.metadata,
                connector_mocks=args.connector_mocks,
            )
        else:
            document = render(
                args.fragment,
                args.title,
                share=args.share,
                metadata_path=args.metadata,
                connector_mocks=args.connector_mocks,
            )
            sys.stdout.write(document)
    except (OSError, UnicodeError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
