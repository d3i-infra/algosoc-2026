"""Every active Meta extractor declares the export files it reads.

Each extractor's ``Table config::`` block carries an ``inputs`` list: one
plain name per ``reader.json(...)`` / ``reader.raw(...)`` request and one
``"re:<pattern>"`` per ``reader.json_all(...)`` / ``reader.raw_all(...)``
pattern. The next validation tier accepts an export when any declared input
is present, so a missing declaration is a false rejection of a participant's
export. The guard is ``walk_reads``: a walker over the platform module's
*source* (``ast``, never an import) that enumerates every reader request
reachable from an extractor and pins the declaration to it.

The walker follows every call to a module-level function, binding the call's
arguments to the callee's parameters, and resolves a request's first argument
when it is a string literal; a name bound to a module-level string constant;
a parameter bound at the call site to an argument that resolves in the caller
(a literal, a constant, the caller's own resolvable parameter), else the
parameter's string-literal default (``extraction()`` passes no such keyword,
so the default is what runs); a loop variable iterating a literal tuple or
list of strings (also through a local name bound once to such a literal and
never mutated, with tuple-unpacking targets, as the Facebook ``sources``
loops are written); and an f-string or ``+`` concatenation whose every part
resolves.

Everything else fails the test naming the call site rather than silently
omitting an input: an argument shape outside those rules; a helper parameter
that reaches a request but was passed an argument the caller cannot resolve;
a name bound more than once in one function, or a local that shadows a
module constant; and the reader leaving the walker's sight -- aliased
(``r = reader``), passed to anything but a module-level function's
``reader`` parameter, or used through any attribute but the four requests and
the ``errors`` counter. The one exception is ``LINK_FOLLOW_READS``: a request
whose file name comes from links read out of content, named by function and
by its exact argument expression, and counted as it is consumed.
"""

import ast
import json
import textwrap
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pytest

import port.platforms.facebook as facebook
import port.platforms.instagram as instagram

_PYTHON_PKG = Path(__file__).resolve().parents[1]
_PLATFORMS_DIR = _PYTHON_PKG / "port" / "platforms"
_CONFIGS_DIR = _PYTHON_PKG / "port" / "configs"

PLATFORMS = ("instagram", "facebook")

_SINGLE_READS = frozenset({"json", "raw"})
_PATTERN_READS = frozenset({"json_all", "raw_all"})
_READS = _SINGLE_READS | _PATTERN_READS
_READER = "reader"
#: The reader's one attribute that is not a request: the shared error counter.
_READER_COUNTER = "errors"

#: Per platform, the ``(function, argument expression)`` requests allowed to
#: stay unresolved: the function follows links it read from content, which no
#: declaration can name. Only the Facebook off-Meta HTML index, whose
#: per-business pages are ``reader.raw(root + href)``.
LINK_FOLLOW_READS: dict[str, frozenset[tuple[str, str]]] = {
    "facebook": frozenset({("_your_activity_off_meta_html", "root + href")}),
}


class UnresolvedRead(AssertionError):
    """A reader request whose file name the walker cannot resolve from source."""


@dataclass(frozen=True)
class _Opaque:
    """A parameter a call site bound to an argument the caller cannot resolve."""

    site: str


_Binding = frozenset[str] | _Opaque


@dataclass
class Walk:
    """What one extractor requests: the resolved ``reads``, and each
    ``LINK_FOLLOW_READS`` entry consumed on the way, once per request."""

    reads: set[str] = field(default_factory=set)
    link_follows: list[tuple[str, str]] = field(default_factory=list)


def _module_functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}


def _module_string_constants(tree: ast.Module) -> dict[str, str]:
    constants: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target, value = node.target, node.value
        else:
            continue
        if (
            isinstance(target, ast.Name)
            and isinstance(value, ast.Constant)
            and isinstance(value.value, str)
        ):
            constants[target.id] = value.value
    return constants


def _positional_parameters(fn: ast.FunctionDef) -> list[str]:
    return [arg.arg for arg in fn.args.posonlyargs + fn.args.args]


def _parameters(fn: ast.FunctionDef) -> set[str]:
    args = fn.args
    every = args.posonlyargs + args.args + args.kwonlyargs + [args.vararg, args.kwarg]
    return {arg.arg for arg in every if arg is not None}


