from __future__ import annotations

from diffcog.languages.python.parser import parse_snapshot


def test_parse_snapshot_extracts_module_function() -> None:
    snapshot = parse_snapshot("def run(x):\n    return x\n")

    assert snapshot.present is True
    assert snapshot.parse_error is False
    assert len(snapshot.callables) == 1
    callable_ = snapshot.callables[0]
    assert callable_.kind == "function"
    assert callable_.name == "run"
    assert callable_.namespace_path == []
    assert callable_.parameter_count == 1
    assert callable_.start_line == 1
    assert callable_.end_line == 2


def test_parse_snapshot_extracts_async_module_function() -> None:
    snapshot = parse_snapshot("async def fetch(url):\n    return url\n")

    assert len(snapshot.callables) == 1
    callable_ = snapshot.callables[0]
    assert callable_.kind == "function"
    assert callable_.name == "fetch"
    assert callable_.namespace_path == []
    assert callable_.parameter_count == 1


def test_parse_snapshot_extracts_class_method() -> None:
    snapshot = parse_snapshot("class Service:\n    def run(self, value):\n        return value\n")

    assert len(snapshot.callables) == 1
    callable_ = snapshot.callables[0]
    assert callable_.kind == "method"
    assert callable_.name == "run"
    assert callable_.namespace_path == ["Service"]
    assert callable_.parameter_count == 2
    assert callable_.start_line == 2
    assert callable_.end_line == 3


def test_parse_snapshot_extracts_async_class_method() -> None:
    snapshot = parse_snapshot("class Service:\n    async def run(self):\n        return None\n")

    assert len(snapshot.callables) == 1
    callable_ = snapshot.callables[0]
    assert callable_.kind == "method"
    assert callable_.name == "run"
    assert callable_.namespace_path == ["Service"]
    assert callable_.parameter_count == 1


def test_parse_snapshot_extracts_decorated_function_and_method() -> None:
    snapshot = parse_snapshot(
        "@decorator\n"
        "def top():\n"
        "    return None\n"
        "\n"
        "class Service:\n"
        "    @classmethod\n"
        "    def build(cls):\n"
        "        return cls()\n"
    )

    assert [(callable_.kind, callable_.name, callable_.namespace_path) for callable_ in snapshot.callables] == [
        ("function", "top", []),
        ("method", "build", ["Service"]),
    ]


def test_parse_snapshot_extracts_decorated_class_method() -> None:
    snapshot = parse_snapshot(
        "@registered\n"
        "class Service:\n"
        "    def run(self):\n"
        "        return None\n"
    )

    assert len(snapshot.callables) == 1
    callable_ = snapshot.callables[0]
    assert callable_.kind == "method"
    assert callable_.name == "run"
    assert callable_.namespace_path == ["Service"]


def test_parse_snapshot_extracts_nested_class_namespace_path() -> None:
    snapshot = parse_snapshot(
        "class Outer:\n"
        "    class Inner:\n"
        "        def run(self):\n"
        "            return None\n"
    )

    assert len(snapshot.callables) == 1
    callable_ = snapshot.callables[0]
    assert callable_.name == "run"
    assert callable_.namespace_path == ["Outer", "Inner"]


def test_parse_snapshot_extracts_nested_local_function() -> None:
    snapshot = parse_snapshot(
        "class Service:\n"
        "    def outer(self):\n"
        "        def inner(value):\n"
        "            return value\n"
        "        return inner(1)\n"
    )

    assert [(callable_.kind, callable_.name, callable_.namespace_path) for callable_ in snapshot.callables] == [
        ("method", "outer", ["Service"]),
        ("function", "inner", ["Service", "outer"]),
    ]


def test_parse_snapshot_counts_all_declared_parameters() -> None:
    snapshot = parse_snapshot(
        "class Service:\n"
        "    def run(self, x: int, y=1, *args, z, **kwargs):\n"
        "        return x\n"
        "\n"
        "def top(a, /, b=1, *, c, **kw):\n"
        "    return a\n"
    )

    assert {callable_.name: callable_.parameter_count for callable_ in snapshot.callables} == {
        "run": 6,
        "top": 4,
    }


def test_parse_snapshot_missing_source() -> None:
    snapshot = parse_snapshot(None)

    assert snapshot.present is False
    assert snapshot.parse_error is False
    assert snapshot.callables == []


def test_parse_snapshot_malformed_python_sets_parse_error() -> None:
    snapshot = parse_snapshot("def bad(:\n    pass\n")

    assert snapshot.present is True
    assert snapshot.parse_error is True
