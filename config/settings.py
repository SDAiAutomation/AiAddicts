import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent


class Settings:
    # Ollama local inference
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    llm_model: str = os.getenv("LLM_MODEL", "mistral")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")

    # ChromaDB persistent storage
    chroma_persist_dir: str = str(BASE_DIR / "data" / "chroma_db")
    chroma_collection_name: str = "fi_alstom_crl"

    # Document chunking
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "500"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "50"))

    # Retrieval
    retrieval_k: int = int(os.getenv("RETRIEVAL_K", "4"))

    # Conformity validation
    conformity_threshold: float = float(os.getenv("CONFORMITY_THRESHOLD", "70"))

    # SharePoint / Microsoft Graph API (Phase 2)
    sp_tenant_id: str = os.getenv("SP_TENANT_ID", "")
    sp_client_id: str = os.getenv("SP_CLIENT_ID", "")
    sp_client_secret: str = os.getenv("SP_CLIENT_SECRET", "")
    sp_site_url: str = os.getenv("SP_SITE_URL", "")
    sp_library_name: str = os.getenv("SP_LIBRARY_NAME", "Fiches d'Instructions")
    sp_poll_interval: int = 300  # seconds


settings = Settings()
