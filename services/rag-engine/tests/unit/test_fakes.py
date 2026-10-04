"""Tests for the deterministic in-memory fakes (E0-04).

The point of these tests is that determinism itself is verified: a fake whose
vectors move between runs would make every eval number fiction.
"""

import math
from dataclasses import replace
from pathlib import Path

import pytest

from adapters.fakes import (
    FakeDocumentParser,
    FakeEmbedder,
    FakeLLMClient,
    FakeSparseEncoder,
    FakeVectorStore,
    ScriptedResponse,
    tokenize,
)
from domain.chunks import IndexedChunk
from domain.documents import BlockKind, DocumentSource, ParsedBlock, ParsedDocument
from domain.errors import (
    DocumentParserError,
    EmbedderError,
    LLMClientError,
    VectorStoreError,
)
from domain.ids import ChunkId, DocId
from domain.retrieval import MetadataFilter
from ports.llm import LLMRequest
from ports.vector_store import FusionMode, SearchRequest
from tests.conftest import DOC_ID, OTHER_DOC_ID, make_chunk, write_text_fixture

CAPEX_ROW = "Purchases of property and equipment | (10,959) | (11,085)"
REVENUE_ROW = "Net sales | 4,521 | 4,073 | 3,809"


class TestTokenizer:
    """Financial tokens must survive analysis intact."""

    def test_numbers_keep_digits_and_lose_separators(self) -> None:
        assert tokenize("(10,959)") == ("10959",)
        assert tokenize("$4,521.3 million") == ("4521.3", "million")

    def test_hyphenated_filing_identifiers_stay_whole(self) -> None:
        assert tokenize("Form 10-K Item 7A") == ("form", "10-k", "item", "7a")

    def test_punctuation_only_text_has_no_tokens(self) -> None:
        assert tokenize("$ — % ( )") == ()


class TestFakeEmbedder:
    """The dense fake must be stable, normalised and contract-respecting."""

    def test_same_text_gives_same_vector_across_instances(self) -> None:
        first = FakeEmbedder(dimension=32).embed(CAPEX_ROW)
        second = FakeEmbedder(dimension=32).embed(CAPEX_ROW)
        assert first == second

    def test_vector_is_l2_normalised(self) -> None:
        vector = FakeEmbedder(dimension=32).embed(CAPEX_ROW)
        assert math.isclose(math.sqrt(sum(value * value for value in vector)), 1.0)

    def test_shared_terms_raise_similarity(self) -> None:
        embedder = FakeEmbedder(dimension=256)
        query = embedder.embed("purchases of property and equipment")
        related = embedder.embed("purchases of property, plant and equipment")
        unrelated = embedder.embed("consolidated balance sheet total assets")
        assert _dot(query, related) > _dot(query, unrelated)

    def test_empty_input_raises_instead_of_returning_zero_vector(self) -> None:
        with pytest.raises(EmbedderError):
            FakeEmbedder().embed("   ")

    async def test_embed_documents_preserves_order_and_count(self) -> None:
        embedder = FakeEmbedder(dimension=32)
        vectors = await embedder.embed_documents([CAPEX_ROW, REVENUE_ROW])
        assert len(vectors) == 2
        assert vectors[0] == embedder.embed(CAPEX_ROW)

    async def test_empty_batch_raises(self) -> None:
        with pytest.raises(EmbedderError):
            await FakeEmbedder().embed_documents([])

    def test_dimension_below_floor_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="dimension"):
            FakeEmbedder(dimension=2)


class TestFakeSparseEncoder:
    """Sparse weights are term frequencies with sub-linear growth."""

    def test_repeated_terms_are_damped(self) -> None:
        once = FakeSparseEncoder().encode("revenue revenue")
        twice = FakeSparseEncoder().encode("revenue")
        assert once["revenue"] > twice["revenue"]
        assert once["revenue"] == pytest.approx(1.0 + math.log(2))

    def test_only_nonzero_terms_are_returned(self) -> None:
        assert set(FakeSparseEncoder().encode(CAPEX_ROW)) == set(tokenize(CAPEX_ROW))

    def test_unrelated_text_shares_no_terms(self) -> None:
        query = FakeSparseEncoder().encode("purchases of property and equipment")
        document = FakeSparseEncoder().encode("net sales for the fiscal year")
        assert set(query) & set(document) == set()


