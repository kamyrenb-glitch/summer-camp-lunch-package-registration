"""
Automated tests for Issue #5: Track Lunch Orders.

Run them from the project folder with:
    python -m unittest discover tests
"""

import re
import unittest

from app import count_lunches, lunch_status_class, lunch_status_label
from base import AppTestCase
from models import DailyLunch, Order, db

FIRST_ORDER = {"Day 2": "chicken-tenders", "Day 4": "cheese-pizza", "Day 6": "pepperoni-pizza"}


def meal_field(day):
    return "meal-" + day.lower().replace(" ", "-")


def count(html, name):
    return int(re.search(r'id="count-' + name + r'">(\d+)<', html).group(1))


def order_count_lines(html):
    """The "3 ordered · 1 completed · ..." line on each order card, as plain text."""
    return [" ".join(re.sub(r"<[^>]+>", "", line).split())
            for line in re.findall(r'<p class="order-counts">(.*?)</p>', html, re.S)]


def all_counts(html):
    """(ordered, completed, remaining, unavailable) from the summary tiles."""
    return tuple(count(html, name) for name in ("ordered", "completed", "remaining", "unavailable"))


def status_rows(html):
    """Return [(day, meal, status label), ...] from every status table on the page."""
    rows = []
    for body in re.findall(r"<tbody[^>]*>(.*?)</tbody>", html, re.S):
        for row in re.findall(r"<tr>(.*?)</tr>", body, re.S):
            cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.S)
            rows.append(tuple(re.sub(r"<[^>]+>", "", cell).strip() for cell in cells))
    return rows


