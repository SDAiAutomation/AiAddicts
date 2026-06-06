#!/usr/bin/env python3
"""CLI: ingest FI documents into ChromaDB.

Usage:
    python scripts/ingest_documents.py --file /path/to/FI-001.pdf
    python scripts/ingest_documents.py --dir /path/to/fi_folder
    python scripts/ingest_documents.py --dir data/fi_samples --delete-existing
"""
import sys
import argparse
import logging
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.document_loader import load_document, load_directory
from src.ingestion.chunker import chunk_text, chunk_documents
from src.retrieval.vector_store import add_documents, delete_document, get_indexed_sources

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest FI documents into ChromaDB")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", help="Path to a single document (PDF, DOCX, TXT)")
    group.add_argument("--dir", help="Path to a directory of documents")
    parser.add_argument(
        "--delete-existing",
        action="store_true",
        help="Delete existing index for the same source before re-indexing",
    )
    parser.add_argument("--list", action="store_true", help="List indexed documents and exit")
    args = parser.parse_args()

    if args.list:
        sources = get_indexed_sources()
        if sources:
            print(f"\n{len(sources)} document(s) indexé(s) :")
            for s in sources:
                print(f"  • {s}")
        else:
            print("Aucun document indexé.")
        return

    if args.file:
        path = Path(args.file)
        if not path.exists():
            logger.error("Fichier introuvable : %s", args.file)
            sys.exit(1)

        if args.delete_existing:
            delete_document(path.name)

        result = load_document(str(path))
        if not result:
            logger.error("Impossible de charger : %s", args.file)
            sys.exit(1)

        text, metadata = result
        chunks = chunk_text(text, metadata)
        n = add_documents(chunks)
        logger.info("Indexé : %s → %d chunks", path.name, n)

    elif args.dir:
        dir_path = Path(args.dir)
        if not dir_path.is_dir():
            logger.error("Dossier introuvable : %s", args.dir)
            sys.exit(1)

        docs = load_directory(str(dir_path))
        if not docs:
            logger.warning("Aucun document trouvé dans : %s", args.dir)
            return

        if args.delete_existing:
            for _, meta in docs:
                delete_document(meta["source"])

        chunks = chunk_documents(docs)
        n = add_documents(chunks)
        logger.info("Indexé : %d document(s), %d chunks au total", len(docs), n)


if __name__ == "__main__":
    main()