def _parameter_defaults(fn: ast.FunctionDef) -> dict[str, str]:
    """Parameters of *fn* whose default is a string literal."""
    defaults: dict[str, str] = {}
    positional = fn.args.posonlyargs + fn.args.args
    for arg, default in zip(positional[len(positional) - len(fn.args.defaults):], fn.args.defaults):
        if isinstance(default, ast.Constant) and isinstance(default.value, str):
            defaults[arg.arg] = default.value
    for arg, default in zip(fn.args.kwonlyargs, fn.args.kw_defaults):
        if isinstance(default, ast.Constant) and isinstance(default.value, str):
            defaults[arg.arg] = default.value
    return defaults


def _binding_counts(fn: ast.FunctionDef) -> Counter[str]:
    """How many times each name is bound anywhere in *fn*, nested scopes included
    (an over-count only makes the walker fail where it might have resolved)."""
    counts: Counter[str] = Counter()
    for node in ast.walk(fn):
        if isinstance(node, ast.arg):
            counts[node.arg] += 1
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            counts[node.id] += 1
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node is not fn:
            counts[node.name] += 1
        elif isinstance(node, ast.ExceptHandler) and node.name:
            counts[node.name] += 1
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                counts[alias.asname or alias.name.split(".")[0]] += 1
    return counts


def _local_literal_sequences(fn: ast.FunctionDef) -> dict[str, ast.List | ast.Tuple]:
    """Local names of *fn* assigned a literal list or tuple."""
    bound: dict[str, ast.List | ast.Tuple] = {}
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target, value = node.target, node.value
        else:
            continue
        if isinstance(target, ast.Name) and isinstance(value, (ast.List, ast.Tuple)):
            bound[target.id] = value
    return bound


def _mutated_names(fn: ast.FunctionDef) -> set[str]:
    """Names whose object *fn* may change in place: the receiver of a method
    call (``links.append(...)``) or of a subscript store."""
    mutated: set[str] = set()
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
        ):
            mutated.add(node.func.value.id)
        elif (
            isinstance(node, ast.Subscript)
            and isinstance(node.ctx, ast.Store)
            and isinstance(node.value, ast.Name)
        ):
            mutated.add(node.value.id)
    return mutated


class _Resolver:
    """Resolves an expression in one function, under one call's bindings, to
    the set of strings it can be; None when the rules cannot."""

    def __init__(
        self,
        constants: dict[str, str],
        fn: ast.FunctionDef,
        bindings: dict[str, _Binding],
    ) -> None:
        self._fn = fn
        self._constants = constants
        self._bindings = bindings
        self._counts = _binding_counts(fn)
        self._parameters = _parameters(fn)
        self._defaults = _parameter_defaults(fn)
        self._sequences = _local_literal_sequences(fn)
        self._mutated = _mutated_names(fn)
        self._loops = [node for node in ast.walk(fn) if isinstance(node, ast.For)]

    def resolve(self, expr: ast.expr) -> set[str] | None:
        if isinstance(expr, ast.Constant):
            return {expr.value} if isinstance(expr.value, str) else None
        if isinstance(expr, ast.Name):
            return self._resolve_name(expr.id)
        if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Add):
            return self._concat([expr.left, expr.right])
        if isinstance(expr, ast.JoinedStr):
            parts = [
                part.value if isinstance(part, ast.FormattedValue) else part
                for part in expr.values
            ]
            return self._concat(parts)
        return None

    def _concat(self, parts: list[ast.expr]) -> set[str] | None:
        joined: set[str] = {""}
        for part in parts:
            resolved = self.resolve(part)
            if resolved is None:
                return None
            joined = {head + tail for head in joined for tail in resolved}
        return joined

    def _local(self, name: str) -> bool:
        """Whether *name* is bound in this function; raises when the binding
        a use sees is ambiguous."""
        count = self._counts[name]
        if count > 1:
            raise UnresolvedRead(
                f"{self._fn.name}: name {name!r} is bound {count} times; "
                "the walker cannot tell which binding a read sees"
            )
        if count == 1 and name in self._constants:
            raise UnresolvedRead(
                f"{self._fn.name}: name {name!r} shadows the module constant of that name"
            )
        return count == 1

    def _resolve_name(self, name: str) -> set[str] | None:
        if not self._local(name):
            return {self._constants[name]} if name in self._constants else None
        if name in self._bindings:
            binding = self._bindings[name]
            if isinstance(binding, _Opaque):
                raise UnresolvedRead(f"{binding.site}, and that parameter reaches a reader request")
            return set(binding)
        if name in self._defaults:
            return {self._defaults[name]}
        if name in self._parameters:
            return None
        for loop in self._loops:
            values = self._loop_values(loop, name)
            if values is not None:
                return values
        return None

    def _loop_values(self, loop: ast.For, name: str) -> set[str] | None:
        """Names *name* takes in *loop*, or None when *loop* does not bind it
        or its values do not resolve."""
        target = loop.target
        if isinstance(target, ast.Name):
            index: int | None = None
            if target.id != name:
                return None
        elif isinstance(target, ast.Tuple):
            positions = [
                i for i, elt in enumerate(target.elts)
                if isinstance(elt, ast.Name) and elt.id == name
            ]
            if not positions:
                return None
            index = positions[0]
        else:
            return None

        iterable = loop.iter
        if isinstance(iterable, ast.Name):
            if not self._local(iterable.id) or iterable.id in self._mutated:
                return None
            iterable = self._sequences.get(iterable.id)
        if not isinstance(iterable, (ast.List, ast.Tuple)):
            return None

        values: set[str] = set()
        for element in iterable.elts:
            if index is not None:
                if not isinstance(element, ast.Tuple) or index >= len(element.elts):
                    return None
                element = element.elts[index]
            resolved = self.resolve(element)
            if resolved is None:
                return None
            values |= resolved
        return values or None


