from __future__ import annotations

import hashlib
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps

VERSION = "coverage_resnet34_unet_tuned_v1"
EXPECTED_SHA256 = "6cd686722b70aae0290175125848f317d75e593b0f7b93ddefb0d202fe47fefc"
DEFAULT_MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / "best_model_tuned.pt"
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""): digest.update(chunk)
    return digest.hexdigest()


def _model_class():
    import torch
    import torch.nn as nn
    from torchvision.models import resnet34

    class DoubleConv(nn.Module):
        def __init__(self, in_ch, out_ch):
            super().__init__()
            self.block = nn.Sequential(
                nn.Conv2d(in_ch, out_ch, 3, padding=1, bias=False), nn.BatchNorm2d(out_ch), nn.ReLU(inplace=True),
                nn.Conv2d(out_ch, out_ch, 3, padding=1, bias=False), nn.BatchNorm2d(out_ch), nn.ReLU(inplace=True),
            )
        def forward(self, x): return self.block(x)

    class ResNet34UNet(nn.Module):
        def __init__(self):
            super().__init__(); base = resnet34(weights=None)
            self.enc0 = nn.Sequential(base.conv1, base.bn1, base.relu); self.pool = base.maxpool
            self.enc1, self.enc2, self.enc3, self.enc4 = base.layer1, base.layer2, base.layer3, base.layer4
            self.up4 = nn.ConvTranspose2d(512, 256, 2, stride=2); self.dec4 = DoubleConv(512, 256)
            self.up3 = nn.ConvTranspose2d(256, 128, 2, stride=2); self.dec3 = DoubleConv(256, 128)
            self.up2 = nn.ConvTranspose2d(128, 64, 2, stride=2); self.dec2 = DoubleConv(128, 64)
            self.up1 = nn.ConvTranspose2d(64, 64, 2, stride=2); self.dec1 = DoubleConv(128, 64)
            self.up0 = nn.ConvTranspose2d(64, 32, 2, stride=2); self.dec0 = DoubleConv(32, 32)
            self.final = nn.Conv2d(32, 1, kernel_size=1)
        def forward(self, x):
            import torch
            e0 = self.enc0(x); e1 = self.enc1(self.pool(e0)); e2 = self.enc2(e1); e3 = self.enc3(e2); e4 = self.enc4(e3)
            d4 = self.dec4(torch.cat([self.up4(e4), e3], dim=1))
            d3 = self.dec3(torch.cat([self.up3(d4), e2], dim=1))
            d2 = self.dec2(torch.cat([self.up2(d3), e1], dim=1))
            d1 = self.dec1(torch.cat([self.up1(d2), e0], dim=1))
            return self.final(self.dec0(self.up0(d1)))
    return ResNet34UNet


@lru_cache(maxsize=2)
def _load(path_text: str):
    import torch
    path = Path(path_text)
    device = "cuda" if torch.cuda.is_available() and os.getenv("ECOSIGNAL_FORCE_CPU", "0") != "1" else "cpu"
    try: checkpoint = torch.load(path, map_location=device, weights_only=True)
    except TypeError: checkpoint = torch.load(path, map_location=device)
    model = _model_class()().to(device); model.load_state_dict(checkpoint["model_state_dict"], strict=True); model.eval()
    return model, device, int(checkpoint.get("img_size", 384)), float(checkpoint.get("threshold", 0.5)), checkpoint


def _clean_mask(mask: np.ndarray, min_area: int) -> np.ndarray:
    import cv2
    mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=1)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    cleaned = np.zeros_like(mask)
    for label in range(1, count):
        if stats[label, cv2.CC_STAT_AREA] >= min_area: cleaned[labels == label] = 1
    return cleaned


