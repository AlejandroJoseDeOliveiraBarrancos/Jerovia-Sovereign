"""Structural conformance of the fakes with the ports (E0-03, E0-04).

These tests are the guard rail for the hexagonal boundary. If a fake drifts from
a port signature, the whole offline pipeline stops working, and the drift is
silent unless something checks it.
"""

import inspect
from typing import Any

from adapters.fakes import (
    FakeDocumentParser,
    FakeEmbedder,
    FakeLLMClient,
    FakeSparseEncoder,
    FakeVectorStore,
)
from ports import (
    AuditStore,
    Chunker,
    DocumentParser,
    Embedder,
    LLMClient,
    SparseEncoder,
    Validator,
    VectorStore,
)

IMPLEMENTATIONS: list[tuple[Any, type[Any]]] = [
    (FakeDocumentParser(), DocumentParser),
    (FakeEmbedder(), Embedder),
    (FakeSparseEncoder(), SparseEncoder),
    (FakeVectorStore(), VectorStore),
    (FakeLLMClient(), LLMClient),
]


class TestRuntimeConformance:
    """A fake must be usable wherever its port is required."""

    def test_fakes_satisfy_their_protocols(self) -> None:
        for instance, protocol in IMPLEMENTATIONS:
            assert isinstance(instance, protocol), (
                f"{type(instance).__name__} !~ {protocol.__name__}"
            )

    def test_every_port_declares_its_failure_modes(self) -> None:
        for port in (
            DocumentParser,
            Chunker,
            Embedder,
            SparseEncoder,
            VectorStore,
            LLMClient,
            Validator,
            AuditStore,
        ):
            doc = inspect.getdoc(port) or ""
            assert "Contract:" in doc, f"{port.__name__} does not state its contract"
            assert "Failure modes:" in doc, f"{port.__name__} does not state its failure modes"
            assert "Determinism" in doc, f"{port.__name__} does not state its determinism"


class TestBoundaryDirection:
    """Dependencies point inward only: the domain imports nothing from outside."""

    def test_domain_imports_no_ports_adapters_or_app(self) -> None:
        from pathlib import Path

        domain_root = Path(__file__).resolve().parents[2] / "src" / "domain"
        forbidden = (
            "src.ports",
            "src.adapters",
            "src.app",
            "fastapi",
            "pydantic_settings",
        )
        offenders: list[str] = []
        for module in sorted(domain_root.glob("*.py")):
            source = module.read_text(encoding="utf-8")
            for token in forbidden:
                if f"import {token}" in source or f"from {token}" in source:
                    offenders.append(f"{module.name}: {token}")
        assert offenders == []

    def test_ports_do_not_import_adapters(self) -> None:
        from pathlib import Path

        ports_root = Path(__file__).resolve().parents[2] / "src" / "ports"
        offenders = [
            module.name
            for module in sorted(ports_root.glob("*.py"))
            if "src.adapters" in module.read_text(encoding="utf-8")
        ]
        assert offenders == []
