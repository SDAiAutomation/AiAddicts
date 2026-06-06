"""FI Validator — Streamlit POC for Alstom CRL.

Run from project root:
    streamlit run app.py
"""
import sys
import tempfile
import logging
from pathlib import Path

import streamlit as st
import pandas as pd

# Ensure project root is on the path when launched from any directory
sys.path.insert(0, str(Path(__file__).parent))

from src.ingestion.document_loader import load_document, load_directory
from src.ingestion.chunker import chunk_text, chunk_documents
from src.retrieval.vector_store import (
    add_documents,
    delete_document,
    get_indexed_sources,
    get_document_text,
    similarity_search_with_score,
)
from src.validation.conformity_checker import check_conformity

logging.basicConfig(level=logging.WARNING)

# ─── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FI Validator — Alstom CRL",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🔧 FI Validator — Alstom CRL")
st.caption(
    "Système RAG d'interrogation et de validation des Fiches d'Instructions"
    " · Charleroi · POC Juin 2026"
)

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## Système")
    indexed = get_indexed_sources()
    st.metric("Documents indexés", len(indexed))

    st.markdown("## Modèles (Ollama)")
    st.code("LLM : mistral\nEmbeddings : nomic-embed-text", language=None)

    st.markdown("## Documents indexés")
    if indexed:
        for name in indexed:
            col_name, col_del = st.columns([5, 1])
            col_name.caption(name)
            if col_del.button("✕", key=f"del_{name}", help=f"Supprimer {name}"):
                delete_document(name)
                st.rerun()
    else:
        st.info("Aucun document.\nUtilisez l'onglet **Ingestion**.")

# ─── Tabs ─────────────────────────────────────────────────────────────────────
tab_ingest, tab_search, tab_validate, tab_compare, tab_audit = st.tabs([
    "📥 Ingestion",
    "🔍 Recherche",
    "✅ Validation",
    "↔️ Comparaison",
    "📊 Audit",
])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB — INGESTION
# ═══════════════════════════════════════════════════════════════════════════════
with tab_ingest:
    st.header("Indexation de documents FI")

    col_upload, col_folder = st.columns(2)

    with col_upload:
        st.subheader("Importer des fichiers")
        uploaded_files = st.file_uploader(
            "Glisser-déposer des FI (PDF, DOCX, TXT)",
            type=["pdf", "docx", "doc", "txt"],
            accept_multiple_files=True,
        )

        if uploaded_files and st.button("Indexer", type="primary", key="btn_index_files"):
            progress_bar = st.progress(0.0, text="Traitement en cours…")
            all_chunks = []

            for i, uf in enumerate(uploaded_files):
                progress_bar.progress((i + 1) / len(uploaded_files), text=f"Traitement : {uf.name}")
                ext = Path(uf.name).suffix
                with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                    tmp.write(uf.read())
                    tmp_path = tmp.name

                result = load_document(tmp_path)
                if result:
                    text, meta = result
                    meta["source"] = uf.name
                    all_chunks.extend(chunk_text(text, meta))

            if all_chunks:
                with st.spinner("Calcul des embeddings…"):
                    n = add_documents(all_chunks)
                st.success(f"✅ {len(uploaded_files)} fichier(s) — {n} chunks indexés")
                st.rerun()
            else:
                st.error("Aucun document n'a pu être traité.")

    with col_folder:
        st.subheader("Charger un dossier")
        st.caption("Utile pour indexer les FI de démonstration en une seule opération.")
        folder = st.text_input("Chemin absolu du dossier", placeholder="/chemin/vers/fi")

        if folder and st.button("Indexer le dossier", key="btn_index_dir"):
            if Path(folder).is_dir():
                with st.spinner("Chargement et embeddings…"):
                    docs = load_directory(folder)
                    if docs:
                        chunks = chunk_documents(docs)
                        n = add_documents(chunks)
                        st.success(f"✅ {len(docs)} document(s) — {n} chunks indexés")
                        st.rerun()
                    else:
                        st.warning("Aucun document trouvé.")
            else:
                st.error("Dossier introuvable.")

        # Quick shortcut to index the sample FIs
        sample_dir = Path(__file__).parent / "data" / "fi_samples"
        if sample_dir.exists():
            st.divider()
            st.caption(f"Dossier FI de démonstration détecté : `{sample_dir}`")
            if st.button("Indexer les FI de démonstration", key="btn_demo"):
                with st.spinner("Embeddings en cours…"):
                    docs = load_directory(str(sample_dir))
                    chunks = chunk_documents(docs)
                    n = add_documents(chunks)
                st.success(f"✅ {len(docs)} FI de démo — {n} chunks indexés")
                st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# TAB — RECHERCHE SÉMANTIQUE
