"""
Automated tests for the package page (Issue #2) and meal page (Issue #3).

Run them from the project folder with:
    python -m unittest discover tests

Flask's test client acts like a browser: it sends requests to the app and
remembers the session cookie between requests, without starting a server.
Each test registers a camper first, because these pages require one.
"""

import unittest

from base import AppTestCase, checked_values, form_message


class PackageAndMealTestCase(AppTestCase):
    def setUp(self):
        super().setUp()
        self.register()
        self.camper = self.camper_id()

    # ----- Helpers -----

    def choose_package(self, package="4-day", days=("Day 1", "Day 3", "Day 5")):
        """Submit the package page, the way a parent pressing Confirm Selection would."""
        return self.client.post("/", data={"package": package, "days": list(days)})

    def order(self, package_id, days, meals=None):
        """Build the order we expect to find in the session."""
        return {
            "status": "in_progress",
            "camper_id": self.camper,
            "package_id": package_id,
            "days": days,
            "meals": meals or {},
        }

    # ----- Issue #2: package page -----

    def test_package_page_shows_all_packages(self):
        html = self.client.get("/").get_data(as_text=True)
        for name in ("4-Day Package", "6-Day Package", "12-Day Package"):
            self.assertIn(name, html)

    def test_valid_package_redirects_to_meal_page_and_saves_order(self):
        response = self.choose_package("6-day", ["Day 2", "Day 4"])
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/meals"))
        self.assertEqual(self.saved_order(), self.order("6-day", ["Day 2", "Day 4"]))

        html = self.client.get("/meals").get_data(as_text=True)
        self.assertIn("Lunch package selection confirmed: 6-Day Package with 2 camp days selected.", html)

    def test_package_over_limit_shows_error_and_saves_nothing(self):
        response = self.choose_package("4-day", [f"Day {n}" for n in range(1, 7)])
        self.assertEqual(response.status_code, 200)
        self.assertIn("Please unselect 2 days", form_message(response.get_data(as_text=True)))
        self.assertIsNone(self.saved_order())

    def test_package_missing_shows_error(self):
        response = self.client.post("/", data={"days": ["Day 1"]})
        self.assertEqual(form_message(response.get_data(as_text=True)), "Please choose a lunch package.")
        self.assertIsNone(self.saved_order())

    def test_duplicate_and_fake_days_are_ignored(self):
        self.choose_package("4-day", ["Day 3", "Day 3", "Day 1", "Day 99"])
        self.assertEqual(self.saved_order()["days"], ["Day 1", "Day 3"])

    # ----- Issue #3: getting to the meal page -----

    def test_meal_page_without_package_redirects_to_package_page(self):
        response = self.client.get("/meals")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/"))

        html = self.client.get("/").get_data(as_text=True)
        self.assertEqual(
            form_message(html),
            "Please choose a lunch package and camp days before choosing meals.",
        )

    def test_meal_post_without_package_redirects(self):
        response = self.client.post("/meals", data={"meal-day-1": "cheese-pizza"})
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(self.saved_order())

    def test_meal_page_shows_only_selected_days_with_all_meals_and_prices(self):
        self.choose_package("4-day", ["Day 2", "Day 7"])
        html = self.client.get("/meals").get_data(as_text=True)

        self.assertIn('name="meal-day-2"', html)
        self.assertIn('name="meal-day-7"', html)
        self.assertNotIn('name="meal-day-1"', html)
        self.assertNotIn('name="meal-day-3"', html)
        # One radio group per selected day, each with all three meals.
        self.assertEqual(html.count('type="radio"'), 2 * 3)
        self.assertIn("Chicken Tenders + Fries + Drink", html)
        self.assertIn("Cheese Pizza + Fries + Drink", html)
        self.assertIn("Pepperoni Pizza + Fries + Drink", html)
        self.assertEqual(html.count("$11<"), 2 * 2)
        self.assertEqual(html.count("$12<"), 2)

    # ----- Issue #3: saving meals -----

    def test_valid_meals_are_saved_with_ids_and_prices_in_cents(self):
        self.choose_package("4-day", ["Day 1", "Day 3"])
        response = self.client.post(
            "/meals", data={"meal-day-1": "pepperoni-pizza", "meal-day-3": "chicken-tenders"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/meals"))

        self.assertEqual(
            self.saved_order(),
            self.order("4-day", ["Day 1", "Day 3"], {
                "Day 1": {"meal_id": "pepperoni-pizza", "price_cents": 1200},
                "Day 3": {"meal_id": "chicken-tenders", "price_cents": 1100},
            }),
        )

        html = self.client.get("/meals").get_data(as_text=True)
        self.assertEqual(
            form_message(html),
            "Meal choices saved for all 2 camp days. Your 4-Day Package order is in progress.",
        )
        self.assertEqual(checked_values(html, "meal-day-1"), ["pepperoni-pizza"])
        self.assertEqual(checked_values(html, "meal-day-3"), ["chicken-tenders"])

    def test_missing_meal_shows_error_and_keeps_other_choices(self):
        self.choose_package("4-day", ["Day 1", "Day 3", "Day 5"])
        response = self.client.post("/meals", data={"meal-day-3": "cheese-pizza"})
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(form_message(html), "Please choose a meal for Day 1 and Day 5.")
        self.assertIn('class="alert alert-error"', html)
        # The valid choice is still selected on the page.
        self.assertEqual(checked_values(html, "meal-day-3"), ["cheese-pizza"])
        # Nothing was saved.
        self.assertEqual(self.saved_order()["meals"], {})

    def test_invalid_meal_id_is_rejected(self):
        self.choose_package("4-day", ["Day 1", "Day 2"])
        response = self.client.post(
            "/meals", data={"meal-day-1": "lobster", "meal-day-2": "cheese-pizza"}
        )
        html = response.get_data(as_text=True)
        self.assertEqual(form_message(html), "Please choose a meal from the menu for Day 1.")
        self.assertEqual(checked_values(html, "meal-day-1"), [])
        self.assertEqual(self.saved_order()["meals"], {})

    def test_more_than_one_meal_for_a_day_is_rejected(self):
        self.choose_package("4-day", ["Day 1"])
        response = self.client.post("/meals", data={"meal-day-1": ["cheese-pizza", "pepperoni-pizza"]})
        self.assertEqual(
            form_message(response.get_data(as_text=True)),
            "Please choose only one meal for Day 1.",
        )
        self.assertEqual(self.saved_order()["meals"], {})

    def test_meal_for_unselected_day_is_rejected(self):
        self.choose_package("4-day", ["Day 1"])
        response = self.client.post(
            "/meals", data={"meal-day-1": "cheese-pizza", "meal-day-9": "cheese-pizza"}
        )
        self.assertIn(
            "Meals can only be chosen for the camp days in your order.",
            form_message(response.get_data(as_text=True)),
        )
        self.assertEqual(self.saved_order()["meals"], {})

    def test_prices_and_names_sent_by_browser_are_ignored(self):
        self.choose_package("4-day", ["Day 1"])
        self.client.post(
            "/meals",
            data={
                "meal-day-1": "pepperoni-pizza",
                "price": "1",
                "price_cents": "1",
                "meal_name": "Free Lunch",
                "package": "12-day",
                "camper_id": "999",
            },
        )
        order = self.saved_order()
        self.assertEqual(order["meals"], {"Day 1": {"meal_id": "pepperoni-pizza", "price_cents": 1200}})
        self.assertEqual(order["package_id"], "4-day")
        self.assertEqual(order["camper_id"], self.camper)

    def test_order_over_package_limit_is_rejected(self):
        # Pretend the saved order somehow has more days than the package allows.
        self.set_order(self.order("4-day", [f"Day {n}" for n in range(1, 7)]))

        response = self.client.get("/meals")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/"))

        response = self.client.post("/meals", data={f"meal-day-{n}": "cheese-pizza" for n in range(1, 7)})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.saved_order()["meals"], {})

        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("Please unselect 2 days", form_message(html))

    def test_tampered_prices_in_session_are_replaced_with_menu_prices(self):
        self.set_order(self.order("4-day", ["Day 1"], {"Day 1": {"meal_id": "cheese-pizza", "price_cents": 1}}))
        self.client.post("/meals", data={"action": "back"})
        self.assertEqual(self.saved_order()["meals"]["Day 1"]["price_cents"], 1100)

    def test_order_for_a_different_camper_is_ignored(self):
        other = self.order("4-day", ["Day 1"])
        other["camper_id"] = self.camper + 1
        self.set_order(other)

        html = self.client.get("/").get_data(as_text=True)
        self.assertEqual(checked_values(html, "package"), [])
        self.assertEqual(checked_values(html, "days"), [])
        self.assertEqual(self.client.get("/meals").status_code, 302)

    # ----- Going back without losing anything -----

    def test_back_button_keeps_package_days_and_unfinished_meals(self):
        self.choose_package("6-day", ["Day 2", "Day 4", "Day 6"])
        # Only one day has a meal so far. Back should still keep it.
        response = self.client.post(
            "/meals", data={"meal-day-4": "cheese-pizza", "action": "back"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/"))
        self.assertEqual(
            self.saved_order()["meals"], {"Day 4": {"meal_id": "cheese-pizza", "price_cents": 1100}}
        )

        html = self.client.get("/").get_data(as_text=True)
        self.assertEqual(checked_values(html, "package"), ["6-day"])
        self.assertEqual(checked_values(html, "days"), ["Day 2", "Day 4", "Day 6"])

        html = self.client.get("/meals").get_data(as_text=True)
        self.assertEqual(checked_values(html, "meal-day-4"), ["cheese-pizza"])

    def test_changing_days_keeps_meals_for_days_still_selected(self):
        self.choose_package("4-day", ["Day 1", "Day 2"])
        self.client.post("/meals", data={"meal-day-1": "cheese-pizza", "meal-day-2": "pepperoni-pizza"})

        # Go back, swap Day 2 for Day 8, and switch packages.
        self.choose_package("6-day", ["Day 1", "Day 8"])
        self.assertEqual(
            self.saved_order(),
            self.order("6-day", ["Day 1", "Day 8"], {"Day 1": {"meal_id": "cheese-pizza", "price_cents": 1100}}),
        )


if __name__ == "__main__":
    unittest.main()
