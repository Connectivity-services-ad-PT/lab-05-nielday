import os
import json
import urllib.request
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional
from http import HTTPStatus

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Biến môi trường
SERVICE_NAME = os.getenv("SERVICE_NAME", "iot-ingestion")
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "0.1.0")
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "local-dev-token")

# DB config
DB_HOST = os.getenv("POSTGRES_HOST", "db")
DB_NAME = os.getenv("POSTGRES_DB", "iotdb")
DB_USER = os.getenv("POSTGRES_USER", "lab05")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "lab05pass")

app = FastAPI(
    title="FIT4110 Lab 05 - IoT Ingestion Service",
    version=SERVICE_VERSION,
    description="IoT Ingestion API tích hợp PostgreSQL và AI Service cho Lab 05.",
)

class SensorMetric(str, Enum):
    temperature = "temperature"
    humidity = "humidity"
    motion = "motion"
    smoke = "smoke"

class SensorUnit(str, Enum):
    celsius = "celsius"
    percent = "percent"
    boolean = "boolean"
    ppm = "ppm"

class ProblemDetails(BaseModel):
    type: str = "about:blank"
    title: str
    status: int = Field(..., ge=400, le=599)
    detail: str
    instance: Optional[str] = None

class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    db: str
    ai: str

class SensorReadingCreate(BaseModel):
    device_id: str = Field(..., min_length=3, examples=["ESP32-LAB-A01"])
    metric: SensorMetric = Field(..., examples=["temperature"])
    value: float = Field(..., ge=-40, le=80, description="Boundary range used in Lab 03 và Lab 04: -40 đến 80.")
    unit: Optional[SensorUnit] = Field(default=None, examples=["celsius"])
    timestamp: str = Field(..., examples=["2026-05-13T08:30:00+07:00"])

class SensorReadingCreated(BaseModel):
    reading_id: str
    device_id: str
    metric: SensorMetric
    accepted: bool
    created_at: str

def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )

@app.on_event("startup")
def startup_event():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS readings (
                reading_id VARCHAR(50) PRIMARY KEY,
                device_id VARCHAR(100) NOT NULL,
                metric VARCHAR(50) NOT NULL,
                value FLOAT NOT NULL,
                unit VARCHAR(50),
                timestamp VARCHAR(50) NOT NULL,
                created_at VARCHAR(50) NOT NULL
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error initializing database: {e}")

def build_problem(*, status_code: int, title: str, detail: str, instance: Optional[str] = None, problem_type: str = "about:blank") -> Dict:
    problem = {"type": problem_type, "title": title, "status": status_code, "detail": detail}
    if instance:
        problem["instance"] = instance
    return problem

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    try:
        title = HTTPStatus(exc.status_code).phrase
    except ValueError:
        title = "HTTP Error"

    if isinstance(exc.detail, dict):
        problem = exc.detail
    else:
        problem = build_problem(status_code=exc.status_code, title=title, detail=str(exc.detail), instance=str(request.url.path))

    problem.setdefault("status", exc.status_code)
    problem.setdefault("title", title)
    problem.setdefault("type", "about:blank")
    problem.setdefault("detail", "Request failed")
    problem.setdefault("instance", str(request.url.path))

    return JSONResponse(status_code=exc.status_code, content=problem, media_type="application/problem+json", headers=getattr(exc, "headers", None))

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    first_error = exc.errors()[0] if exc.errors() else {}
    location = ".".join(str(item) for item in first_error.get("loc", []))
    message = first_error.get("msg", "Request validation error")
    detail = f"{location}: {message}" if location else message

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=build_problem(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            title="Validation error",
            detail=detail,
            instance=str(request.url.path),
            problem_type="https://smart-campus.local/problems/validation-error",
        ),
        media_type="application/problem+json",
    )

def verify_bearer_token(authorization: Optional[str] = Header(default=None)) -> None:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=build_problem(
                status_code=status.HTTP_401_UNAUTHORIZED,
                title="Unauthorized",
                detail="Missing Authorization header",
                problem_type="https://smart-campus.local/problems/unauthorized",
            ),
        )
    expected = f"Bearer {AUTH_TOKEN}"
    if authorization != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=build_problem(
                status_code=status.HTTP_401_UNAUTHORIZED,
                title="Unauthorized",
                detail="Invalid bearer token",
                problem_type="https://smart-campus.local/problems/unauthorized",
            ),
        )

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

import random

def generate_reading_id() -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"R-{today}-{random.randint(1000, 9999)}"

@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    db_status = "error"
    try:
        conn = get_db_connection()
        conn.close()
        db_status = "ok"
    except Exception:
        pass

    ai_status = "error"
    try:
        req = urllib.request.urlopen("http://ai-service:9000/health", timeout=2)
        if req.getcode() == 200:
            ai_status = "ok"
    except Exception:
        pass

    return HealthResponse(
        status="ok",
        service=SERVICE_NAME,
        version=SERVICE_VERSION,
        db=db_status,
        ai=ai_status
    )

@app.post(
    "/readings",
    response_model=SensorReadingCreated,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_bearer_token)],
    responses={
        401: {"model": ProblemDetails},
        422: {"model": ProblemDetails},
        429: {"model": ProblemDetails},
    },
)
def create_reading(payload: SensorReadingCreate, response: Response) -> SensorReadingCreated:
    if payload.metric == SensorMetric.temperature and payload.value >= 70:
        response.headers["X-Warning"] = "high-temperature"

    # Gọi AI service
    try:
        ai_payload = json.dumps({"metric": payload.metric.value, "value": payload.value}).encode('utf-8')
        req = urllib.request.Request("http://ai-service:9000/predict", data=ai_payload, headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=2)
    except Exception as e:
        print(f"AI Service call failed: {e}")

    reading_id = generate_reading_id()
    created_at = now_iso()
    unit_val = payload.unit.value if payload.unit else None

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO readings (reading_id, device_id, metric, value, unit, timestamp, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (reading_id, payload.device_id, payload.metric.value, payload.value, unit_val, payload.timestamp, created_at)
    )
    conn.commit()
    cur.close()
    conn.close()

    return SensorReadingCreated(
        reading_id=reading_id,
        device_id=payload.device_id,
        metric=payload.metric,
        accepted=True,
        created_at=created_at,
    )

@app.get("/readings/latest", dependencies=[Depends(verify_bearer_token)])
def latest_readings(
    device_id: Optional[str] = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100),
) -> Dict[str, List[Dict]]:
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    if device_id:
        cur.execute("SELECT * FROM readings WHERE device_id = %s ORDER BY created_at DESC LIMIT %s", (device_id, limit))
    else:
        cur.execute("SELECT * FROM readings ORDER BY created_at DESC LIMIT %s", (limit,))
    
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {"items": [dict(r) for r in rows]}

@app.get("/readings/{reading_id}", dependencies=[Depends(verify_bearer_token)])
def get_reading(reading_id: str) -> Dict:
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM readings WHERE reading_id = %s", (reading_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=build_problem(
                status_code=status.HTTP_404_NOT_FOUND,
                title="Not Found",
                detail=f"Reading {reading_id} does not exist",
                instance=f"/readings/{reading_id}",
                problem_type="https://smart-campus.local/problems/not-found",
            ),
        )
    return dict(row)