class TestFakeVectorStore:
    """Filtering, ranking and fusion semantics the eval harness depends on."""

    @pytest.fixture
    async def indexed(self, embedder: FakeEmbedder, sparse: FakeSparseEncoder) -> FakeVectorStore:
        store = FakeVectorStore(dimension=64)
        await store.upsert_chunks(
            [
                make_chunk(embedder, sparse, chunk_id="c1", text=CAPEX_ROW),
                make_chunk(embedder, sparse, chunk_id="c2", text=REVENUE_ROW),
                make_chunk(embedder, sparse, chunk_id="c3", text=CAPEX_ROW, doc_id=OTHER_DOC_ID),
            ]
        )
        return store

    def _query(self, embedder: FakeEmbedder, sparse: FakeSparseEncoder, text: str) -> SearchRequest:
        return SearchRequest(
            dense=embedder.embed(text),
            sparse=sparse.encode(text),
            metadata_filter=MetadataFilter(equality=(("doc_id", str(DOC_ID)),)),
            k=5,
            candidates=10,
        )

    async def test_metadata_filter_excludes_other_documents_before_scoring(
        self, indexed: FakeVectorStore, embedder: FakeEmbedder, sparse: FakeSparseEncoder
    ) -> None:
        hits = await indexed.search(self._query(embedder, sparse, CAPEX_ROW))
        found = [hit.chunk_id for hit in hits]
        assert found[0] == "c1"
        assert set(found) <= {"c1", "c2"}
        assert "c3" not in found
        assert all(hit.payload["doc_id"] == str(DOC_ID) for hit in hits)

    async def test_ranks_are_dense_and_ordered_by_score(
        self, indexed: FakeVectorStore, embedder: FakeEmbedder, sparse: FakeSparseEncoder
    ) -> None:
        hits = await indexed.search(self._query(embedder, sparse, CAPEX_ROW))
        assert [hit.rank for hit in hits] == list(range(1, len(hits) + 1))
        assert [hit.score for hit in hits] == sorted((hit.score for hit in hits), reverse=True)

    async def test_identical_ranking_across_repeated_searches(
        self, indexed: FakeVectorStore, embedder: FakeEmbedder, sparse: FakeSparseEncoder
    ) -> None:
        request = self._query(embedder, sparse, CAPEX_ROW)
        first = await indexed.search(request)
        second = await indexed.search(request)
        assert [(hit.chunk_id, hit.score) for hit in first] == [
            (hit.chunk_id, hit.score) for hit in second
        ]

    async def test_reranking_headroom_is_required(
        self, embedder: FakeEmbedder, sparse: FakeSparseEncoder
    ) -> None:
        with pytest.raises(ValueError, match="candidates"):
            SearchRequest(dense=embedder.embed(CAPEX_ROW), sparse={}, k=10, candidates=5)

    async def test_sparse_fusion_requires_a_sparse_vector(self, embedder: FakeEmbedder) -> None:
        with pytest.raises(ValueError, match="sparse"):
            SearchRequest(dense=embedder.embed(CAPEX_ROW), fusion=FusionMode.RRF)

    async def test_dense_only_and_sparse_only_are_both_measurable(
        self, indexed: FakeVectorStore, embedder: FakeEmbedder, sparse: FakeSparseEncoder
    ) -> None:
        request = self._query(embedder, sparse, CAPEX_ROW)
        dense_only = await indexed.search(replace(request, fusion=FusionMode.DENSE_ONLY))
        sparse_only = await indexed.search(replace(request, fusion=FusionMode.SPARSE_ONLY))
        fused = await indexed.search(request)
        assert dense_only[0].chunk_id == "c1"
        assert [hit.chunk_id for hit in sparse_only] == ["c1"]
        assert fused[0].chunk_id == "c1"

    async def test_hits_carry_both_per_retriever_scores(
        self, indexed: FakeVectorStore, embedder: FakeEmbedder, sparse: FakeSparseEncoder
    ) -> None:
        hits = await indexed.search(self._query(embedder, sparse, CAPEX_ROW))
        assert all(hit.dense_score is not None for hit in hits)
        assert all(hit.sparse_score is not None for hit in hits)

    async def test_empty_index_returns_no_hits_rather_than_raising(
        self, embedder: FakeEmbedder, sparse: FakeSparseEncoder
    ) -> None:
        empty = FakeVectorStore(dimension=64)
        hits = await empty.search(self._query(embedder, sparse, CAPEX_ROW))
        assert hits == []

    async def test_search_before_init_raises(self, embedder: FakeEmbedder) -> None:
        with pytest.raises(VectorStoreError, match="initialised"):
            await FakeVectorStore().search(
                SearchRequest(dense=embedder.embed(CAPEX_ROW), fusion=FusionMode.DENSE_ONLY)
            )

    async def test_upsert_rejects_dimension_mismatch(
        self, embedder: FakeEmbedder, sparse: FakeSparseEncoder
    ) -> None:
        store = FakeVectorStore(dimension=16)
        with pytest.raises(VectorStoreError, match="dimension"):
            await store.upsert_chunks([make_chunk(embedder, sparse, chunk_id="c1", text=CAPEX_ROW)])

    async def test_upsert_requires_doc_id_so_a_document_can_be_purged(self) -> None:
        orphan = IndexedChunk(chunk_id=ChunkId("c1"), text=CAPEX_ROW, dense=(0.1,) * 64)
        with pytest.raises(VectorStoreError, match="doc_id"):
            await FakeVectorStore(dimension=64).upsert_chunks([orphan])

    async def test_upsert_rejects_empty_batch(self) -> None:
        with pytest.raises(VectorStoreError):
            await FakeVectorStore(dimension=64).upsert_chunks([])

    async def test_delete_document_purges_only_that_document(
        self, indexed: FakeVectorStore
    ) -> None:
        assert await indexed.delete_document(OTHER_DOC_ID) == 1
        assert await indexed.count() == 2
        assert await indexed.count(OTHER_DOC_ID) == 0

    async def test_upsert_is_idempotent_per_chunk_id(
        self, indexed: FakeVectorStore, embedder: FakeEmbedder, sparse: FakeSparseEncoder
    ) -> None:
        await indexed.upsert_chunks([make_chunk(embedder, sparse, chunk_id="c1", text=CAPEX_ROW)])
        assert await indexed.count(DOC_ID) == 2

    async def test_ensure_collection_refuses_to_change_dimension(self) -> None:
        store = FakeVectorStore(dimension=64)
        with pytest.raises(VectorStoreError, match="already expects"):
            await store.ensure_collection(128, sparse=True)


