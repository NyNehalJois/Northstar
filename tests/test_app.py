import tempfile
import unittest
from pathlib import Path

from app import create_app
from database import (
    connect,
    create_course,
    create_student,
    enroll_student,
)


class TrainingPlatformTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = str(Path(self.temp_dir.name) / "training.db")
        self.app = create_app(
            {
                "TESTING": True,
                "DATABASE": self.database_path,
                "SECRET_KEY": "test-key",
                "ADMIN_USERNAME": "test-admin",
                "ADMIN_PASSWORD": "test-password",
                "WTF_CSRF_ENABLED": False,
            }
        )
        self.client = self.app.test_client()
        self.client.post(
            "/login", data={"username": "test-admin", "password": "test-password"}
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def course_data(self, capacity=2):
        return {
            "title": "Practical Design",
            "description": "Build better interfaces.",
            "instructor": "Morgan Lee",
            "start_date": "2026-11-01",
            "end_date": "2026-11-02",
            "capacity": capacity,
            "status": "Upcoming",
        }

    def student_data(self, name, email):
        return {"name": name, "email": email, "phone": ""}

    def test_default_admin_credentials_are_used_when_env_is_unset(self):
        default_app = create_app(
            {
                "TESTING": True,
                "DATABASE": self.database_path,
                "SECRET_KEY": "default-admin-test-key",
                "ADMIN_USERNAME": "",
                "ADMIN_PASSWORD": "",
                "WTF_CSRF_ENABLED": False,
            }
        )
        client = default_app.test_client()
        response = client.post(
            "/login",
            data={"username": "admin123", "password": "123"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Northstar", response.data)

    def test_management_pages_require_admin_sign_in(self):
        client = self.app.test_client()
        response = client.get("/courses")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.location)
        self.assertIn("next=/courses", response.location)

        response = client.post(
            "/login", data={"username": "test-admin", "password": "wrong-password"}
        )
        self.assertIn(b"did not match", response.data)
        response = client.post(
            "/login", data={"username": "test-admin", "password": "test-password"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(client.get("/courses").status_code, 200)

    def test_settings_page_shows_account_and_logout_ends_session(self):
        response = self.client.get("/settings")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Appearance", response.data)
        self.assertIn(b"Dark", response.data)
        self.assertIn(b"test-admin", response.data)

        response = self.client.post("/logout")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/login")
        self.assertEqual(self.client.get("/settings").status_code, 302)

    def test_health_check_is_public_and_login_redirect_stays_local(self):
        client = self.app.test_client()
        self.assertEqual(client.get("/healthz").status_code, 200)
        response = client.post(
            "/login?next=%2Fstudents",
            data={
                "username": "test-admin",
                "password": "test-password",
                "next": "//example.com",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/")

    def test_csrf_protection_rejects_state_change_without_token(self):
        csrf_app = create_app(
            {
                "TESTING": True,
                "DATABASE": self.database_path,
                "SECRET_KEY": "csrf-test-key",
                "ADMIN_USERNAME": "test-admin",
                "ADMIN_PASSWORD": "test-password",
                "WTF_CSRF_ENABLED": True,
            }
        )
        client = csrf_app.test_client()
        response = client.post(
            "/login", data={"username": "test-admin", "password": "test-password"}
        )
        self.assertEqual(response.status_code, 400)

    def test_course_creation_and_dashboard(self):
        response = self.client.post("/courses", data=self.course_data(), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Practical Design", response.data)
        dashboard = self.client.get("/")
        self.assertIn(b"ALL COURSES", dashboard.data)
        self.assertIn(b"1", dashboard.data)

    def test_invalid_course_dates_are_rejected(self):
        data = self.course_data()
        data["end_date"] = "2026-10-31"
        self.client.post("/courses", data=data)
        with connect(self.database_path) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM courses").fetchone()[0], 0)

    def test_course_can_be_updated_and_capacity_cannot_drop_below_enrollment(self):
        course_id = create_course(self.course_data(capacity=2), self.database_path)
        student_id = create_student(
            self.student_data("Avery Stone", "avery@example.com"), self.database_path
        )
        enroll_student(course_id, student_id, self.database_path)

        response = self.client.get(f"/courses/{course_id}/edit")
        self.assertEqual(response.status_code, 200)

        updated = self.course_data(capacity=3)
        updated["title"] = "Design Systems Lab"
        response = self.client.post(
            f"/courses/{course_id}/edit", data=updated, follow_redirects=True
        )
        self.assertIn(b"Design Systems Lab", response.data)
        with connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT title, capacity FROM courses WHERE id = ?", (course_id,)
            ).fetchone()
            self.assertEqual((row["title"], row["capacity"]), ("Design Systems Lab", 3))

        updated["capacity"] = 0
        response = self.client.post(
            f"/courses/{course_id}/edit", data=updated, follow_redirects=True
        )
        self.assertIn(b"Capacity must be between", response.data)
        with connect(self.database_path) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT capacity FROM courses WHERE id = ?", (course_id,)
                ).fetchone()[0],
                3,
            )

    def test_student_duplicate_email_is_rejected(self):
        self.client.post("/students", data=self.student_data("Jordan Lee", "jordan@example.com"))
        response = self.client.post(
            "/students",
            data=self.student_data("Jordan Again", "JORDAN@example.com"),
            follow_redirects=True,
        )
        self.assertIn(b"already exists", response.data)
        with connect(self.database_path) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM students").fetchone()[0], 1)

    def test_student_can_be_updated_and_duplicate_email_is_rejected(self):
        student_id = create_student(
            self.student_data("Jordan Lee", "jordan@example.com"), self.database_path
        )
        create_student(self.student_data("Riley Chen", "riley@example.com"), self.database_path)
        response = self.client.get(f"/students/{student_id}/edit")
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            f"/students/{student_id}/edit",
            data=self.student_data("Jordan Updated", "jordan.updated@example.com"),
            follow_redirects=True,
        )
        self.assertIn(b"Jordan Updated", response.data)
        with connect(self.database_path) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT email FROM students WHERE id = ?", (student_id,)
                ).fetchone()[0],
                "jordan.updated@example.com",
            )

        response = self.client.post(
            f"/students/{student_id}/edit",
            data=self.student_data("Jordan Updated", "riley@example.com"),
            follow_redirects=True,
        )
        self.assertIn(b"already exists", response.data)
        with connect(self.database_path) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT email FROM students WHERE id = ?", (student_id,)
                ).fetchone()[0],
                "jordan.updated@example.com",
            )
    def test_enrollment_roster_duplicate_and_capacity(self):
        course_id = create_course(self.course_data(capacity=1), self.database_path)
        first_student_id = create_student(
            self.student_data("Avery Stone", "avery@example.com"), self.database_path
        )
        second_student_id = create_student(
            self.student_data("Riley Chen", "riley@example.com"), self.database_path
        )
        response = self.client.post(
            f"/courses/{course_id}/enroll",
            data={"student_id": first_student_id},
            follow_redirects=True,
        )
        self.assertIn(b"Avery Stone", response.data)
        duplicate = self.client.post(
            f"/courses/{course_id}/enroll",
            data={"student_id": first_student_id},
            follow_redirects=True,
        )
        self.assertIn(b"already enrolled", duplicate.data)
        full = self.client.post(
            f"/courses/{course_id}/enroll",
            data={"student_id": second_student_id},
            follow_redirects=True,
        )
        self.assertIn(b"capacity", full.data)
        with connect(self.database_path) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM enrollments").fetchone()[0], 1)

    def test_unenrollment_releases_seat(self):
        course_id = create_course(self.course_data(capacity=1), self.database_path)
        student_id = create_student(
            self.student_data("Casey Park", "casey@example.com"), self.database_path
        )
        enroll_student(course_id, student_id, self.database_path)
        response = self.client.post(
            f"/courses/{course_id}/unenroll/{student_id}", follow_redirects=True
        )
        self.assertIn(b"removed from the course", response.data)
        with connect(self.database_path) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM enrollments").fetchone()[0], 0)

    def test_archiving_course_preserves_roster_and_restore_reactivates_it(self):
        course_id = create_course(self.course_data(), self.database_path)
        student_id = create_student(
            self.student_data("Avery Stone", "avery@example.com"), self.database_path
        )
        enroll_student(course_id, student_id, self.database_path)

        archived = self.client.post(
            f"/courses/{course_id}/archive",
            data={"archived": "1"},
            follow_redirects=True,
        )
        self.assertIn(b"Archived courses", archived.data)
        detail = self.client.get(f"/courses/{course_id}")
        self.assertIn(b"roster is preserved", detail.data)
        self.assertIn(b"Avery Stone", detail.data)
        blocked = self.client.post(
            f"/courses/{course_id}/enroll",
            data={"student_id": student_id},
            follow_redirects=True,
        )
        self.assertIn(b"archived and cannot accept enrollments", blocked.data)
        with connect(self.database_path) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM courses").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM enrollments").fetchone()[0], 1)

        restored = self.client.post(
            f"/courses/{course_id}/archive",
            data={"archived": "0"},
            follow_redirects=True,
        )
        self.assertIn(b"Practical Design", restored.data)

    def test_archiving_student_preserves_enrollment_history_and_can_restore(self):
        course_id = create_course(self.course_data(), self.database_path)
        student_id = create_student(
            self.student_data("Avery Stone", "avery@example.com"), self.database_path
        )
        enroll_student(course_id, student_id, self.database_path)

        archived = self.client.post(
            f"/students/{student_id}/archive",
            data={"archived": "1"},
            follow_redirects=True,
        )
        self.assertIn(b"Archived learners", archived.data)
        roster = self.client.get(f"/courses/{course_id}")
        self.assertIn(b"Avery Stone", roster.data)
        self.assertIn(b"Archived learner", roster.data)
        with connect(self.database_path) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM enrollments").fetchone()[0], 1)

        restored = self.client.post(
            f"/students/{student_id}/archive",
            data={"archived": "0"},
            follow_redirects=True,
        )
        self.assertIn(b"Avery Stone", restored.data)
        active = self.client.get("/students")
        self.assertIn(b"Avery Stone", active.data)


if __name__ == "__main__":
    unittest.main()