# ═══════════════════════════════════════════════════════════════════════════════
with tab_search:
    st.header("Recherche Sémantique")

    query = st.text_input(
        "Votre question",
        placeholder="Quels sont les outils requis pour le serrage des boulons de bogie ?",
    )
    k = st.slider("Nombre de sources à consulter", 1, 10, 4)

    if query:
        if not get_indexed_sources():
            st.warning("Aucun document indexé. Utilisez l'onglet **Ingestion**.")
        else:
            with st.spinner("Recherche et génération de la réponse…"):
                try:
                    from src.rag.pipeline import query_with_scores
                    result = query_with_scores(query)

                    st.markdown("### Réponse")
                    st.markdown(result["answer"])

                    st.markdown("### Sources utilisées")
                    for src in result["sources"]:
                        score_pct = f"{src.get('score', 0):.1%}"
                        with st.expander(
                            f"📄 {src['source']} — pertinence : {score_pct}"
                        ):
                            st.text(src["excerpt"])
                except Exception as exc:
                    st.error(f"Erreur Ollama : {exc}\n\nVérifiez qu'Ollama est en cours d'exécution.")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB — VALIDATION DE CONFORMITÉ
# ═══════════════════════════════════════════════════════════════════════════════
with tab_validate:
    st.header("Validation de Conformité")

    source_type = st.radio(
        "Source du document",
        ["Télécharger un fichier", "Document déjà indexé"],
        horizontal=True,
    )

    fi_text: str | None = None
    fi_name: str | None = None

    if source_type == "Télécharger un fichier":
        up = st.file_uploader(
            "Sélectionner une FI", type=["pdf", "docx", "doc", "txt"], key="val_up"
        )
        if up:
            ext = Path(up.name).suffix
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(up.read())
            result = load_document(tmp.name)
            if result:
                fi_text, _ = result
                fi_name = up.name
    else:
        docs = get_indexed_sources()
        if docs:
            fi_name = st.selectbox("Choisir un document", docs, key="val_select")
            fi_text = get_document_text(fi_name)
        else:
            st.warning("Aucun document indexé.")

    if fi_text:
        if st.button("Lancer la validation", type="primary"):
            with st.spinner("Analyse de conformité…"):
                report = check_conformity(fi_text, source=fi_name or "Document")

            # Score headline
            col_score, col_status, col_empty = st.columns([1, 1, 2])
            with col_score:
                st.metric("Score de conformité", f"{report.total_score:.0f} / 100")
                st.progress(report.total_score / 100)
            with col_status:
                if report.status == "Conforme":
                    st.success(f"✅ {report.status}")
                elif report.status == "Partiellement conforme":
                    st.warning(f"⚠️ {report.status}")
                else:
                    st.error(f"❌ {report.status}")

            # Detailed breakdown
            st.markdown("### Détail des critères")
            for r in report.rule_results:
                icon = "✅" if r.passed else ("❌" if r.required else "⚪")
                c1, c2, c3 = st.columns([4, 1, 3])
                c1.write(f"{icon} **{r.rule_name}**")
                c2.write(f"{r.score:.0f} / {r.max_score:.0f}")
                if r.matched_keywords:
                    c3.caption(", ".join(r.matched_keywords[:3]))

            # Recommendations
            if report.recommendations:
                st.markdown("### Recommandations")
                for rec in report.recommendations:
                    st.write(rec)
            else:
                st.success("Aucune recommandation — document conforme sur tous les critères.")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB — COMPARAISON INTER-FI