def _parents(fn: ast.FunctionDef) -> dict[ast.AST, ast.AST]:
    return {child: node for node in ast.walk(fn) for child in ast.iter_child_nodes(node)}


def _is_module_call(node: ast.AST | None, functions: dict[str, ast.FunctionDef]) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in functions
    )


def _reader_requests(fn: ast.FunctionDef, functions: dict[str, ast.FunctionDef]):
    """Yield ``(call, method)`` for every ``reader.<request>(...)`` in *fn*.

    Raises ``UnresolvedRead`` for any other use of the reader: an attribute
    other than a request or the error counter, or the reader itself going
    anywhere but an argument of a module-level function (alias, return,
    another module's function, a container)."""
    loads = [
        node for node in ast.walk(fn)
        if isinstance(node, ast.Name) and node.id == _READER and isinstance(node.ctx, ast.Load)
    ]
    if not loads:
        return
    if _binding_counts(fn)[_READER] != 1 or _READER not in _parameters(fn):
        raise UnresolvedRead(f"{fn.name}: name {_READER!r} must be bound once, as a parameter")
    parents = _parents(fn)
    for node in loads:
        parent = parents[node]
        if isinstance(parent, ast.Attribute):
            caller = parents.get(parent)
            called = isinstance(caller, ast.Call) and caller.func is parent
            if called and parent.attr in _READS:
                yield caller, parent.attr
                continue
            if not called and parent.attr == _READER_COUNTER:
                continue
            raise UnresolvedRead(
                f"{fn.name}:{node.lineno}: {ast.unparse(caller if called else parent)} "
                "is not a reader request the walker inventories"
            )
        if isinstance(parent, ast.keyword):
            parent = parents[parent]
        if _is_module_call(parent, functions) and node in (
            list(parent.args) + [kw.value for kw in parent.keywords]
        ):
            continue
        raise UnresolvedRead(
            f"{fn.name}:{node.lineno}: the reader escapes the walker in {ast.unparse(parent)}"
        )


