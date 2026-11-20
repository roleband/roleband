"""Only the listed places build an httpx client; every other request borrows one.

An outbound request follows the project's rules only if its client does: the tier client
(`make_tier_client`) paces, retries and identifies collection traffic, `public_client`
connects only to public addresses, and `make_client` sets the shared timeout and redirect
defaults. A module that builds its own `httpx.Client` or `httpx.AsyncClient`, or calls one of
httpx's module-level request helpers (`httpx.get`, `httpx.stream`, ...), which build a client
for the one request, skips all of them, and nothing in review points at it. So each place that
does is listed here with its reason, and the scan fails on a place that is not listed and on a
listed place that no longer does: the list can only shrink, and growing it is a decision a
reviewer sees.

The scan counts every reference to a client class or a request helper, so an alias, a default
argument or a factory counts where it is made, and it follows a name or a module through
first-party imports and re-exports. Type positions do not count: annotations, `type` aliases,
the type of `isinstance`, `issubclass` and typing's `cast`, and the arguments of a generic
(`Callable[...]`, `list[...]`). Names are resolved per file, so a parameter that shadows an
imported name is counted too, and a local `cast` is not typing's: the scan errs toward a place
a reviewer looks at.

`scripts/` is scanned as well as `tracker/`: it ships with the engine, and its checks reach
the network. `tests/` is not: tests build clients around in-process transports. Other HTTP
stacks (`urllib.request`, `curl_cffi`) are outside this fence.
"""

from __future__ import annotations

import ast
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
SCANNED = ("tracker", "scripts")
CLIENTS = {"Client", "AsyncClient"}
HELPERS = {"get", "post", "put", "patch", "delete", "head", "options", "request", "stream"}
TARGETS = CLIENTS | HELPERS

#: `path::function` -> why that place may build its own client.
ALLOWED = {
    "tracker/connectors/runtime/tiers.py::make_tier_client":
        "the tier client every collection request goes through",
    "tracker/platform/http.py::make_client": "the shared client for other tracker requests",
    "tracker/platform/safe_fetch.py::public_client":
        "connects only to public addresses, for a URL a person or agent supplies",
    "tracker/platform/windows_packages.py::download":
        "the Windows update download: synchronous, no redirects, no environment proxy",
    "tracker/platform/windows_updates.py::fetch_release":
        "the Windows update feed: synchronous, no redirects, no environment proxy",
    "tracker/platform/windows_updates.py::check":
        "the Windows update feed: synchronous, no redirects, no environment proxy",
    "tracker/semantic/provision.py::_download":
        "the embedding-model download: a pinned revision, each file held to its pinned size and digest",
    "tracker/supervisor/api.py::ApiService._healthy": "the supervisor's probe of its own loopback API",
    "scripts/bench_agent_tasks.py::RecordingProxy.__call__": "a benchmark proxy to the local engine",
    "scripts/bench_agent_tasks.py::bench_engine": "a benchmark polling the local engine it started",
    "scripts/bench_agent_tasks.py::local_host_info": "a benchmark reading the local model server",
    "scripts/bench_agent_tasks.py::_local_loop": "a benchmark talking to the local model server",
    "scripts/bench_pay_transparency.py::main_async": "a maintainer benchmark of public pay pages",
    "scripts/bench_reference_answers.py::_snapshot": "an in-process ASGI client, no network",
    "scripts/check_catalog_tokens.py::check_all": "a maintainer check, through the public-only transport",
    "scripts/check_company_listings.py::main": "a maintainer check of public job boards",
    "scripts/check_source_review.py::check_all_evidence": "a maintainer check of source-review evidence pages",
    "scripts/check_vendored_upstream.py::_client": "a maintainer check of vendored upstream releases",
    "scripts/discover_board_tokens.py::main.run": "a maintainer directory build from public job boards",
    "scripts/discover_board_tokens.py::_directory.scan": "a maintainer directory build from public job boards",
    "scripts/fetch_sec_filings.py::main": "a maintainer fetch of public SEC filings",
    "scripts/gen_city_table.py::_fetch": "a maintainer fetch of a pinned dataset, held to its digest",
    "scripts/gen_country_table.py::_pinned": "a maintainer fetch of a pinned dataset, held to its digest",
    "scripts/gen_country_table.py::main": "a maintainer fetch of a pinned dataset, held to its digest",
    "scripts/smoke_model_tools.py::main": "a smoke test of the local model server",
    "scripts/upstream_http.py::get": "the retrying GET of the runtime and Postgres upstream checks",
}


