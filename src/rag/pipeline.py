from langchain_ollama import OllamaLLM
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate

from config.settings import settings
from src.retrieval.vector_store import get_vector_store, similarity_search_with_score

_QA_TEMPLATE = """\
Tu es un assistant expert en Fiches d'Instructions industrielles pour Alstom CRL (Charleroi, Belgique).
Ton rôle est d'aider les ingénieurs méthodes à trouver des informations précises dans les FI.

Utilise UNIQUEMENT les extraits de documents fournis ci-dessous pour répondre.
Si la réponse ne figure pas dans ces extraits, dis-le clairement sans inventer.
Cite toujours la source (nom du fichier) de chaque information.

Extraits de documents :
{context}

Question : {question}

Réponse (en français, avec références aux sources) :"""

_COMPARE_TEMPLATE = """\
Tu es un expert en Fiches d'Instructions industrielles pour Alstom CRL.

Compare les deux Fiches d'Instructions suivantes et fournis une analyse structurée :

1. **Points communs** — éléments identiques ou très similaires
2. **Différences significatives** — divergences importantes (procédures, couples, EPI, outillage…)
3. **Incohérences ou contradictions** — points qui pourraient causer des problèmes
4. **Recommandations** — laquelle est la plus à jour / complète, et pourquoi

--- FI 1 ---
{fi1}

--- FI 2 ---
{fi2}

Analyse comparative (en français) :"""


def get_llm() -> OllamaLLM:
    return OllamaLLM(
        model=settings.llm_model,
        base_url=settings.ollama_base_url,
        temperature=0.1,
    )


def build_rag_chain() -> RetrievalQA:
    prompt = PromptTemplate(template=_QA_TEMPLATE, input_variables=["context", "question"])
    return RetrievalQA.from_chain_type(
        llm=get_llm(),
        chain_type="stuff",
        retriever=get_vector_store().as_retriever(
            search_type="similarity",
            search_kwargs={"k": settings.retrieval_k},
        ),
        chain_type_kwargs={"prompt": prompt},
        return_source_documents=True,
    )


def query_rag(question: str) -> dict:
    """Simple RAG query — returns answer and deduplicated source list."""
    chain = build_rag_chain()
    result = chain.invoke({"query": question})

    seen: set[str] = set()
    sources = []
    for doc in result.get("source_documents", []):
        name = doc.metadata.get("source", "Inconnu")
        if name not in seen:
            seen.add(name)
            sources.append({"source": name, "excerpt": doc.page_content[:300] + "…"})

    return {"answer": result.get("result", ""), "sources": sources}


def query_with_scores(question: str) -> dict:
    """RAG query that exposes relevance scores per source chunk."""
    hits = similarity_search_with_score(question)

    context = "\n\n".join(
        f"[Source : {doc.metadata.get('source', 'Inconnu')}]\n{doc.page_content}"
        for doc, _ in hits
    )

    prompt = PromptTemplate(template=_QA_TEMPLATE, input_variables=["context", "question"])
    answer = get_llm().invoke(prompt.format(context=context, question=question))

    sources = [
        {
            "source": doc.metadata.get("source", "Inconnu"),
            "score": round(float(score), 3),
            "excerpt": doc.page_content[:300] + "…",
        }
        for doc, score in hits
    ]

    return {"answer": answer, "sources": sources}


def compare_fi(fi1_text: str, fi2_text: str) -> str:
    """LLM-based comparison of two FI documents."""
    prompt = _COMPARE_TEMPLATE.format(fi1=fi1_text[:3000], fi2=fi2_text[:3000])
    return get_llm().invoke(prompt)
