"""
Shared setup for the tests.

Every test gets a brand-new SQLite database in a temporary folder that is
deleted afterwards, so tests never touch the development database
(instance/lunch_dev.db) or the deployed Supabase database.
"""

import os
import re
import shutil
import tempfile
import unittest

from app import create_app
from models import db

VALID_REGISTRATION = {
    "camper_first_name": "Ava",
    "camper_last_name": "Smith",
    "guardian_name": "Jordan Smith",
    "guardian_email": "jordan@example.com",
    "guardian_phone": "(410) 555-0123",
}


def checked_values(html, name):
    """Return the values of the checked inputs with this name in the HTML."""
    pattern = r'<input\s[^>]*name="' + re.escape(name) + r'"[^>]*>'
    values = []
    for tag in re.findall(pattern, html):
        if re.search(r"\schecked\b", tag):
            values.append(re.search(r'value="([^"]*)"', tag).group(1))
    return values


def form_message(html):
    """Return the text inside the result banner near the button."""
    match = re.search(r'id="form-message".*?>(.*?)</div>', html, re.S)
    return match.group(1).strip()


class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        database_path = os.path.join(self.temp_dir, "test.db")
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-only-key",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///" + database_path,
        })
        # Safety check: stop right away if this isn't the temporary database.
        uri = self.app.config["SQLALCHEMY_DATABASE_URI"]
        if not (uri.startswith("sqlite:///") and self.temp_dir in uri):
            raise RuntimeError(f"Tests must use a temporary database, not {uri}")

        with self.app.app_context():
            db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()  # closes the file so Windows can delete it
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # ----- Helpers -----

    def register(self, client=None, **changes):
        """Submit the registration form. Pass field=value to change a field."""
        data = {**VALID_REGISTRATION, **changes}
        return (client or self.client).post("/register", data=data)

    def session_data(self, client=None):
        with (client or self.client).session_transaction() as session:
            return dict(session)

    def saved_order(self, client=None):
        return self.session_data(client).get("order")

    def camper_id(self, client=None):
        return self.session_data(client).get("camper_id")

    def set_order(self, order):
        """Put an order straight into the session (to test bad or changed data)."""
        with self.client.session_transaction() as session:
            session["order"] = order
