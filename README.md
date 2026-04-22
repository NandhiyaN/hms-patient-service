# Patient Service - Hospital Management System

## 1. Overview
Patient Service is one of the microservices in the Hospital Management System. It is responsible for managing patient records and exposing versioned REST APIs for patient-related operations.

This service supports:
- Create patient
- View patient by ID
- List patients with pagination
- Search/filter patients by name, phone, and active status
- Update patient details
- Deactivate patient records using soft delete
- Role-based access control (RBAC)
- Correlation ID propagation
- Standard error responses
- PII masking in logs

This service follows the **database-per-service** pattern required by the assignment.

---

## 2. Assignment Mapping
This repository addresses the following assignment requirements for **Patient Service**:

- CRUD operations for patient records
- Search functionality by name or phone number
- Versioned APIs using `/v1`
- Standard error response structure: `code`, `message`, `correlationId`
- Pagination and filtering support
- PII masking in logs
- Docker containerization support
- Readiness and health endpoints
- OpenAPI 3.0 documentation
- Unit/API test cases
- Bruno API collection for manual testing

---

## 3. Tech Stack
- Python 3.11+
- FastAPI
- SQLAlchemy
- SQLite (for local development)
- Pytest
- Bruno
- Docker

---

## 4. Project Structure

```text
patient-service/
│── patient_service.py
│── common_utils.py
│── requirements.txt
│── Dockerfile
│── openapi_patient_service.yaml
│── README.md
│── .gitignore
│── tests/
│   └── test_patient_service.py
│── bruno/
│   ├── bruno.json
│   └── Patient Service/
│       ├── Create Patient.bru
│       ├── Get Patients.bru
│       ├── Get Patient By Id.bru
│       ├── Update Patient.bru
│       └── Deactivate Patient.bru

```

## 5. Service Responsibilities
This service owns only patient-related data and does not directly access any other microservice database.

**Responsibilities**:

 - Store patient master data

 - Provide patient lookup for downstream services

 - Allow search and pagination for patient listing

 - Keep patient records active/inactive

 - Enforce service-level authorization

---

## 6. API Base URL
Local:
    http://localhost:9001

Swagger UI:
    http://localhost:9001/docs

Health:
    http://localhost:9001/health

Readiness:
    http://localhost:9001/ready

---

## 7. API Endpoints
**Health Endpoints**

| Method | Endpoint | Description                    |
| ------ | -------- | ------------------------------ |
| GET    | /health  | Basic service health check     |
| GET    | /ready   | Readiness check for deployment |

**Patient Endpoints**

| Method | Endpoint                  | Description                |
| ------ | ------------------------- | -------------------------- |
| GET    | /v1/patients              | List patients with filters |
| GET    | /v1/patients/{patient_id} | Get patient by ID          |
| POST   | /v1/patients              | Create a new patient       |
| PUT    | /v1/patients/{patient_id} | Update patient details     |
| DELETE | /v1/patients/{patient_id} | Soft delete (deactivate)   |

---

## 8. Query Parameters for List API
Endpoint: GET /v1/patients

| Parameter | Type    | Required | Description             |
| --------- | ------- | -------- | ----------------------- |
| name      | string  | No       | Filter by patient name  |
| phone     | string  | No       | Filter by phone number  |
| is_active | boolean | No       | Filter by active status |
| skip      | integer | No       | Pagination offset       |
| limit     | integer | No       | Pagination page size    |

Example:
GET /v1/patients?name=John&is_active=true&skip=0&limit=10

---

## 9. RBAC
**Authorization header format:**
Authorization: Bearer <role>_test

**Examples:**

Authorization: Bearer admin_test

Authorization: Bearer reception_test

Authorization: Bearer doctor_test

**Allowed Roles by Endpoint:**

| Endpoint                 | admin  | reception | doctor |
| ------------------------ | ------ | --------- | ------ |
| GET /v1/patients         | Yes    | Yes       | Yes    |
| GET /v1/patients/{id}    | Yes    | Yes       | Yes    |
| POST /v1/patients        | Yes    | Yes       | No     |
| PUT /v1/patients/{id}    | Yes    | Yes       | No     |
| DELETE /v1/patients/{id} | Yes    | No        | No     |

