"""
Automated tests for the navigation fixes:
  1. the "Café staff sign in" footer link on parent pages
  2. the way back from the café sign-in page
  3. returning to the right page after editing the camper's information
  4. the 404 and 405 error pages

Run them from the project folder with:
    python -m unittest discover tests
"""

import os
import re
import shutil
import tempfile
import unittest

from app import create_app
from base import VALID_REGISTRATION, AppTestCase, checked_values
from models import DailyLunch, db

PASSCODE = "test-cafe-passcode"
MEALS = {"Day 2": "chicken-tenders", "Day 4": "pepperoni-pizza"}
STAFF_LINK = '<a class="footer-link" href="/cafe/login">Café staff sign in</a>'
CAFE_ORDERS_LINK = '<a class="footer-link" href="/cafe">Café daily orders</a>'


def meal_field(day):
    return "meal-" + day.lower().replace(" ", "-")


class NavigationTestCase(AppTestCase):
    # ----- Helpers -----

    def place_order(self, client=None):
        client = client or self.client
        client.post("/", data={"package": "4-day", "days": list(MEALS)})
        client.post("/meals", data={meal_field(day): meal for day, meal in MEALS.items()})
        html = client.get("/review").get_data(as_text=True)
        token = re.search(r'name="confirmation_token" value="([^"]*)"', html).group(1)
        client.post("/review", data={"confirmation_token": token})

    def html(self, path, client=None, status=200):
        response = (client or self.client).get(path)
        self.assertEqual(response.status_code, status, path)
        return response.get_data(as_text=True)

    def edit(self, next_value=None, **changes):
        """Save the edit form, the way the parent pressing Save Changes would."""
        data = {**VALID_REGISTRATION, **changes}
        if next_value is not None:
            data["next"] = next_value
        return self.client.post("/register", data=data)

    def unavailable_lunch_id(self):
        with self.app.app_context():
            lunch = db.session.scalars(db.select(DailyLunch).filter_by(camp_day="Day 4")).first()
            lunch.status = "unavailable"
            db.session.commit()
            return lunch.id

    # ----- 1. Footer link -----

    def test_staff_link_on_every_parent_page(self):
        self.assertIn(STAFF_LINK, self.html("/register"))
        self.register()
        self.client.post("/", data={"package": "4-day", "days": list(MEALS)})
        self.client.post("/meals", data={meal_field(day): meal for day, meal in MEALS.items()})
        for path in ("/", "/meals", "/review", "/register"):
            self.assertIn(STAFF_LINK, self.html(path), path)
        self.place_order()
        lunch_id = self.unavailable_lunch_id()
        for path in ("/order-confirmed", "/order-status", f"/order-status/lunches/{lunch_id}/change-meal"):
            self.assertIn(STAFF_LINK, self.html(path), path)

    def test_no_staff_link_on_cafe_pages(self):
        html = self.html("/cafe/login")
        self.assertNotIn("Café staff sign in", html)
        self.assertNotIn("footer-link", html)
        self.client.post("/cafe/login", data={"passcode": PASSCODE})
        html = self.html("/cafe")
        self.assertNotIn("Café staff sign in", html)
        self.assertNotIn("footer-link", html)

    def test_link_becomes_cafe_daily_orders_once_signed_in(self):
        self.register()
        self.client.post("/cafe/login", data={"passcode": PASSCODE})
        html = self.html("/")
        self.assertIn(CAFE_ORDERS_LINK, html)
        self.assertNotIn("Café staff sign in", html)
        # Signing out puts the sign-in link back.
        self.client.post("/cafe/logout")
        self.assertIn(STAFF_LINK, self.html("/"))

    # ----- 2. The way back from café sign-in -----

    def test_cafe_sign_in_has_a_way_back(self):
        html = " ".join(self.html("/cafe/login").split())
        self.assertIn('This page is for café staff. <a href="/">Return to lunch registration</a>.', html)
        # Wrong passcode: the way back is still there.
        html = " ".join(self.client.post("/cafe/login", data={"passcode": "wrong"}).get_data(as_text=True).split())
        self.assertIn('<a href="/">Return to lunch registration</a>', html)

    def test_way_back_when_cafe_access_is_not_set_up(self):
        temp_dir = tempfile.mkdtemp()
        locked = create_app({"TESTING": True, "SECRET_KEY": "x", "CAFE_PASSCODE": "",
                             "SQLALCHEMY_DATABASE_URI": "sqlite:///" + os.path.join(temp_dir, "t.db")})
        try:
            html = " ".join(locked.test_client().get("/cafe/login").get_data(as_text=True).split())
            self.assertIn("Café access isn't set up yet.", html)
            self.assertIn('<a href="/">Return to lunch registration</a>', html)
        finally:
            with locked.app_context():
                db.engine.dispose()
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_return_link_leads_into_the_parent_flow(self):
        # Not registered yet: the package page sends them to registration.
        response = self.client.get("/")
        self.assertTrue(response.headers["Location"].endswith("/register"))

    # ----- 3. Returning after editing the camper -----

    def test_each_page_edit_link_names_its_own_page(self):
        self.register()
        self.client.post("/", data={"package": "4-day", "days": list(MEALS)})
        self.client.post("/meals", data={meal_field(day): meal for day, meal in MEALS.items()})
        expected = {"/": "package", "/meals": "meals", "/review": "review"}
        for path, name in expected.items():
            self.assertIn(f'id="edit-camper-link" class="link-button" href="/register?next={name}"', self.html(path), path)
        self.place_order()
        lunch_id = self.unavailable_lunch_id()
        for path, name in (("/order-confirmed", "confirmation"), ("/order-status", "status"),
                           (f"/order-status/lunches/{lunch_id}/change-meal", "status")):
            self.assertIn(f'href="/register?next={name}"', self.html(path), path)

    def test_cancel_and_save_return_to_the_page_they_came_from(self):
        self.register()
        self.place_order()
        destinations = {
            "package": "/",
            "review": "/review",
            "confirmation": "/order-confirmed",
            "status": "/order-status",
            "meals": "/meals",
        }
        for name, path in destinations.items():
            html = self.html(f"/register?next={name}")
            self.assertIn(f'<input type="hidden" name="next" value="{name}">', html)
            self.assertIn(f'<a class="button button-secondary" href="{path}">Cancel</a>', html)
            response = self.edit(next_value=name)
            self.assertEqual(response.headers["Location"], path, name)

    def test_saving_shows_the_updated_message_on_the_return_page(self):
        self.register()
        self.place_order()
        self.edit(next_value="status", camper_first_name="Avery")
        html = self.html("/order-status")
        self.assertIn('<div class="alert alert-success" role="status">Camper and contact information updated.</div>', html)
        self.assertIn("<strong>Avery Smith</strong>", html)
        # The message is shown once, not again on the next page.
        self.assertNotIn("Camper and contact information updated.", self.html("/"))

    def test_edit_from_meal_page_comes_back_with_meals_kept(self):
        self.register()
        self.client.post("/", data={"package": "4-day", "days": ["Day 1", "Day 2"]})
        # meals.js sends this when "Edit camper & contact information" is clicked.
        response = self.client.post("/meals", data={"meal-day-1": "cheese-pizza", "action": "edit-camper"})
        self.assertTrue(response.headers["Location"].endswith("/register?next=meals"))
        self.assertTrue(self.edit(next_value="meals").headers["Location"].endswith("/meals"))
        self.assertEqual(checked_values(self.html("/meals"), "meal-day-1"), ["cheese-pizza"])

    def test_unsafe_return_values_are_ignored(self):
        self.register()
        for value in ("https://evil.example.com", "//evil.example.com", "/order-status", "status/../x",
                      "javascript:alert(1)", "STATUS", "", "cafe", "main.order_status"):
            html = self.html(f"/register?next={value}")
            self.assertNotIn('name="next"', html, value)
            self.assertIn('<a class="button button-secondary" href="/">Cancel</a>', html)
            response = self.edit(next_value=value)
            self.assertEqual(response.headers["Location"], "/", value)

    def test_no_return_value_keeps_the_old_behavior(self):
        self.register()
        self.assertIn('<a class="button button-secondary" href="/">Cancel</a>', self.html("/register"))
        self.assertEqual(self.edit().headers["Location"], "/")
        self.assertIn("Camper and contact information updated.", self.html("/"))

    def test_new_registration_ignores_the_return_value(self):
        response = self.client.post("/register", data={**VALID_REGISTRATION, "next": "status"})
        self.assertEqual(response.headers["Location"], "/")
        self.assertIn("Thanks! Ava Smith is registered.", self.html("/"))

    def test_invalid_edit_keeps_the_return_page(self):
        self.register()
        response = self.edit(next_value="review", guardian_email="not-an-email")
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('<input type="hidden" name="next" value="review">', html)
        self.assertIn('<a class="button button-secondary" href="/review">Cancel</a>', html)

    # ----- 4. Error pages -----

    def test_404_page_is_styled_and_offers_registration(self):
        response = self.client.get("/no-such-page")
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 404)
        self.assertIn("<h1>Summer Camp Lunch Registration</h1>", html)
        self.assertIn("Page not found", html)
        self.assertIn('<a class="button" href="/">Return to Lunch Registration</a>', html)
        self.assertIn(STAFF_LINK, html)

    def test_404_offers_order_status_once_an_order_exists(self):
        self.register()
        self.assertIn('href="/">Return to Lunch Registration</a>', self.html("/nope", status=404))
        self.place_order()
        self.assertIn('<a class="button" href="/order-status">View Order Status</a>', self.html("/nope", status=404))

    def test_another_campers_lunch_looks_like_a_missing_one(self):
        self.register()
        self.place_order()
        lunch_id = self.unavailable_lunch_id()
        other = self.app.test_client()
        self.register(client=other, camper_first_name="Ben", guardian_email="ben@example.com")
        theirs = self.html(f"/order-status/lunches/{lunch_id}/change-meal", client=other, status=404)
        missing = self.html("/order-status/lunches/99999/change-meal", client=other, status=404)
        self.assertEqual(theirs, missing)
        self.assertNotIn("Ava", theirs)
        self.assertNotIn("Day 4", theirs)

    def test_405_page_for_opening_sign_out_directly(self):
        response = self.client.get("/cafe/logout")
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 405)
        self.assertIn("This page can&#39;t be opened that way", html)
        # A café address, so no café staff link, and a café-style header.
        self.assertIn("<h1>Daily Lunch Orders</h1>", html)
        self.assertNotIn("footer-link", html)
        self.assertIn('<a class="button" href="/">Return to Lunch Registration</a>', html)

    def test_cafe_errors_offer_cafe_daily_orders_when_signed_in(self):
        self.client.post("/cafe/login", data={"passcode": PASSCODE})
        response = self.client.post("/cafe/lunches/99999/status", data={"status": "completed"})
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 404)
        self.assertIn('<a class="button" href="/cafe">Back to Café Daily Orders</a>', html)
        self.assertIn('<a class="button" href="/cafe">Back to Café Daily Orders</a>',
                      self.html("/cafe/lunches/1/status", status=405))

    def test_cafe_error_without_sign_in_does_not_offer_the_cafe(self):
        html = self.html("/cafe/lunches/1/status", status=405)
        self.assertNotIn('href="/cafe"', html)
        self.assertIn('href="/">Return to Lunch Registration</a>', html)


if __name__ == "__main__":
    unittest.main()
