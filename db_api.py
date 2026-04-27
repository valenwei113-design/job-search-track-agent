from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import psycopg2
import psycopg2.extras
import re
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "user": "postgres",
    "password": "difyai123456",
    "database": "jobsdb"
}

SECRET_KEY = "jobtrack-secret-key-change-in-production"
ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer()

BLOCKED = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|GRANT|REVOKE)\b",
    re.IGNORECASE
)

# ── Models ──

class QueryRequest(BaseModel):
    sql: str

class ApplicationRequest(BaseModel):
    company: str
    position: str
    applied_date: str | None = None
    location: str | None = None
    link: str | None = None
    feedback: str | None = None
    work_type: str | None = None

class AuthRequest(BaseModel):
    email: str
    password: str

# ── Auth helpers ──

def get_db():
    return psycopg2.connect(**DB_CONFIG)

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)

def create_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.utcnow() + timedelta(days=TOKEN_EXPIRE_DAYS)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> int:
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return int(payload["sub"])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

# ── Auth endpoints ──

@app.post("/auth/register")
def register(req: AuthRequest):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM users WHERE email=%s", (req.email,))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="Email already registered")
        cur.execute(
            "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id",
            (req.email, hash_password(req.password))
        )
        user_id = cur.fetchone()[0]
        conn.commit()
        return {"token": create_token(user_id), "email": req.email}
    finally:
        cur.close(); conn.close()

@app.post("/auth/login")
def login(req: AuthRequest):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, password_hash FROM users WHERE email=%s", (req.email,))
        row = cur.fetchone()
        if not row or not verify_password(req.password, row[1]):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        return {"token": create_token(row[0]), "email": req.email}
    finally:
        cur.close(); conn.close()

# ── Application endpoints (auth required) ──

@app.get("/applications")
def get_applications(user_id: int = Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT id, company, position, applied_date, location, link, feedback, work_type
        FROM job_applications
        WHERE user_id=%s
        ORDER BY applied_date DESC NULLS LAST, id DESC
    """, (user_id,))
    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    for r in rows:
        if r['applied_date']:
            r['applied_date'] = r['applied_date'].isoformat()
    return rows

@app.post("/applications")
def add_application(req: ApplicationRequest, user_id: int = Depends(get_current_user)):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO job_applications (company, position, applied_date, location, link, feedback, work_type, user_id)
            VALUES (%s, %s, %s::date, %s, %s, %s, %s, %s)
        """, (req.company, req.position, req.applied_date or None,
              req.location, req.link, req.feedback, req.work_type, user_id))
        conn.commit()
        cur.close(); conn.close()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/applications/{app_id}")
def update_application(app_id: int, req: ApplicationRequest, user_id: int = Depends(get_current_user)):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            UPDATE job_applications
            SET company=%s, position=%s, applied_date=%s::date,
                location=%s, link=%s, feedback=%s, work_type=%s
            WHERE id=%s AND user_id=%s
        """, (req.company, req.position, req.applied_date or None,
              req.location, req.link, req.feedback, req.work_type, app_id, user_id))
        conn.commit()
        cur.close(); conn.close()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Stats endpoints (auth required) ──

@app.get("/stats/summary")
def stats_summary(user_id: int = Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE feedback IS NULL) as pending,
            COUNT(DISTINCT location) as countries
        FROM job_applications WHERE user_id=%s
    """, (user_id,))
    row = dict(cur.fetchone())
    cur.close(); conn.close()
    return row

@app.get("/stats/countries")
def stats_countries(user_id: int = Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT location, COUNT(*) as count
        FROM job_applications
        WHERE user_id=%s AND location IS NOT NULL AND location != 'NaN'
        GROUP BY location ORDER BY count DESC LIMIT 10
    """, (user_id,))
    rows = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return rows

@app.get("/stats/worktype")
def stats_worktype(user_id: int = Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE work_type = 'Remote') as remote,
            COUNT(*) FILTER (WHERE work_type = 'Onsite') as onsite
        FROM job_applications WHERE user_id=%s
    """, (user_id,))
    row = dict(cur.fetchone())
    cur.close(); conn.close()
    return row

@app.get("/stats/feedback")
def stats_feedback(user_id: int = Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE feedback IS NULL) as pending,
            COUNT(*) FILTER (WHERE feedback = 'Fail') as rejected
        FROM job_applications WHERE user_id=%s
    """, (user_id,))
    row = dict(cur.fetchone())
    cur.close(); conn.close()
    return row

# ── Public endpoints ──

@app.post("/query")
async def run_query(req: QueryRequest):
    if BLOCKED.search(req.sql):
        raise HTTPException(status_code=400, detail="Only SELECT queries are allowed.")
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(req.sql)
        rows = cur.fetchall()
        cur.close(); conn.close()
        return {"result": [dict(r) for r in rows], "count": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok"}