class TestFakeLLMClient:
    """Scripting must be explicit, ordered and loud when a fixture is missing."""

    def _request(self, prompt: str) -> LLMRequest:
        return LLMRequest(system="s", prompt=prompt, json_schema={"type": "object"})

    async def test_returns_scripted_content_and_records_the_call(self) -> None:
        client = FakeLLMClient([ScriptedResponse(content='{"status": "found"}')])
        response = await client.complete(self._request("find capex"))
        assert response.json() == {"status": "found"}
        assert client.call_count == 1
        assert client.calls[0].prompt == "find capex"

    async def test_matching_entry_wins_over_an_unrelated_catch_all(self) -> None:
        client = FakeLLMClient(
            [
                ScriptedResponse(content='{"metric": "other"}'),
                ScriptedResponse(match="capex", content='{"metric": "capex"}'),
            ]
        )
        response = await client.complete(self._request("capex for fy2024"))
        assert response.json() == {"metric": "capex"}

    async def test_entries_are_consumed_once_so_retries_see_the_next_script(self) -> None:
        client = FakeLLMClient(
            [
                ScriptedResponse(content="not json"),
                ScriptedResponse(content='{"metric": "capex"}'),
            ]
        )
        first = await client.complete(self._request("capex"))
        second = await client.complete(self._request("capex"))
        assert first.content == "not json"
        with pytest.raises(LLMClientError):
            first.json()
        assert second.json() == {"metric": "capex"}

    async def test_scripted_error_is_raised_for_transport_failures(self) -> None:
        client = FakeLLMClient([ScriptedResponse(error=LLMClientError("timeout"))])
        with pytest.raises(LLMClientError, match="timeout"):
            await client.complete(self._request("capex"))

    async def test_exhausted_script_raises_instead_of_inventing_an_answer(self) -> None:
        client = FakeLLMClient([ScriptedResponse(content="{}")])
        await client.complete(self._request("first"))
        with pytest.raises(LLMClientError, match="no scripted response"):
            await client.complete(self._request("first"))

    async def test_requested_model_id_is_reported_so_audits_stay_honest(self) -> None:
        client = FakeLLMClient([ScriptedResponse(content="{}")], model_id="fake-model-v1")
        response = await client.complete(
            LLMRequest(system="s", prompt="p", model_id="override-model")
        )
        assert response.model_id == "override-model"

    async def test_reset_restores_call_history_and_script(self) -> None:
        client = FakeLLMClient([ScriptedResponse(content="{}")])
        await client.complete(self._request("p"))
        client.reset()
        assert client.call_count == 0
        assert (await client.complete(self._request("p"))).content == "{}"


