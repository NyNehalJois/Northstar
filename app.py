import re
import os
import secrets
import sqlite3
from datetime import date
from urllib.parse import urlsplit

from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFProtect

from database import (
    DEFAULT_DATABASE,
    create_course,
    create_student,
    enroll_student,
    get_course,
    get_course_detail,
    get_dashboard_data,
    get_student,
    initialize_database,
    connect,
    list_courses,
    list_students,
    set_course_archived,
    set_student_archived,
    update_course,
    update_student,
    unenroll_student,
)


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32),
        ADMIN_USERNAME=os.environ.get("ADMIN_USERNAME") or "admin123",
        ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD") or "123",
        DATABASE=os.environ.get("DATABASE_PATH", str(DEFAULT_DATABASE)),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("FLASK_COOKIE_SECURE") == "1",
        WTF_CSRF_ENABLED=os.environ.get("WTF_CSRF_ENABLED") == "1",
    )
    if test_config:
        app.config.update(test_config)
    initialize_database(app.config["DATABASE"])
    CSRFProtect(app)

    @app.before_request
    def require_admin_login():
        if request.endpoint in {"login", "static", "healthz"}:
            return None
        if not session.get("admin_authenticated"):
            return redirect(url_for("login", next=request.full_path))
        return None

    @app.route("/login", methods=["GET", "POST"])
    def login():
        credentials_configured = bool(app.config["ADMIN_USERNAME"] and app.config["ADMIN_PASSWORD"])
        if request.method == "POST":
            username = request.form.get("username", "")
            password = request.form.get("password", "")
            expected_username = app.config["ADMIN_USERNAME"] or ""
            expected_password = app.config["ADMIN_PASSWORD"] or ""
            if credentials_configured and secrets.compare_digest(
                username, expected_username
            ) and secrets.compare_digest(password, expected_password):
                session.clear()
                session["admin_authenticated"] = True
                target = request.form.get("next", "")
                parsed_target = urlsplit(target)
                if target.startswith("/") and not target.startswith("//") and not parsed_target.netloc:
                    return redirect(target)
                return redirect(url_for("dashboard"))
            flash(
                "Administrator sign-in is not configured."
                if not credentials_configured
                else "Those sign-in details did not match.",
                "error",
            )
        return render_template("login.html", credentials_configured=credentials_configured)

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/settings")
    def settings():
        return render_template(
            "settings.html",
            admin_username=app.config["ADMIN_USERNAME"],
        )

    @app.get("/healthz")
    def healthz():
        with connect(app.config["DATABASE"]) as connection:
            connection.execute("SELECT 1").fetchone()
        return "ok", 200

    def read_course_form():
        data = {
            "title": request.form.get("title", "").strip(),
            "description": request.form.get("description", "").strip(),
            "instructor": request.form.get("instructor", "").strip(),
            "start_date": request.form.get("start_date", "").strip(),
            "end_date": request.form.get("end_date", "").strip(),
            "capacity": request.form.get("capacity", "").strip(),
            "status": request.form.get("status", "Upcoming").strip(),
        }
        start = date.fromisoformat(data["start_date"])
        end = date.fromisoformat(data["end_date"])
        capacity = int(data["capacity"])
        if not data["title"] or not data["instructor"]:
            raise ValueError("Add a course title and instructor.")
        if len(data["title"]) > 120 or len(data["instructor"]) > 100:
            raise ValueError("Course name or instructor is too long.")
        if len(data["description"]) > 500:
            raise ValueError("Description must be 500 characters or fewer.")
        if end < start:
            raise ValueError("The end date must be on or after the start date.")
        if not 1 <= capacity <= 10000:
            raise ValueError("Capacity must be between 1 and 10,000.")
        if data["status"] not in {"Upcoming", "In progress", "Completed"}:
            raise ValueError("Choose a valid course status.")
        data["capacity"] = capacity
        return data

    def read_student_form():
        data = {
            "name": request.form.get("name", "").strip(),
            "email": request.form.get("email", "").strip().lower(),
            "phone": request.form.get("phone", "").strip(),
        }
        if not data["name"] or len(data["name"]) > 120:
            raise ValueError("Enter a name up to 120 characters.")
        if len(data["email"]) > 254 or not re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+", data["email"]
        ):
            raise ValueError("Enter a valid email address.")
        if len(data["phone"]) > 40:
            raise ValueError("Phone must be 40 characters or fewer.")
        return data

    @app.get("/")
    def dashboard():
        stats, courses = get_dashboard_data(app.config["DATABASE"])
        return render_template("dashboard.html", stats=stats, courses=courses)

    @app.get("/courses")
    def courses():
        archived = request.args.get("archived") == "1"
        return render_template(
            "courses.html",
            courses=list_courses(app.config["DATABASE"], include_archived=archived),
            archived=archived,
        )

    @app.post("/courses/<int:course_id>/archive")
    def archive_course(course_id):
        archived = request.form.get("archived") == "1"
        if not set_course_archived(course_id, archived, app.config["DATABASE"]):
            return render_template("not_found.html"), 404
        flash("Course archived and its enrollment history preserved." if archived else "Course restored.", "success")
        return redirect(url_for("courses", archived="1" if archived else None))

    @app.post("/courses")
    def add_course():
        try:
            create_course(read_course_form(), app.config["DATABASE"])
        except (ValueError, TypeError) as error:
            flash(str(error) or "Enter valid course details.", "error")
            return redirect(url_for("courses"))
        flash("Course created successfully.", "success")
        return redirect(url_for("courses"))

    @app.get("/courses/<int:course_id>/edit")
    def edit_course(course_id):
        course = get_course(course_id, app.config["DATABASE"])
        if course is None:
            return render_template("not_found.html"), 404
        if course["archived_at"] is not None:
            flash("Restore this course before editing it.", "error")
            return redirect(url_for("courses", archived="1"))
        return render_template("edit_course.html", course=course)

    @app.post("/courses/<int:course_id>/edit")
    def save_course(course_id):
        existing = get_course(course_id, app.config["DATABASE"])
        if existing is None:
            return render_template("not_found.html"), 404
        if existing["archived_at"] is not None:
            flash("Restore this course before editing it.", "error")
            return redirect(url_for("courses", archived="1"))
        try:
            data = read_course_form()
            current_course, _, _ = get_course_detail(course_id, app.config["DATABASE"])
            if data["capacity"] < current_course["enrolled"]:
                raise ValueError("Capacity cannot be lower than the current enrollment.")
            update_course(course_id, data, app.config["DATABASE"])
        except (ValueError, TypeError) as error:
            flash(str(error) or "Enter valid course details.", "error")
            return redirect(url_for("edit_course", course_id=course_id))
        flash("Course details updated.", "success")
        return redirect(url_for("course_detail", course_id=course_id))

    @app.get("/students")
    def students():
        archived = request.args.get("archived") == "1"
        return render_template(
            "students.html",
            students=list_students(app.config["DATABASE"], include_archived=archived),
            archived=archived,
        )

    @app.post("/students/<int:student_id>/archive")
    def archive_student(student_id):
        archived = request.form.get("archived") == "1"
        if not set_student_archived(student_id, archived, app.config["DATABASE"]):
            return render_template("not_found.html"), 404
        flash("Learner archived; enrollment history preserved." if archived else "Learner restored.", "success")
        return redirect(url_for("students", archived="1" if archived else None))

    @app.post("/students")
    def add_student():
        try:
            data = read_student_form()
        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("students"))
        try:
            create_student(data, app.config["DATABASE"])
        except sqlite3.IntegrityError:
            flash("A student with that email address already exists.", "error")
            return redirect(url_for("students"))
        flash("Student added successfully.", "success")
        return redirect(url_for("students"))

    @app.get("/students/<int:student_id>/edit")
    def edit_student(student_id):
        student = get_student(student_id, app.config["DATABASE"])
        if student is None:
            return render_template("not_found.html"), 404
        if student["archived_at"] is not None:
            flash("Restore this learner before editing their details.", "error")
            return redirect(url_for("students", archived="1"))
        return render_template("edit_student.html", student=student)

    @app.post("/students/<int:student_id>/edit")
    def save_student(student_id):
        student = get_student(student_id, app.config["DATABASE"])
        if student is None:
            return render_template("not_found.html"), 404
        if student["archived_at"] is not None:
            flash("Restore this learner before editing their details.", "error")
            return redirect(url_for("students", archived="1"))
        try:
            data = read_student_form()
        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("edit_student", student_id=student_id))
        try:
            update_student(student_id, data, app.config["DATABASE"])
        except sqlite3.IntegrityError:
            flash("A student with that email address already exists.", "error")
            return redirect(url_for("edit_student", student_id=student_id))
        flash("Learner details updated.", "success")
        return redirect(url_for("students"))

    @app.get("/courses/<int:course_id>")
    def course_detail(course_id):
        course, enrolled_students, available_students = get_course_detail(
            course_id, app.config["DATABASE"]
        )
        if course is None:
            return render_template("not_found.html"), 404
        return render_template(
            "course_detail.html",
            course=course,
            enrolled_students=enrolled_students,
            available_students=available_students,
        )

    @app.post("/courses/<int:course_id>/enroll")
    def add_enrollment(course_id):
        try:
            student_id = int(request.form.get("student_id", ""))
            enroll_student(course_id, student_id, app.config["DATABASE"])
        except ValueError as error:
            flash(str(error) or "Choose a valid student.", "error")
        except LookupError as error:
            flash(str(error), "error")
        else:
            flash("Student enrolled successfully.", "success")
        return redirect(url_for("course_detail", course_id=course_id))

    @app.post("/courses/<int:course_id>/unenroll/<int:student_id>")
    def remove_enrollment(course_id, student_id):
        if unenroll_student(course_id, student_id, app.config["DATABASE"]):
            flash("Student removed from the course.", "success")
        else:
            flash("That student was not enrolled in this course.", "error")
        return redirect(url_for("course_detail", course_id=course_id))

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