# ═══════════════════════════════════════════════════════════════════════════════
with tab_compare:
    st.header("Comparaison de Fiches d'Instructions")

    col_fi1, col_fi2 = st.columns(2)

    def _get_fi_text(col_key: str, col: st.delta_generator.DeltaGenerator) -> tuple[str | None, str | None]:
        with col:
            src = st.radio("Source", ["Fichier", "Indexé"], key=f"{col_key}_src", horizontal=True)
            if src == "Fichier":
                up = st.file_uploader(
                    "FI", type=["pdf", "docx", "txt"], key=f"{col_key}_up"
                )
                if up:
                    ext = Path(up.name).suffix
                    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                        tmp.write(up.read())
                    res = load_document(tmp.name)
                    if res:
                        return res[0], up.name
            else:
                docs = get_indexed_sources()
                if docs:
                    name = st.selectbox("Choisir", docs, key=f"{col_key}_sel")
                    return get_document_text(name), name
                else:
                    st.warning("Aucun document indexé.")
        return None, None

    with col_fi1:
        st.subheader("FI 1")
    with col_fi2:
        st.subheader("FI 2")

    fi1_text, fi1_name = _get_fi_text("fi1", col_fi1)
    fi2_text, fi2_name = _get_fi_text("fi2", col_fi2)

    if fi1_text and fi2_text:
        if st.button("Comparer les deux FI", type="primary"):
            with st.spinner("Analyse comparative en cours (peut prendre 30-60s)…"):
                try:
                    from src.rag.pipeline import compare_fi
                    comparison = compare_fi(fi1_text, fi2_text)
                    st.markdown("### Analyse comparative")
                    st.markdown(comparison)
                except Exception as exc:
                    st.error(f"Erreur Ollama : {exc}")
    else:
        st.info("Sélectionnez deux FI pour activer la comparaison.")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB — AUDIT DOCUMENTAIRE
# ═══════════════════════════════════════════════════════════════════════════════
with tab_audit:
    st.header("Audit Documentaire")

    docs = get_indexed_sources()
    if not docs:
        st.warning("Aucun document indexé.")
    else:
        st.info(f"**{len(docs)}** document(s) dans la base vectorielle.")

        if st.button("Analyser tous les documents", type="primary"):
            audit_rows = []
            progress_bar = st.progress(0.0, text="Analyse…")

            for i, doc_name in enumerate(docs):
                progress_bar.progress((i + 1) / len(docs), text=f"Analyse : {doc_name}")
                text = get_document_text(doc_name)
                if text:
                    report = check_conformity(text, source=doc_name)
                    audit_rows.append(
                        {
                            "Document": doc_name,
                            "Score (%)": round(report.total_score, 0),
                            "Statut": report.status,
                            "Critères manquants": len(report.recommendations),
                        }
                    )

            if audit_rows:
                df = pd.DataFrame(audit_rows).sort_values("Score (%)", ascending=False)

                # KPI row
                k1, k2, k3 = st.columns(3)
                k1.metric("Conformes (≥80)", len(df[df["Statut"] == "Conforme"]))
                k2.metric(
                    "Partiels (60-79)",
                    len(df[df["Statut"] == "Partiellement conforme"]),
                )
                k3.metric("Non conformes (<60)", len(df[df["Statut"] == "Non conforme"]))

                st.dataframe(
                    df,
                    column_config={
                        "Score (%)": st.column_config.ProgressColumn(
                            "Score de conformité",
                            min_value=0,
                            max_value=100,
                            format="%d%%",
                        )
                    },
                    use_container_width=True,
                    hide_index=True,
                )

                csv = df.to_csv(index=False)
                st.download_button(
                    "⬇️ Exporter l'audit (CSV)",
                    csv,
                    file_name="audit_fi_alstom_crl.csv",
                    mime="text/csv",
                )
