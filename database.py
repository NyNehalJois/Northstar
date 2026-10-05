from contextlib import contextmanager
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_DATABASE = ROOT / "instance" / "training.db"


@contextmanager
def connect(database_path=DEFAULT_DATABASE):
    connection = sqlite3.connect(database_path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database(database_path=DEFAULT_DATABASE):
    database_path = Path(database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(database_path) as connection:
        connection.executescript((ROOT / "schema.sql").read_text(encoding="utf-8"))
        for table in ("courses", "students"):
            columns = {
                row["name"]
                for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
            }
            if "archived_at" not in columns:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN archived_at TEXT")


def get_dashboard_data(database_path=DEFAULT_DATABASE):
    with connect(database_path) as connection:
        stats = {
            "courses": connection.execute(
                "SELECT COUNT(*) FROM courses WHERE archived_at IS NULL"
            ).fetchone()[0],
            "students": connection.execute(
                "SELECT COUNT(*) FROM students WHERE archived_at IS NULL"
            ).fetchone()[0],
            "enrollments": connection.execute(
                """
                SELECT COUNT(*)
                FROM enrollments e
                JOIN courses c ON c.id = e.course_id AND c.archived_at IS NULL
                JOIN students s ON s.id = e.student_id AND s.archived_at IS NULL
                """
            ).fetchone()[0],
        }
        courses = connection.execute(
            """
            SELECT c.*, COUNT(s.id) AS enrolled
            FROM courses c
            LEFT JOIN enrollments e ON e.course_id = c.id
            LEFT JOIN students s ON s.id = e.student_id AND s.archived_at IS NULL
            WHERE c.archived_at IS NULL
            GROUP BY c.id
            ORDER BY c.start_date, c.id
            LIMIT 5
            """
        ).fetchall()
        return stats, courses


def list_courses(database_path=DEFAULT_DATABASE, include_archived=False):
    with connect(database_path) as connection:
        return connection.execute(
            f"""
            SELECT c.*, COUNT(s.id) AS enrolled
            FROM courses c
            LEFT JOIN enrollments e ON e.course_id = c.id
            LEFT JOIN students s ON s.id = e.student_id AND s.archived_at IS NULL
            WHERE c.archived_at IS {'NOT ' if include_archived else ''}NULL
            GROUP BY c.id
            ORDER BY c.start_date, c.id
            """
        ).fetchall()


def create_course(data, database_path=DEFAULT_DATABASE):
    with connect(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO courses (title, description, instructor, start_date, end_date, capacity, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["title"],
                data["description"],
                data["instructor"],
                data["start_date"],
                data["end_date"],
                data["capacity"],
                data["status"],
            ),
        )
        return cursor.lastrowid


def get_course(course_id, database_path=DEFAULT_DATABASE):
    with connect(database_path) as connection:
        return connection.execute(
            "SELECT * FROM courses WHERE id = ?", (course_id,)
        ).fetchone()


def set_course_archived(course_id, archived, database_path=DEFAULT_DATABASE):
    with connect(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE courses SET archived_at = CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE NULL END
            WHERE id = ?
            """,
            (int(archived), course_id),
        )
        return cursor.rowcount > 0


def update_course(course_id, data, database_path=DEFAULT_DATABASE):
    with connect(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE courses
            SET title = ?, description = ?, instructor = ?, start_date = ?,
                end_date = ?, capacity = ?, status = ?
            WHERE id = ?
            """,
            (
                data["title"],
                data["description"],
                data["instructor"],
                data["start_date"],
                data["end_date"],
                data["capacity"],
                data["status"],
                course_id,
            ),
        )
        return cursor.rowcount > 0


def list_students(database_path=DEFAULT_DATABASE, include_archived=False):
    with connect(database_path) as connection:
        return connection.execute(
            f"""
            SELECT s.*, COUNT(c.id) AS course_count
            FROM students s
            LEFT JOIN enrollments e ON e.student_id = s.id
            LEFT JOIN courses c ON c.id = e.course_id AND c.archived_at IS NULL
            WHERE s.archived_at IS {'NOT ' if include_archived else ''}NULL
            GROUP BY s.id
            ORDER BY s.name COLLATE NOCASE, s.id
            """
        ).fetchall()


def create_student(data, database_path=DEFAULT_DATABASE):
    with connect(database_path) as connection:
        cursor = connection.execute(
            "INSERT INTO students (name, email, phone) VALUES (?, ?, ?)",
            (data["name"], data["email"], data["phone"]),
        )
        return cursor.lastrowid


def get_student(student_id, database_path=DEFAULT_DATABASE):
    with connect(database_path) as connection:
        return connection.execute(
            "SELECT * FROM students WHERE id = ?", (student_id,)
        ).fetchone()


def set_student_archived(student_id, archived, database_path=DEFAULT_DATABASE):
    with connect(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE students SET archived_at = CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE NULL END
            WHERE id = ?
            """,
            (int(archived), student_id),
        )
        return cursor.rowcount > 0


def update_student(student_id, data, database_path=DEFAULT_DATABASE):
    with connect(database_path) as connection:
        cursor = connection.execute(
            "UPDATE students SET name = ?, email = ?, phone = ? WHERE id = ?",
            (data["name"], data["email"], data["phone"], student_id),
        )
        return cursor.rowcount > 0


def get_course_detail(course_id, database_path=DEFAULT_DATABASE):
    with connect(database_path) as connection:
        course = connection.execute(
            """
            SELECT c.*, COUNT(s.id) AS enrolled
            FROM courses c
            LEFT JOIN enrollments e ON e.course_id = c.id
            LEFT JOIN students s ON s.id = e.student_id AND s.archived_at IS NULL
            WHERE c.id = ?
            GROUP BY c.id
            """,
            (course_id,),
        ).fetchone()
        if course is None:
            return None, [], []
        students = connection.execute(
            """
            SELECT s.*, e.enrolled_at
            FROM enrollments e
            JOIN students s ON s.id = e.student_id
            WHERE e.course_id = ?
            ORDER BY s.name COLLATE NOCASE
            """,
            (course_id,),
        ).fetchall()
        available_students = connection.execute(
            """
            SELECT s.id, s.name, s.email
            FROM students s
            WHERE s.archived_at IS NULL
            AND NOT EXISTS (
                SELECT 1 FROM enrollments e
                WHERE e.student_id = s.id AND e.course_id = ?
            )
            ORDER BY s.name COLLATE NOCASE
            """,
            (course_id,),
        ).fetchall()
        return course, students, available_students


def enroll_student(course_id, student_id, database_path=DEFAULT_DATABASE):
    with connect(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        course = connection.execute(
            "SELECT capacity, archived_at FROM courses WHERE id = ?", (course_id,)
        ).fetchone()
        if course is None:
            raise LookupError("Course not found.")
        if course["archived_at"] is not None:
            raise ValueError("This course is archived and cannot accept enrollments.")
        if connection.execute(
            "SELECT id FROM students WHERE id = ? AND archived_at IS NULL", (student_id,)
        ).fetchone() is None:
            raise LookupError("Student not found.")
        if connection.execute(
            "SELECT id FROM enrollments WHERE course_id = ? AND student_id = ?",
            (course_id, student_id),
        ).fetchone():
            raise ValueError("This student is already enrolled in the course.")
        enrolled = connection.execute(
            """
            SELECT COUNT(*)
            FROM enrollments e
            JOIN students s ON s.id = e.student_id AND s.archived_at IS NULL
            WHERE e.course_id = ?
            """,
            (course_id,),
        ).fetchone()[0]
        if enrolled >= course["capacity"]:
            raise ValueError("This course has reached its enrollment capacity.")
        connection.execute(
            "INSERT INTO enrollments (course_id, student_id) VALUES (?, ?)",
            (course_id, student_id),
        )


def unenroll_student(course_id, student_id, database_path=DEFAULT_DATABASE):
    with connect(database_path) as connection:
        cursor = connection.execute(
            "DELETE FROM enrollments WHERE course_id = ? AND student_id = ?",
            (course_id, student_id),
        )
        return cursor.rowcount > 0
