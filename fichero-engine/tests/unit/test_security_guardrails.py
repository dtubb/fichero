"""Consolidated source-scanning security guardrails for non-test engine code."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "fichero"
LOGGER_METHODS = {"debug", "info", "warning", "error", "exception", "critical", "log"}
SECRET_WORDS = ("api_key", "token", "password", "secret")
PERSISTENCE_PATH_ALLOWLIST = frozenset(
    {
        "db.py",
        "db_embeddings.py",
        "db_migrations.py",
        "db_manager.py",
        "app_db.py",
        "migrations.py",
        "api/change_stream.py",
        "storage_snapshots.py",
        "workflows/action_store.py",
        "workflows/cache.py",
        "workflows/checkpointer.py",
        "workflows/activity_store.py",
        "workflows/batch.py",
        "workflows/file_watcher.py",
        "workflows/scheduler.py",
        "workflows/tasks.py",
    }
)

DANGEROUS_CALL_ALLOWLIST: dict[str, str] = {}
SQL_INTERPOLATION_ALLOWLIST: dict[str, str] = {}
XML_ETREE_ALLOWLIST: dict[str, str] = {}
SECRET_LOG_ALLOWLIST: dict[str, str] = {}
WILDCARD_BIND_ALLOWLIST: dict[str, str] = {
    "security/bind_host.py:resolve_bind_host": "bind_host is the enforcement choke point that refuses 0.0.0.0.",
    "security/bind_host.py:resolve_lan_bind_host": "Refusal guard: the only 0.0.0.0 mention raises ValueError demanding one explicit LAN address.",
}

ALLOWLISTS: dict[str, dict[str, str]] = {
    "dangerous_calls": DANGEROUS_CALL_ALLOWLIST,
    "sql_interpolation": SQL_INTERPOLATION_ALLOWLIST,
    "xml_etree": XML_ETREE_ALLOWLIST,
    "secret_logging": SECRET_LOG_ALLOWLIST,
    "wildcard_bind": WILDCARD_BIND_ALLOWLIST,
}

SQL_PATTERNS = (
    re.compile(r"^\s*SELECT\b.*\bFROM\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"^\s*INSERT\s+INTO\b", re.IGNORECASE),
    re.compile(r"^\s*UPDATE\b.*\bSET\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"^\s*DELETE\s+FROM\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class Finding:
    key: str
    location: str
    detail: str


class SecurityVisitor(ast.NodeVisitor):
    def __init__(self, rel_path: str, source: str) -> None:
        self.rel_path = rel_path
        self.source = source
        self.symbol_stack: list[str] = []
        self.import_aliases: dict[str, str] = {}
        self.from_imports: dict[str, str] = {}
        self.dangerous_calls: list[Finding] = []
        self.sql_interpolation: list[Finding] = []
        self.xml_etree: list[Finding] = []
        self.secret_logging: list[Finding] = []
        self.wildcard_bind: list[Finding] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name.startswith("xml.etree"):
                local_name = alias.asname or alias.name.split(".")[0]
                self.import_aliases[local_name] = alias.name
                self.xml_etree.append(
                    self._finding(node, f"import {alias.name}")
                )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        if module.startswith("xml.etree"):
            self.xml_etree.append(self._finding(node, f"from {module} import ..."))
        for alias in node.names:
            local_name = alias.asname or alias.name
            self.from_imports[local_name] = module

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.symbol_stack.append(node.name)
        self.generic_visit(node)
        self.symbol_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.symbol_stack.append(node.name)
        self.generic_visit(node)
        self.symbol_stack.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.symbol_stack.append(node.name)
        self.generic_visit(node)
        self.symbol_stack.pop()

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str) and node.value == "0.0.0.0":
            self.wildcard_bind.append(self._finding(node, "literal 0.0.0.0"))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        qualified_name = self._qualified_name(node.func)

        if self._is_dangerous_call(node, qualified_name):
            self.dangerous_calls.append(self._finding(node, qualified_name))

        if self._is_sql_interpolation(node):
            sql_shape = self._sql_shape(node)
            self.sql_interpolation.append(
                self._finding(node, f"interpolated SQL via {sql_shape}")
            )

        if self._is_direct_xml_parse(node):
            self.xml_etree.append(
                self._finding(node, f"direct xml.etree.{self._call_name(node.func)}")
            )

        if self._is_secret_logging(node):
            call_text = " ".join((ast.get_source_segment(self.source, node) or "").split())
            self.secret_logging.append(
                self._finding(node, f"f-string secret log: {call_text}")
            )

        self.generic_visit(node)

    def _finding(self, node: ast.AST, detail: str) -> Finding:
        symbol = self.symbol_stack[-1] if self.symbol_stack else "<module>"
        key = f"{self.rel_path}:{symbol}"
        return Finding(key=key, location=f"{self.rel_path}:{node.lineno}", detail=detail)

    def _qualified_name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            left = self._qualified_name(node.value)
            return f"{left}.{node.attr}" if left else node.attr
        return ""

    def _call_name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Attribute):
            return node.attr
        if isinstance(node, ast.Name):
            return node.id
        return "<unknown>"

    def _is_dangerous_call(self, node: ast.Call, qualified_name: str) -> bool:
        if qualified_name in {"pickle.load", "pickle.loads", "os.system"}:
            return True
        if qualified_name == "yaml.load":
            return not self._uses_safe_yaml_loader(node)
        if qualified_name in {"eval", "exec"}:
            return not self._has_constant_string_argument(node)
        if self._call_name(node.func) in {"run", "Popen", "call", "check_call", "check_output"}:
            return any(
                keyword.arg == "shell"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
                for keyword in node.keywords
            )
        return False

    def _uses_safe_yaml_loader(self, node: ast.Call) -> bool:
        for keyword in node.keywords:
            if keyword.arg != "Loader":
                continue
            loader_name = self._qualified_name(keyword.value)
            if loader_name.endswith("SafeLoader"):
                return True
        return False

    def _has_constant_string_argument(self, node: ast.Call) -> bool:
        if not node.args:
            return False
        first_arg = node.args[0]
        return isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str)

    def _is_sql_interpolation(self, node: ast.Call) -> bool:
        for expr in self._iter_candidate_expressions(node):
            if self._has_sql_interpolation(expr):
                return True
        return False

    def _iter_candidate_expressions(self, node: ast.Call) -> Iterable[ast.AST]:
        if node.args:
            yield node.args[0]
        for keyword in node.keywords:
            if keyword.arg in {"query", "sql", "statement"}:
                yield keyword.value

    def _has_sql_interpolation(self, expr: ast.AST) -> bool:
        if isinstance(expr, ast.JoinedStr):
            return self._looks_like_sql(self._joined_str_shape(expr))
        if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Mod):
            return isinstance(expr.left, ast.Constant) and isinstance(expr.left.value, str) and self._looks_like_sql(expr.left.value)
        if (
            isinstance(expr, ast.Call)
            and isinstance(expr.func, ast.Attribute)
            and expr.func.attr == "format"
            and isinstance(expr.func.value, ast.Constant)
            and isinstance(expr.func.value.value, str)
        ):
            return self._looks_like_sql(expr.func.value.value)
        return False

    def _sql_shape(self, node: ast.Call) -> str:
        if not node.args:
            return "call"
        expr = node.args[0]
        if isinstance(expr, ast.JoinedStr):
            return "f-string"
        if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Mod):
            return "% formatting"
        if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute) and expr.func.attr == "format":
            return ".format()"
        return "call"

    def _joined_str_shape(self, expr: ast.JoinedStr) -> str:
        parts: list[str] = []
        for value in expr.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            else:
                parts.append("{}")
        return "".join(parts)

    def _looks_like_sql(self, value: str) -> bool:
        if "{" in value or re.search(r"\?\w", value):
            return False
        return any(pattern.search(value) for pattern in SQL_PATTERNS)

    def _is_direct_xml_parse(self, node: ast.Call) -> bool:
        func = node.func
        if isinstance(func, ast.Attribute):
            owner = self._qualified_name(func.value)
            owner_root = owner.split(".")[0] if owner else ""
            direct_module = self.import_aliases.get(owner_root, "")
            return direct_module.startswith("xml.etree") and func.attr in {"parse", "fromstring"}
        if isinstance(func, ast.Name):
            module = self.from_imports.get(func.id, "")
            return module.startswith("xml.etree") and func.id in {"parse", "fromstring"}
        return False

    def _is_secret_logging(self, node: ast.Call) -> bool:
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr in LOGGER_METHODS):
            return False
        if not node.args or not isinstance(node.args[0], ast.JoinedStr):
            return False
        call_text = (ast.get_source_segment(self.source, node) or "").lower()
        return "[: " in call_text or ("[:" in call_text and any(word in call_text for word in SECRET_WORDS))


def _iter_source_files() -> Iterable[Path]:
    yield from sorted(SRC_ROOT.rglob("*.py"))


def _is_persistence_path(rel_path: str) -> bool:
    return rel_path in PERSISTENCE_PATH_ALLOWLIST or "migrations" in Path(rel_path).parts


def _scan_source_tree() -> dict[str, list[Finding]]:
    results = {
        "dangerous_calls": [],
        "sql_interpolation": [],
        "xml_etree": [],
        "secret_logging": [],
        "wildcard_bind": [],
    }
    for path in _iter_source_files():
        rel_path = path.relative_to(SRC_ROOT).as_posix()
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        visitor = SecurityVisitor(rel_path, source)
        visitor.visit(tree)
        results["dangerous_calls"].extend(visitor.dangerous_calls)
        if not _is_persistence_path(rel_path):
            results["sql_interpolation"].extend(visitor.sql_interpolation)
        if rel_path != "security/xml_security.py":
            results["xml_etree"].extend(visitor.xml_etree)
        results["secret_logging"].extend(visitor.secret_logging)
        results["wildcard_bind"].extend(visitor.wildcard_bind)
    return results


def _unexpected_findings(findings: list[Finding], allowlist: dict[str, str]) -> list[Finding]:
    return [finding for finding in findings if finding.key not in allowlist]


def _assert_allowlist_not_stale(
    findings: list[Finding], allowlist: dict[str, str], allowlist_name: str
) -> None:
    live_keys = {finding.key for finding in findings}
    stale = sorted(key for key in allowlist if key not in live_keys)
    assert not stale, (
        f"Remove stale {allowlist_name} entries:\n  " + "\n  ".join(stale)
    )


def _assert_allowlist_has_reasons(
    allowlist: dict[str, str], allowlist_name: str
) -> None:
    missing = sorted(key for key, reason in allowlist.items() if not reason.strip())
    assert not missing, (
        f"Every {allowlist_name} entry needs a justification:\n  "
        + "\n  ".join(missing)
    )


def _scan_snippet(source: str, rel_path: str = "synthetic.py") -> SecurityVisitor:
    visitor = SecurityVisitor(rel_path, source)
    visitor.visit(ast.parse(source))
    return visitor


def test_no_dangerous_runtime_execution_primitives_in_non_test_code() -> None:
    findings = _scan_source_tree()["dangerous_calls"]
    unexpected = _unexpected_findings(findings, DANGEROUS_CALL_ALLOWLIST)
    lines = [
        "Non-test engine code must not use eval/exec on dynamic input, pickle.load(s),",
        "yaml.load without SafeLoader, subprocess shell=True, or os.system.",
        "",
        "Unexpected dangerous-call findings:",
        *[f"  {finding.location}: {finding.detail} [{finding.key}]" for finding in unexpected],
        "",
        "If a finding is a deliberately constrained exception, add file:symbol to",
        "DANGEROUS_CALL_ALLOWLIST with a justification. Do not allowlist a real vuln.",
    ]
    assert not unexpected, "\n".join(lines)


def test_no_new_sql_string_interpolation_outside_persistence_layer() -> None:
    findings = _scan_source_tree()["sql_interpolation"]
    unexpected = _unexpected_findings(findings, SQL_INTERPOLATION_ALLOWLIST)
    lines = [
        "Raw SQL interpolation must not escape the persistence layer.",
        "The existing DB guardrail already blocks raw SQL string literals; this one",
        "catches interpolated SQL shapes such as f-strings and .format/% variants.",
        "",
        "Unexpected SQL interpolation findings:",
        *[f"  {finding.location}: {finding.detail} [{finding.key}]" for finding in unexpected],
        "",
        "Move the query behind typed persistence code, or add a narrowly justified",
        "file:symbol allowlist entry if the exception is truly sanctioned.",
    ]
    assert not unexpected, "\n".join(lines)


def test_xml_parsing_stays_inside_xml_security_chokepoint() -> None:
    findings = _scan_source_tree()["xml_etree"]
    unexpected = _unexpected_findings(findings, XML_ETREE_ALLOWLIST)
    lines = [
        "Non-test engine code must not import or call xml.etree directly.",
        "Route all XML parsing through fichero.xml_security instead.",
        "",
        "Unexpected xml.etree findings:",
        *[f"  {finding.location}: {finding.detail} [{finding.key}]" for finding in unexpected],
        "",
        "If an exception is required, add file:symbol to XML_ETREE_ALLOWLIST with",
        "a justification. Prefer tightening xml_security instead of branching around it.",
    ]
    assert not unexpected, "\n".join(lines)


def test_logs_do_not_slice_or_preview_secret_values() -> None:
    findings = _scan_source_tree()["secret_logging"]
    unexpected = _unexpected_findings(findings, SECRET_LOG_ALLOWLIST)
    lines = [
        "Logger calls must not preview secret-bearing values (api_key/token/password/secret)",
        "with f-string slices such as value[:4]. Log redaction state, not the secret itself.",
        "",
        "Unexpected secret-logging findings:",
        *[f"  {finding.location}: {finding.detail} [{finding.key}]" for finding in unexpected],
        "",
        "If a finding is provably redacted and intentionally safe, add file:symbol to",
        "SECRET_LOG_ALLOWLIST with a justification.",
    ]
    assert not unexpected, "\n".join(lines)


def test_wildcard_bind_host_is_never_used_outside_sanctioned_guards() -> None:
    findings = _scan_source_tree()["wildcard_bind"]
    unexpected = _unexpected_findings(findings, WILDCARD_BIND_ALLOWLIST)
    lines = [
        "Engine code must not bind or default to 0.0.0.0.",
        "Use fichero.bind_host.resolve_bind_host and only mention 0.0.0.0 inside",
        "the existing refusal/SSRF guard paths.",
        "",
        "Unexpected 0.0.0.0 findings:",
        *[f"  {finding.location}: {finding.detail} [{finding.key}]" for finding in unexpected],
        "",
        "If this is a sanctioned refusal or SSRF-blocklist mention, add file:symbol to",
        "WILDCARD_BIND_ALLOWLIST with a justification.",
    ]
    assert not unexpected, "\n".join(lines)


def test_security_guardrail_allowlists_are_not_stale() -> None:
    scans = _scan_source_tree()
    _assert_allowlist_not_stale(
        scans["dangerous_calls"], DANGEROUS_CALL_ALLOWLIST, "DANGEROUS_CALL_ALLOWLIST"
    )
    _assert_allowlist_not_stale(
        scans["sql_interpolation"],
        SQL_INTERPOLATION_ALLOWLIST,
        "SQL_INTERPOLATION_ALLOWLIST",
    )
    _assert_allowlist_not_stale(
        scans["xml_etree"], XML_ETREE_ALLOWLIST, "XML_ETREE_ALLOWLIST"
    )
    _assert_allowlist_not_stale(
        scans["secret_logging"],
        SECRET_LOG_ALLOWLIST,
        "SECRET_LOG_ALLOWLIST",
    )
    _assert_allowlist_not_stale(
        scans["wildcard_bind"],
        WILDCARD_BIND_ALLOWLIST,
        "WILDCARD_BIND_ALLOWLIST",
    )


def test_security_guardrail_allowlist_entries_have_reasons() -> None:
    for allowlist_name, allowlist in ALLOWLISTS.items():
        _assert_allowlist_has_reasons(allowlist, allowlist_name)


def test_security_guardrail_keys_are_line_independent() -> None:
    visitor = _scan_snippet(
        """


def danger(user_input):
    eval(user_input)
"""
    )
    assert "synthetic.py:4:danger" not in {
        finding.location.replace(".py:", ".py:", 1)
        for finding in visitor.dangerous_calls
    }
    assert [finding.key for finding in visitor.dangerous_calls] == [
        "synthetic.py:danger"
    ]


def test_security_guardrail_detector_flags_dynamic_eval_in_synthetic_source() -> None:
    visitor = _scan_snippet(
        """
def exploit(user_input):
    eval(user_input)
"""
    )
    assert [finding.detail for finding in visitor.dangerous_calls] == ["eval"]
    assert [finding.key for finding in visitor.dangerous_calls] == [
        "synthetic.py:exploit"
    ]


def test_security_guardrail_does_not_flag_constant_eval_fixture() -> None:
    visitor = _scan_snippet(
        """
def constant_only():
    eval("1 + 1")
"""
    )
    assert visitor.dangerous_calls == []
