CREATE TABLE IF NOT EXISTS users (
    id           SERIAL PRIMARY KEY,
    email        TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    is_admin     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS invite_codes (
    id         SERIAL PRIMARY KEY,
    code       TEXT UNIQUE NOT NULL,
    is_active  BOOLEAN NOT NULL DEFAULT TRUE,
    created_by INTEGER REFERENCES users(id),
    used_by    INTEGER REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    used_at    TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS job_applications (
    id           SERIAL PRIMARY KEY,
    company      TEXT NOT NULL,
    position     TEXT NOT NULL,
    applied_date DATE,
    location     TEXT,
    link         TEXT,
    feedback     TEXT,
    work_type    TEXT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chat_usage (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date    DATE NOT NULL,
    count   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, date)
);

CREATE TABLE IF NOT EXISTS work_permits (
    country            TEXT PRIMARY KEY,
    visa               TEXT,
    annual_salary      TEXT,
    permanent_residence TEXT
);
