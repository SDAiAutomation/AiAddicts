import logging
from pathlib import Path

from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document

from config.settings import settings

logger = logging.getLogger(__name__)


def get_embeddings():
    return OllamaEmbeddings(
        model=settings.embedding_model,
        base_url=settings.ollama_base_url,
    )


def get_vector_store() -> Chroma:
    Path(settings.chroma_persist_dir).mkdir(parents=True, exist_ok=True)
    return Chroma(
        collection_name=settings.chroma_collection_name,
        embedding_function=get_embeddings(),
        persist_directory=settings.chroma_persist_dir,
    )


def add_documents(documents: list[Document]) -> int:
    """Add documents to the store, skipping sources already indexed. Returns chunk count."""
    store = get_vector_store()

    existing_sources: set[str] = set()
    try:
        data = store.get()
        if data and data.get("metadatas"):
            existing_sources = {m.get("source", "") for m in data["metadatas"] if m}
    except Exception:
        pass

    new_docs = [d for d in documents if d.metadata.get("source") not in existing_sources]
    if not new_docs:
        logger.info("No new chunks to add (all sources already indexed).")
        return 0

    store.add_documents(new_docs)
    logger.info("Added %d chunks to vector store.", len(new_docs))
    return len(new_docs)


def delete_document(source_name: str) -> None:
    """Remove all chunks for a given source from the store."""
    store = get_vector_store()
    try:
        data = store.get(where={"source": source_name})
        ids = data.get("ids", [])
        if ids:
            store.delete(ids=ids)
            logger.info("Deleted %d chunks for '%s'.", len(ids), source_name)
    except Exception as exc:
        logger.error("Failed to delete '%s': %s", source_name, exc)


def similarity_search(query: str, k: int | None = None) -> list[Document]:
    return get_vector_store().similarity_search(query, k=k or settings.retrieval_k)


def similarity_search_with_score(
    query: str, k: int | None = None
) -> list[tuple[Document, float]]:
    return get_vector_store().similarity_search_with_relevance_scores(
        query, k=k or settings.retrieval_k
    )


def get_indexed_sources() -> list[str]:
    """Return sorted list of indexed document source names."""
    try:
        data = get_vector_store().get()
        if data and data.get("metadatas"):
            return sorted({m.get("source", "") for m in data["metadatas"] if m})
    except Exception:
        pass
    return []


def get_document_text(source_name: str) -> str:
    """Retrieve and reassemble all chunks for a given source."""
    try:
        data = get_vector_store().get(where={"source": source_name})
        chunks = data.get("documents", [])
        return "\n\n".join(chunks) if chunks else ""
    except Exception:
        return ""
