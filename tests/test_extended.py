import pytest
from fastapi.testclient import TestClient

from backend.api import app
from backend.coordinator import shard
from backend.matcher import score
import backend.matcher as matcher

client = TestClient(app)


@pytest.mark.parametrize("key", [
    "request/123",
    "resource/456",
    "demo/recovery-0",
    "request/abc",
    "resource/xyz"
])
def test_shard_range(key):
    assert 0 <= shard(key) < 3


def test_shard_consistency():
    key = "request/test-123"
    assert len({shard(key) for _ in range(100)}) == 1


def test_exact_location_match():
    request = {"type": "water", "location": "Bengaluru"}
    resource = {
        "type": "water",
        "location": "Bengaluru",
        "availability": True
    }
    assert score(request, resource) == 100


def test_different_location_match():
    request = {"type": "water", "location": "Bengaluru"}
    resource = {
        "type": "water",
        "location": "Mysuru",
        "availability": True
    }
    assert score(request, resource) == 20


def test_wrong_resource_type():
    request = {"type": "water", "location": "Bengaluru"}
    resource = {
        "type": "food",
        "location": "Bengaluru",
        "availability": True
    }
    assert score(request, resource) == -1


def test_unavailable_resource():
    request = {"type": "water", "location": "Bengaluru"}
    resource = {
        "type": "water",
        "location": "Bengaluru",
        "availability": False
    }
    assert score(request, resource) == -1


def test_location_normalization():
    request = {"type": "water", "location": " Bengaluru "}
    resource = {
        "type": "water",
        "location": "bengaluru",
        "availability": True
    }
    assert score(request, resource) == 100


def test_api_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_invalid_request_type():
    response = client.post("/requests", json={
        "type": "invalid",
        "location": "Bengaluru",
        "details": "Test emergency request",
        "priority": 3
    })
    assert response.status_code == 400


def test_invalid_priority():
    response = client.post("/requests", json={
        "type": "water",
        "location": "Bengaluru",
        "details": "Test emergency request",
        "priority": 10
    })
    assert response.status_code == 422


def test_invalid_resource_type():
    response = client.post("/resources", json={
        "type": "invalid",
        "location": "Bengaluru",
        "availability": True
    })
    assert response.status_code == 400


def test_missing_request_fields():
    response = client.post("/requests", json={
        "type": "water"
    })
    assert response.status_code == 422


def test_matching_workflow(monkeypatch):
    request = {
        "id": "test-request",
        "type": "water",
        "location": "Bengaluru",
        "status": "pending"
    }

    resource = {
        "id": "test-resource",
        "type": "water",
        "location": "Bengaluru",
        "availability": True,
        "status": "available"
    }

    saved = {}

    monkeypatch.setattr(
        matcher, "get_record", lambda key: request
    )

    monkeypatch.setattr(
        matcher, "scan", lambda prefix: [resource]
    )

    monkeypatch.setattr(
        matcher, "save",
        lambda key, value: saved.update({key: value.copy()})
    )

    matcher.match_one("test-request")

    assert saved["request/test-request"]["status"] == "matched"
    assert saved["request/test-request"]["match_score"] == 100
    assert saved["request/test-request"]["assigned_resource"] == "test-resource"
    assert saved["resource/test-resource"]["availability"] is False


def test_no_available_match(monkeypatch):
    request = {
        "id": "test-request",
        "type": "water",
        "location": "Bengaluru",
        "status": "pending"
    }

    saved = {}

    monkeypatch.setattr(
        matcher, "get_record", lambda key: request
    )

    monkeypatch.setattr(
        matcher, "scan", lambda prefix: []
    )

    monkeypatch.setattr(
        matcher, "save",
        lambda key, value: saved.update({key: value.copy()})
    )

    matcher.match_one("test-request")

    assert request["status"] == "pending"
    assert saved == {}
