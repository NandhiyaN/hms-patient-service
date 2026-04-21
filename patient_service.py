from fastapi import FastAPI, HTTPException, Depends, Request, APIRouter, Query, status
from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.exc import IntegrityError
from datetime import datetime, date
import logging
import os
import re
import json
from starlette.middleware.base import BaseHTTPMiddleware
from datetime import datetime, UTC
from common_utils import CorrelationIdMiddleware, setup_exception_handlers, require_role

# --------------------------------------------------------------------------------------
# Database configuration
# --------------------------------------------------------------------------------------
# We keep database-per-service, so Patient Service owns only the patient database.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./patients.db")

# For SQLite, check_same_thread=False is needed when FastAPI uses multiple threads.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


# --------------------------------------------------------------------------------------
# SQLAlchemy model
# --------------------------------------------------------------------------------------
class Patient(Base):
    __tablename__ = "patients"

    patient_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    phone = Column(String(20), index=True, nullable=False)
    dob = Column(String(10), nullable=False)  # Stored as YYYY-MM-DD string for simplicity
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)

# Create tables on service startup if not already present.
Base.metadata.create_all(bind=engine)


# --------------------------------------------------------------------------------------
# Pydantic schemas
# --------------------------------------------------------------------------------------
class PatientResponse(BaseModel):
    patient_id: int
    name: str
    email: str
    phone: str
    dob: str
    is_active: bool
    created_at: datetime

    # Allows returning SQLAlchemy objects directly.
    model_config = ConfigDict(from_attributes=True)


class PatientCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, description="Full patient name")
    email: EmailStr
    phone: str = Field(..., min_length=10, max_length=20, description="Patient phone number")
    dob: str = Field(..., description="Date of birth in YYYY-MM-DD format")

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        # Accepts numbers with separators, but enforces at least 10 digits.
        cleaned = re.sub(r"[^\d+]", "", value)
        if len(re.sub(r"\D", "", cleaned)) < 10:
            raise ValueError("Phone number must contain at least 10 digits")
        return value

    @field_validator("dob")
    @classmethod
    def validate_dob(cls, value: str) -> str:
        # Ensures dob is valid ISO date and not in the future.
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            raise ValueError("dob must be in YYYY-MM-DD format")

        if parsed >= date.today():
            raise ValueError("dob must be a past date")

        return value


class PatientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, min_length=10, max_length=20)
    dob: str | None = None
    is_active: bool | None = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        if value is None:
            return value
        cleaned = re.sub(r"[^\d+]", "", value)
        if len(re.sub(r"\D", "", cleaned)) < 10:
            raise ValueError("Phone number must contain at least 10 digits")
        return value

    @field_validator("dob")
    @classmethod
    def validate_dob(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            raise ValueError("dob must be in YYYY-MM-DD format")

        if parsed >= date.today():
            raise ValueError("dob must be a past date")

        return value


class PatientListResponse(BaseModel):
    # Standard paginated response wrapper for list API.
    items: list[PatientResponse]
    total: int
    skip: int
    limit: int


# --------------------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------------------
# We log structured JSON so logs are easier to monitor and demo.
logger = logging.getLogger("patient_service")
logger.setLevel(logging.INFO)

if not logger.handlers:
    stream_handler = logging.StreamHandler()
    logger.addHandler(stream_handler)


def mask_pii(text: str) -> str:
    """
    Mask emails and phone numbers in logs.
    This is important because assignment explicitly asks to mask PII in logs.
    """
    if not text:
        return text

    # Mask email like a***@domain.com
    text = re.sub(
        r'([a-zA-Z0-9])([a-zA-Z0-9._%+-]*)(@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
        r'\1***\3',
        text
    )

    # Mask phone numbers like +91***-***-1234 or ***-***-1234
    text = re.sub(
        r'(\+?\d{0,3})[\s\-\.]?\d{3}[\s\-\.]?\d{3}[\s\-\.]?(\d{4})',
        r'\1***-***-\2',
        text
    )

    return text


def log_event(level: str, message: str, correlation_id: str | None = None, **kwargs):
    """
    Centralized structured logging helper.
    All extra values are masked before logging.
    """
    safe_payload = {}
    for key, value in kwargs.items():
        safe_payload[key] = mask_pii(str(value)) if value is not None else value

    log_entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "service": "patient-service",
        "level": level.upper(),
        "message": message,
        "correlationId": correlation_id,
        **safe_payload
    }

    getattr(logger, level.lower(), logger.info)(json.dumps(log_entry))


class PIIMaskingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that logs incoming request metadata in structured JSON format
    while masking sensitive values.
    """
    async def dispatch(self, request: Request, call_next):
        correlation_id = getattr(request.state, "correlation_id", None)
        safe_url = mask_pii(str(request.url))

        log_event(
            "info",
            "incoming_request",
            correlation_id=correlation_id,
            method=request.method,
            url=safe_url
        )

        response = await call_next(request)
        return response


# --------------------------------------------------------------------------------------
# FastAPI app setup
# --------------------------------------------------------------------------------------
app = FastAPI(title="Patient Service", version="1.0.0")
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(PIIMaskingMiddleware)
setup_exception_handlers(app)

router = APIRouter(prefix="/v1")


# --------------------------------------------------------------------------------------
# Dependency
# --------------------------------------------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --------------------------------------------------------------------------------------
# Health and readiness endpoints
# --------------------------------------------------------------------------------------
@app.get("/health")
def health_check():
    return {"status": "ok", "service": "patient"}


@app.get("/ready")
def readiness_check():
    return {"status": "ok", "service": "patient", "ready": True}


# --------------------------------------------------------------------------------------
# Patient APIs
# --------------------------------------------------------------------------------------
@router.get("/patients", response_model=PatientListResponse)
def get_patients(
    name: str | None = Query(default=None, description="Filter by patient name"),
    phone: str | None = Query(default=None, description="Filter by phone"),
    is_active: bool | None = Query(default=None, description="Filter by active status"),
    skip: int = Query(default=0, ge=0, description="Pagination offset"),
    limit: int = Query(default=10, ge=1, le=100, description="Pagination limit"),
    db: Session = Depends(get_db),
    role: str = Depends(require_role(["admin", "reception", "doctor"]))
):
    """
    Returns paginated patient list with optional filtering.
    Assignment asks for pagination and filtering support.
    """
    query = db.query(Patient)

    if name:
        query = query.filter(Patient.name.ilike(f"%{name}%"))

    if phone:
        query = query.filter(Patient.phone.like(f"%{phone}%"))

    if is_active is not None:
        query = query.filter(Patient.is_active == is_active)

    total = query.count()
    items = query.offset(skip).limit(limit).all()

    return PatientListResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit
    )


@router.get("/patients/{patient_id}", response_model=PatientResponse)
def get_patient(
    patient_id: int,
    db: Session = Depends(get_db),
    role: str = Depends(require_role(["admin", "reception", "doctor"]))
):
    """
    Get a single patient by id.
    """
    patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


@router.post("/patients", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
def create_patient(
    patient: PatientCreate,
    request: Request,
    db: Session = Depends(get_db),
    role: str = Depends(require_role(["admin", "reception"]))
):
    """
    Create a patient.
    Only admin or reception can create patient records.
    """
    db_patient = Patient(**patient.model_dump())
    db.add(db_patient)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Patient with this email already exists")

    db.refresh(db_patient)

    log_event(
        "info",
        "patient_created",
        correlation_id=getattr(request.state, "correlation_id", None),
        patient_id=db_patient.patient_id,
        email=db_patient.email,
        phone=db_patient.phone
    )

    return db_patient


@router.put("/patients/{patient_id}", response_model=PatientResponse)
def update_patient(
    patient_id: int,
    updates: PatientUpdate,
    request: Request,
    db: Session = Depends(get_db),
    role: str = Depends(require_role(["admin", "reception"]))
):
    """
    Update patient details.
    """
    patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    for key, value in updates.model_dump(exclude_unset=True).items():
        setattr(patient, key, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Patient with this email already exists")

    db.refresh(patient)

    log_event(
        "info",
        "patient_updated",
        correlation_id=getattr(request.state, "correlation_id", None),
        patient_id=patient.patient_id,
        email=patient.email,
        phone=patient.phone
    )

    return patient


@router.delete("/patients/{patient_id}")
def delete_patient(
    patient_id: int,
    request: Request,
    db: Session = Depends(get_db),
    role: str = Depends(require_role(["admin"]))
):
    """
    Soft delete instead of hard delete.
    This is better for hospital workflows because other services may still reference patient_id.
    """
    patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    patient.is_active = False
    db.commit()
    db.refresh(patient)

    log_event(
        "info",
        "patient_deactivated",
        correlation_id=getattr(request.state, "correlation_id", None),
        patient_id=patient.patient_id,
        email=patient.email,
        phone=patient.phone
    )

    return {"status": "Successfully deactivated", "patient_id": patient.patient_id}


# Register versioned routes
app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("patient_service:app", host="127.0.0.1", port=9001, reload=True)