"""Stateless image inference. Photos and generated masks are never retained."""
from __future__ import annotations

import base64
import hashlib
import io
import logging
import os
import secrets
import tempfile
import threading
import warnings
from contextlib import asynccontextmanager
from pathlib import Path

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "1")
os.environ.setdefault("TF_NUM_INTEROP_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile, File
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool
from . import coverage, growth

ROOT = Path(__file__).resolve().parents[1]
MAX_UPLOAD = 8 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 25_000_000
INFERENCE_LOCK = threading.Lock()
log = logging.getLogger("ecosignal")


def verify_models():
    for adapter in (coverage, growth):
        path = adapter.DEFAULT_MODEL_PATH
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != adapter.EXPECTED_SHA256:
            raise RuntimeError(f"Missing or mismatched trained model: {path.name}")


@asynccontextmanager
async def lifespan(app):
    if not os.environ.get("ECOSIGNAL_API_TOKEN"):
        raise RuntimeError("Set ECOSIGNAL_API_TOKEN before starting the API")
    verify_models()
    # Loading at startup makes /health a readiness check for both model runtimes.
    if os.environ.get("ECOSIGNAL_SKIP_WARMUP") != "1":
        import torch
        torch.set_num_threads(1)
        coverage._load(str(coverage.DEFAULT_MODEL_PATH.resolve()))
        growth._load(str(growth.DEFAULT_MODEL_PATH.resolve()))
    yield


app = FastAPI(title="EcoSignal photo analysis", version="1.0.0", lifespan=lifespan)


def authorize(request: Request):
    token = os.environ.get("ECOSIGNAL_API_TOKEN", "")
    provided = request.headers.get("authorization", "")
    if not token or not secrets.compare_digest(provided, "Bearer " + token):
        raise HTTPException(401, "A valid API token is required")


@app.get("/health")
def health():
    return {"status": "ok", "models": {"coverage": coverage.VERSION, "growth_form": growth.VERSION}}


def png_data(path: str):
    return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode("ascii")


def infer(content: bytes):
    if not INFERENCE_LOCK.acquire(blocking=False):
        raise HTTPException(503, "Another photo is being analyzed. Please retry shortly.", headers={"Retry-After": "5"})
    try:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(content)) as source:
                    # iPhone JPEGs can contain an auxiliary image and decode as MPO.
                    if source.format not in {"JPEG", "MPO", "PNG", "WEBP"}:
                        raise ValueError("Use JPEG, PNG, or WebP")
                    image = ImageOps.exif_transpose(source).convert("RGB")
            original_size = image.size
            if min(image.size) < 64:
                raise ValueError("Choose a photograph at least 64 pixels on each side")
            image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise HTTPException(422, "Unreadable or oversized image. Use a JPEG, PNG, or WebP under 25 megapixels.") from exc

        with tempfile.TemporaryDirectory(prefix="ecosignal-") as tmp:
            path = Path(tmp) / "input.png"
            image.save(path)
            context = {"artifact_dir": tmp}
            components = {}
            for name, adapter in (("coverage", coverage), ("growth_form", growth)):
                try:
                    components[name] = adapter.predict(image_path=str(path), context=context)
                except Exception:
                    log.exception("%s inference failed", name)
                    components[name] = {"status": "failed", "value": None, "version": adapter.VERSION,
                                        "warnings": [f"{name} analysis failed. Retry or check the server logs."]}
            cov = components["coverage"]
            artifacts = cov.pop("artifacts", {})
            media = {name: png_data(path) for name, path in artifacts.items() if name in {"coverage_mask", "coverage_overlay"}}
            accepted = sum(x["status"] == "available" for x in components.values())
            return {"status": "completed" if accepted == 2 else "partial" if accepted else "needs_review",
                    **components, "media": media,
                    "image_sha256": hashlib.sha256(content).hexdigest(),
                    "image_dimensions": {"original": list(original_size), "analyzed": list(image.size)},
                    "warnings": [w for x in components.values() for w in x.get("warnings", [])],
                    "coverage_basis": "Percent of the entire analyzed photograph, not a separately identified bark surface."}
    finally:
        INFERENCE_LOCK.release()


@app.post("/analyze", dependencies=[Depends(authorize)])
async def analyze(image: UploadFile = File(...)):
    # Bound application reads as well as the advertised Content-Length.
    try:
        content = await image.read(MAX_UPLOAD + 1)
    finally:
        await image.close()
    if not content:
        raise HTTPException(422, "Choose a photograph")
    if len(content) > MAX_UPLOAD:
        raise HTTPException(413, "Choose a photograph under 8 MB")
    return await run_in_threadpool(infer, content)
