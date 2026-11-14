"""
Automated tests for Issue #6: Manage Daily Orders.

Covers the café attendant pages (signing in, viewing a camp day, changing
statuses) and the parent's "Choose a Different Meal" page for lunches the
café marks unavailable.

Run them from the project folder with:
    python -m unittest discover tests
"""

import html as html_module
import os
import re
import shutil
import tempfile
import unittest

from sqlalchemy import inspect

from app import change_lunch_meal, create_app, find_meal
from base import AppTestCase
from models import DailyLunch, LunchHistory, Order, db

PASSCODE = "test-cafe-passcode"
AVA_MEALS = {"Day 2": "chicken-tenders", "Day 4": "pepperoni-pizza", "Day 6": "cheese-pizza"}


def meal_field(day):
    return "meal-" + day.lower().replace(" ", "-")


def plain(html):
    """The page's text with tags removed and spacing tidied, for easy searching."""
    return " ".join(html_module.unescape(re.sub(r"<[^>]+>", " ", html)).split())


class CafeTestCase(AppTestCase):
    def setUp(self):
        super().setUp()
        # Ava's parent places an order for Day 2, Day 4, and Day 6.
        self.register()
        self.ava_order = self.place_order(self.client, AVA_MEALS)
        # The café uses a separate browser.
        self.cafe = self.app.test_client()

    # ----- Helpers -----

    def place_order(self, client, meals, package="6-day"):
        client.post("/", data={"package": package, "days": list(meals)})
        client.post("/meals", data={meal_field(day): meal for day, meal in meals.items()})
        html = client.get("/review").get_data(as_text=True)
        token = re.search(r'name="confirmation_token" value="([^"]*)"', html).group(1)
        client.post("/review", data={"confirmation_token": token})
        with client.session_transaction() as session:
            return session["last_order_id"]

    def sign_in(self, client=None):
        return (client or self.cafe).post("/cafe/login", data={"passcode": PASSCODE})

    def lunch(self, day, order_id=None):
        """Read a lunch fresh from the database."""
        with self.app.app_context():
            query = db.select(DailyLunch).filter_by(camp_day=day, order_id=order_id or self.ava_order)
            lunch = db.session.scalars(query).one()
            return {
                "id": lunch.id, "status": lunch.status, "meal_id": lunch.meal_id,
                "price_cents": lunch.price_cents,
                "history": [(h.changed_by, h.from_status, h.to_status, h.from_meal_id, h.to_meal_id, h.note)
                            for h in lunch.history],
            }

    def order_total(self, order_id=None):
        with self.app.app_context():
            return db.session.get(Order, order_id or self.ava_order).total_cents

    def set_status(self, day, status):
        with self.app.app_context():
            lunch = db.session.scalars(db.select(DailyLunch).filter_by(camp_day=day, order_id=self.ava_order)).one()
            lunch.status = status
            db.session.commit()

    def update(self, day, status, reason=None, expected=None, extra=None):
        """Press a status button on the café page for one of Ava's lunches."""
        lunch = self.lunch(day)
        data = {"status": status, "expected_status": expected if expected is not None else lunch["status"],
                **(extra or {})}
        if reason is not None:
            data["reason"] = reason
        return self.cafe.post(f"/cafe/lunches/{lunch['id']}/status", data=data)

    def cafe_day(self, day="Day 4"):
        response = self.cafe.get(f"/cafe?day={day}")
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def mark_unavailable(self, day="Day 4", reason="Out of pepperoni today"):
        self.sign_in()
        response = self.update(day, "unavailable", reason=reason)
        self.assertEqual(response.status_code, 302)
        return self.lunch(day)

    # ----- Café sign-in -----

    def test_cafe_pages_need_the_passcode(self):
        self.assertTrue(self.cafe.get("/cafe").headers["Location"].endswith("/cafe/login"))
        lunch = self.lunch("Day 2")
        response = self.cafe.post(f"/cafe/lunches/{lunch['id']}/status",
                                  data={"status": "completed", "expected_status": "ordered"})
        self.assertTrue(response.headers["Location"].endswith("/cafe/login"))
        self.assertEqual(self.lunch("Day 2")["status"], "ordered")

    def test_wrong_passcode_is_refused(self):
        response = self.cafe.post("/cafe/login", data={"passcode": "guess"})
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("That passcode isn&#39;t right. Please try again.", html)
        self.assertIn('aria-invalid="true"', html)
        self.assertTrue(self.cafe.get("/cafe").headers["Location"].endswith("/cafe/login"))

    def test_right_passcode_opens_the_cafe_page_and_sign_out_closes_it(self):
        response = self.sign_in()
        self.assertTrue(response.headers["Location"].endswith("/cafe"))
        self.assertEqual(self.cafe.get("/cafe").status_code, 200)
        self.cafe.post("/cafe/logout")
        self.assertTrue(self.cafe.get("/cafe").headers["Location"].endswith("/cafe/login"))

    def test_a_registered_parent_cannot_open_the_cafe_page(self):
        self.assertTrue(self.client.get("/cafe").headers["Location"].endswith("/cafe/login"))

    def test_cafe_is_locked_when_no_passcode_is_set(self):
        temp_dir = tempfile.mkdtemp()
        try:
            locked = create_app({"TESTING": True, "SECRET_KEY": "x", "CAFE_PASSCODE": "",
                                 "SQLALCHEMY_DATABASE_URI": "sqlite:///" + os.path.join(temp_dir, "t.db")})
            client = locked.test_client()
            html = client.get("/cafe/login").get_data(as_text=True)
            self.assertIn("Café access isn't set up yet.", plain(html))
            client.post("/cafe/login", data={"passcode": ""})
            # Even a session that says "signed in" can't get in without a passcode set.
            with client.session_transaction() as session:
                session["cafe_attendant"] = True
            self.assertTrue(client.get("/cafe").headers["Location"].endswith("/cafe/login"))
        finally:
            with locked.app_context():
                db.engine.dispose()
            shutil.rmtree(temp_dir, ignore_errors=True)

    # ----- Viewing a camp day -----

    def test_day_page_lists_camper_meal_order_and_status(self):
        # A second camper also orders Day 4.
        ben = self.app.test_client()
        self.register(client=ben, camper_first_name="Ben", camper_last_name="Adams", guardian_email="ben@example.com")
        ben_order = self.place_order(ben, {"Day 4": "cheese-pizza"}, package="4-day")

        self.sign_in()
        html = self.cafe_day("Day 4")
        text = plain(html)
        # Sorted by last name: Adams before Smith.
        self.assertLess(text.index("Ben Adams"), text.index("Ava Smith"))
        self.assertIn(f"Ben Adams Ordered Cheese Pizza + Fries + Drink Order {ben_order}", text)
        self.assertIn(f"Ava Smith Ordered Pepperoni Pizza + Fries + Drink Order {self.ava_order}", text)
        self.assertIn("Day 4: 2 lunches", text)
        # Only Day 4's lunches are on the Day 4 page.
        self.assertNotIn("Chicken Tenders", text.split("Meals to make")[1])
        # Day buttons show how many lunches each day has.
        self.assertIn('aria-current="page"', html)
        self.assertIn("Day 2 1 lunch", text)
        self.assertIn("Day 4 2 lunches", text)
        self.assertIn("Day 1 0 lunches", text)
        # What to make today.
        self.assertIn("1 × Cheese Pizza + Fries + Drink", text)
        self.assertIn("1 × Pepperoni Pizza + Fries + Drink", text)

    def test_unknown_day_shows_day_one(self):
        self.sign_in()
        html = self.cafe.get("/cafe?day=Day%2099").get_data(as_text=True)
        self.assertIn("Day 1: 0 lunches", plain(html))
        self.assertIn("No lunches are ordered for Day 1.", html)

    def test_day_page_is_never_cached(self):
        self.sign_in()
        self.assertEqual(self.cafe.get("/cafe").headers["Cache-Control"], "no-store")

    def test_buttons_offered_for_each_status(self):
        self.sign_in()
        html = self.cafe_day("Day 2")
        self.assertIn(">Start Preparing</button>", html)
        self.assertIn(">Mark Completed</button>", html)
        self.assertIn("<summary>Mark Unavailable…</summary>", html)
        self.assertNotIn(">Back to Ordered</button>", html)

        self.update("Day 2", "preparing")
        html = self.cafe_day("Day 2")
        self.assertIn(">Mark Completed</button>", html)
        self.assertIn(">Back to Ordered</button>", html)
        self.assertNotIn(">Start Preparing</button>", html)

        self.update("Day 2", "completed")
        html = self.cafe_day("Day 2")
        self.assertIn(">Back to Preparing</button>", html)
        self.assertNotIn(">Mark Completed</button>", html)
        self.assertNotIn("Mark Unavailable", html)

    # ----- Changing statuses -----

    def test_ordered_to_preparing_to_completed_is_saved(self):
        self.sign_in()
        response = self.update("Day 2", "preparing")
        self.assertTrue(response.headers["Location"].endswith(f"/cafe?day=Day+2#lunch-{self.lunch('Day 2')['id']}"))
        self.assertEqual(self.lunch("Day 2")["status"], "preparing")
        self.update("Day 2", "completed")
        lunch = self.lunch("Day 2")
        self.assertEqual(lunch["status"], "completed")
        self.assertEqual(lunch["history"], [
            ("cafe", "ordered", "preparing", "chicken-tenders", "chicken-tenders", None),
            ("cafe", "preparing", "completed", "chicken-tenders", "chicken-tenders", None),
        ])
        html = self.cafe_day("Day 2")
        self.assertIn("Updated: Ava Smith&#39;s Day 2 lunch is now Completed.", html)

    def test_ordered_straight_to_completed(self):
        self.sign_in()
        self.update("Day 6", "completed")
        self.assertEqual(self.lunch("Day 6")["status"], "completed")

    def test_unavailable_needs_a_reason(self):
        self.sign_in()
        for reason in (None, "", "    "):
            response = self.update("Day 4", "unavailable", reason=reason)
            html = response.get_data(as_text=True)
            self.assertEqual(response.status_code, 200, repr(reason))
            self.assertIn("Please explain why this lunch is unavailable. The parent will see this note.", html)
            self.assertIn("<details class=\"unavailable-form\" open>", html)
            self.assertEqual(self.lunch("Day 4")["status"], "ordered")
        self.assertEqual(self.lunch("Day 4")["history"], [])

    def test_unavailable_reason_has_a_length_limit(self):
        self.sign_in()
        response = self.update("Day 4", "unavailable", reason="x" * 301)
        self.assertIn("Please keep the note to 300 characters or fewer.", response.get_data(as_text=True))
        self.assertEqual(self.lunch("Day 4")["status"], "ordered")
        self.update("Day 4", "unavailable", reason="x" * 300)
        self.assertEqual(self.lunch("Day 4")["status"], "unavailable")

    def test_unavailable_with_reason_is_saved_with_the_note(self):
        lunch = self.mark_unavailable(reason="  Out of pepperoni today  ")
        self.assertEqual(lunch["status"], "unavailable")
        self.assertEqual(lunch["history"], [
            ("cafe", "ordered", "unavailable", "pepperoni-pizza", "pepperoni-pizza", "Out of pepperoni today"),
        ])
        text = plain(self.cafe_day("Day 4"))
        self.assertIn("Pepperoni Pizza + Fries + Drink marked unavailable: “Out of pepperoni today”", text)
        # Nothing is left to make for Day 4.
        self.assertNotIn("Meals to make", text)

    def test_reason_is_not_kept_for_other_statuses(self):
        self.sign_in()
        self.update("Day 2", "completed", reason="tasty")
        self.assertIsNone(self.lunch("Day 2")["history"][0][5])

    def test_undo_mistakes(self):
        self.sign_in()
        self.update("Day 2", "completed")
        self.update("Day 2", "preparing")
        self.assertEqual(self.lunch("Day 2")["status"], "preparing")
        self.update("Day 2", "ordered")
        self.assertEqual(self.lunch("Day 2")["status"], "ordered")
        self.update("Day 4", "unavailable", reason="Oven broke")
        self.update("Day 4", "ordered")
        self.assertEqual(self.lunch("Day 4")["status"], "ordered")

    def test_changes_that_are_not_allowed(self):
        self.sign_in()
        for status in ("eaten", "", "ORDERED", "ordered"):
            response = self.update("Day 2", status)
            self.assertTrue(response.headers["Location"].endswith(f"#lunch-{self.lunch('Day 2')['id']}"))
            self.assertEqual(self.lunch("Day 2")["status"], "ordered", status)
        self.update("Day 2", "completed")
        self.update("Day 2", "unavailable", reason="too late")  # completed can't become unavailable
        self.assertEqual(self.lunch("Day 2")["status"], "completed")
        self.assertIn("Not changed: a lunch that is Completed can&#39;t be changed that way.", self.cafe_day("Day 2"))
        self.assertEqual(len(self.lunch("Day 2")["history"]), 1)

    def test_out_of_date_page_does_not_overwrite_a_newer_status(self):
        self.sign_in()
        # Another attendant marks it completed after this page was drawn.
        self.update("Day 2", "completed")
        self.update("Day 2", "preparing", expected="ordered")
        self.assertEqual(self.lunch("Day 2")["status"], "completed")
        self.assertIn("Not changed: this lunch was already updated to Completed.", self.cafe_day("Day 2"))

    def test_missing_lunch_is_not_found(self):
        self.sign_in()
        response = self.cafe.post("/cafe/lunches/99999/status", data={"status": "completed", "expected_status": "ordered"})
        self.assertEqual(response.status_code, 404)

    def test_browser_cannot_change_meal_price_day_or_camper(self):
        self.sign_in()
        response = self.update("Day 2", "completed", extra={
            "meal_id": "pepperoni-pizza", "price_cents": "1", "day": "Day 9", "camper_id": "999", "camp_day": "Day 9",
        })
        # The redirect goes to the lunch's own day, not the one sent.
        self.assertIn("day=Day+2", response.headers["Location"])
        lunch = self.lunch("Day 2")
        self.assertEqual((lunch["status"], lunch["meal_id"], lunch["price_cents"]), ("completed", "chicken-tenders", 1100))

    def test_old_status_names_still_work_for_the_cafe(self):
        self.set_status("Day 2", "cooking")
        self.sign_in()
        html = self.cafe_day("Day 2")
        self.assertIn(">Preparing</span>", html)
        self.assertIn(">Mark Completed</button>", html)
        self.update("Day 2", "completed", expected="cooking")
        self.assertEqual(self.lunch("Day 2")["status"], "completed")
        self.assertEqual(self.lunch("Day 2")["history"][0][1], "preparing")

    def test_parent_sees_cafe_updates_after_refresh(self):
        self.sign_in()
        self.update("Day 2", "completed")
        self.update("Day 6", "preparing")
        text = plain(self.client.get("/order-status").get_data(as_text=True))
        self.assertIn("Day 2 Chicken Tenders + Fries + Drink Completed", text)
        self.assertIn("Day 6 Cheese Pizza + Fries + Drink Preparing", text)

    # ----- The parent sees the note and picks a different meal -----

    def test_parent_sees_the_note_and_a_change_button_only_for_unavailable_lunches(self):
        lunch = self.mark_unavailable()
        html = self.client.get("/order-status").get_data(as_text=True)
        text = plain(html)
        self.assertIn("Pepperoni Pizza + Fries + Drink was unavailable. Café note: “Out of pepperoni today”", text)
        self.assertEqual(html.count("Choose a Different Meal</a>"), 1)
        self.assertIn(f'href="/order-status/lunches/{lunch["id"]}/change-meal"', html)
        self.assertIn('aria-label="Choose a different meal for Day 4"', html)

    def test_unavailable_lunch_is_shown_as_one_unit(self):
        self.mark_unavailable(day="Day 4", reason="Out of pepperoni today")
        self.update("Day 6", "unavailable", reason="Pizza oven is down")
        html = self.client.get("/order-status").get_data(as_text=True)
        # Each lunch is its own row group, so a lunch and its note stay together.
        self.assertEqual(html.count('<tbody class="lunch-group">'), 3)
        groups = re.findall(r'<tbody class="lunch-group">(.*?)</tbody>', html, re.S)
        day4 = next(group for group in groups if ">Day 4<" in group)
        self.assertIn('<div class="lunch-callout lunch-callout-unavailable">', day4)
        self.assertIn("Café note: “Out of pepperoni today”", day4)
        self.assertIn('class="button button-secondary change-meal-button"', day4)
        self.assertNotIn("Pizza oven is down", day4)  # Day 6's note stays with Day 6
        # The old full-width pink row is gone.
        self.assertNotIn("lunch-details-unavailable", html)
        # The replacement page's cards share the row evenly.
        lunch = self.lunch("Day 4")
        page = self.client.get(f"/order-status/lunches/{lunch['id']}/change-meal").get_data(as_text=True)
        self.assertIn('class="meal-options meal-options-fill"', page)

    FALLBACK = "This meal is unavailable. Choose a different meal for this day."

    def day_group(self, html, day):
        groups = re.findall(r'<tbody class="lunch-group">(.*?)</tbody>', html, re.S)
        return next(group for group in groups if f">{day}<" in group)

    def test_fallback_text_when_the_cafe_left_no_note(self):
        # Marked unavailable outside the café page, so there's no note.
        self.set_status("Day 4", "unavailable")
        html = self.client.get("/order-status").get_data(as_text=True)
        day4 = self.day_group(html, "Day 4")
        self.assertIn('<div class="lunch-callout lunch-callout-unavailable">', day4)
        self.assertIn(f'<p class="callout-fallback">{self.FALLBACK}</p>', day4)
        self.assertIn("Choose a Different Meal</a>", day4)
        self.assertNotIn('class="cafe-note"', day4)
        self.assertNotIn('class="lunch-history"', day4)  # no empty list
        # The change page still works without a note.
        page = self.client.get(f"/order-status/lunches/{self.lunch('Day 4')['id']}/change-meal")
        self.assertEqual(page.status_code, 200)
        self.assertNotIn("cafe-note-box", page.get_data(as_text=True))

    def test_fallback_for_the_old_status_name(self):
        self.set_status("Day 6", "cannot_complete")
        html = self.client.get("/order-status").get_data(as_text=True)
        self.assertIn(self.FALLBACK, self.day_group(html, "Day 6"))

    def test_real_note_is_used_instead_of_the_fallback(self):
        self.mark_unavailable(day="Day 4", reason="Out of pepperoni today")
        html = self.client.get("/order-status").get_data(as_text=True)
        day4 = self.day_group(html, "Day 4")
        self.assertIn("Café note: “Out of pepperoni today”", day4)
        self.assertNotIn(self.FALLBACK, html)

    def test_old_note_is_not_reused_for_a_newer_unavailable(self):
        # Unavailable with a note, then swapped, then unavailable again without a note.
        lunch = self.mark_unavailable(day="Day 4", reason="Out of pepperoni today")
        self.client.post(f"/order-status/lunches/{lunch['id']}/change-meal", data={"meal": "cheese-pizza"})
        self.set_status("Day 4", "unavailable")
        html = self.client.get("/order-status").get_data(as_text=True)
        day4 = self.day_group(html, "Day 4")
        # The old note stays as history, and the fallback explains the new problem.
        self.assertIn("Pepperoni Pizza + Fries + Drink was unavailable. "
                      "<span class=\"cafe-note\">Café note: “Out of pepperoni today”</span>", day4)
        self.assertIn(self.FALLBACK, day4)
        page = self.client.get(f"/order-status/lunches/{lunch['id']}/change-meal").get_data(as_text=True)
        self.assertNotIn("Out of pepperoni today", page)

    def test_cafe_notes_are_escaped(self):
        self.mark_unavailable(reason="<script>alert('x')</script>")
        html = self.client.get("/order-status").get_data(as_text=True)
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;", html)

    def test_change_page_offers_the_other_meals(self):
        lunch = self.mark_unavailable()
        html = self.client.get(f"/order-status/lunches/{lunch['id']}/change-meal").get_data(as_text=True)
        text = plain(html)
        self.assertIn("Choose a different meal for Day 4", text)
        self.assertIn("Café note: “Out of pepperoni today”", text)
        self.assertNotIn('value="pepperoni-pizza"', html)  # the unavailable meal isn't offered again
        self.assertIn('value="cheese-pizza"', html)
        self.assertIn('value="chicken-tenders"', html)
        self.assertIn("$11 (−$1)", text)
        self.assertIn("Your order total is $34.", text)

    def test_choosing_a_cheaper_meal_updates_the_lunch_and_total(self):
        lunch = self.mark_unavailable()
        self.assertEqual(self.order_total(), 3400)
        response = self.client.post(f"/order-status/lunches/{lunch['id']}/change-meal",
                                    data={"meal": "cheese-pizza", "price_cents": "1", "status": "completed"})
        self.assertTrue(response.headers["Location"].endswith("/order-status"))

        after = self.lunch("Day 4")
        self.assertEqual((after["status"], after["meal_id"], after["price_cents"]), ("ordered", "cheese-pizza", 1100))
        self.assertEqual(self.order_total(), 3300)
        # The café's note is kept, and the swap is recorded after it.
        self.assertEqual(after["history"], [
            ("cafe", "ordered", "unavailable", "pepperoni-pizza", "pepperoni-pizza", "Out of pepperoni today"),
            ("parent", "unavailable", "ordered", "pepperoni-pizza", "cheese-pizza", None),
        ])

        text = plain(self.client.get("/order-status").get_data(as_text=True))
        self.assertIn("Day 4 changed to Cheese Pizza + Fries + Drink. It is back to Ordered. "
                      "Your order total is now $33.", text)
        self.assertIn("Day 4 Cheese Pizza + Fries + Drink Ordered", text)
        self.assertIn("Pepperoni Pizza + Fries + Drink was unavailable. Café note: “Out of pepperoni today”", text)
        self.assertIn("You changed this lunch to Cheese Pizza + Fries + Drink.", text)
        self.assertIn("Order total: $33", text)
        self.assertNotIn("Choose a Different Meal</a>", text)

    def test_same_price_meal_keeps_the_total(self):
        lunch = self.mark_unavailable(day="Day 6", reason="Pizza oven is down")
        self.client.post(f"/order-status/lunches/{lunch['id']}/change-meal", data={"meal": "chicken-tenders"})
        self.assertEqual(self.order_total(), 3400)
        self.assertIn("Your order total is still $34.", plain(self.client.get("/order-status").get_data(as_text=True)))

    def test_more_expensive_meal_raises_the_total(self):
        lunch = self.mark_unavailable(day="Day 2", reason="No chicken")
        self.client.post(f"/order-status/lunches/{lunch['id']}/change-meal", data={"meal": "pepperoni-pizza"})
        self.assertEqual(self.order_total(), 3500)
        self.assertEqual(self.lunch("Day 2")["price_cents"], 1200)

    def test_bad_meal_choices_are_refused(self):
        lunch = self.mark_unavailable()
        url = f"/order-status/lunches/{lunch['id']}/change-meal"
        for data in ({}, {"meal": ""}, {"meal": "lobster"}, {"meal": "pepperoni-pizza"}):
            response = self.client.post(url, data=data)
            html = response.get_data(as_text=True)
            self.assertEqual(response.status_code, 200, data)
            self.assertIn("Please choose one of the meals listed.", html)
            self.assertIn("meal-day meal-day-invalid", html)
        after = self.lunch("Day 4")
        self.assertEqual((after["status"], after["meal_id"]), ("unavailable", "pepperoni-pizza"))
        self.assertEqual(self.order_total(), 3400)

    def test_lunches_that_are_not_unavailable_cannot_be_changed(self):
        self.sign_in()
        self.update("Day 2", "completed")
        self.update("Day 6", "preparing")
        for day, label in (("Day 2", "Completed"), ("Day 4", "Ordered"), ("Day 6", "Preparing")):
            lunch = self.lunch(day)
            url = f"/order-status/lunches/{lunch['id']}/change-meal"
            self.assertTrue(self.client.get(url).headers["Location"].endswith("/order-status"))
            response = self.client.post(url, data={"meal": "cheese-pizza"})
            self.assertTrue(response.headers["Location"].endswith("/order-status"))
            self.assertEqual(self.lunch(day)["meal_id"], lunch["meal_id"], day)
            text = plain(self.client.get("/order-status").get_data(as_text=True))
            self.assertIn(f"The {day} lunch can't be changed here because its status is {label}.", text)
        self.assertEqual(self.order_total(), 3400)

    def test_another_campers_lunch_is_not_found(self):
        lunch = self.mark_unavailable()
        other = self.app.test_client()
        self.register(client=other, camper_first_name="Ben", guardian_email="ben@example.com")
        url = f"/order-status/lunches/{lunch['id']}/change-meal"
        self.assertEqual(other.get(url).status_code, 404)
        self.assertEqual(other.post(url, data={"meal": "cheese-pizza"}).status_code, 404)
        self.assertEqual(self.lunch("Day 4")["meal_id"], "pepperoni-pizza")
        self.assertEqual(self.client.get("/order-status/lunches/99999/change-meal").status_code, 404)

    def test_change_page_needs_registration(self):
        lunch = self.mark_unavailable()
        stranger = self.app.test_client()
        response = stranger.get(f"/order-status/lunches/{lunch['id']}/change-meal")
        self.assertTrue(response.headers["Location"].endswith("/register"))

    def test_sending_the_change_twice_changes_it_once(self):
        lunch = self.mark_unavailable()
        url = f"/order-status/lunches/{lunch['id']}/change-meal"
        self.client.post(url, data={"meal": "cheese-pizza"})
        self.client.post(url, data={"meal": "chicken-tenders"})
        after = self.lunch("Day 4")
        self.assertEqual(after["meal_id"], "cheese-pizza")
        self.assertEqual([h[0] for h in after["history"]], ["cafe", "parent"])
        self.assertEqual(self.order_total(), 3300)

    def test_change_is_refused_if_the_cafe_updated_the_lunch_first(self):
        lunch_id = self.mark_unavailable()["id"]
        with self.app.app_context():
            stale = db.session.get(DailyLunch, lunch_id)  # loaded while still "unavailable"
            # Meanwhile, the café puts it back to "ordered" from another computer
            # (a separate database connection, so this copy doesn't hear about it).
            with db.engine.begin() as other_connection:
                other_connection.execute(
                    db.update(DailyLunch).where(DailyLunch.id == lunch_id).values(status="ordered")
                )
            self.assertEqual(stale.status, "unavailable")
            self.assertIsNone(change_lunch_meal(stale, find_meal("cheese-pizza")))
        after = self.lunch("Day 4")
        self.assertEqual((after["status"], after["meal_id"]), ("ordered", "pepperoni-pizza"))
        self.assertEqual(self.order_total(), 3400)

    def test_cafe_sees_the_parents_change(self):
        lunch = self.mark_unavailable()
        self.client.post(f"/order-status/lunches/{lunch['id']}/change-meal", data={"meal": "cheese-pizza"})
        text = plain(self.cafe_day("Day 4"))
        self.assertIn("Ava Smith Ordered Cheese Pizza + Fries + Drink", text)
        self.assertIn("Parent changed Pepperoni Pizza + Fries + Drink to Cheese Pizza + Fries + Drink.", text)
        self.assertIn("Pepperoni Pizza + Fries + Drink marked unavailable: “Out of pepperoni today”", text)
        self.assertIn("1 × Cheese Pizza + Fries + Drink", text)

    # ----- The complete workflow -----

    def test_complete_cafe_and_parent_workflow(self):
        self.sign_in()
        # The café works through Ava's lunches.
        self.update("Day 2", "preparing")
        self.update("Day 2", "completed")
        self.update("Day 4", "unavailable", reason="Out of pepperoni today")

        # The parent checks the status page.
        html = self.client.get("/order-status").get_data(as_text=True)
        counts = [int(re.search(rf'id="count-{n}">(\d+)<', html).group(1))
                  for n in ("ordered", "completed", "remaining", "unavailable")]
        self.assertEqual(counts, [3, 1, 1, 1])

        # The parent picks a different meal for Day 4.
        lunch = self.lunch("Day 4")
        self.client.post(f"/order-status/lunches/{lunch['id']}/change-meal", data={"meal": "chicken-tenders"})
        html = self.client.get("/order-status").get_data(as_text=True)
        counts = [int(re.search(rf'id="count-{n}">(\d+)<', html).group(1))
                  for n in ("ordered", "completed", "remaining", "unavailable")]
        self.assertEqual(counts, [3, 1, 2, 0])
        self.assertEqual(self.order_total(), 3300)

        # The café makes the new meal.
        self.update("Day 4", "completed")
        self.update("Day 6", "completed")
        html = self.client.get("/order-status").get_data(as_text=True)
        self.assertIn('id="count-completed">3<', html)
        self.assertIn('id="count-remaining">0<', html)
        self.assertEqual([h[2] for h in self.lunch("Day 4")["history"]], ["unavailable", "ordered", "completed"])


