from __future__ import annotations

from diffcog.languages.java.parser import parse_snapshot


def test_parse_snapshot_extracts_method() -> None:
    snapshot = parse_snapshot("class Foo {\n  void a(int x) {}\n}\n")

    assert snapshot.present is True
    assert snapshot.parse_error is False
    assert len(snapshot.callables) == 1
    callable_ = snapshot.callables[0]
    assert callable_.kind == "method"
    assert callable_.name == "a"
    assert callable_.class_path == ["Foo"]
    assert callable_.parameter_count == 1
    assert callable_.start_line == 2
    assert callable_.end_line == 2


def test_parse_snapshot_extracts_constructor() -> None:
    snapshot = parse_snapshot("class Foo {\n  Foo() {}\n}\n")

    assert len(snapshot.callables) == 1
    callable_ = snapshot.callables[0]
    assert callable_.kind == "constructor"
    assert callable_.name == "Foo"
    assert callable_.class_path == ["Foo"]
    assert callable_.parameter_count == 0


def test_parse_snapshot_extracts_compact_record_constructor() -> None:
    snapshot = parse_snapshot(
        "record Foo(String name) {\n"
        "  public Foo {\n"
        "    name = name.strip();\n"
        "  }\n"
        "}\n"
    )

    assert len(snapshot.callables) == 1
    callable_ = snapshot.callables[0]
    assert callable_.kind == "constructor"
    assert callable_.name == "Foo"
    assert callable_.class_path == ["Foo"]
    assert callable_.parameter_count == 0
    assert callable_.start_line == 2
    assert callable_.end_line == 4


def test_parse_snapshot_extracts_nested_class_path() -> None:
    snapshot = parse_snapshot("class Foo {\n  class Bar {\n    String b() { return \"\"; }\n  }\n}\n")

    assert len(snapshot.callables) == 1
    callable_ = snapshot.callables[0]
    assert callable_.name == "b"
    assert callable_.class_path == ["Foo", "Bar"]
    assert callable_.start_line == 3
    assert callable_.end_line == 3


def test_parse_snapshot_empty_class_returns_no_callables() -> None:
    snapshot = parse_snapshot("class Foo {}\n")

    assert snapshot.present is True
    assert snapshot.parse_error is False
    assert snapshot.callables == []


def test_parse_snapshot_missing_source() -> None:
    snapshot = parse_snapshot(None)

    assert snapshot.present is False
    assert snapshot.parse_error is False
    assert snapshot.callables == []


def test_parse_snapshot_malformed_java_sets_parse_error() -> None:
    snapshot = parse_snapshot("class Foo {\n  void a( {}\n")

    assert snapshot.present is True
    assert snapshot.parse_error is True