def _call_bindings(
    call: ast.Call, caller: ast.FunctionDef, callee: ast.FunctionDef, resolver: _Resolver
) -> dict[str, _Binding]:
    """The callee's parameters bound at *call*, each to the strings its
    argument resolves to in the caller, or to an ``_Opaque`` naming the call
    site. The reader binds nothing, and only to a parameter named ``reader``."""
    bindings: dict[str, _Binding] = {}
    spread = False

    def bind(param: str, expr: ast.expr) -> None:
        site = (
            f"{caller.name}:{call.lineno}: passes {ast.unparse(expr)} "
            f"to {callee.name}() parameter {param!r}"
        )
        passes_reader = isinstance(expr, ast.Name) and expr.id == _READER
        if passes_reader != (param == _READER):
            raise UnresolvedRead(f"{site}; the reader is walked only as a parameter named {_READER!r}")
        if passes_reader:
            return
        try:
            values = resolver.resolve(expr)
            reason = ""
        except UnresolvedRead as unresolved:
            values, reason = None, f" ({unresolved})"
        bindings[param] = frozenset(values) if values else _Opaque(site + reason)

    positional = _positional_parameters(callee)
    for i, arg in enumerate(call.args):
        if isinstance(arg, ast.Starred):
            spread = True
        elif i < len(positional):
            bind(positional[i], arg)
    for keyword in call.keywords:
        if keyword.arg is None:
            spread = True
        else:
            bind(keyword.arg, keyword.value)
    if spread:
        site = f"{caller.name}:{call.lineno}: spreads arguments into {callee.name}()"
        for param in _parameters(callee) - set(bindings) - {_READER}:
            bindings[param] = _Opaque(f"{site}, binding parameter {param!r}")
    return bindings


def walk_reads(
    module_source: str,
    fn_name: str,
    *,
    link_follows: frozenset[tuple[str, str]] = frozenset(),
) -> Walk:
    """Every file name or ``re:`` pattern *fn_name* requests from the reader.

    Walks the function body and, transitively, every module-level function it
    calls, under that call's argument bindings. Raises ``UnresolvedRead``
    naming the call site for anything the rules in the module docstring cannot
    resolve, except a request whose ``(function, argument expression)`` is in
    *link_follows*; each such request is recorded in ``Walk.link_follows``.
    """
    tree = ast.parse(module_source)
    functions = _module_functions(tree)
    constants = _module_string_constants(tree)
    if fn_name not in functions:
        raise KeyError(f"{fn_name}: not a module-level function")

    walk = Walk()
    visited: set[tuple[str, tuple[tuple[str, _Binding], ...]]] = set()
    pending: list[tuple[str, dict[str, _Binding]]] = [(fn_name, {})]
    while pending:
        name, bindings = pending.pop()
        key = (name, tuple(sorted(bindings.items(), key=lambda item: item[0])))
        if key in visited:
            continue
        visited.add(key)
        fn = functions[name]
        resolver = _Resolver(constants, fn, bindings)
        for call, method in _reader_requests(fn, functions):
            if not call.args:
                raise UnresolvedRead(f"{name}:{call.lineno}: reader.{method}() without a positional argument")
            argument = ast.unparse(call.args[0])
            resolved = resolver.resolve(call.args[0])
            if resolved is None:
                if (name, argument) in link_follows:
                    walk.link_follows.append((name, argument))
                    continue
                raise UnresolvedRead(f"{name}:{call.lineno}: cannot resolve reader.{method}({argument})")
            if method in _PATTERN_READS:
                resolved = {f"re:{pattern}" for pattern in resolved}
            walk.reads |= resolved
        for node in ast.walk(fn):
            if _is_module_call(node, functions):
                assert isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                callee = functions[node.func.id]
                pending.append((callee.name, _call_bindings(node, fn, callee, resolver)))
    return walk


def reachable_reads(module_source: str, fn_name: str) -> set[str]:
    """``walk_reads(...).reads``, with no link-following request allowed."""
    return walk_reads(module_source, fn_name).reads


def _source(platform: str) -> str:
    return (_PLATFORMS_DIR / f"{platform}.py").read_text(encoding="utf-8")


