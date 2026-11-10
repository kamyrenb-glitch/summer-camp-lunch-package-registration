"""
Automated tests for Issue #1: Register a Camper.

Run them from the project folder with:
    python -m unittest discover tests
"""

import json
import os
import re
import unittest
from unittest import mock

from app import create_app, get_database_url, get_secret_key
from base import VALID_REGISTRATION, AppTestCase, checked_values, form_message
from models import Camper, Guardian, db
from registration import normalize_phone


def field_error(html, name):
    """Return the error text shown for one field ("" if none)."""
    match = re.search(r'id="' + name + r'-error"[^>]*>(.*?)</p>', html, re.S)
    return match.group(1).strip()


def field_value(html, name):
    """Return the value attribute of one input."""
    tag = re.search(r'<input\s[^>]*id="' + name + r'"[^>]*>', html, re.S).group(0)
    return re.search(r'value="([^"]*)"', tag).group(1)


def field_tag(html, name):
    return re.search(r'<input\s[^>]*id="' + name + r'"[^>]*>', html, re.S).group(0)


class RegistrationTestCase(AppTestCase):
    # ----- Helpers -----

    def campers(self):
        with self.app.app_context():
            return [
                {
                    "id": camper.id,
                    "first_name": camper.first_name,
                    "last_name": camper.last_name,
                    "guardian_id": camper.guardian_id,
                    "guardian_name": camper.guardian.full_name,
                    "email": camper.guardian.email,
                    "phone": camper.guardian.phone,
                }
                for camper in db.session.scalars(db.select(Camper).order_by(Camper.id))
            ]

    def guardian_count(self):
        with self.app.app_context():
            return db.session.scalar(db.select(db.func.count()).select_from(Guardian))

    # ----- Getting to the pages -----

    def test_pages_redirect_to_registration_when_not_registered(self):
        for method, path in (("get", "/"), ("post", "/"), ("get", "/meals"), ("post", "/meals")):
            response = getattr(self.client, method)(path)
            self.assertEqual(response.status_code, 302, f"{method} {path}")
            self.assertTrue(response.headers["Location"].endswith("/register"), f"{method} {path}")

        html = self.client.get("/register").get_data(as_text=True)
        self.assertIn("Please register your camper before ordering lunches.", html)

    def test_registration_page_has_labeled_required_fields(self):
        html = self.client.get("/register").get_data(as_text=True)
        self.assertIn("Register your camper", html)
        for name, _ in VALID_REGISTRATION.items():
            self.assertIn(f'<label for="{name}">', html)
            tag = field_tag(html, name)
            self.assertIn("required", tag)
            self.assertIn(f'aria-describedby="', tag)
            self.assertIn(f"{name}-error", tag)
            self.assertNotIn("aria-invalid", tag)
        self.assertIn('type="email"', field_tag(html, "guardian_email"))
        self.assertIn('type="tel"', field_tag(html, "guardian_phone"))

    # ----- Successful registration -----

    def test_successful_registration_saves_to_database_and_redirects(self):
        response = self.register()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/"))

        campers = self.campers()
        self.assertEqual(len(campers), 1)
        self.assertEqual(campers[0]["first_name"], "Ava")
        self.assertEqual(campers[0]["last_name"], "Smith")
        self.assertEqual(campers[0]["guardian_name"], "Jordan Smith")
        self.assertEqual(campers[0]["email"], "jordan@example.com")
        self.assertEqual(campers[0]["phone"], "+14105550123")

        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("Thanks! Ava Smith is registered. Next, choose a lunch package.", html)
        self.assertIn("Ordering for", html)
        self.assertIn("<strong>Ava Smith</strong>", html)
        self.assertIn("Edit camper &amp; contact information", html)

    def test_registration_is_stored_in_the_database_not_just_the_session(self):
        self.register()
        database_uri = self.app.config["SQLALCHEMY_DATABASE_URI"]

        # A completely separate app connected to the same database file can read it.
        other_app = create_app({"TESTING": True, "SECRET_KEY": "x", "SQLALCHEMY_DATABASE_URI": database_uri})
        with other_app.app_context():
            camper = db.session.scalars(db.select(Camper)).one()
            self.assertEqual(camper.full_name, "Ava Smith")
            self.assertEqual(camper.guardian.email, "jordan@example.com")
            db.engine.dispose()

    def test_session_stores_only_the_camper_database_id(self):
        self.register()
        session = self.session_data()
        session.pop("_flashes", None)  # one-time messages, removed once shown
        camper_id = self.campers()[0]["id"]
        self.assertEqual(session, {"camper_id": camper_id})

        # No personal information anywhere in the session, even after ordering.
        self.client.get("/")
        self.client.post("/", data={"package": "4-day", "days": ["Day 1"]})
        self.client.post("/meals", data={"meal-day-1": "cheese-pizza"})
        stored = json.dumps(self.session_data())
        for private in ("Ava", "Smith", "Jordan", "jordan@example.com", "410", "555", "0123"):
            self.assertNotIn(private, stored)
        self.assertEqual(self.saved_order()["camper_id"], camper_id)

    # ----- Validation -----

    def test_missing_fields_show_field_errors_and_save_nothing(self):
        response = self.client.post("/register", data={key: "   " for key in VALID_REGISTRATION})
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(field_error(html, "camper_first_name"), "Enter the camper&#39;s first name.")
        self.assertEqual(field_error(html, "camper_last_name"), "Enter the camper&#39;s last name.")
        self.assertEqual(field_error(html, "guardian_name"), "Enter the parent or guardian&#39;s full name.")
        self.assertEqual(field_error(html, "guardian_email"), "Enter an email address.")
        self.assertEqual(field_error(html, "guardian_phone"), "Enter a phone number.")
        for name in VALID_REGISTRATION:
            self.assertIn('aria-invalid="true"', field_tag(html, name))
        self.assertEqual(form_message(html), "Please fix the 5 fields marked above.")
        self.assertEqual(self.campers(), [])
        self.assertIsNone(self.camper_id())

    def test_one_missing_field(self):
        response = self.register(camper_last_name="")
        html = response.get_data(as_text=True)
        self.assertEqual(form_message(html), "Please fix the 1 field marked above.")
        self.assertEqual(field_error(html, "camper_first_name"), "")
        self.assertNotIn("aria-invalid", field_tag(html, "camper_first_name"))
        self.assertIn('aria-invalid="true"', field_tag(html, "camper_last_name"))

    def test_invalid_email_addresses_are_rejected(self):
        for email in ("jordan", "jordan@", "@example.com", "jordan@example", "jor dan@example.com",
                      "jordan@@example.com", "jordan@example.c"):
            response = self.register(guardian_email=email)
            html = response.get_data(as_text=True)
            self.assertEqual(response.status_code, 200, email)
            self.assertEqual(field_error(html, "guardian_email"),
                             "Enter a valid email address, like name@example.com.", email)
        self.assertEqual(self.campers(), [])

    def test_invalid_phone_numbers_are_rejected(self):
        for phone in ("555-0123", "410-555-012", "410-555-01234", "(110) 555-0123", "(410) 155-0123",
                      "410-CALL-NOW", "+44 20 7946 0958", "2-410-555-0123", "410/555/0123"):
            response = self.register(guardian_phone=phone)
            html = response.get_data(as_text=True)
            self.assertEqual(response.status_code, 200, phone)
            self.assertEqual(field_error(html, "guardian_phone"),
                             "Enter a 10-digit U.S. phone number, like (410) 555-0123.", phone)
        self.assertEqual(self.campers(), [])

    def test_common_phone_formats_are_saved_the_same_way(self):
        for phone in ("(410) 555-0123", "410-555-0123", "410.555.0123", "410 555 0123",
                      "4105550123", "+1 410 555 0123", "1-410-555-0123", "+1 (410) 555-0123"):
            self.assertEqual(normalize_phone(phone), "+14105550123", phone)

    def test_too_long_values_are_rejected(self):
        response = self.register(camper_first_name="A" * 51, guardian_name="B" * 101)
        html = response.get_data(as_text=True)
        self.assertEqual(field_error(html, "camper_first_name"), "Camper first name must be 50 characters or fewer.")
        self.assertEqual(field_error(html, "guardian_name"),
                         "Parent or guardian full name must be 100 characters or fewer.")
        self.assertEqual(self.campers(), [])

        # Exactly the limit is fine.
        self.assertEqual(self.register(camper_first_name="A" * 50).status_code, 302)

    def test_valid_entries_are_kept_after_an_invalid_submission(self):
        response = self.register(guardian_email="not-an-email", camper_first_name="  Ava  ")
        html = response.get_data(as_text=True)
        self.assertEqual(field_value(html, "camper_first_name"), "Ava")
        self.assertEqual(field_value(html, "camper_last_name"), "Smith")
        self.assertEqual(field_value(html, "guardian_name"), "Jordan Smith")
        self.assertEqual(field_value(html, "guardian_phone"), "(410) 555-0123")
        # The invalid entry is kept too, so the parent can fix the typo.
        self.assertEqual(field_value(html, "guardian_email"), "not-an-email")

    def test_whitespace_is_trimmed_and_email_lowercased(self):
        self.register(
            camper_first_name="   Ava ",
            camper_last_name="\tSmith  ",
            guardian_name="  Jordan Smith  ",
            guardian_email="  Jordan@Example.COM ",
            guardian_phone="  410.555.0123  ",
        )
        camper = self.campers()[0]
        self.assertEqual(camper["first_name"], "Ava")
        self.assertEqual(camper["last_name"], "Smith")
        self.assertEqual(camper["guardian_name"], "Jordan Smith")
        self.assertEqual(camper["email"], "jordan@example.com")
        self.assertEqual(camper["phone"], "+14105550123")

    # ----- Editing -----

    def test_edit_page_is_filled_in_from_the_database(self):
        self.register()
        html = self.client.get("/register").get_data(as_text=True)
        self.assertIn("Edit camper and contact information", html)
        self.assertIn("Save Changes", html)
        self.assertEqual(field_value(html, "camper_first_name"), "Ava")
        self.assertEqual(field_value(html, "guardian_email"), "jordan@example.com")
        self.assertEqual(field_value(html, "guardian_phone"), "(410) 555-0123")

    def test_editing_updates_the_same_records_without_duplicates(self):
        self.register()
        before = self.campers()[0]

        response = self.register(camper_first_name="Avery", guardian_email="new@example.com",
                                 guardian_phone="443-555-0199")
        self.assertEqual(response.status_code, 302)

        campers = self.campers()
        self.assertEqual(len(campers), 1)
        self.assertEqual(self.guardian_count(), 1)
        self.assertEqual(campers[0]["id"], before["id"])
        self.assertEqual(campers[0]["guardian_id"], before["guardian_id"])
        self.assertEqual(campers[0]["first_name"], "Avery")
        self.assertEqual(campers[0]["email"], "new@example.com")
        self.assertEqual(campers[0]["phone"], "+14435550199")
        self.assertEqual(self.camper_id(), before["id"])

        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("Camper and contact information updated.", html)
        self.assertIn("<strong>Avery Smith</strong>", html)

    def test_invalid_edit_changes_nothing(self):
        self.register()
        self.register(camper_first_name="", guardian_email="bad")
        self.assertEqual(self.campers()[0]["first_name"], "Ava")
        self.assertEqual(self.campers()[0]["email"], "jordan@example.com")

    def test_editing_keeps_package_days_and_meals(self):
        self.register()
        self.client.post("/", data={"package": "6-day", "days": ["Day 2", "Day 4"]})
        self.client.post("/meals", data={"meal-day-2": "pepperoni-pizza", "meal-day-4": "cheese-pizza"})
        order_before = self.saved_order()

        self.register(guardian_name="Jordan Lee")
        self.assertEqual(self.saved_order(), order_before)

        html = self.client.get("/").get_data(as_text=True)
        self.assertEqual(checked_values(html, "package"), ["6-day"])
        self.assertEqual(checked_values(html, "days"), ["Day 2", "Day 4"])
        html = self.client.get("/meals").get_data(as_text=True)
        self.assertEqual(checked_values(html, "meal-day-2"), ["pepperoni-pizza"])
        self.assertEqual(checked_values(html, "meal-day-4"), ["cheese-pizza"])

    def test_edit_link_on_meal_page_keeps_unsaved_meals(self):
        self.register()
        self.client.post("/", data={"package": "4-day", "days": ["Day 1", "Day 2"]})
        # meals.js sends this when "Edit camper & contact information" is clicked.
        response = self.client.post("/meals", data={"meal-day-1": "cheese-pizza", "action": "edit-camper"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/register"))
        self.assertEqual(self.saved_order()["meals"], {"Day 1": {"meal_id": "cheese-pizza", "price_cents": 1100}})

    # ----- Not trusting the browser -----

    def test_ids_sent_by_the_browser_cannot_edit_someone_else(self):
        first_client = self.client
        second_client = self.app.test_client()
        self.register(client=first_client)
        self.register(client=second_client, camper_first_name="Ben", guardian_email="ben@example.com")
        first_id = self.camper_id(first_client)
        second_id = self.camper_id(second_client)
        self.assertNotEqual(first_id, second_id)

        # The second browser tries to point the form at the first camper.
        self.register(client=second_client, camper_first_name="Hacked",
                      camper_id=str(first_id), id=str(first_id), guardian_id=str(first_id))

        campers = {camper["id"]: camper for camper in self.campers()}
        self.assertEqual(campers[first_id]["first_name"], "Ava")
        self.assertEqual(campers[second_id]["first_name"], "Hacked")
        self.assertEqual(len(campers), 2)

    def test_session_id_for_missing_camper_requires_registration_again(self):
        with self.client.session_transaction() as session:
            session["camper_id"] = 9999
            session["order"] = {"camper_id": 9999, "package_id": "4-day", "days": ["Day 1"], "meals": {}}

        response = self.client.get("/")
        self.assertTrue(response.headers["Location"].endswith("/register"))
        self.assertNotIn("order", self.session_data())
        self.assertNotIn("camper_id", self.session_data())

    def test_session_id_that_is_not_a_number_is_ignored(self):
        self.register()
        real_id = self.camper_id()
        with self.client.session_transaction() as session:
            session["camper_id"] = str(real_id)
        response = self.client.get("/")
        self.assertTrue(response.headers["Location"].endswith("/register"))

    # ----- The complete flow -----

    def test_complete_flow_from_registration_to_meals(self):
        # 1. Start at the package page -> sent to registration.
        self.assertTrue(self.client.get("/").headers["Location"].endswith("/register"))

        # 2. Register -> package page.
        self.assertTrue(self.register().headers["Location"].endswith("/"))
        camper_id = self.camper_id()
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("<strong>Ava Smith</strong>", html)

        # 3. Choose a package and days -> meal page.
        response = self.client.post("/", data={"package": "6-day", "days": ["Day 3", "Day 6", "Day 9"]})
        self.assertTrue(response.headers["Location"].endswith("/meals"))
        html = self.client.get("/meals").get_data(as_text=True)
        self.assertIn("<strong>Ava Smith</strong>", html)
        self.assertIn('id="edit-camper-link"', html)

        # 4. Save meals.
        response = self.client.post("/meals", data={
            "meal-day-3": "chicken-tenders", "meal-day-6": "cheese-pizza", "meal-day-9": "pepperoni-pizza",
        })
        self.assertTrue(response.headers["Location"].endswith("/meals"))

        self.assertEqual(self.saved_order(), {
            "status": "in_progress",
            "camper_id": camper_id,
            "package_id": "6-day",
            "days": ["Day 3", "Day 6", "Day 9"],
            "meals": {
                "Day 3": {"meal_id": "chicken-tenders", "price_cents": 1100},
                "Day 6": {"meal_id": "cheese-pizza", "price_cents": 1100},
                "Day 9": {"meal_id": "pepperoni-pizza", "price_cents": 1200},
            },
        })


class DatabaseSetupTestCase(AppTestCase):
    def test_init_db_is_safe_to_run_again(self):
        self.register()
        runner = self.app.test_cli_runner()
        for _ in range(2):
            result = runner.invoke(args=["init-db"])
            self.assertIn("Database tables are ready.", result.output)
        # The camper registered before is still there.
        with self.app.app_context():
            self.assertEqual(db.session.scalar(db.select(db.func.count()).select_from(Camper)), 1)


class SettingsTestCase(unittest.TestCase):
    def test_sqlite_is_used_when_database_url_is_missing(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            url = get_database_url(os.path.join("some", "instance"))
        self.assertTrue(url.startswith("sqlite:///"))
        self.assertTrue(url.endswith("lunch_dev.db"))

    def test_database_url_is_used_with_the_psycopg2_driver(self):
        url = "postgresql://user:password@db.example.com:5432/postgres?sslmode=require"
        with mock.patch.dict(os.environ, {"DATABASE_URL": url}, clear=True):
            self.assertEqual(
                get_database_url("instance"),
                "postgresql+psycopg2://user:password@db.example.com:5432/postgres?sslmode=require",
            )

    def test_old_postgres_prefix_is_fixed(self):
        with mock.patch.dict(os.environ, {"DATABASE_URL": "postgres://u:p@host/db"}, clear=True):
            self.assertEqual(get_database_url("instance"), "postgresql+psycopg2://u:p@host/db")

    def test_database_url_connects_with_installed_driver(self):
        # Builds the database engine without connecting, which fails if the
        # needed driver package isn't installed.
        from sqlalchemy import create_engine
        with mock.patch.dict(os.environ, {"DATABASE_URL": "postgresql://u:p@localhost:5432/db"}, clear=True):
            engine = create_engine(get_database_url("instance"))
        self.assertEqual(engine.dialect.driver, "psycopg2")

    def test_secret_key_comes_from_environment(self):
        with mock.patch.dict(os.environ, {"SECRET_KEY": "from-env"}, clear=True):
            self.assertEqual(get_secret_key("unused"), "from-env")

    def test_secret_key_is_required_with_a_deployed_database(self):
        with mock.patch.dict(os.environ, {"DATABASE_URL": "postgresql://u:p@host/db"}, clear=True):
            with self.assertRaises(RuntimeError):
                get_secret_key("unused")


if __name__ == "__main__":
    unittest.main()