#: Subscripting one of these names a type, as subscripting a CapWords name (`Callable`, `Optional`) does.
GENERICS = {"list", "dict", "set", "frozenset", "tuple", "type"}
TYPING = {"typing", "typing_extensions"}


def _module_name(relative: str) -> str:
    return relative.removesuffix(".py").removesuffix("/__init__").replace("/", ".")


def _package(relative: str) -> str:
    """Where a file's relative imports start: its folder, for a module and a package's `__init__` alike."""
    return relative.rpartition("/")[0].replace("/", ".")


def _absolute(module: str | None, level: int, package: str) -> str:
    """The module a `from ... import` names, with a relative one resolved against `package`."""
    if not level:
        return module or ""
    parts = package.split(".") if package else []
    base = parts[:len(parts) - level + 1]
    return ".".join([*base, module] if module else base)


def _is_httpx(module: str) -> bool:
    return module == "httpx" or module.startswith("httpx.")


@dataclass
class Bound:
    """Names bound to a client class or request helper, and names bound to httpx or one of its
    private submodules."""
    names: set[str] = field(default_factory=set)
    modules: set[str] = field(default_factory=set)


def _imports(nodes: Iterable[ast.AST]) -> list[ast.Import | ast.ImportFrom]:
    return [node for node in nodes if isinstance(node, (ast.Import, ast.ImportFrom))]


def _bind(imports: list[ast.Import | ast.ImportFrom], package: str,
          exports: Mapping[str, Bound]) -> tuple[Bound, dict[str, str]]:
    """What `imports` bind, and each first-party module they bind by its local name."""
    bound, packages = Bound(), {}
    for node in imports:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_httpx(alias.name):
                    # `import httpx._client` binds `httpx`; `import httpx._client as c` binds the submodule.
                    bound.modules.add(alias.asname or alias.name.split(".")[0])
                else:
                    local = alias.asname or alias.name.split(".")[0]
                    packages[local] = alias.name if alias.asname else local
            continue
        source = _absolute(node.module, node.level, package)
        if _is_httpx(source):
            for alias in node.names:
                if alias.name == "*":
                    bound.names |= TARGETS
                elif alias.name in TARGETS:
                    bound.names.add(alias.asname or alias.name)
                elif alias.name.startswith("_"):
                    bound.modules.add(alias.asname or alias.name)
            continue
        other = exports.get(source, Bound())
        for alias in node.names:
            local = alias.asname or alias.name
            if alias.name == "*":
                bound.names |= other.names
                bound.modules |= other.modules
            elif alias.name in other.names:
                bound.names.add(local)
            elif alias.name == "httpx" or alias.name in other.modules:
                bound.modules.add(local)
            elif f"{source}.{alias.name}" in exports:
                packages[local] = f"{source}.{alias.name}"
    return bound, packages


def _module_level(tree: ast.Module) -> Iterator[ast.AST]:
    """Every node of a module outside its functions and classes."""
    stack: list[ast.AST] = list(tree.body)
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            stack.extend(ast.iter_child_nodes(node))


def exported(files: Mapping[str, str]) -> dict[str, Bound]:
    """What each first-party module binds at its top level, through re-exports of any length."""
    modules = {_module_name(relative): (_package(relative), _imports(_module_level(ast.parse(source))))
               for relative, source in files.items()}
    exports = {module: Bound() for module in modules}
    changed = True
    while changed:
        changed = False
        for module, (package, imports) in modules.items():
            bound, _ = _bind(imports, package, exports)
            if bound != exports[module]:
                exports[module], changed = bound, True
    return exports


