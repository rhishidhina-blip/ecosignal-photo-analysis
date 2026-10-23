import io
import os
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from api import main


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ECOSIGNAL_API_TOKEN", "contract-test-token")
    monkeypatch.setenv("ECOSIGNAL_SKIP_WARMUP", "1")
    with TestClient(main.app) as c:
        yield c


def picture():
    b = io.BytesIO()
    Image.new("RGB", (120, 180), (70, 130, 80)).save(b, "PNG")
    return b.getvalue()


AUTH = {"Authorization": "Bearer contract-test-token"}


def test_health_and_auth(client):
    assert client.get("/health").json()["status"] == "ok"
    assert client.post("/analyze", files={"image": ("photo.png", picture())}).status_code == 401


def test_rejects_invalid_and_large_images(client):
    assert client.post("/analyze", headers=AUTH, files={"image": ("x.jpg", b"not an image")}).status_code == 422
    assert client.post("/analyze", headers=AUTH, files={"image": ("x.jpg", b"x" * (main.MAX_UPLOAD + 1))}).status_code == 413


def test_actual_transport_preserves_mask_and_partial_results(client, monkeypatch):
    def cov(**kw):
        path = os.path.join(kw["context"]["artifact_dir"], "mask.png")
        Image.new("L", (120, 180), 255).save(path)
        return {"status": "available", "value": {"coverage_percent": 100.0}, "version": "synthetic-contract-fixture",
                "artifacts": {"coverage_mask": path}, "warnings": []}
    monkeypatch.setattr(main.coverage, "predict", cov)
    monkeypatch.setattr(main.growth, "predict", lambda **kw: {"status": "rejected_low_confidence", "value": {"growth_form": "uncertain"}, "version": "synthetic-contract-fixture", "warnings": ["Retake"]})
    r = client.post("/analyze", headers=AUTH, files={"image": ("photo.png", picture())})
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "partial"
    assert j["media"]["coverage_mask"].startswith("data:image/png;base64,")
    assert "artifacts" not in j["coverage"]
    assert j["growth_form"]["status"] == "rejected_low_confidence"
    assert len(j["image_sha256"]) == 64


def test_one_model_failure_does_not_hide_other_result(client, monkeypatch):
    monkeypatch.setattr(main.coverage, "predict", lambda **kw: (_ for _ in ()).throw(RuntimeError("private server detail")))
    monkeypatch.setattr(main.growth, "predict", lambda **kw: {"status": "available", "value": {"growth_form": "foliose"}, "version": "fixture", "warnings": []})
    j = client.post("/analyze", headers=AUTH, files={"image": ("photo.png", picture())}).json()
    assert j["coverage"]["status"] == "failed"
    assert j["growth_form"]["status"] == "available"
    assert "private server detail" not in str(j)


def test_busy_does_not_queue_unbounded_inference(client):
    main.INFERENCE_LOCK.acquire()
    try:
        r = client.post("/analyze", headers=AUTH, files={"image": ("photo.png", picture())})
        assert r.status_code == 503
    finally:
        main.INFERENCE_LOCK.release()