class LunchHistoryTableTestCase(unittest.TestCase):
    def test_init_db_adds_the_new_table_and_keeps_existing_data(self):
        temp_dir = tempfile.mkdtemp()
        uri = "sqlite:///" + os.path.join(temp_dir, "old.db")
        app = create_app({"TESTING": True, "SECRET_KEY": "x", "SQLALCHEMY_DATABASE_URI": uri})
        try:
            with app.app_context():
                # A database from before Issue #6: every table except lunch_history.
                old_tables = [t for t in db.metadata.sorted_tables if t.name != "lunch_history"]
                db.metadata.create_all(db.engine, tables=old_tables)
                db.session.execute(db.text(
                    "INSERT INTO guardians (full_name, email, phone) VALUES ('Jordan', 'j@example.com', '+14105550123')"
                ))
                db.session.commit()
                self.assertNotIn("lunch_history", inspect(db.engine).get_table_names())

            result = app.test_cli_runner().invoke(args=["init-db"])
            self.assertIn("Database tables are ready.", result.output)

            with app.app_context():
                self.assertIn("lunch_history", inspect(db.engine).get_table_names())
                self.assertEqual(db.session.scalar(db.text("SELECT COUNT(*) FROM guardians")), 1)
                self.assertEqual(db.session.scalar(db.select(db.func.count()).select_from(LunchHistory)), 0)
        finally:
            with app.app_context():
                db.engine.dispose()
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
