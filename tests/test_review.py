"""
Automated tests for Issue #4: Review Order and Total.

Run them from the project folder with:
    python -m unittest discover tests
"""

import re
import unittest
from unittest import mock

from sqlalchemy.exc import IntegrityError

import app as app_module
from app import calculate_total_cents, format_price
from base import AppTestCase, checked_values, form_message
from models import DailyLunch, Order, db


def review_rows(html):
    """Return [(day, meal, price), ...] from the order table."""
    body = re.search(r"<tbody>(.*?)</tbody>", html, re.S).group(1)
    rows = []
    for row in re.findall(r"<tr>(.*?)</tr>", body, re.S):
        cells = [re.sub(r"<[^>]+>", "", cell).strip() for cell in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.S)]
        rows.append(tuple(cells))
    return rows


def order_total(html):
    return re.search(r'id="order-total">(.*?)<', html).group(1)


def token_in(html):
    return re.search(r'name="confirmation_token" value="([^"]*)"', html).group(1)


class ReviewTestCase(AppTestCase):
    def setUp(self):
        super().setUp()
        self.register()
        self.camper = self.camper_id()

    # ----- Helpers -----

    def prepare_order(self, package="6-day", meals=None):
        """Choose a package and days, then save a meal for each day."""
        meals = meals or {
            "Day 2": "chicken-tenders",
            "Day 4": "cheese-pizza",
            "Day 6": "pepperoni-pizza",
        }
        self.client.post("/", data={"package": package, "days": list(meals)})
        self.client.post("/meals", data={
            "meal-" + day.lower().replace(" ", "-"): meal_id for day, meal_id in meals.items()
        })

    def open_review(self):
        response = self.client.get("/review")
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def confirm(self, token):
        return self.client.post("/review", data={"confirmation_token": token})

    def saved_orders(self):
        with self.app.app_context():
            return [
                {
                    "id": order.id,
                    "camper_id": order.camper_id,
                    "package_id": order.package_id,
                    "total_cents": order.total_cents,
                    "status": order.status,
                    "lunches": [(l.camp_day, l.meal_id, l.price_cents, l.status) for l in order.daily_lunches],
                }
                for order in db.session.scalars(db.select(Order).order_by(Order.id))
            ]

    def lunch_count(self):
        with self.app.app_context():
            return db.session.scalar(db.select(db.func.count()).select_from(DailyLunch))

    # ----- Getting to the review page -----

    def test_review_requires_registration(self):
        other_client = self.app.test_client()
        for method in ("get", "post"):
            response = getattr(other_client, method)("/review")
            self.assertTrue(response.headers["Location"].endswith("/register"), method)
        response = other_client.get("/order-confirmed")
        self.assertTrue(response.headers["Location"].endswith("/register"))

    def test_review_without_package_redirects_to_package_page(self):
        response = self.client.get("/review")
        self.assertTrue(response.headers["Location"].endswith("/"))
        html = self.client.get("/").get_data(as_text=True)
        self.assertEqual(form_message(html), "Please choose a lunch package and camp days before choosing meals.")

    def test_review_with_missing_meals_redirects_to_meal_page(self):
        self.client.post("/", data={"package": "4-day", "days": ["Day 1", "Day 3", "Day 5"]})
        self.client.post("/meals", data={"meal-day-3": "cheese-pizza", "action": "back"})

        response = self.client.get("/review")
        self.assertTrue(response.headers["Location"].endswith("/meals"))
        html = self.client.get("/meals").get_data(as_text=True)
        self.assertEqual(form_message(html), "Please choose a meal for Day 1 and Day 5 before reviewing your order.")
        # The days that still need a meal are highlighted.
        self.assertEqual(html.count("meal-day meal-day-invalid"), 2)
        self.assertNotIn('id="review-link"', html)

    def test_confirm_without_session_order_saves_nothing(self):
        response = self.confirm("made-up-token")
        self.assertTrue(response.headers["Location"].endswith("/"))
        self.assertEqual(self.saved_orders(), [])

    def test_meal_page_offers_review_only_when_every_day_is_saved(self):
        self.client.post("/", data={"package": "4-day", "days": ["Day 1", "Day 2"]})
        html = self.client.get("/meals").get_data(as_text=True)
        self.assertNotIn('id="review-link"', html)

        self.client.post("/meals", data={"meal-day-1": "cheese-pizza", "meal-day-2": "cheese-pizza"})
        html = self.client.get("/meals").get_data(as_text=True)
        self.assertIn('id="review-link"', html)
        self.assertIn("Review Order", html)

    # ----- The review page -----

    def test_review_page_shows_camper_package_days_meals_and_total(self):
        self.prepare_order()
        html = self.open_review()

        self.assertIn("<strong>Ava Smith</strong>", html)
        self.assertIn("6-Day Package — 3 lunches selected", html)
        self.assertEqual(review_rows(html), [
            ("Day 2", "Chicken Tenders + Fries + Drink", "$11"),
            ("Day 4", "Cheese Pizza + Fries + Drink", "$11"),
            ("Day 6", "Pepperoni Pizza + Fries + Drink", "$12"),
        ])
        self.assertEqual(order_total(html), "$34")
        self.assertIn("Total (3 lunches)", html)
        # Ways to go back and edit, and the confirm button.
        self.assertIn('href="/?return_to=review">Change package or days</a>', html)
        self.assertIn('href="/meals?return_to=review">Change meals</a>', html)
        self.assertIn('href="/register?next=review"', html)
        self.assertIn(">Confirm Order</button>", html)

    def test_going_back_to_edit_keeps_the_order(self):
        self.prepare_order()
        self.open_review()
        html = self.client.get("/").get_data(as_text=True)
        self.assertEqual(checked_values(html, "package"), ["6-day"])
        self.assertEqual(checked_values(html, "days"), ["Day 2", "Day 4", "Day 6"])
        html = self.client.get("/meals").get_data(as_text=True)
        self.assertEqual(checked_values(html, "meal-day-6"), ["pepperoni-pizza"])

    def test_review_shows_changes_after_editing_meals(self):
        self.prepare_order()
        self.open_review()
        self.client.post("/meals", data={
            "meal-day-2": "pepperoni-pizza", "meal-day-4": "pepperoni-pizza", "meal-day-6": "pepperoni-pizza",
        })
        self.assertEqual(order_total(self.open_review()), "$36")

    # ----- Totals -----

    def test_total_is_calculated_from_the_selected_meals(self):
        lines = [{"price_cents": 1100}, {"price_cents": 1100}, {"price_cents": 1200}]
        self.assertEqual(calculate_total_cents(lines), 3400)
        self.assertEqual(calculate_total_cents([]), 0)
        self.assertEqual(format_price(3400), "$34")
        self.assertEqual(format_price(1150), "$11.50")

    def test_twelve_day_total(self):
        meals = {f"Day {n}": ("pepperoni-pizza" if n % 2 else "cheese-pizza") for n in range(1, 13)}
        self.prepare_order("12-day", meals)
        # 6 x $12 + 6 x $11 = $138
        self.assertEqual(order_total(self.open_review()), "$138")

    def test_total_ignores_changed_prices_in_the_session(self):
        self.prepare_order(meals={"Day 1": "cheese-pizza"})
        with self.client.session_transaction() as session:
            order = session["order"]
            order["meals"]["Day 1"]["price_cents"] = 1
            session["order"] = order
        html = self.open_review()
        self.assertEqual(order_total(html), "$11")
        self.confirm(token_in(html))
        self.assertEqual(self.saved_orders()[0]["total_cents"], 1100)

    # ----- Confirming and saving -----

    def test_confirm_saves_order_and_daily_lunches(self):
        self.prepare_order()
        response = self.confirm(token_in(self.open_review()))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/order-confirmed"))

        orders = self.saved_orders()
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["camper_id"], self.camper)
        self.assertEqual(orders[0]["package_id"], "6-day")
        self.assertEqual(orders[0]["total_cents"], 3400)
        self.assertEqual(orders[0]["status"], "confirmed")
        self.assertEqual(orders[0]["lunches"], [
            ("Day 2", "chicken-tenders", 1100, "ordered"),
            ("Day 4", "cheese-pizza", 1100, "ordered"),
            ("Day 6", "pepperoni-pizza", 1200, "ordered"),
        ])

        # The in-progress order is finished; the session keeps only IDs.
        session = self.session_data()
        session.pop("_flashes", None)
        self.assertEqual(session, {"camper_id": self.camper, "last_order_id": orders[0]["id"]})

    def test_confirmation_page_shows_the_saved_order(self):
        self.prepare_order()
        self.confirm(token_in(self.open_review()))
        order_id = self.saved_orders()[0]["id"]

        html = self.client.get("/order-confirmed").get_data(as_text=True)
        self.assertIn(f"Your order is confirmed. Order number {order_id}.", html)
        self.assertIn("<strong>Ava Smith</strong>", html)
        self.assertIn("6-Day Package — 3 lunches", html)
        self.assertEqual(review_rows(html)[2], ("Day 6", "Pepperoni Pizza + Fries + Drink", "$12"))
        self.assertEqual(order_total(html), "$34")

    def test_prices_or_totals_sent_by_the_browser_are_ignored(self):
        self.prepare_order(meals={"Day 1": "pepperoni-pizza"})
        token = token_in(self.open_review())
        self.client.post("/review", data={
            "confirmation_token": token, "total_cents": "1", "total": "$0", "price_cents": "0",
            "package": "12-day", "camper_id": "999",
        })
        order = self.saved_orders()[0]
        self.assertEqual(order["total_cents"], 1200)
        self.assertEqual(order["package_id"], "6-day")
        self.assertEqual(order["camper_id"], self.camper)

    def test_starting_another_order_after_confirming_is_empty(self):
        self.prepare_order()
        self.confirm(token_in(self.open_review()))
        html = self.client.get("/").get_data(as_text=True)
        self.assertEqual(checked_values(html, "package"), [])
        self.assertEqual(checked_values(html, "days"), [])
        self.assertTrue(self.client.get("/review").headers["Location"].endswith("/"))

    # ----- Duplicate prevention -----

    def test_confirming_twice_saves_only_one_order(self):
        self.prepare_order()
        token = token_in(self.open_review())

        first = self.confirm(token)
        second = self.confirm(token)  # e.g. a double-click or the browser resending the form
        self.assertTrue(first.headers["Location"].endswith("/order-confirmed"))
        self.assertTrue(second.headers["Location"].endswith("/order-confirmed"))
        self.assertEqual(len(self.saved_orders()), 1)
        self.assertEqual(self.lunch_count(), 3)

    def test_second_request_with_the_old_session_saves_only_one_order(self):
        # Two clicks sent so close together that both carry the same session cookie.
        self.prepare_order()
        token = token_in(self.open_review())
        old_order = self.saved_order()

        self.confirm(token)
        with self.client.session_transaction() as session:
            session["order"] = old_order  # the second request still has the old cookie
        response = self.confirm(token)

        self.assertTrue(response.headers["Location"].endswith("/order-confirmed"))
        self.assertEqual(len(self.saved_orders()), 1)
        self.assertNotIn("order", self.session_data())

    def test_database_blocks_a_duplicate_if_two_requests_race(self):
        self.prepare_order()
        token = token_in(self.open_review())
        self.confirm(token)

        with self.client.session_transaction() as session:
            session["order"] = {**self.saved_order_for_race(), "confirmation_token": token}
        # Pretend the duplicate checks ran before the first order was saved
        # (a true race), so only the database's unique rules can stop the
        # second copy.
        real_find = app_module.find_confirmed_order
        calls = {"count": 0}

        def find_misses_first_two_times(camper, token):
            calls["count"] += 1
            return None if calls["count"] <= 2 else real_find(camper, token)

        real_days = app_module.already_ordered_days
        day_calls = {"count": 0}

        def days_miss_first_time(camper, days):
            day_calls["count"] += 1
            return [] if day_calls["count"] == 1 else real_days(camper, days)

        with mock.patch.object(app_module, "find_confirmed_order", side_effect=find_misses_first_two_times), \
                mock.patch.object(app_module, "already_ordered_days", side_effect=days_miss_first_time):
            response = self.confirm(token)

        # 1st call: the page's check, 2nd: the save's check, 3rd: the lookup
        # after the database refused the duplicate.
        self.assertEqual(calls["count"], 3)
        self.assertTrue(response.headers["Location"].endswith("/order-confirmed"))
        self.assertEqual(len(self.saved_orders()), 1)
        self.assertEqual(self.lunch_count(), 3)

    def saved_order_for_race(self):
        return {
            "status": "in_progress", "camper_id": self.camper, "package_id": "6-day",
            "days": ["Day 2", "Day 4", "Day 6"],
            "meals": {
                "Day 2": {"meal_id": "chicken-tenders", "price_cents": 1100},
                "Day 4": {"meal_id": "cheese-pizza", "price_cents": 1100},
                "Day 6": {"meal_id": "pepperoni-pizza", "price_cents": 1200},
            },
        }

    def test_stale_or_missing_token_does_not_save(self):
        self.prepare_order()
        self.open_review()
        for token in ("", "wrong-token"):
            response = self.confirm(token)
            self.assertTrue(response.headers["Location"].endswith("/review"), token)
        self.assertEqual(self.saved_orders(), [])
        html = self.open_review()
        self.assertEqual(form_message(html), "Your order changed since this page was opened. Please review it again.")

    def test_order_changed_after_review_needs_a_new_review(self):
        self.prepare_order()
        old_token = token_in(self.open_review())
        # The meals change (for example, in another tab) after the review page was opened.
        self.client.post("/meals", data={
            "meal-day-2": "cheese-pizza", "meal-day-4": "cheese-pizza", "meal-day-6": "cheese-pizza",
        })
        self.confirm(old_token)
        self.assertEqual(self.saved_orders(), [])

        new_token = token_in(self.open_review())
        self.assertNotEqual(new_token, old_token)
        self.confirm(new_token)
        self.assertEqual(self.saved_orders()[0]["total_cents"], 3300)

    def test_confirmation_page_needs_this_campers_order(self):
        self.assertTrue(self.client.get("/order-confirmed").headers["Location"].endswith("/"))

        # Another camper's order can't be shown by putting its ID in this session.
        other = self.app.test_client()
        self.register(client=other, camper_first_name="Ben", guardian_email="ben@example.com")
        with other.session_transaction() as session:
            session["order"] = {**self.saved_order_for_race(), "camper_id": session["camper_id"]}
        html = other.get("/review").get_data(as_text=True)
        other.post("/review", data={"confirmation_token": token_in(html)})
        other_order_id = self.saved_orders()[0]["id"]

        with self.client.session_transaction() as session:
            session["last_order_id"] = other_order_id
        self.assertTrue(self.client.get("/order-confirmed").headers["Location"].endswith("/"))

    # ----- One lunch per camper per day, across orders -----

    def confirm_first_order(self):
        """Confirm an order for Day 2, Day 4, and Day 6."""
        self.prepare_order()
        self.confirm(token_in(self.open_review()))
        self.assertEqual(len(self.saved_orders()), 1)

    def test_one_day_already_ordered_is_refused(self):
        self.confirm_first_order()
        self.prepare_order("4-day", {"Day 4": "pepperoni-pizza", "Day 8": "cheese-pizza"})

        html = self.open_review()
        message = form_message(html)
        self.assertIn("Ava Smith already has a confirmed lunch on Day 4.", message)
        self.assertIn('href="/?return_to=review">Change camp days</a>', message)
        self.assertEqual(html.count('class="order-conflict"'), 1)
        self.assertIn("Already ordered", html)
        self.assertNotIn(">Confirm Order</button>", html)

        # Even sending the form directly saves nothing.
        response = self.confirm(token_in(html))
        self.assertTrue(response.headers["Location"].endswith("/review"))
        self.assertEqual(len(self.saved_orders()), 1)

    def test_several_days_already_ordered_are_all_named(self):
        self.confirm_first_order()
        self.prepare_order("6-day", {"Day 2": "cheese-pizza", "Day 6": "cheese-pizza", "Day 9": "cheese-pizza"})
        html = self.open_review()
        self.assertIn("Ava Smith already has a confirmed lunch on Day 2 and Day 6.", form_message(html))
        self.assertEqual(html.count('class="order-conflict"'), 2)

    def test_no_part_of_a_conflicting_order_is_saved(self):
        self.confirm_first_order()
        self.prepare_order("4-day", {"Day 4": "pepperoni-pizza", "Day 8": "cheese-pizza"})
        self.confirm(token_in(self.open_review()))

        orders = self.saved_orders()
        self.assertEqual(len(orders), 1)
        self.assertEqual(self.lunch_count(), 3)
        self.assertNotIn("Day 8", [lunch[0] for lunch in orders[0]["lunches"]])
        # The new order is still in progress, so the parent can change it.
        self.assertEqual(self.saved_order()["days"], ["Day 4", "Day 8"])

    def test_changing_the_days_fixes_the_conflict(self):
        self.confirm_first_order()
        self.prepare_order("4-day", {"Day 4": "pepperoni-pizza", "Day 8": "cheese-pizza"})
        self.open_review()

        # Follow "Change camp days": drop Day 4. Day 8's meal is kept.
        self.client.post("/", data={"package": "4-day", "days": ["Day 8"]})
        html = self.open_review()
        self.assertNotIn("already has a confirmed lunch", html)
        self.assertIn(">Confirm Order</button>", html)
        self.confirm(token_in(html))

        orders = self.saved_orders()
        self.assertEqual(len(orders), 2)
        self.assertEqual(orders[1]["lunches"], [("Day 8", "cheese-pizza", 1100, "ordered")])

    def test_a_different_camper_can_order_the_same_day(self):
        self.confirm_first_order()
        other = self.app.test_client()
        self.register(client=other, camper_first_name="Ben", guardian_email="ben@example.com")
        other.post("/", data={"package": "4-day", "days": ["Day 2", "Day 4"]})
        other.post("/meals", data={"meal-day-2": "cheese-pizza", "meal-day-4": "cheese-pizza"})
        html = other.get("/review").get_data(as_text=True)
        self.assertNotIn("already has a confirmed lunch", html)
        other.post("/review", data={"confirmation_token": token_in(html)})

        orders = self.saved_orders()
        self.assertEqual(len(orders), 2)
        self.assertNotEqual(orders[0]["camper_id"], orders[1]["camper_id"])
        self.assertEqual([lunch[0] for lunch in orders[1]["lunches"]], ["Day 2", "Day 4"])

    def test_simultaneous_orders_for_the_same_day_save_only_one(self):
        self.confirm_first_order()
        self.prepare_order("4-day", {"Day 4": "pepperoni-pizza", "Day 8": "cheese-pizza"})
        with mock.patch.object(app_module, "already_ordered_days", return_value=[]):
            token = token_in(self.open_review())

        # Pretend this request checked the days before the other order was
        # saved (a true race), so only the database's rule can stop it.
        real_days = app_module.already_ordered_days
        calls = {"count": 0}

        def days_miss_first_time(camper, days):
            calls["count"] += 1
            return [] if calls["count"] == 1 else real_days(camper, days)

        with mock.patch.object(app_module, "already_ordered_days", side_effect=days_miss_first_time):
            response = self.confirm(token)

        # 1st call: the check before saving, 2nd: finding the taken days
        # after the database refused the order.
        self.assertEqual(calls["count"], 2)
        self.assertTrue(response.headers["Location"].endswith("/review"))
        self.assertEqual(len(self.saved_orders()), 1)
        self.assertEqual(self.lunch_count(), 3)
        self.assertIn("already has a confirmed lunch on Day 4.", form_message(self.open_review()))

    def test_database_refuses_two_lunches_for_one_camper_on_one_day(self):
        self.confirm_first_order()
        with self.app.app_context():
            first = db.session.scalars(db.select(Order)).one()
            second = Order(camper_id=self.camper, package_id="4-day", total_cents=1100,
                           confirmation_token="another-order")
            second.daily_lunches.append(
                DailyLunch(camper_id=self.camper, camp_day="Day 2", meal_id="cheese-pizza", price_cents=1100)
            )
            db.session.add(second)
            with self.assertRaises(IntegrityError):
                db.session.commit()
            db.session.rollback()
            self.assertEqual(first.id, db.session.scalars(db.select(Order)).one().id)

    # ----- The complete flow -----

    def test_complete_flow_from_registration_to_confirmed_order(self):
        client = self.app.test_client()
        self.assertTrue(client.get("/review").headers["Location"].endswith("/register"))

        self.register(client=client, camper_first_name="Mia", guardian_email="mia.parent@example.com")
        self.assertTrue(client.post("/", data={"package": "4-day", "days": ["Day 1", "Day 8"]})
                        .headers["Location"].endswith("/meals"))
        self.assertTrue(client.post("/meals", data={"meal-day-1": "cheese-pizza", "meal-day-8": "pepperoni-pizza"})
                        .headers["Location"].endswith("/meals"))
        self.assertIn('id="review-link"', client.get("/meals").get_data(as_text=True))

        html = client.get("/review").get_data(as_text=True)
        self.assertIn("<strong>Mia Smith</strong>", html)
        self.assertEqual(order_total(html), "$23")

        response = client.post("/review", data={"confirmation_token": token_in(html)})
        self.assertTrue(response.headers["Location"].endswith("/order-confirmed"))
        html = client.get("/order-confirmed").get_data(as_text=True)
        self.assertIn("Your order is confirmed.", html)

        with client.session_transaction() as session:
            mia_id = session["camper_id"]
        orders = self.saved_orders()
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["camper_id"], mia_id)
        self.assertEqual(orders[0]["total_cents"], 2300)
        self.assertEqual(orders[0]["lunches"], [
            ("Day 1", "cheese-pizza", 1100, "ordered"),
            ("Day 8", "pepperoni-pizza", 1200, "ordered"),
        ])


if __name__ == "__main__":
    unittest.main()
