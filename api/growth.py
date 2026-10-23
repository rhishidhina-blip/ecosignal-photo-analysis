from __future__ import annotations

import hashlib
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps

VERSION = "growthform_effnet_filtered_highacc_v1"
EXPECTED_SHA256 = "e8a1bc9033e9f0eada2aaf756abc15a73adf1e60ab082cf38b39f1314290e077"
CLASS_NAMES = ["crustose", "foliose", "fruticose"]
DEFAULT_MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / "growthform_effnet_filtered_highacc.keras"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""): digest.update(chunk)
    return digest.hexdigest()


@lru_cache(maxsize=2)
def _load(path: str):
    import tensorflow as tf
    return tf.keras.models.load_model(path, compile=False)


def predict(*, image_path: str, context: dict[str, Any]) -> dict[str, Any]:
    path = Path(os.getenv("ECOSIGNAL_GROWTH_FORM_MODEL_PATH", str(DEFAULT_MODEL_PATH)))
    if not path.exists(): return {"status": "unavailable", "version": VERSION, "warnings": [f"Growth-form model not found: {path}"]}
    checksum = _sha256(path)
    if checksum != EXPECTED_SHA256: return {"status": "failed", "version": VERSION, "warnings": ["Growth-form model checksum does not match the validated Drive model"]}
    model = _load(str(path.resolve()))
    image = ImageOps.exif_transpose(Image.open(image_path)).convert("RGB").resize((224, 224), Image.Resampling.BILINEAR)
    batch = np.asarray(image, dtype=np.float32)[None, ...]
    probabilities = np.asarray(model.predict(batch, verbose=0)[0], dtype=float)
    if probabilities.shape != (3,) or not np.isfinite(probabilities).all() or (probabilities < 0).any() or (probabilities > 1).any() or not np.isclose(probabilities.sum(), 1, atol=.01):
        raise ValueError("Growth-form model returned invalid class probabilities")
    index = int(np.argmax(probabilities)); raw_label = CLASS_NAMES[index]; confidence = float(probabilities[index])
    if confidence >= .75: status, final, decision = "available", raw_label, "accepted"
    elif confidence >= .60: status, final, decision = "available", raw_label, "tentative"
    else: status, final, decision = "rejected_low_confidence", "uncertain", "retake_required"
    warnings = [] if decision == "accepted" else ["Growth-form result is tentative; retake preferred"] if decision == "tentative" else ["Growth-form confidence below 0.60; retake required"]
    return {"status": status, "value": {"growth_form": final, "raw_prediction": raw_label, "decision": decision}, "confidence": confidence,
            "version": VERSION, "warnings": warnings, "details": {"class_order": CLASS_NAMES, "probabilities": dict(zip(CLASS_NAMES, map(float, probabilities))),
            "input_size": [224, 224], "preferred_confidence_threshold": .75, "minimum_tentative_threshold": .60, "checkpoint_sha256": checksum,
            "validation_at_0_80": {"accepted_accuracy": .848, "coverage": .458, "retake_rate": .542}}}
