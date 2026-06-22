from __future__ import annotations

from diffcog.languages.go.metrics import score_class_metrics as score_go_class_metrics
from diffcog.languages.go.parser import parse_snapshot as parse_go_snapshot
from diffcog.languages.java.metrics import score_class_metrics as score_java_class_metrics
from diffcog.languages.java.parser import parse_snapshot as parse_java_snapshot
from diffcog.languages.python.metrics import score_class_metrics as score_python_class_metrics
from diffcog.languages.python.parser import parse_snapshot as parse_python_snapshot


def test_java_ck_metrics_count_coupling_cohesion_and_methods() -> None:
    snapshot = parse_java_snapshot(
        "import java.util.List;\n"
        "class Foo extends Base {\n"
        "  Bar bar;\n"
        "  Baz baz;\n"
        "  Foo(Bar bar) { this.bar = bar; }\n"
        "  int first(Qux q) { return bar.size(); }\n"
        "  void second() { baz.reset(); }\n"
        "  static void helper(List<String> values) {}\n"
        "}\n"
    )

    metrics = score_java_class_metrics(snapshot)[("Foo",)]

    assert metrics.cbo == 4
    assert metrics.lcom == 1
    assert metrics.wmc == 3


def test_java_lcom_zero_when_all_methods_use_no_instance_fields() -> None:
    snapshot = parse_java_snapshot(
        "class Foo {\n"
        "  void first() { int x = 1; }\n"
        "  void second() { int y = 2; }\n"
        "}\n"
    )

    metrics = score_java_class_metrics(snapshot)[("Foo",)]

    assert metrics.lcom == 0


def test_java_nested_class_has_separate_ck_metrics() -> None:
    snapshot = parse_java_snapshot(
        "class Outer {\n"
        "  String name;\n"
        "  void run() { name.trim(); }\n"
        "  class Inner { Other other; void call() { other.go(); } }\n"
        "}\n"
    )

    metrics = score_java_class_metrics(snapshot)

    assert metrics[("Outer",)].cbo == 0
    assert metrics[("Outer", "Inner")].cbo == 1


def test_python_ck_metrics_count_static_references_only() -> None:
    snapshot = parse_python_snapshot(
        "from pkg import Client\n"
        "class Service(Base):\n"
        "    field: Client\n"
        "    def __init__(self, client: Client):\n"
        "        self.client = client\n"
        "        self.count = 0\n"
        "    def run(self, item: Item) -> Result:\n"
        "        self.count += 1\n"
        "        return self.client.call(item)\n"
        "    @staticmethod\n"
        "    def make(raw: Raw):\n"
        "        return Service(Client(raw))\n"
    )

    metrics = score_python_class_metrics(snapshot)[("Service",)]

    assert metrics.cbo == 5
    assert metrics.lcom == 0
    assert metrics.wmc == 2


def test_python_lcom_counts_disjoint_self_fields() -> None:
    snapshot = parse_python_snapshot(
        "class Service:\n"
        "    def first(self):\n"
        "        return self.left\n"
        "    def second(self):\n"
        "        return self.right\n"
        "    @classmethod\n"
        "    def build(cls):\n"
        "        return cls()\n"
    )

    metrics = score_python_class_metrics(snapshot)[("Service",)]

    assert metrics.lcom == 1
    assert metrics.wmc == 2


def test_go_ck_metrics_count_struct_coupling_cohesion_and_methods() -> None:
    snapshot = parse_go_snapshot(
        "package app\n\n"
        "type Service struct {\n"
        "    client Client\n"
        "    item Item\n"
        "    count int\n"
        "}\n"
        "func (s *Service) First(ctx Context) Result { return s.client.Call(ctx) }\n"
        "func (s Service) Second(raw Raw) { _ = s.item; var helper Helper }\n"
        "func HelperFunc(raw Raw) Service { return Service{} }\n"
    )

    metrics = score_go_class_metrics(snapshot)[("app", "Service")]

    assert metrics.cbo == 6
    assert metrics.lcom == 1
    assert metrics.wmc == 2


def test_go_struct_lcom_zero_when_all_methods_use_no_declared_fields() -> None:
    snapshot = parse_go_snapshot(
        "package app\n\n"
        "type Service struct { count int }\n"
        "func (s *Service) First() { local := 1; _ = local }\n"
        "func (s *Service) Second() { local := 2; _ = local }\n"
    )

    metrics = score_go_class_metrics(snapshot)[("app", "Service")]

    assert metrics.lcom == 0
    assert metrics.wmc == 2


def test_go_interface_metrics_count_signatures_and_embeds() -> None:
    snapshot = parse_go_snapshot(
        "package app\n\n"
        "type Runner interface {\n"
        "    BaseRunner\n"
        "    Run(ctx Context) Result\n"
        "    Stop(reason Reason) error\n"
        "}\n"
    )

    metrics = score_go_class_metrics(snapshot)[("app", "Runner")]

    assert metrics.cbo == 4
    assert metrics.lcom == 0
    assert metrics.wmc == 2


def test_go_parser_ignores_non_struct_interface_metric_types() -> None:
    snapshot = parse_go_snapshot(
        "package app\n\n"
        "type Service struct{}\n"
        "type Runner interface { Run() }\n"
        "type Alias = Service\n"
        "type Status int\n"
    )

    assert [(class_.namespace_path, class_.kind) for class_ in snapshot.classes] == [
        (["app", "Service"], "struct"),
        (["app", "Runner"], "interface"),
    ]
