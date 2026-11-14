"""
Automated tests for the "Editing your order" bar (Issue #4).

When the parent leaves the review page to change the package, days, or meals,
the package and meal pages show a bar with a "Return to Review" button.

Run them from the project folder with:
    python -m unittest discover tests
"""

import re
import unittest

from base import AppTestCase, form_message

SAVED_MEALS = {"Day 2": "chicken-tenders", "Day 4": "cheese-pizza", "Day 6": "pepperoni-pizza"}


def meal_field(day):
    return "meal-" + day.lower().replace(" ", "-")


def has_bar(html):
    return 'class="edit-bar"' in html


def saved_state(html):
    return re.search(r'data-saved-state="([^"]*)"', html).group(1)


def order_total(html):
    return re.search(r'id="order-total">(.*?)<', html).group(1)


class EditNavigationTestCase(AppTestCase):
    def setUp(self):
        super().setUp()
        self.register()
        # A complete order: 6-day package, Day 2/4/6, a meal for each day.
        self.client.post("/", data={"package": "6-day", "days": list(SAVED_MEALS)})
        self.client.post("/meals", data={meal_field(day): meal for day, meal in SAVED_MEALS.items()})

    def get(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, path)
        return response.get_data(as_text=True)

    def flag(self):
        return self.session_data().get("return_to_review")

    # ----- When the bar shows -----

    def test_no_bar_without_coming_from_review(self):
        self.assertFalse(has_bar(self.get("/")))
        self.assertFalse(has_bar(self.get("/meals")))

    def test_review_links_mark_the_trip(self):
        html = self.get("/review")
        self.assertIn('href="/?return_to=review"', html)
        self.assertIn('href="/meals?return_to=review"', html)

    def test_bar_on_package_page_from_review(self):
        self.get("/review")
        html = self.get("/?return_to=review")
        self.assertTrue(has_bar(html))
        self.assertIn('aria-label="Editing your order"', html)
        self.assertIn('<a id="return-to-review" class="button edit-bar-button" href="/review">Return to Review</a>', html)
        self.assertIn('data-track-form="package-form"', html)
        self.assertEqual(saved_state(html), "package=6-day&amp;days=Day 2&amp;days=Day 4&amp;days=Day 6")
        # The unsaved-changes warning is there, without a save option on this page.
        self.assertIn('id="unsaved-dialog"', html)
        self.assertIn("Discard Changes and Return", html)
        self.assertNotIn('value="save-review"', html)
        self.assertIn("/static/edit-bar.js", html)
        # The bottom button is still there.
        self.assertIn('id="confirm-button"', html)

    def test_bar_on_meal_page_from_review(self):
        self.get("/review")
        html = self.get("/meals?return_to=review")
        self.assertTrue(has_bar(html))
        self.assertIn('data-track-form="meal-form"', html)
        self.assertEqual(
            saved_state(html),
            "meal-day-2=chicken-tenders&amp;meal-day-4=cheese-pizza&amp;meal-day-6=pepperoni-pizza",
        )
        self.assertIn("Save any changes, then return to review.", html)
        # "Save and Return to Review" belongs to the meal form, but comes after
        # the normal Save button so pressing Enter still saves normally.
        self.assertIn('form="meal-form" name="action" value="save-review"', html)
        self.assertLess(html.index('id="save-button"'), html.index('value="save-review"'))
        # The bottom buttons are still there.
        for button in ('id="save-button"', 'id="back-button"', 'id="review-link"'):
            self.assertIn(button, html)

    def test_other_return_to_values_are_ignored(self):
        self.get("/?return_to=somewhere-else")
        self.assertIsNone(self.flag())
        self.assertFalse(has_bar(self.get("/")))

    def test_no_bar_without_an_order(self):
        with self.client.session_transaction() as session:
            session["return_to_review"] = True
            session.pop("order")
        self.assertFalse(has_bar(self.get("/")))

    def test_bar_stays_while_moving_between_edit_pages(self):
        self.get("/?return_to=review")
        # Confirm the same days -> meal page; the bar is still there.
        response = self.client.post("/", data={"package": "6-day", "days": list(SAVED_MEALS)})
        self.assertTrue(response.headers["Location"].endswith("/meals"))
        self.assertTrue(has_bar(self.get("/meals")))
        # "Back to Package & Days" keeps it too.
        self.client.post("/meals", data={"action": "back"})
        self.assertTrue(has_bar(self.get("/")))

    def test_opening_review_ends_the_editing_trip(self):
        self.get("/meals?return_to=review")
        self.assertTrue(self.flag())
        self.get("/review")
        self.assertIsNone(self.flag())
        self.assertFalse(has_bar(self.get("/meals")))

    # ----- Returning to review -----

    def test_return_without_saving_shows_the_saved_order(self):
        # Unsaved changes are never sent to the server, so returning shows
        # exactly what was saved before (the parent chose to discard).
        self.get("/meals?return_to=review")
        html = self.get("/review")
        self.assertEqual(order_total(html), "$34")

    def test_saved_changes_show_on_review(self):
        self.get("/meals?return_to=review")
        self.client.post("/meals", data={meal_field(day): "pepperoni-pizza" for day in SAVED_MEALS})
        self.assertEqual(order_total(self.get("/review")), "$36")

    def test_save_and_return_saves_then_opens_review(self):
        self.get("/meals?return_to=review")
        response = self.client.post("/meals", data={
            **{meal_field(day): "pepperoni-pizza" for day in SAVED_MEALS}, "action": "save-review",
        })
        self.assertTrue(response.headers["Location"].endswith("/review"))
        html = self.get("/review")
        self.assertEqual(order_total(html), "$36")
        self.assertIsNone(self.flag())

    def test_save_and_return_with_a_missing_meal_stays_on_meal_page(self):
        self.get("/meals?return_to=review")
        response = self.client.post("/meals", data={"meal-day-2": "cheese-pizza", "action": "save-review"})
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(form_message(html), "Please choose a meal for Day 4 and Day 6.")
        self.assertTrue(has_bar(html))
        # Nothing changed in the saved order.
        self.assertEqual(self.saved_order()["meals"]["Day 2"]["meal_id"], "chicken-tenders")

    def test_new_days_must_get_meals_before_review(self):
        self.get("/?return_to=review")
        # Add Day 8, which has no meal yet.
        self.client.post("/", data={"package": "6-day", "days": ["Day 2", "Day 4", "Day 6", "Day 8"]})

        html = " ".join(self.get("/meals").split())  # ignore line breaks and spacing
        self.assertIn("Day 8 needs a meal before you can return to review.", html)

        # The review page won't open with Day 8 missing a meal.
        response = self.client.get("/review")
        self.assertTrue(response.headers["Location"].endswith("/meals"))
        html = self.get("/meals")
        self.assertEqual(form_message(html), "Please choose a meal for Day 8 before reviewing your order.")
        self.assertIn('class="meal-day meal-day-invalid"', html)
        self.assertTrue(has_bar(html))  # still editing

        # Once Day 8 has a meal, the updated review and total show.
        self.client.post("/meals", data={
            **{meal_field(day): meal for day, meal in SAVED_MEALS.items()}, "meal-day-8": "cheese-pizza",
            "action": "save-review",
        })
        html = self.get("/review")
        self.assertIn("6-Day Package — 4 lunches selected", html)
        self.assertEqual(order_total(html), "$45")

    def test_confirming_ends_the_editing_trip(self):
        self.get("/meals?return_to=review")
        html = self.get("/review")
        token = re.search(r'name="confirmation_token" value="([^"]*)"', html).group(1)
        self.client.post("/review", data={"confirmation_token": token})
        self.assertIsNone(self.flag())
        self.assertFalse(has_bar(self.get("/")))


if __name__ == "__main__":
    unittest.main()
