from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from config.settings import settings


def _make_splitter() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ".", " ", ""],
        length_function=len,
    )


def chunk_text(text: str, metadata: dict) -> list[Document]:
    splitter = _make_splitter()
    return [
        Document(page_content=chunk, metadata=dict(metadata))
        for chunk in splitter.split_text(text)
    ]


def chunk_documents(documents: list[tuple[str, dict]]) -> list[Document]:
    all_chunks: list[Document] = []
    for text, metadata in documents:
        all_chunks.extend(chunk_text(text, metadata))
    return all_chunks