def _type_names(tree: ast.Module) -> tuple[set[str], set[str], set[str]]:
    """The builtins `isinstance` and `issubclass`, the names bound to typing's `cast`, and those
    bound to the typing module, less any the file also binds another way: names are resolved per
    file, so a name with two meanings keeps the one that counts."""
    casts: set[str] = set()
    typing: set[str] = set()
    other: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                cast = node.module in TYPING and not node.level and alias.name == "cast"
                (casts if cast else other).add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                (typing if alias.name in TYPING else other).add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            other.add(node.name)
        elif isinstance(node, ast.arg):
            other.add(node.arg)
        elif isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load):
            other.add(node.id)
    return {"isinstance", "issubclass"} - other, casts - other, typing - other


def _generic(node: ast.expr) -> bool:
    """Whether a subscripted value is a generic type, whose arguments are types."""
    name = node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else ""
    return name in GENERICS or (name[:1].isupper() and not name.isupper())


class _Sites(ast.NodeVisitor):
    """Each place a module refers to a client class or request helper as a value."""

    def __init__(self, tree: ast.Module, package: str, exports: Mapping[str, Bound]) -> None:
        self.bound, self.packages = _bind(_imports(ast.walk(tree)), package, exports)
        self.exports = exports
        self.checks, self.casts, self.typing = _type_names(tree)
        self.scope: list[str] = []
        self.found: Counter[str] = Counter()

    def _count(self) -> None:
        self.found[".".join(self.scope) or "<module>"] += 1

    def _first_party(self, node: ast.expr) -> Bound | None:
        """What the first-party module `node` names binds: `clients` or `tracker.net.clients`."""
        def dotted(node: ast.expr) -> str | None:
            if isinstance(node, ast.Name):
                return self.packages.get(node.id)
            base = dotted(node.value) if isinstance(node, ast.Attribute) else None
            return f"{base}.{node.attr}" if base and isinstance(node, ast.Attribute) else None
        module = dotted(node)
        return self.exports.get(module) if module else None

    def _httpx(self, node: ast.expr) -> bool:
        """httpx, a private submodule reached from it (`httpx._client`), or httpx as a first-party
        module binds it (`http.httpx`)."""
        if isinstance(node, ast.Name):
            return node.id in self.bound.modules
        if not isinstance(node, ast.Attribute):
            return False
        module = self._first_party(node.value)
        return (node.attr.startswith("_") and self._httpx(node.value)) or (
            module is not None and node.attr in module.modules)

    def _target(self, node: ast.AST) -> bool:
        if isinstance(node, ast.Name):
            return node.id in self.bound.names
        if not isinstance(node, ast.Attribute):
            return False
        module = self._first_party(node.value)
        return (node.attr in TARGETS and self._httpx(node.value)) or (module is not None and node.attr in module.names)

    def _visit(self, nodes: list[ast.expr] | list[ast.stmt]) -> None:
        for node in nodes:
            self.visit(node)

    def _enter(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> None:
        self.scope.append(node.name)
        self._visit(node.decorator_list)
        if isinstance(node, ast.ClassDef):
            self._visit(node.bases)
            self._visit([word.value for word in node.keywords])
        else:
            self.visit(node.args)
        self._visit(node.body)
        self.scope.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = _enter

    def visit_arg(self, node: ast.arg) -> None:
        """An annotation only names a type."""

    def visit_TypeAlias(self, node: ast.TypeAlias) -> None:
        """`type Pool = list[httpx.Client]` only names a type."""

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.visit(node.target)
        if node.value is not None:
            self.visit(node.value)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        """`Callable[[], httpx.AsyncClient]` names types; `responses[httpx.get(url).status_code]` runs."""
        self.visit(node.value)
        if not _generic(node.value):
            self.visit(node.slice)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load) and self._target(node):
            self._count()

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if isinstance(node.ctx, ast.Load) and self._target(node):
            self._count()
        else:
            self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Name) and func.id in self.checks:
            self._visit(node.args[:1])
            return
        if (isinstance(func, ast.Name) and func.id in self.casts) or (
                isinstance(func, ast.Attribute) and func.attr == "cast" and isinstance(func.value, ast.Name)
                and func.value.id in self.typing):
            self._visit([*node.args[1:], *(word.value for word in node.keywords)])
            return
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
        constant = [argument.value for argument in node.args[1:2] if isinstance(argument, ast.Constant)]
        if name == "getattr" and node.args and self._httpx(node.args[0]) and (not constant or constant[0] in TARGETS):
            self._count()
        if name in {"import_module", "__import__"} and node.args and isinstance(node.args[0], ast.Constant) \
                and _is_httpx(str(node.args[0].value)):
            self._count()
        self.generic_visit(node)