---

## 10. Request and Response Examples

 ### Create Patient

**Request**

POST /v1/patients
Authorization: Bearer admin_test
Content-Type: application/json
X-Correlation-ID: patient-create-001


```json
{
  "name": "John Doe",
  "email": "john.doe@example.com",
  "phone": "9876543210",
  "dob": "1990-01-15"
}

Response

{
  "patient_id": 1,
  "name": "John Doe",
  "email": "john.doe@example.com",
  "phone": "9876543210",
  "dob": "1990-01-15",
  "is_active": true,
  "created_at": "2026-04-19T12:34:56.000000"
}

```
---

## 11. Standard Error Response
```json
{
  "code": "404",
  "message": "Patient not found",
  "correlationId": "xxx"
}
```
| Status Code | Meaning           |
|------------ |------------------ |
| 401         | Invalid token     |
| 403         | Role not allowed  |
| 404         | Patient not found |
| 409         | Duplicate email   |
| 422         | Validation error  |
| 500         | Internal error    |

---

## 12. Validation Rules
Name: 2–100 characters

Email: valid format

Phone: ≥10 digits

DOB: YYYY-MM-DD, must be past date

Duplicate emails rejected

---

## 13. Soft Delete Behavior
is_active set to false instead of physical deletion

Preserves historical references and prevents accidental loss

---

## 14. Logging and PII Masking

This service uses structured JSON logging.

- Logs are generated in JSON format for better monitoring
- Sensitive fields such as email and phone are masked
- Correlation ID is included in every log for traceability

Example:
```json
{
  "timestamp": "2026-04-19T10:00:00Z",
  "service": "patient-service",
  "level": "INFO",
  "message": "patient_created",
  "correlationId": "patient-create-001",
  "email": "j***@example.com",
  "phone": "***-***-3210"
}

```
---

## 15. Correlation ID Support
Client-provided X-Correlation-ID propagated

Auto-generated if missing

Returned in response

---

## 16. Local Setup Instructions

 ### Step 1: Clone the repository
    ```bash
    git clone https://github.com/NandhiyaN/hms-patient-service
    cd patient-service
    ```
 ### Step 2: Create virtual environment
    ```bash
    python -m venv venv
    ```
 ### Step 3: Activate environment

    Windows:
        venv\Scripts\activate
    Linux/Mac:
        source venv/bin/activate

 ### Step 4: Install dependencies
    ```bash
    pip install -r requirements.txt
    pip install uvicorn
    ```

 ### Step 5: Run the service
    ```bash
    python -m uvicorn gateway:app --reload --port 9001
    ```
 ### Step 6: Open Swagger UI
    http://localhost:9001/docs

---

## 17. Running Tests
Run:
python -m pytest tests/test_patient_service.py -v

Covers health, readiness, CRUD, validation, RBAC, etc.

---

## 18. Bruno API Collection
Located under bruno/ for manual validation and demo.

---

## 19. OpenAPI Specification

File: openapi_patient_service.yaml

This file documents:
- API endpoints
- Request and response schemas
- Standard error responses
- RBAC/security requirements
- Pagination and filtering
- Health and readiness APIs

---

## 20. Docker Support
Build: docker build -t patient-service .

Run: docker run -p 9001:9001 patient-service

Verify: curl http://localhost:9001/health

---

## 21. Kubernetes Readiness
Supports /health, /ready, containerized startup, env-based DB config.
Future manifests under k8s/.

---

## 22. Important Design Decisions
Database-per-service

Soft delete for integrity

Service-level RBAC

Structured logging

Versioned APIs under /v1

---

## 23. Future Improvements
JWT-based RBAC

PostgreSQL

Prometheus metrics

Alembic migrations

CI/CD pipeline

Kubernetes manifests

Audit fields

---

## 24. Author / Contribution
Scope: Patient CRUD, validation, logging, tests, Bruno collection, Docker setup, OpenAPI docs.













