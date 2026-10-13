"""Very small database layer that works with PostgreSQL (real system) and SQLite (tests).
All SQL in the project uses %s placeholders; they are converted for SQLite."""
import sqlite3
from contextlib import contextmanager

from . import config


class DB:
    def __init__(self, conn, engine):
        self.conn = conn
        self.engine = engine

    @property
    def is_pg(self):
        return self.engine == "postgres"

    def _sql(self, sql):
        return sql if self.is_pg else sql.replace("%s", "?")

    def q(self, sql, params=()):
        """Run a SELECT and return a list of dicts."""
        cur = self.conn.cursor()
        cur.execute(self._sql(sql), tuple(params))
        rows = cur.fetchall()
        cur.close()
        return [dict(r) for r in rows]

    def one(self, sql, params=()):
        rows = self.q(sql, params)
        return rows[0] if rows else None

    def run(self, sql, params=()):
        cur = self.conn.cursor()
        cur.execute(self._sql(sql), tuple(params))
        cur.close()

    def insert(self, table, values):
        cols = ", ".join(values.keys())
        marks = ", ".join(["%s"] * len(values))
        sql = "INSERT INTO {} ({}) VALUES ({})".format(table, cols, marks)
        cur = self.conn.cursor()
        if self.is_pg:
            cur.execute(sql + " RETURNING id", tuple(values.values()))
            new_id = cur.fetchone()["id"]
        else:
            cur.execute(self._sql(sql), tuple(values.values()))
            new_id = cur.lastrowid
        cur.close()
        return new_id


def _open():
    eng = config.db_engine()
    if eng == "sqlite":
        conn = sqlite3.connect(config.sqlite_path(), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn, eng
    import psycopg2
    import psycopg2.extras
    s = config.pg_settings()
    conn = psycopg2.connect(host=s["host"], port=s["port"], user=s["user"],
                            password=s["password"], dbname=s["dbname"],
                            cursor_factory=psycopg2.extras.RealDictCursor)
    return conn, eng


@contextmanager
def connect():
    """Use:  with connect() as db:  ...  (commits at the end, rolls back on error)."""
    conn, eng = _open()
    db = DB(conn, eng)
    try:
        yield db
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_postgres_database():
    """Create the PostgreSQL database if it does not exist yet (so pgAdmin is optional)."""
    if config.db_engine() != "postgres":
        return
    import psycopg2
    s = config.pg_settings()
    conn = psycopg2.connect(host=s["host"], port=s["port"], user=s["user"],
                            password=s["password"], dbname="postgres")
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (s["dbname"],))
    if cur.fetchone() is None:
        cur.execute('CREATE DATABASE "{}"'.format(s["dbname"]))
    cur.close()
    conn.close()
