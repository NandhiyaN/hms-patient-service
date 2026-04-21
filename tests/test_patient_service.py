import os
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Add project root to Python path so patient_service can be imported
sys.path.append(str(Path(__file__).resolve().parent.parent))

# Use separate test database
os.environ["DATABASE_URL"] = "sqlite:///./test_patients.db"

from patient_service import app, Base, engine 

# --------------------------------------------------------------------------------------
# Test setup / teardown
# --------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def client():
    # Recreate schema before tests so test execution is deterministic.
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    with TestClient(app) as test_client:
        yield test_client

    # Cleanup after tests
    Base.metadata.drop_all(bind=engine)

    # Properly dispose engine before deleting DB file
    engine.dispose()

    import time
    time.sleep(0.5)

    if os.path.exists("test_patients.db"):
        os.remove("test_patients.db")


def auth_header(role: str):
    """
    Helper to generate mock bearer token accepted by require_role().
    Example: role=admin -> Authorization: Bearer admin_test
    """
    return {"Authorization": f"Bearer {role}_test"}


# --------------------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------------------
def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness(client):
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["ready"] is True


def test_create_patient_success(client):
    payload = {
        "name": "Test Patient",
        "email": "test.patient@example.com",
        "phone": "9876543210",
        "dob": "1995-08-20"
    }

    response = client.post("/v1/patients", json=payload, headers=auth_header("admin"))
    assert response.status_code == 201

    body = response.json()
    assert body["name"] == "Test Patient"
    assert body["email"] == "test.patient@example.com"
    assert body["is_active"] is True
    assert "patient_id" in body


def test_create_patient_duplicate_email(client):
    payload = {
        "name": "Duplicate Patient",
        "email": "test.patient@example.com",
        "phone": "9999999999",
        "dob": "1990-01-01"
    }

    response = client.post("/v1/patients", json=payload, headers=auth_header("admin"))
    assert response.status_code == 409
    assert response.json()["message"] == "Patient with this email already exists"


def test_create_patient_invalid_dob(client):
    payload = {
        "name": "Future DOB",
        "email": "future@example.com",
        "phone": "9876543211",
        "dob": "2999-01-01"
    }

    response = client.post("/v1/patients", json=payload, headers=auth_header("admin"))
    assert response.status_code == 422


def test_get_patients_with_pagination(client):
    response = client.get("/v1/patients?skip=0&limit=10", headers=auth_header("reception"))
    assert response.status_code == 200

    body = response.json()
    assert "items" in body
    assert "total" in body
    assert "skip" in body
    assert "limit" in body


def test_get_patient_by_id(client):
    response = client.get("/v1/patients/1", headers=auth_header("doctor"))
    assert response.status_code == 200
    assert response.json()["patient_id"] == 1


def test_update_patient(client):
    payload = {
        "name": "Updated Patient",
        "phone": "9000000000"
    }

    response = client.put("/v1/patients/1", json=payload, headers=auth_header("reception"))
    assert response.status_code == 200

    body = response.json()
    assert body["name"] == "Updated Patient"
    assert body["phone"] == "9000000000"


def test_soft_delete_patient(client):
    response = client.delete("/v1/patients/1", headers=auth_header("admin"))
    assert response.status_code == 200
    assert response.json()["status"] == "Successfully deactivated"

    get_response = client.get("/v1/patients/1", headers=auth_header("doctor"))
    assert get_response.status_code == 200
    assert get_response.json()["is_active"] is False


def test_rbac_forbidden_for_doctor_on_create(client):
    payload = {
        "name": "Doctor Not Allowed",
        "email": "doctor.not.allowed@example.com",
        "phone": "9888888888",
        "dob": "1992-10-10"
    }

    response = client.post("/v1/patients", json=payload, headers=auth_header("doctor"))
    assert response.status_code == 403


def test_missing_auth_header_defaults_to_admin_mock(client):
    """
    In this demo helper, missing auth defaults to Bearer admin_test.
    This is acceptable for assignment/demo, though real systems should enforce JWT strictly.
    """
    payload = {
        "name": "No Auth Header",
        "email": "noauth@example.com",
        "phone": "9777777777",
        "dob": "1991-04-15"
    }

    response = client.post("/v1/patients", json=payload)
    assert response.status_code == 201