from __future__ import annotations

from diffcog.languages.go.parser import parse_snapshot


def test_parse_snapshot_extracts_package_function() -> None:
    snapshot = parse_snapshot("package app\n\nfunc Run(value int) int { return value }\n")

    assert snapshot.present is True
    assert snapshot.parse_error is False
    assert len(snapshot.callables) == 1
    callable_ = snapshot.callables[0]
    assert callable_.kind == "function"
    assert callable_.name == "Run"
    assert callable_.namespace_path == ["app"]
    assert callable_.parameter_count == 1
    assert callable_.start_line == 3
    assert callable_.end_line == 3


def test_parse_snapshot_extracts_method_receiver_namespace() -> None:
    snapshot = parse_snapshot("package app\n\ntype Service struct{}\nfunc (s *Service) Run(ctx Context) {}\n")

    assert len(snapshot.callables) == 1
    callable_ = snapshot.callables[0]
    assert callable_.kind == "method"
    assert callable_.name == "Run"
    assert callable_.namespace_path == ["app", "Service"]
    assert callable_.parameter_count == 1


def test_parse_snapshot_counts_grouped_and_variadic_parameters() -> None:
    snapshot = parse_snapshot("package app\n\nfunc Run(a, b int, c string, rest ...int) {}\n")

    assert len(snapshot.callables) == 1
    assert snapshot.callables[0].parameter_count == 4


def test_parse_snapshot_does_not_extract_function_literal() -> None:
    snapshot = parse_snapshot("package app\n\nfunc Run() { fn := func(value int) int { return value }; fn(1) }\n")

    assert len(snapshot.callables) == 1
    assert snapshot.callables[0].name == "Run"


def test_parse_snapshot_missing_source() -> None:
    snapshot = parse_snapshot(None)

    assert snapshot.present is False
    assert snapshot.parse_error is False
    assert snapshot.callables == []


def test_parse_snapshot_malformed_go_sets_parse_error() -> None:
    snapshot = parse_snapshot("package app\n\nfunc Run( {}\n")

    assert snapshot.present is True
    assert snapshot.parse_error is True