def sites(source: str, *, package: str = "", exports: Mapping[str, Bound] | None = None) -> Counter[str]:
    """Each function, method or class in `source` that builds an httpx client, and how often.

    `package` is where the file's relative imports start, and `exports` what each first-party
    module binds, so a name or module imported from one counts like httpx's own.
    """
    tree = ast.parse(source)
    visitor = _Sites(tree, package, exports or {})
    visitor.visit(tree)
    return visitor.found


def scan(root: Path, folders: tuple[str, ...] = SCANNED) -> Counter[str]:
    files = {path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
             for folder in folders for path in sorted((root / folder).rglob("*.py"))}
    exports = exported(files)
    found: Counter[str] = Counter()
    for relative, source in files.items():
        for place, count in sites(source, package=_package(relative), exports=exports).items():
            found[f"{relative}::{place}"] += count
    return found


def problems(found: Counter[str], allowed: Mapping[str, str]) -> list[str]:
    unlisted = [f"{site} builds an httpx client: borrow make_client, make_tier_client or public_client, "
                "or list it in ALLOWED with the reason" for site in sorted(set(found) - set(allowed))]
    gone = [f"{site} no longer builds a client: remove it from ALLOWED" for site in sorted(set(allowed) - set(found))]
    doubled = [f"{site} builds {count} clients: one place, one client" for site, count in sorted(found.items())
               if count > 1]
    return unlisted + gone + doubled


def test_only_the_listed_places_build_an_httpx_client():
    assert problems(scan(BACKEND), ALLOWED) == []


#: One function per way to reach a client; `types_only` names them only as types.
PLANTED = '''
import functools
import importlib
import typing
import httpx
import httpx as web
import httpx._client
from httpx import AsyncClient as Session, Timeout, get as fetch
from httpx import _api

Factory = typing.Callable[[], httpx.AsyncClient]
type Pool = httpx.Client | httpx.AsyncClient
shared = httpx.Client()


def types_only(client: httpx.AsyncClient, factory: Factory) -> httpx.Client | None:
    held: httpx.AsyncClient | None = None
    pair, maybe = tuple[httpx.Client, httpx.AsyncClient], typing.Optional[httpx.Client]
    if isinstance(client, (httpx.AsyncClient, Session)) or issubclass(type(client), httpx.Client):
        held = typing.cast(httpx.AsyncClient, client)
    try:
        return held
    except httpx.HTTPError:
        return None


def local_cast():
    def cast(make):
        return make()
    return cast(httpx.Client)


def indexed(responses, url):
    return responses[httpx.get(url).status_code]


async def direct():
    async with web.AsyncClient(timeout=Timeout(1.0)) as client:
        return await client.get("https://example.com")


def renamed():
    return Session()


def helper():
    return httpx.get("https://example.com")


def streamed():
    with httpx.stream("GET", "https://example.com") as response:
        return response.read()


def imported_helper():
    return fetch("https://example.com")


def factory():
    return functools.partial(httpx.Client, timeout=5)


def keyword(make):
    return make(client_class=httpx.Client)


def default(make=httpx.AsyncClient):
    return make()


def aliased():
    Maker = httpx.Client
    return Maker()


def returned():
    return httpx.AsyncClient


def private():
    return httpx._client.Client(), _api.request("GET", "https://example.com")


def by_name(which):
    return getattr(httpx, which)()


def imported_late():
    return importlib.import_module("httpx").Client()


def local_import():
    from httpx import Client
    return Client()


class Wrapped(Session):
    pass


class Holder:
    kind = httpx.Client

    def build(self):
        def inner():
            return httpx.Client()
        return inner
'''

