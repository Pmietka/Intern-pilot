"""
SQLite database layer: schema creation and CRUD operations.
"""
import csv
import hashlib
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional

from .models import Application, Job, Outreach

logger = logging.getLogger(__name__)

# Default DB path relative to project root
DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "internpilot.db"

DDL = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    url_hash TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT,
    description TEXT,
    source TEXT,
    date_discovered TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    match_score INTEGER,
    match_rationale TEXT,
    status TEXT DEFAULT 'discovered',
    workday_portal TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES jobs(id),
    resume_path TEXT,
    cover_letter_path TEXT,
    applied_at TIMESTAMP,
    method TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS outreach (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER REFERENCES jobs(id),
    company TEXT NOT NULL,
    contact_name TEXT,
    contact_email TEXT,
    contact_title TEXT,
    email_subject TEXT,
    email_body TEXT,
    sent_at TIMESTAMP,
    followup_scheduled_at TIMESTAMP,
    followup_sent_at TIMESTAMP,
    response_received BOOLEAN DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER IF NOT EXISTS jobs_updated_at
AFTER UPDATE ON jobs
BEGIN
    UPDATE jobs SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;
"""


def compute_url_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


class Database:
    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create tables if they do not exist."""
        try:
            with self._conn() as conn:
                conn.executescript(DDL)
            logger.debug("Database schema ready at %s", self.db_path)
        except sqlite3.Error as exc:
            logger.error("Failed to initialize database schema: %s", exc)
            raise

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------ Jobs

    def insert_job(
        self,
        url: str,
        title: str,
        company: str,
        location: Optional[str] = None,
        description: Optional[str] = None,
        source: Optional[str] = None,
        workday_portal: Optional[str] = None,
    ) -> Optional[int]:
        """
        Insert a new job. Returns the new row ID, or None if already exists
        (deduplication by URL hash).
        """
        url_hash = compute_url_hash(url)
        try:
            with self._conn() as conn:
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO jobs
                        (url, url_hash, title, company, location, description, source, workday_portal)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (url, url_hash, title, company, location, description, source, workday_portal),
                )
                if cursor.rowcount == 0:
                    logger.debug("Job already exists (skipped): %s", url)
                    return None
                logger.info("Inserted new job: %s at %s (id=%d)", title, company, cursor.lastrowid)
                return cursor.lastrowid
        except sqlite3.Error as exc:
            logger.error("Failed to insert job %s: %s", url, exc)
            raise

    def get_job(self, job_id: int) -> Optional[Job]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return Job.from_row(dict(row)) if row else None

    def get_job_by_url(self, url: str) -> Optional[Job]:
        url_hash = compute_url_hash(url)
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE url_hash = ?", (url_hash,)
            ).fetchone()
            return Job.from_row(dict(row)) if row else None

    def get_all_jobs(self, status: Optional[str] = None) -> list[Job]:
        with self._conn() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC", (status,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM jobs ORDER BY created_at DESC"
                ).fetchall()
            return [Job.from_row(dict(r)) for r in rows]

    def get_unscored_jobs(self) -> list[Job]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE match_score IS NULL ORDER BY created_at"
            ).fetchall()
            return [Job.from_row(dict(r)) for r in rows]

    def get_jobs_by_min_score(self, min_score: int) -> list[Job]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE match_score >= ? ORDER BY match_score DESC",
                (min_score,),
            ).fetchall()
            return [Job.from_row(dict(r)) for r in rows]

    def update_job_score(
        self, job_id: int, score: int, rationale: str
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE jobs SET match_score = ?, match_rationale = ?, status = 'scored' WHERE id = ?",
                (score, rationale, job_id),
            )
        logger.info("Updated job %d score to %d", job_id, score)

    def update_job_status(self, job_id: int, status: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE jobs SET status = ? WHERE id = ?", (status, job_id)
            )
        logger.info("Updated job %d status to %s", job_id, status)

    def update_job_workday_portal(self, job_id: int, portal_url: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE jobs SET workday_portal = ? WHERE id = ?", (portal_url, job_id)
            )

    def url_exists(self, url: str) -> bool:
        url_hash = compute_url_hash(url)
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM jobs WHERE url_hash = ?", (url_hash,)
            ).fetchone()
            return row is not None

    def get_companies_applied_recently(self, cooldown_days: int) -> set[str]:
        """Return set of company names applied to within cooldown_days."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT j.company
                FROM applications a
                JOIN jobs j ON a.job_id = j.id
                WHERE a.applied_at >= datetime('now', ? || ' days')
                """,
                (f"-{cooldown_days}",),
            ).fetchall()
            return {r["company"] for r in rows}

    def count_applications_today(self) -> int:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) as cnt FROM applications
                WHERE date(applied_at) = date('now')
                """
            ).fetchone()
            return row["cnt"] if row else 0

    # ------------------------------------------------------------ Applications

    def insert_application(
        self,
        job_id: int,
        resume_path: Optional[str] = None,
        cover_letter_path: Optional[str] = None,
        method: str = "auto",
        notes: Optional[str] = None,
    ) -> int:
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO applications (job_id, resume_path, cover_letter_path, applied_at, method, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (job_id, resume_path, cover_letter_path, now, method, notes),
            )
            self.update_job_status(job_id, "applied")
            return cursor.lastrowid

    def get_application(self, job_id: int) -> Optional[Application]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM applications WHERE job_id = ? ORDER BY created_at DESC LIMIT 1",
                (job_id,),
            ).fetchone()
            return Application.from_row(dict(row)) if row else None

    def update_application_paths(
        self,
        job_id: int,
        resume_path: Optional[str] = None,
        cover_letter_path: Optional[str] = None,
    ) -> None:
        """Upsert content paths on a job's application record (or create a draft record)."""
        existing = self.get_application(job_id)
        if existing:
            with self._conn() as conn:
                conn.execute(
                    """
                    UPDATE applications
                    SET resume_path = COALESCE(?, resume_path),
                        cover_letter_path = COALESCE(?, cover_letter_path)
                    WHERE job_id = ?
                    """,
                    (resume_path, cover_letter_path, job_id),
                )
        else:
            with self._conn() as conn:
                conn.execute(
                    """
                    INSERT INTO applications (job_id, resume_path, cover_letter_path, method)
                    VALUES (?, ?, ?, 'pending')
                    """,
                    (job_id, resume_path, cover_letter_path),
                )

    # --------------------------------------------------------------- Outreach

    def insert_outreach(
        self,
        company: str,
        job_id: Optional[int] = None,
        contact_name: Optional[str] = None,
        contact_email: Optional[str] = None,
        contact_title: Optional[str] = None,
        email_subject: Optional[str] = None,
        email_body: Optional[str] = None,
        followup_days: int = 7,
    ) -> int:
        from datetime import timedelta

        followup_dt = (
            datetime.utcnow() + timedelta(days=followup_days)
        ).isoformat()
        with self._conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO outreach
                    (job_id, company, contact_name, contact_email, contact_title,
                     email_subject, email_body, followup_scheduled_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id, company, contact_name, contact_email, contact_title,
                    email_subject, email_body, followup_dt,
                ),
            )
            return cursor.lastrowid

    def mark_outreach_sent(self, outreach_id: int) -> None:
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            conn.execute(
                "UPDATE outreach SET sent_at = ? WHERE id = ?", (now, outreach_id)
            )

    def mark_followup_sent(self, outreach_id: int) -> None:
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            conn.execute(
                "UPDATE outreach SET followup_sent_at = ? WHERE id = ?", (now, outreach_id)
            )

    def get_due_followups(self) -> list[Outreach]:
        """Return outreach records where followup is due but not yet sent."""
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM outreach
                WHERE sent_at IS NOT NULL
                  AND followup_scheduled_at <= ?
                  AND followup_sent_at IS NULL
                  AND response_received = 0
                ORDER BY followup_scheduled_at
                """,
                (now,),
            ).fetchall()
            return [Outreach.from_row(dict(r)) for r in rows]

    def get_outreach_for_job(self, job_id: int) -> list[Outreach]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM outreach WHERE job_id = ? ORDER BY created_at DESC",
                (job_id,),
            ).fetchall()
            return [Outreach.from_row(dict(r)) for r in rows]

    # ------------------------------------------------------------------ Stats

    def get_summary_stats(self) -> dict:
        with self._conn() as conn:
            stats = {}
            for status in ["discovered", "scored", "content_generated", "applied", "rejected", "interview", "offer"]:
                row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM jobs WHERE status = ?", (status,)
                ).fetchone()
                stats[status] = row["cnt"] if row else 0
            stats["total"] = sum(stats.values())
            stats["outreach_sent"] = conn.execute(
                "SELECT COUNT(*) as cnt FROM outreach WHERE sent_at IS NOT NULL"
            ).fetchone()["cnt"]
            stats["responses"] = conn.execute(
                "SELECT COUNT(*) as cnt FROM outreach WHERE response_received = 1"
            ).fetchone()["cnt"]
            return stats

    # ---------------------------------------------------------------- Export

    def export_to_csv(self, output_path: Path) -> None:
        """Export all jobs and their application status to CSV."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT
                    j.id, j.title, j.company, j.location, j.source,
                    j.match_score, j.status, j.date_discovered,
                    a.applied_at, a.method, a.resume_path, a.cover_letter_path
                FROM jobs j
                LEFT JOIN applications a ON a.job_id = j.id
                ORDER BY j.match_score DESC NULLS LAST, j.created_at DESC
                """
            ).fetchall()

        with open(output_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow([
                "id", "title", "company", "location", "source",
                "match_score", "status", "date_discovered",
                "applied_at", "method", "resume_path", "cover_letter_path",
            ])
            for row in rows:
                writer.writerow(list(row))
        logger.info("Exported %d jobs to %s", len(rows), output_path)