def _quality(mask: np.ndarray, probability: np.ndarray) -> dict[str, Any]:
    import cv2
    h, w = mask.shape; coverage = float(100 * mask.mean()); reasons = []
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    areas = stats[1:, cv2.CC_STAT_AREA] if count > 1 else np.array([], dtype=int)
    inside = probability[mask == 1]
    if inside.size:
        mean_inside = float(inside.mean()); p10 = float(np.percentile(inside, 10)); uncertain_inside = float(((inside > .35) & (inside < .65)).mean())
    else: mean_inside, p10, uncertain_inside = 0.0, 0.0, 1.0
    kernel = np.ones((5, 5), np.uint8); boundary = cv2.dilate(mask, kernel) - cv2.erode(mask, kernel)
    boundary_values = probability[boundary == 1]
    boundary_uncertain = float(((boundary_values > .35) & (boundary_values < .65)).mean()) if boundary_values.size else 1.0
    border = np.zeros_like(mask); border[:8] = 1; border[-8:] = 1; border[:, :8] = 1; border[:, -8:] = 1
    edge_fraction = float(((mask == 1) & (border == 1)).sum() / max(mask.sum(), 1))
    component_count = int(len(areas)); small_count = int((areas < 200).sum()); largest_ratio = float(areas.max() / max(areas.sum(), 1)) if areas.size else 0.0
    checks = [(coverage < 2, "coverage_too_low"), (coverage > 75, "coverage_too_high"), (mean_inside < .78, "mean_probability_low"),
              (p10 < .52, "low_confidence_regions_inside_mask"), (uncertain_inside > .25, "too_much_uncertainty_inside_mask"),
              (boundary_uncertain > .35, "uncertain_boundaries"), (component_count > 80, "too_fragmented"),
              (small_count > 40, "too_many_tiny_regions"), (component_count > 1 and largest_ratio < .25, "no_dominant_lichen_region"),
              (edge_fraction > .40, "mask_touches_edges_too_much")]
    reasons.extend(reason for failed, reason in checks if failed)
    label = "auto_accept_high_quality" if not reasons else "review_medium_quality" if len(reasons) <= 2 else "review_or_reject_low_quality"
    confidence = float(np.clip(mean_inside * (1 - .5 * uncertain_inside) * (1 - .35 * boundary_uncertain), 0, 1))
    return {"quality_label": label, "needs_manual_review": bool(reasons), "quality_reasons": reasons, "lichen_coverage_percent": coverage,
            "mean_prob_inside": mean_inside, "p10_prob_inside": p10, "uncertain_fraction_inside": uncertain_inside,
            "boundary_uncertain_fraction": boundary_uncertain, "component_count": component_count, "largest_component_ratio": largest_ratio,
            "small_component_count": small_count, "edge_touch_fraction": edge_fraction, "mask_pixels": int(mask.sum()),
            "image_pixels": int(h * w), "coverage_confidence": confidence}


def predict(*, image_path: str, context: dict[str, Any]) -> dict[str, Any]:
    import torch
    model_path = Path(os.getenv("ECOSIGNAL_COVERAGE_MODEL_PATH", str(DEFAULT_MODEL_PATH)))
    if not model_path.exists(): return {"status": "unavailable", "version": VERSION, "warnings": [f"Coverage checkpoint not found: {model_path}"]}
    checksum = _sha256(model_path)
    if checksum != EXPECTED_SHA256: return {"status": "failed", "version": VERSION, "warnings": ["Coverage checkpoint checksum does not match the validated uploaded model"]}
    model, device, size, threshold, checkpoint = _load(str(model_path.resolve()))
    rgb_image = ImageOps.exif_transpose(Image.open(image_path)).convert("RGB"); rgb = np.asarray(rgb_image); h, w = rgb.shape[:2]
    resized = np.asarray(rgb_image.resize((size, size), Image.Resampling.BOX), dtype=np.float32) / 255.0
    normalized = (resized - IMAGENET_MEAN) / IMAGENET_STD
    tensor = torch.from_numpy(np.transpose(normalized, (2, 0, 1))).float().unsqueeze(0).to(device)
    with torch.no_grad(): probability_small = torch.sigmoid(model(tensor))[0, 0].cpu().numpy()
    probability = np.asarray(Image.fromarray(probability_small.astype(np.float32), mode="F").resize((w, h), Image.Resampling.BILINEAR))
    mask = _clean_mask((probability > threshold).astype(np.uint8), max(100, int(.0002 * h * w)))
    qa = _quality(mask, probability)
    artifact_dir = Path(context["artifact_dir"]); artifact_dir.mkdir(parents=True, exist_ok=True)
    mask_path = artifact_dir / "coverage_mask.png"; overlay_path = artifact_dir / "coverage_overlay.png"; probability_path = artifact_dir / "coverage_probability.png"
    Image.fromarray(mask * 255).save(mask_path)
    overlay = rgb.astype(np.float32); color = rgb.copy(); color[mask == 1] = [255, 70, 70]
    Image.fromarray(np.clip(.68 * overlay + .32 * color, 0, 255).astype(np.uint8)).save(overlay_path)
    Image.fromarray(np.clip(probability * 255, 0, 255).astype(np.uint8)).save(probability_path)
    rejected = qa["quality_label"] == "review_or_reject_low_quality"
    warnings = [f"Coverage mask QA: {reason}" for reason in qa["quality_reasons"]]
    return {"status": "rejected_low_confidence" if rejected else "available", "value": {"coverage_percent": qa["lichen_coverage_percent"]},
            "confidence": qa["coverage_confidence"], "version": VERSION, "warnings": warnings,
            "artifacts": {"coverage_mask": str(mask_path), "coverage_overlay": str(overlay_path), "coverage_probability": str(probability_path)},
            "details": {**qa, "checkpoint_sha256": checksum, "checkpoint_val_dice": float(checkpoint.get("val_dice", 0)),
                        "checkpoint_val_iou": float(checkpoint.get("val_iou", 0)), "threshold": threshold, "input_size": size}}
