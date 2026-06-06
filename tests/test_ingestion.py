"""Tests for document loading and chunking."""
import sys
import os
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.document_loader import load_txt, load_document, load_directory
from src.ingestion.chunker import chunk_text, chunk_documents


SAMPLE_TEXT = """\
FICHE D'INSTRUCTIONS TEST
Révision: Rev. 01
Date: 2026-01-01
Auteur: Test

1. Objet
Cette fiche décrit la procédure de test.

2. Sécurité
EPI requis : casque, gants, chaussures de sécurité.
Risques identifiés : chute, coupure.

3. Outillage
Clé dynamométrique, tournevis.

4. Mode opératoire
Étape 1 : préparer l'outillage.
Étape 2 : réaliser l'opération.

5. Contrôle qualité
Vérification visuelle de conformité.
"""


@pytest.fixture
def sample_txt_file(tmp_path):
    p = tmp_path / "FI-TEST.txt"
    p.write_text(SAMPLE_TEXT, encoding="utf-8")
    return str(p)


class TestDocumentLoader:
    def test_load_txt(self, sample_txt_file):
        text, meta = load_txt(sample_txt_file)
        assert "FICHE D'INSTRUCTIONS TEST" in text
        assert meta["file_type"] == "txt"
        assert meta["source"] == "FI-TEST.txt"

    def test_load_document_txt(self, sample_txt_file):
        result = load_document(sample_txt_file)
        assert result is not None
        text, meta = result
        assert len(text) > 0
        assert meta["source"].endswith(".txt")

    def test_load_document_unsupported(self, tmp_path):
        bad_file = tmp_path / "file.xyz"
        bad_file.write_text("test")
        result = load_document(str(bad_file))
        assert result is None

    def test_load_directory(self, tmp_path):
        for i in range(3):
            f = tmp_path / f"FI-00{i}.txt"
            f.write_text(SAMPLE_TEXT)
        docs = load_directory(str(tmp_path))
        assert len(docs) == 3
        for text, meta in docs:
            assert len(text) > 0
            assert meta["file_type"] == "txt"


class TestChunker:
    def test_chunk_text_produces_documents(self, sample_txt_file):
        text, meta = load_txt(sample_txt_file)
        chunks = chunk_text(text, meta)
        assert len(chunks) >= 1
        for chunk in chunks:
            assert len(chunk.page_content) > 0
            assert chunk.metadata["source"] == "FI-TEST.txt"

    def test_chunk_text_respects_size(self, sample_txt_file):
        from config.settings import settings
        text, meta = load_txt(sample_txt_file)
        chunks = chunk_text(text, meta)
        for chunk in chunks:
            assert len(chunk.page_content) <= settings.chunk_size * 1.2

    def test_chunk_documents_aggregates(self, tmp_path):
        docs = []
        for i in range(3):
            docs.append((SAMPLE_TEXT, {"source": f"FI-00{i}.txt", "file_type": "txt"}))
        chunks = chunk_documents(docs)
        sources = {c.metadata["source"] for c in chunks}
        assert len(sources) == 3

    def test_metadata_preserved_in_chunks(self, sample_txt_file):
        text, meta = load_txt(sample_txt_file)
        meta["custom_field"] = "alstom_crl"
        chunks = chunk_text(text, meta)
        for chunk in chunks:
            assert chunk.metadata["custom_field"] == "alstom_crl"
