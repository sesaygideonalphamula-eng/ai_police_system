"""Database tables (they match the ER diagram in Chapter 2)."""

TABLES = [
    "evaluation_labels", "audit_log", "recommendations", "case_entities",
    "cases", "users", "stations",
]


def _ddl():
    return [
        """CREATE TABLE IF NOT EXISTS stations (
            id {pk},
            name TEXT NOT NULL UNIQUE,
            code TEXT NOT NULL,
            patrol_officers INTEGER NOT NULL,
            investigators INTEGER NOT NULL,
            coverage_weight {real} NOT NULL DEFAULT 1.0
        )""",
        """CREATE TABLE IF NOT EXISTS users (
            id {pk},
            username TEXT NOT NULL UNIQUE,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL,
            station_id INTEGER REFERENCES stations(id),
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS cases (
            id {pk},
            case_number TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            offence_type TEXT NOT NULL,
            priority INTEGER NOT NULL,
            status TEXT NOT NULL,
            station_id INTEGER NOT NULL REFERENCES stations(id),
            location TEXT,
            reported_date TEXT NOT NULL,
            narrative TEXT NOT NULL,
            outcome_note TEXT,
            created_by INTEGER REFERENCES users(id),
            created_at TEXT NOT NULL,
            analysed INTEGER NOT NULL DEFAULT 0
        )""",
        """CREATE TABLE IF NOT EXISTS case_entities (
            id {pk},
            case_id INTEGER NOT NULL REFERENCES cases(id),
            entity_type TEXT NOT NULL,
            value TEXT NOT NULL,
            normalized TEXT NOT NULL,
            role TEXT,
            source TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS recommendations (
            id {pk},
            agent TEXT NOT NULL,
            kind TEXT NOT NULL,
            case_id INTEGER REFERENCES cases(id),
            station_id INTEGER REFERENCES stations(id),
            score {real},
            payload TEXT NOT NULL,
            explanation TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            decided_by INTEGER REFERENCES users(id),
            decided_at TEXT,
            decision_comment TEXT,
            created_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS audit_log (
            id {pk},
            created_at TEXT NOT NULL,
            user_id INTEGER,
            username TEXT,
            event TEXT NOT NULL,
            case_id INTEGER,
            recommendation_id INTEGER,
            detail TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS evaluation_labels (
            case_id INTEGER PRIMARY KEY REFERENCES cases(id),
            series TEXT NOT NULL
        )""",
    ]


def create_schema(db):
    pk = "SERIAL PRIMARY KEY" if db.is_pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
    real = "DOUBLE PRECISION"
    for ddl in _ddl():
        db.run(ddl.format(pk=pk, real=real))


def drop_schema(db):
    for t in TABLES:
        db.run("DROP TABLE IF EXISTS {}{}".format(t, " CASCADE" if db.is_pg else ""))