def _config_tables(platform: str) -> list[dict]:
    raw = json.loads((_CONFIGS_DIR / f"{platform}_config.json").read_text(encoding="utf-8"))
    return raw["tables"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_declared_inputs_match_reachable_reads():
    mismatches: list[str] = []
    for platform in PLATFORMS:
        source = _source(platform)
        for table in _config_tables(platform):
            fn = table["extractor"]
            reachable = walk_reads(
                source, fn, link_follows=LINK_FOLLOW_READS.get(platform, frozenset())
            ).reads
            declared = set(table.get("inputs", []))
            if reachable != declared:
                mismatches.append(
                    f"{platform}.{fn}: undeclared reads {sorted(reachable - declared)}, "
                    f"declared but unread {sorted(declared - reachable)}"
                )
    assert not mismatches, "\n".join(mismatches)


def test_every_active_extractor_declares_inputs():
    missing = [
        f"{platform}.{table['extractor']}"
        for platform in PLATFORMS
        for table in _config_tables(platform)
        if not table.get("inputs")
    ]
    assert not missing, f"no 'inputs' declared: {missing}"


def test_extractor_inputs_union():
    assert "following.json" in instagram.EXTRACTOR_INPUTS
    assert r"re:(^|/)post_comments(?:_\d+)?\.json$" in instagram.EXTRACTOR_INPUTS
    assert "ads_information/ad_preferences.json" in facebook.EXTRACTOR_INPUTS
    assert "who_you've_followed.html" in facebook.EXTRACTOR_INPUTS


def test_declared_name_overlap():
    # The declared-string overlap only; the wider resolution surface is Task 6's pin.
    assert instagram.EXTRACTOR_INPUTS & facebook.EXTRACTOR_INPUTS == {
        "advertisers_using_your_activity_or_information.html"
    }


_COMPUTED_SHAPES: list[tuple[str, str, str]] = [
    # (platform, function, a read the walker must resolve from a computed shape)
    ("instagram", "_ads_viewed_json", "ads_viewed.json"),
    ("instagram", "profile_searches_to_df", "profile_searches.json"),
    ("instagram", "threads_viewed_to_df", "threads_viewed.json"),
    ("instagram", "ads_clicked_to_df", "ads_clicked.json"),
    ("instagram", "_posts_published_json", r"re:(^|/)posts(?:_\d+)?\.json$"),
    ("instagram", "_subscription_for_no_ads_json", "subscription_for_no_ads.json"),
    ("facebook", "content_shown_to_you_to_df", "logged_information/interactions/ads.json"),
    ("facebook", "content_shown_to_you_to_df", "logged_information/interactions/ads.html"),
    ("facebook", "profile_visits_to_df", "logged_information/interactions/profile_visits.json"),
    ("facebook", "profile_visits_to_df", "logged_information/interactions/recently_visited.html"),
    ("facebook", "your_activity_off_meta_to_df", "apps_and_websites_off_of_facebook/your_activity_off_meta_technologies.html"),
]


def test_walker_resolves_computed_shapes():
    """The nine computed shapes the brief names: parameter defaults, loops over
    literal tuples, and a module constant. A walker that silently dropped one
    would let a declaration miss a file, so each is pinned here."""
    unresolved = [
        f"{platform}.{fn} should reach {expected!r}"
        for platform, fn, expected in _COMPUTED_SHAPES
        if expected not in walk_reads(
            _source(platform), fn, link_follows=LINK_FOLLOW_READS.get(platform, frozenset())
        ).reads
    ]
    assert not unresolved, "\n".join(unresolved)


def test_meta_configs_carry_no_string_extractor_kwargs():
    """A filename that reached an extractor through ``extractor_kwargs`` would
    bypass the walker, which reads only source. No Meta table carries one."""
    carried = [
        f"{platform}.{table['extractor']}: extractor_kwargs[{key!r}]"
        for platform in PLATFORMS
        for table in _config_tables(platform)
        for key, value in (table.get("extractor_kwargs") or {}).items()
        if isinstance(value, str)
    ]
    assert not carried, "\n".join(carried)


# ---------------------------------------------------------------------------
# The walker itself, on synthetic sources: every hole fails rather than
# silently omitting an input.
# ---------------------------------------------------------------------------


def _walk(code: str, fn: str = "extractor", **kwargs) -> set[str]:
    return reachable_reads(textwrap.dedent(code), fn, **kwargs)


_LINK_FOLLOW = """
    def extractor(reader):
        index = reader.raw("index.html")
        root = index.member_path
        for href in index.links:
            reader.raw(root + href)
"""


def test_link_follow_entry_records_the_read_it_consumes():
    walk = walk_reads(
        textwrap.dedent(_LINK_FOLLOW), "extractor",
        link_follows=frozenset({("extractor", "root + href")}),
    )
    assert walk.reads == {"index.html"}
    assert walk.link_follows == [("extractor", "root + href")]


@pytest.mark.parametrize("entry", [
    ("other_function", "root + href"),  # the right expression in another function
    ("extractor", "root + name"),       # another expression in the right function
])
def test_link_follow_entry_admits_only_its_function_and_expression(entry):
    with pytest.raises(UnresolvedRead, match=r"extractor:6: cannot resolve reader\.raw\(root \+ href\)"):
        walk_reads(textwrap.dedent(_LINK_FOLLOW), "extractor", link_follows=frozenset({entry}))


def test_link_follow_entry_does_not_cover_a_second_unresolved_read():
    source = _LINK_FOLLOW + "        reader.json(index.other)\n"
    with pytest.raises(UnresolvedRead, match=r"extractor:7: cannot resolve reader\.json\(index\.other\)"):
        walk_reads(textwrap.dedent(source), "extractor", link_follows=frozenset({("extractor", "root + href")}))


def test_link_follow_allowlist_is_consumed_once_by_its_extractor_only():
    consumed = {}
    for platform in PLATFORMS:
        source = _source(platform)
        for table in _config_tables(platform):
            fn = table["extractor"]
            walk = walk_reads(source, fn, link_follows=LINK_FOLLOW_READS.get(platform, frozenset()))
            if walk.link_follows:
                consumed[(platform, fn)] = walk.link_follows
    assert consumed == {
        ("facebook", "your_activity_off_meta_to_df"): [("_your_activity_off_meta_html", "root + href")],
    }


def test_helper_arguments_bind_string_literals():
    source = """
        def _helper(reader, filename="default.json", errors=None):
            return reader.json(filename)

        def extractor(reader, errors):
            _helper(reader, "positional.json", errors)
            _helper(reader, filename="keyword.json")
            _helper(reader)
    """
    assert _walk(source) == {"positional.json", "keyword.json", "default.json"}


def test_helper_argument_resolves_in_the_caller():
    source = """
        NAME = "constant.json"

        def _helper(reader, filename):
            return reader.json(filename)

        def extractor(reader, filename="default.json"):
            _helper(reader, filename)
            _helper(reader, NAME)
    """
    assert _walk(source) == {"default.json", "constant.json"}


def test_helper_called_with_a_non_literal_filename_fails():
    source = """
        def _helper(reader, filename="default.json"):
            return reader.json(filename)

        def extractor(reader, names):
            for name in names:
                _helper(reader, name)
    """
    with pytest.raises(UnresolvedRead, match=r"extractor:7: .*_helper\(\) parameter 'filename'"):
        _walk(source)


@pytest.mark.parametrize("source, name", [
    ("""
        def extractor(reader):
            for name in ("a.json", "b.json"):
                reader.json(name)
            for name in ("c.html",):
                reader.raw(name)
    """, "name"),
    ("""
        NAME = "module.json"

        def extractor(reader):
            NAME = "local.json"
            reader.json(NAME)
    """, "NAME"),
    ("""
        NAME = "module.json"

        def extractor(reader):
            for NAME in ("local.json",):
                reader.json(NAME)
    """, "NAME"),
])
def test_a_name_bound_more_than_once_fails(source, name):
    with pytest.raises(UnresolvedRead, match=rf"extractor: name '{name}' "):
        _walk(source)


@pytest.mark.parametrize("source", [
    """
        def extractor(reader):
            r = reader
            return r.json("hidden.json")
    """,
    """
        import helpers

        def extractor(reader):
            return helpers.load(reader, "hidden.json")
    """,
    """
        def _helper(zr):
            return zr.json("hidden.json")

        def extractor(reader):
            return _helper(reader)
    """,
    """
        def extractor(reader):
            return reader.csv("hidden.csv")
    """,
])
def test_reader_escaping_the_walker_fails(source):
    with pytest.raises(UnresolvedRead, match=r"extractor:\d+: "):
        _walk(source)


def test_unrelated_attribute_calls_are_not_reads():
    source = """
        def extractor(reader, errors):
            result = reader.json("seen.json")
            reader.errors["x"] += 1
            return result.data.json("not a read")
    """
    assert _walk(source) == {"seen.json"}
