import datetime
import sqlite3
import threading
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent / "agentcode.db"
_db_lock = threading.Lock()


def _get_connection(path: Path | str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database(path: Path | str = DB_PATH) -> None:
    with _db_lock:
        conn = _get_connection(path)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS instructions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                instruction TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS file_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                file_content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                step_name TEXT NOT NULL,
                status TEXT NOT NULL,
                detail TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            )
            """
        )
        conn.commit()
        conn.close()


def _utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _ensure_session(session_id: str) -> None:
    with _db_lock:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO sessions (session_id, created_at) VALUES (?, ?)",
            (session_id, _utc_now_iso()),
        )
        conn.commit()
        conn.close()


def record_instruction(session_id: str, instruction: str) -> None:
    _ensure_session(session_id)
    with _db_lock:
        conn = _get_connection()
        conn.execute(
            "INSERT INTO instructions (session_id, instruction, created_at) VALUES (?, ?, ?)",
            (session_id, instruction, _utc_now_iso()),
        )
        conn.commit()
        conn.close()


def record_file_history(session_id: str, file_content: str) -> None:
    _ensure_session(session_id)
    with _db_lock:
        conn = _get_connection()
        conn.execute(
            "INSERT INTO file_history (session_id, file_content, created_at) VALUES (?, ?, ?)",
            (session_id, file_content, _utc_now_iso()),
        )
        conn.commit()
        conn.close()


def record_agent_turn(session_id: str, step_name: str, status: str, detail: str) -> None:
    _ensure_session(session_id)
    with _db_lock:
        conn = _get_connection()
        conn.execute(
            "INSERT INTO agent_turns (session_id, step_name, status, detail, created_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, step_name, status, detail, _utc_now_iso()),
        )
        conn.commit()
        conn.close()


def load_session_context(session_id: str, limit: int = 5) -> dict[str, Any]:
    _ensure_session(session_id)
    with _db_lock:
        conn = _get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT instruction FROM instructions WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
            (session_id, limit),
        )
        instructions = [row[0] for row in cursor.fetchall()][::-1]

        cursor.execute(
            "SELECT file_content FROM file_history WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
            (session_id, limit),
        )
        file_history = [row[0] for row in cursor.fetchall()][::-1]
        conn.close()

    return {
        "instructions": instructions,
        "file_history": file_history,
    }