EXPECTED = ("<module>", "local_cast", "indexed", "direct", "renamed", "helper", "streamed", "imported_helper",
            "factory", "keyword", "default", "aliased", "returned", "by_name", "imported_late", "local_import",
            "Wrapped", "Holder", "Holder.build.inner")


def _plant(root: Path, files: Mapping[str, str]) -> Counter[str]:
    for relative, source in files.items():
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_text(source, encoding="utf-8")
    return scan(root, ("tracker",))


def test_the_scan_finds_every_way_a_module_reaches_a_client_and_skips_type_positions(tmp_path):
    found = _plant(tmp_path, {"tracker/planted.py": PLANTED})
    assert set(found) == {f"tracker/planted.py::{place}" for place in (*EXPECTED, "private")}, found
    assert found["tracker/planted.py::private"] == 2
    assert all(found[f"tracker/planted.py::{place}"] == 1 for place in EXPECTED), found


def test_the_scan_follows_a_client_through_first_party_imports_and_re_exports(tmp_path):
    found = _plant(tmp_path, {
        "tracker/__init__.py": "",
        "tracker/net/__init__.py": "from .clients import AsyncClient\n\n\ndef p():\n    return AsyncClient()\n",
        "tracker/net/clients.py": "from httpx import AsyncClient\n\n\ndef typed(c: AsyncClient) -> None: ...\n",
        "tracker/net/bridge.py": "from tracker.net.clients import AsyncClient as Session\n",
        "tracker/net/absolute.py": "from tracker.net.clients import AsyncClient\n\n\ndef f():\n    return AsyncClient()\n",
        "tracker/net/relative.py": "from .clients import AsyncClient as Made\n\n\ndef g():\n    return Made()\n",
        "tracker/net/chained.py": "from tracker.net import AsyncClient\nfrom tracker.net.bridge import Session\n\n\n"
                                  "def q():\n    return Session()\n\n\ndef r():\n    return AsyncClient()\n",
        "tracker/net/module.py": "import tracker.net.clients\nimport tracker.net.clients as named\n"
                                 "from tracker.net import clients\nfrom tracker.platform.http import httpx\n\n\n"
                                 "def h():\n    return httpx.Client()\n\n\ndef j():\n    return clients.AsyncClient()\n\n\n"
                                 "def k():\n    return named.AsyncClient()\n\n\ndef m():\n"
                                 "    return tracker.net.clients.AsyncClient()\n",
        "tracker/net/other.py": "from typing import cast\n\nimport httpx\nfrom tracker.platform.local_http import Client\n\n\n"
                                "def n():\n    return Client()\n\n\ndef t(value: object) -> httpx.Client:\n"
                                "    return cast(httpx.Client, value)\n",
    })
    assert set(found) == {f"tracker/net/{place}" for place in (
        "__init__.py::p", "absolute.py::f", "relative.py::g", "chained.py::q", "chained.py::r", "module.py::h",
        "module.py::j", "module.py::k", "module.py::m")}, found


def test_the_fence_refuses_a_new_place_a_stale_entry_and_a_second_client(tmp_path):
    found = _plant(tmp_path, {"tracker/planted.py": PLANTED})
    listed = {site: "planted" for site in found}
    assert problems(Counter(dict.fromkeys(found, 1)), listed) == []
    new = problems(found, {site: why for site, why in listed.items() if not site.endswith("::direct")})
    assert "tracker/planted.py::direct builds an httpx client: borrow make_client, make_tier_client or " \
           "public_client, or list it in ALLOWED with the reason" in new
    stale = problems(Counter(dict.fromkeys(found, 1)), {**listed, "tracker/planted.py::removed": "planted"})
    assert stale == ["tracker/planted.py::removed no longer builds a client: remove it from ALLOWED"]
    assert "tracker/planted.py::private builds 2 clients: one place, one client" in problems(found, listed)
