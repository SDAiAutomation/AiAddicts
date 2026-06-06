"""SharePoint polling sync — polls every SP_POLL_INTERVAL seconds for new/modified FI."""
import logging
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from config.settings import settings
from src.ingestion.chunker import chunk_text
from src.ingestion.document_loader import load_document
from src.retrieval.vector_store import add_documents, delete_document
from src.sharepoint.graph_client import GraphClient
from src.validation.conformity_checker import check_conformity, ConformityReport

logger = logging.getLogger(__name__)

_SUPPORTED_EXT = {".pdf", ".docx", ".doc"}


def _format_report(report: ConformityReport) -> str:
    lines = [
        f"Score : {report.total_score:.0f}/100 — {report.status}",
        "",
        "Critères :",
    ]
    for r in report.rule_results:
        mark = "✓" if r.passed else "✗"
        lines.append(f"  {mark} {r.rule_name} ({r.score:.0f}/{r.max_score:.0f})")
    if report.recommendations:
        lines += ["", "Recommandations :"] + [f"  {rec}" for rec in report.recommendations]
    return "\n".join(lines)


class SharePointSync:
    def __init__(self):
        self.client = GraphClient()
        self.site_id: str | None = None
        self._processed: dict[str, str] = {}  # filename → lastModifiedDateTime

    def initialize(self) -> None:
        self.site_id = self.client.get_site_id()
        logger.info("Connected to SharePoint site: %s", self.site_id)

    def sync_once(self) -> int:
        if not self.site_id:
            self.initialize()

        documents = self.client.list_fi_documents(self.site_id)
        count = 0

        for doc in documents:
            name: str = doc.get("name", "")
            last_modified: str = doc.get("lastModifiedDateTime", "")

            if Path(name).suffix.lower() not in _SUPPORTED_EXT:
                continue
            if self._processed.get(name) == last_modified:
                continue

            logger.info("Syncing: %s", name)
            try:
                content = self.client.download_file(
                    doc.get("@microsoft.graph.downloadUrl", "")
                )
                ext = Path(name).suffix
                with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                    tmp.write(content)
                    tmp_path = tmp.name

                result = load_document(tmp_path)
                if not result:
                    continue

                text, metadata = result
                metadata["source"] = name

                delete_document(name)
                add_documents(chunk_text(text, metadata))

                report = check_conformity(text, source=name)
                self._write_back(doc, report)

                self._processed[name] = last_modified
                count += 1

            except Exception as exc:
                logger.error("Error processing %s: %s", name, exc)
                self._write_error(doc, str(exc))

        return count

    def _write_back(self, doc: dict, report: ConformityReport) -> None:
        try:
            drive_id = doc.get("parentReference", {}).get("driveId", "")
            item_id = doc.get("id", "")
            self.client.update_fi_columns(
                self.site_id,
                drive_id,
                item_id,
                {
                    "Statut_IA": "Analysé",
                    "Score_Conformite": round(report.total_score),
                    "Analyse_IA": _format_report(report),
                    "Date_Analyse": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception as exc:
            logger.error("Failed to write back to SharePoint: %s", exc)

    def _write_error(self, doc: dict, error_msg: str) -> None:
        try:
            drive_id = doc.get("parentReference", {}).get("driveId", "")
            item_id = doc.get("id", "")
            self.client.update_fi_columns(
                self.site_id,
                drive_id,
                item_id,
                {
                    "Statut_IA": "Erreur",
                    "Analyse_IA": f"Erreur lors de l'analyse : {error_msg}",
                    "Date_Analyse": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception:
            pass

    def run(self) -> None:
        logger.info(
            "SharePoint sync started — interval: %ds", settings.sp_poll_interval
        )
        while True:
            try:
                n = self.sync_once()
                logger.info("Sync cycle complete: %d document(s) processed.", n)
            except Exception as exc:
                logger.error("Sync cycle error: %s", exc)
            time.sleep(settings.sp_poll_interval)