class TestFakeDocumentParser:
    """Fixtures in, parse results out, and page counts are enforced."""

    async def test_registered_fixture_is_returned_verbatim(self, tmp_path: Path) -> None:
        document = ParsedDocument(
            doc_id=DocId("doc_test_0001"),
            checksum="abc",
            page_count=2,
            blocks=(ParsedBlock(page=1, kind=BlockKind.HEADING, text="Item 7"),),
            parser_version="fixture",
        )
        parser = FakeDocumentParser({document.doc_id: document})
        source = DocumentSource(doc_id=document.doc_id, path=tmp_path / "a.pdf", checksum="abc")
        parsed = await parser.parse(source)
        assert parsed.blocks == document.blocks
        assert parsed.parser_version == "fake-parser-v1"

    async def test_plain_text_is_split_into_paragraphs(self, tmp_path: Path) -> None:
        path = write_text_fixture(tmp_path, "filing.txt", "# Item 7\n\nBody paragraph.\n\n")
        parser = FakeDocumentParser()
        parsed = await parser.parse(
            DocumentSource(doc_id=DocId("doc_x"), path=path, checksum="sum")
        )
        assert [block.text for block in parsed.blocks] == ["Item 7", "Body paragraph."]

    async def test_missing_file_raises(self, tmp_path: Path) -> None:
        parser = FakeDocumentParser()
        with pytest.raises(DocumentParserError, match="cannot read"):
            await parser.parse(
                DocumentSource(doc_id=DocId("doc_x"), path=tmp_path / "absent.pdf", checksum="s")
            )

    async def test_page_count_mismatch_is_an_error_not_a_warning(self, tmp_path: Path) -> None:
        path = write_text_fixture(tmp_path, "filing.txt", "Body.\n")
        parser = FakeDocumentParser()
        with pytest.raises(DocumentParserError, match="page count mismatch"):
            await parser.parse(
                DocumentSource(doc_id=DocId("doc_x"), path=path, checksum="s", pages_expected=200)
            )

    async def test_health_flag_is_reported(self) -> None:
        assert await FakeDocumentParser().health_check() is True
        assert await FakeDocumentParser(healthy=False).health_check() is False


def _dot(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))