class StatusTestCase(AppTestCase):
    def setUp(self):
        super().setUp()
        self.register()
        self.camper = self.camper_id()

    # ----- Helpers -----

    def place_order(self, meals=FIRST_ORDER, package="6-day", client=None):
        """Go through package, meals, review, and confirm. Returns the new order's ID."""
        client = client or self.client
        client.post("/", data={"package": package, "days": list(meals)})
        client.post("/meals", data={meal_field(day): meal for day, meal in meals.items()})
        html = client.get("/review").get_data(as_text=True)
        token = re.search(r'name="confirmation_token" value="([^"]*)"', html).group(1)
        client.post("/review", data={"confirmation_token": token})
        with client.session_transaction() as session:
            return session["last_order_id"]

    def set_status(self, order_id, day, status):
        """Change one lunch's status in the database, like the café will (Issue #6)."""
        with self.app.app_context():
            lunch = db.session.scalars(
                db.select(DailyLunch).filter_by(order_id=order_id, camp_day=day)
            ).one()
            lunch.status = status
            db.session.commit()

    def status_page(self, client=None):
        response = (client or self.client).get("/order-status")
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    # ----- Getting to the page -----

    def test_confirmation_page_links_to_order_status(self):
        self.place_order()
        html = self.client.get("/order-confirmed").get_data(as_text=True)
        self.assertIn('<a class="button" href="/order-status">View Order Status</a>', html)

    def test_camper_bar_links_to_status_once_an_order_exists(self):
        self.assertNotIn('id="order-status-link"', self.client.get("/").get_data(as_text=True))
        self.place_order()
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('<a id="order-status-link" class="link-button" href="/order-status">View order status</a>', html)
        # Not repeated on the status page itself.
        self.assertNotIn('id="order-status-link"', self.status_page())

    # ----- What the page shows -----

    def test_shows_camper_order_package_days_meals_and_ordered_status(self):
        order_id = self.place_order()
        html = self.status_page()
        self.assertIn("<strong>Ava Smith</strong>", html)
        self.assertIn(f"Order {order_id} — 6-Day Package", html)
        self.assertEqual(status_rows(html), [
            ("Day 2", "Chicken Tenders + Fries + Drink", "Ordered"),
            ("Day 4", "Cheese Pizza + Fries + Drink", "Ordered"),
            ("Day 6", "Pepperoni Pizza + Fries + Drink", "Ordered"),
        ])
        self.assertEqual(all_counts(html), (3, 0, 3, 0))
        self.assertIn("0 of 3 lunches completed", html)
        # No "unavailable" part on the order card when there are none.
        self.assertEqual(order_count_lines(html), ["3 ordered · 0 completed · 3 remaining"])
        self.assertIn("status-count-unavailable status-count-none", html)
        self.assertNotIn("Not Started", html)

    def test_counts_and_labels_for_every_status(self):
        order_id = self.place_order(
            {"Day 1": "cheese-pizza", "Day 2": "cheese-pizza", "Day 3": "cheese-pizza", "Day 4": "cheese-pizza"},
            package="4-day",
        )
        self.set_status(order_id, "Day 1", "completed")
        self.set_status(order_id, "Day 2", "preparing")
        self.set_status(order_id, "Day 3", "unavailable")
        # Day 4 stays "ordered".

        html = self.status_page()
        self.assertEqual([row[2] for row in status_rows(html)],
                         ["Completed", "Preparing", "Unavailable", "Ordered"])
        # Remaining = ordered + preparing. Unavailable is counted on its own.
        ordered, completed, remaining, unavailable = all_counts(html)
        self.assertEqual((ordered, completed, remaining, unavailable), (4, 1, 2, 1))
        self.assertEqual(ordered, completed + remaining + unavailable)
        # Progress leaves out the lunch that won't be made.
        self.assertIn("1 of 3 available lunches completed", " ".join(html.split()))
        self.assertIn('max="3" value="1"', html)
        self.assertEqual(order_count_lines(html), ["4 ordered · 1 completed · 2 remaining · 1 unavailable"])
        self.assertNotIn("status-count-none", html)
        for status in ("ordered", "preparing", "completed", "unavailable"):
            self.assertIn(f'class="status-badge status-{status}"', html)

    def test_status_labels(self):
        self.assertEqual(lunch_status_label("ordered"), "Ordered")
        self.assertEqual(lunch_status_label("preparing"), "Preparing")
        self.assertEqual(lunch_status_label("completed"), "Completed")
        self.assertEqual(lunch_status_label("unavailable"), "Unavailable")
        # Older names still show as the new status.
        self.assertEqual(lunch_status_label("cooking"), "Preparing")
        self.assertEqual(lunch_status_label("cannot_complete"), "Unavailable")
        self.assertEqual(lunch_status_class("cooking"), "status-preparing")
        self.assertEqual(lunch_status_class("cannot_complete"), "status-unavailable")
        # A status added later still shows sensibly.
        self.assertEqual(lunch_status_label("on_hold"), "On Hold")

    def test_unknown_status_is_shown_and_counted_as_remaining(self):
        order_id = self.place_order({"Day 1": "cheese-pizza"}, package="4-day")
        self.set_status(order_id, "Day 1", "on_hold")
        html = self.status_page()
        self.assertEqual(status_rows(html), [("Day 1", "Cheese Pizza + Fries + Drink", "On Hold")])
        self.assertIn('class="status-badge status-other"', html)
        self.assertEqual(count(html, "remaining"), 1)

    def test_count_lunches_rules(self):
        lunches = [DailyLunch(status=status) for status in
                   ("ordered", "preparing", "completed", "completed", "unavailable", "on_hold")]
        self.assertEqual(count_lunches(lunches),
                         {"ordered": 6, "completed": 2, "remaining": 3, "unavailable": 1, "available": 5})
        self.assertEqual(count_lunches([]),
                         {"ordered": 0, "completed": 0, "remaining": 0, "unavailable": 0, "available": 0})
        # Older names are counted as the new statuses.
        old = [DailyLunch(status=status) for status in ("cooking", "cannot_complete")]
        self.assertEqual(count_lunches(old),
                         {"ordered": 2, "completed": 0, "remaining": 1, "unavailable": 1, "available": 1})

    def test_several_orders_are_listed_and_counted_together(self):
        first = self.place_order()
        second = self.place_order({"Day 9": "pepperoni-pizza", "Day 10": "cheese-pizza"}, package="4-day")
        self.set_status(second, "Day 9", "completed")

        html = self.status_page()
        self.assertIn(f"Order {first} — 6-Day Package", html)
        self.assertIn(f"Order {second} — 4-Day Package", html)
        self.assertIn("2 ordered · 1 completed · 1 remaining", order_count_lines(html))
        self.assertEqual((count(html, "ordered"), count(html, "completed"), count(html, "remaining")), (5, 1, 4))
        # Days are listed in camp order, with Day 10 after Day 9.
        self.assertEqual([row[0] for row in status_rows(html)], ["Day 2", "Day 4", "Day 6", "Day 9", "Day 10"])

    def test_no_orders_yet(self):
        html = self.status_page()
        self.assertIn("No confirmed lunch orders yet for Ava Smith.", html)
        self.assertEqual((count(html, "ordered"), count(html, "completed"), count(html, "remaining")), (0, 0, 0))
        self.assertNotIn("<progress", html)
        self.assertIn("Start an Order", html)

    def test_old_status_names_still_display_and_count(self):
        order_id = self.place_order({"Day 1": "cheese-pizza", "Day 2": "cheese-pizza"}, package="4-day")
        self.set_status(order_id, "Day 1", "cooking")
        self.set_status(order_id, "Day 2", "cannot_complete")
        html = self.status_page()
        self.assertEqual([row[2] for row in status_rows(html)], ["Preparing", "Unavailable"])
        self.assertIn('class="status-badge status-preparing"', html)
        self.assertIn('class="status-badge status-unavailable"', html)
        self.assertEqual(all_counts(html), (2, 0, 1, 1))

    def test_every_lunch_unavailable(self):
        order_id = self.place_order({"Day 1": "cheese-pizza", "Day 2": "cheese-pizza"}, package="4-day")
        self.set_status(order_id, "Day 1", "unavailable")
        self.set_status(order_id, "Day 2", "unavailable")
        html = self.status_page()
        self.assertEqual(all_counts(html), (2, 0, 0, 2))
        self.assertIn("All 2 lunches are unavailable.", html)
        self.assertNotIn("<progress", html)

    def test_all_lunches_done_with_one_unavailable(self):
        order_id = self.place_order(FIRST_ORDER)
        self.set_status(order_id, "Day 2", "completed")
        self.set_status(order_id, "Day 4", "completed")
        self.set_status(order_id, "Day 6", "unavailable")
        html = self.status_page()
        # Nothing is left to make, and the unavailable lunch isn't shown as remaining.
        self.assertEqual(all_counts(html), (3, 2, 0, 1))
        self.assertIn("2 of 2 available lunches completed", " ".join(html.split()))

    # ----- Fresh data on every visit -----

    def test_cafe_updates_appear_when_the_page_is_refreshed(self):
        order_id = self.place_order()
        html = self.status_page()
        self.assertEqual(count(html, "completed"), 0)

        self.set_status(order_id, "Day 2", "completed")
        self.set_status(order_id, "Day 4", "preparing")
        self.set_status(order_id, "Day 6", "unavailable")

        html = self.status_page()  # refresh
        self.assertEqual([row[2] for row in status_rows(html)], ["Completed", "Preparing", "Unavailable"])
        self.assertEqual(all_counts(html), (3, 1, 1, 1))

    def test_page_is_not_cached_by_the_browser(self):
        self.place_order()
        response = self.client.get("/order-status")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        html = response.get_data(as_text=True)
        self.assertIn('href="/order-status">Refresh Status</a>', html)
        # status.js reloads the page if the Back button shows a remembered copy.
        self.assertIn('<script src="/static/status.js"></script>', html)

    # ----- Access protection -----

    def test_requires_registration(self):
        stranger = self.app.test_client()
        response = stranger.get("/order-status")
        self.assertTrue(response.headers["Location"].endswith("/register"))

    def test_parent_sees_only_their_own_camper(self):
        my_order = self.place_order()
        other = self.app.test_client()
        self.register(client=other, camper_first_name="Ben", guardian_email="ben@example.com")
        other_order = self.place_order({"Day 11": "pepperoni-pizza"}, package="4-day", client=other)

        mine = self.status_page()
        self.assertIn(f"Order {my_order} ", mine)
        self.assertNotIn(f"Order {other_order} ", mine)
        self.assertNotIn("Day 11", mine)
        self.assertNotIn("Ben Smith", mine)

        theirs = self.status_page(client=other)
        self.assertIn("<strong>Ben Smith</strong>", theirs)
        self.assertNotIn("Day 2", theirs)

    def test_order_numbers_in_the_url_are_ignored(self):
        self.place_order()
        other = self.app.test_client()
        self.register(client=other, camper_first_name="Ben", guardian_email="ben@example.com")
        other_order = self.place_order({"Day 11": "pepperoni-pizza"}, package="4-day", client=other)

        for path in (f"/order-status?order_id={other_order}", f"/order-status?order={other_order}",
                     f"/order-status?camper_id=2"):
            html = self.status_page_for(path)
            self.assertNotIn("Day 11", html, path)
            self.assertNotIn("Ben Smith", html, path)
        self.assertEqual(self.client.get(f"/order-status/{other_order}").status_code, 404)

    def status_page_for(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def test_changed_session_cookie_cannot_switch_campers(self):
        self.place_order()
        other = self.app.test_client()
        self.register(client=other, camper_first_name="Ben", guardian_email="ben@example.com")
        self.place_order({"Day 11": "pepperoni-pizza"}, package="4-day", client=other)

        # A cookie someone edited by hand fails Flask's signature check, so it's
        # treated as no registration at all.
        stranger = self.app.test_client()
        stranger.set_cookie("session", "eyJjYW1wZXJfaWQiOjJ9.fake.signature")
        response = stranger.get("/order-status")
        self.assertTrue(response.headers["Location"].endswith("/register"))

        # A camper ID that isn't a number is ignored too.
        with stranger.session_transaction() as session:
            session["camper_id"] = "2"
        self.assertTrue(stranger.get("/order-status").headers["Location"].endswith("/register"))

    # ----- The complete flow -----

    def test_complete_flow_from_registration_to_status(self):
        client = self.app.test_client()
        self.assertTrue(client.get("/order-status").headers["Location"].endswith("/register"))
        self.register(client=client, camper_first_name="Mia", guardian_email="mia.parent@example.com")
        order_id = self.place_order({"Day 3": "cheese-pizza", "Day 5": "chicken-tenders"}, package="4-day",
                                    client=client)

        confirmation = client.get("/order-confirmed").get_data(as_text=True)
        self.assertIn("View Order Status", confirmation)

        html = self.status_page(client=client)
        self.assertIn("<strong>Mia Smith</strong>", html)
        self.assertIn(f"Order {order_id} — 4-Day Package", html)
        self.assertEqual(all_counts(html), (2, 0, 2, 0))

        # The café finishes Day 3; the parent refreshes.
        self.set_status(order_id, "Day 3", "completed")
        html = self.status_page(client=client)
        self.assertEqual(status_rows(html), [
            ("Day 3", "Cheese Pizza + Fries + Drink", "Completed"),
            ("Day 5", "Chicken Tenders + Fries + Drink", "Ordered"),
        ])
        self.assertEqual(all_counts(html), (2, 1, 1, 0))

        # The order is still exactly as confirmed in the database.
        with self.app.app_context():
            order = db.session.get(Order, order_id)
            self.assertEqual(order.total_cents, 2200)
            self.assertEqual(len(order.daily_lunches), 2)


if __name__ == "__main__":
    unittest.main()
