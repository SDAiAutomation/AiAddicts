"""API FastAPI : génération asynchrone d'histoires (job queue).

Usage :
    uvicorn api:app --reload
    curl -X POST localhost:8000/jobs -H "Content-Type: application/json" \\
        -d '{"story_path": "stories/histoire-01.json"}'
    curl localhost:8000/jobs/job_000001
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from engine.jobs import JobStore
from engine.worker import JobWorker

BASE_DIR = Path(__file__).resolve().parent
STORIES_DIR = BASE_DIR / "stories"

job_store = JobStore()
job_worker = JobWorker(job_store)


@asynccontextmanager
async def lifespan(app: FastAPI):
    job_worker.start()
    yield


app = FastAPI(title="Faceless Kids Stories API", version="0.1.0", lifespan=lifespan)


class GenerateRequest(BaseModel):
    story_path: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/stories")
def list_stories() -> List[str]:
    if not STORIES_DIR.exists():
        return []
    return sorted(p.name for p in STORIES_DIR.glob("*.json"))


@app.post("/jobs", status_code=201)
def create_job(request: GenerateRequest) -> dict:
    story_path = Path(request.story_path)
    if not story_path.is_absolute():
        story_path = BASE_DIR / story_path
    if not story_path.exists():
        raise HTTPException(status_code=404, detail=f"Script d'histoire introuvable : {request.story_path}")

    job = job_store.create(str(story_path))
    job_worker.enqueue(job.id)
    return job.to_dict()


@app.get("/jobs")
def list_jobs() -> List[dict]:
    return [job.to_dict() for job in job_store.list()]


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job introuvable")
    return job.to_dict()
