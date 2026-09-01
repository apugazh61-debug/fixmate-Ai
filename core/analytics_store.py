"""
SQLite-based persistent analytics store for FixMate AI.

Records metadata for every analysis and fix attempt. Provides aggregation
functions for error frequency, recurring files, and verification rates.
Initializes lazily on first access.
"""

from __future__ import annotations

import datetime
import sqlite3
from pathlib import Path
from typing import Any

from core.models import AnalysisResult


DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "analytics.db"


def _get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open a SQLite connection and ensure schema is initialized."""
    target = Path(db_path) if db_path else DEFAULT_DB_PATH
    conn = sqlite3.connect(str(target))
    conn.row_factory = sqlite3.Row
    _init_schema(conn)
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    """Create the analytics table if it doesn't already exist."""
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS analysis_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                repo_name TEXT DEFAULT '',
                file_path TEXT DEFAULT '',
                error_types TEXT DEFAULT '',
                issue_count INTEGER DEFAULT 0,
                verified INTEGER NOT NULL,
                source TEXT NOT NULL,
                attempts INTEGER NOT NULL
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON analysis_events(timestamp);")


def record_result(
    result: AnalysisResult,
    repo_name: str = "",
    file_path: str = "",
    db_path: str | Path | None = None,
) -> None:
    """Write an AnalysisResult event to the analytics SQLite store. Never throws."""
    try:
        conn = _get_connection(db_path)
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        # Extract unique error type strings
        error_types_list = [i.error_type.value for i in result.issues] if result.issues else ["none"]
        error_types_str = ",".join(sorted(set(error_types_list)))

        with conn:
            conn.execute(
                """
                INSERT INTO analysis_events 
                (timestamp, repo_name, file_path, error_types, issue_count, verified, source, attempts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now_iso,
                    repo_name.strip(),
                    file_path.strip(),
                    error_types_str,
                    len(result.issues),
                    1 if result.verified else 0,
                    result.source,
                    result.attempts,
                ),
            )
        conn.close()
    except Exception:  # noqa: BLE001 - analytics write must never break the main app
        pass


def get_summary_stats(db_path: str | Path | None = None) -> dict[str, Any]:
    """Return top-level aggregate metrics."""
    try:
        conn = _get_connection(db_path)
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM analysis_events")
        total_runs = cur.fetchone()[0]

        if total_runs == 0:
            conn.close()
            return {
                "total_runs": 0,
                "verified_count": 0,
                "verification_rate": 0.0,
                "local_runs": 0,
                "groq_runs": 0,
            }

        cur.execute("SELECT COUNT(*) FROM analysis_events WHERE verified = 1")
        verified_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM analysis_events WHERE source = 'local_engine'")
        local_runs = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM analysis_events WHERE source = 'groq_llm'")
        groq_runs = cur.fetchone()[0]

        conn.close()
        return {
            "total_runs": total_runs,
            "verified_count": verified_count,
            "verification_rate": round((verified_count / total_runs) * 100, 1) if total_runs else 0.0,
            "local_runs": local_runs,
            "groq_runs": groq_runs,
        }
    except Exception:  # noqa: BLE001
        return {
            "total_runs": 0,
            "verified_count": 0,
            "verification_rate": 0.0,
            "local_runs": 0,
            "groq_runs": 0,
        }


def get_error_frequency(db_path: str | Path | None = None) -> dict[str, int]:
    """Return count per error class."""
    counts: dict[str, int] = {}
    try:
        conn = _get_connection(db_path)
        cur = conn.cursor()
        cur.execute("SELECT error_types FROM analysis_events")
        for row in cur.fetchall():
            types = row["error_types"].split(",")
            for t in types:
                t_clean = t.strip()
                if t_clean:
                    counts[t_clean] = counts.get(t_clean, 0) + 1
        conn.close()
    except Exception:  # noqa: BLE001
        pass
    return counts


def get_top_recurring_files(limit: int = 5, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Return top recurring file paths that encountered fixes."""
    results: list[dict[str, Any]] = []
    try:
        conn = _get_connection(db_path)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT file_path, COUNT(*) as count 
            FROM analysis_events 
            WHERE file_path != '' 
            GROUP BY file_path 
            ORDER BY count DESC 
            LIMIT ?
            """,
            (limit,),
        )
        for row in cur.fetchall():
            results.append({"file_path": row["file_path"], "count": row["count"]})
        conn.close()
    except Exception:  # noqa: BLE001
        pass
    return results


def get_recent_history(limit: int = 15, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Return recent analysis records."""
    records: list[dict[str, Any]] = []
    try:
        conn = _get_connection(db_path)
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, timestamp, repo_name, file_path, error_types, issue_count, verified, source, attempts 
            FROM analysis_events 
            ORDER BY id DESC 
            LIMIT ?
            """,
            (limit,),
        )
        for row in cur.fetchall():
            records.append({
                "id": row["id"],
                "timestamp": row["timestamp"],
                "repo_name": row["repo_name"] or "—",
                "file_path": row["file_path"] or "interactive_editor",
                "error_types": row["error_types"],
                "issue_count": row["issue_count"],
                "verified": bool(row["verified"]),
                "source": row["source"],
                "attempts": row["attempts"],
            })
        conn.close()
    except Exception:  # noqa: BLE001
        pass
    return records
