"""
Summer Camp Lunch Package Registration - Tucker Road Ice Rink
Issue #2: Select a Lunch Package
Issue #3: Choose Daily Meals

Page 1 ("/") lets a parent pick one lunch package and the camp days they need,
up to that package's limit. Page 2 ("/meals") lets them pick one meal for each
of those days.

The browser (static/script.js and static/meals.js) checks choices as the parent
clicks, and this file checks everything again on the server. We check twice
because anything done only in the browser can be skipped or changed.

The in-progress order is kept in Flask's session (see save_order below).
A database will be added in a later issue.
"""

import os

from flask import (
    Flask,
    flash,
    get_flashed_messages,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

app = Flask(__name__)

# Flask's session is stored in a cookie in the parent's browser. The cookie is
# signed with SECRET_KEY, so the browser can read it but can't change it without
# Flask noticing. Before deploying, set a long random SECRET_KEY environment
# variable. The fallback below is only for running the app on your own computer.
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-not-a-real-secret")

# The three lunch packages. "lunches" is how many camp days the parent may pick.
# Keeping this in one list means we only have to change it in one place later.
PACKAGES = [
    {"id": "4-day", "name": "4-Day Package", "lunches": 4},
    {"id": "6-day", "name": "6-Day Package", "lunches": 6},
    {"id": "12-day", "name": "12-Day Package", "lunches": 12},
]

# Temporary camp days. The official dates have not been entered yet,
# so we use "Day 1" through "Day 12" as placeholders.
CAMP_DAYS = [f"Day {number}" for number in range(1, 13)]

# The meals on the menu. "id" never changes, so it is what we store in the order.
# Prices are whole numbers of cents (1100 = $11.00). Whole numbers avoid the
# rounding mistakes that decimals like 11.10 can cause in Python.
MEALS = [
    {"id": "chicken-tenders", "name": "Chicken Tenders + Fries + Drink", "price_cents": 1100},
    {"id": "cheese-pizza", "name": "Cheese Pizza + Fries + Drink", "price_cents": 1100},
    {"id": "pepperoni-pizza", "name": "Pepperoni Pizza + Fries + Drink", "price_cents": 1200},
]


# ---------- Small helper functions ----------

def find_package(package_id):
    """Return the package that matches package_id, or None if there is no match."""
    for package in PACKAGES:
        if package["id"] == package_id:
            return package
    return None


def find_meal(meal_id):
    """Return the meal that matches meal_id, or None if it isn't on the menu."""
    for meal in MEALS:
        if meal["id"] == meal_id:
            return meal
    return None


@app.template_filter("price")
def format_price(cents):
    """Turn cents into price text for the page: 1100 -> "$11", 1150 -> "$11.50"."""
    dollars, extra_cents = divmod(cents, 100)
    if extra_cents == 0:
        return f"${dollars}"
    return f"${dollars}.{extra_cents:02d}"


def meal_field_name(day):
    """Form field name for one day's meal choice, e.g. "Day 3" -> "meal-day-3"."""
    return "meal-" + day.lower().replace(" ", "-")


def join_days(days):
    """Make a readable list: "Day 1", "Day 1 and Day 2", "Day 1, Day 2, and Day 3"."""
    if len(days) <= 2:
        return " and ".join(days)
    return ", ".join(days[:-1]) + ", and " + days[-1]


def clean_days(raw_days):
    """Keep only real camp days, in calendar order, with no duplicates."""
    if not isinstance(raw_days, list):
        return []
    return [day for day in CAMP_DAYS if day in raw_days]


def check_package_selection(package, days):
    """Return an error message if the package/day choice is not allowed, or None if it is.

    These messages match the ones in script.js, so the parent sees the
    same wording whether the browser or the server catches the problem.
    """
    if package is None and len(days) == 0:
        return "Please choose a lunch package and at least one camp day."
    if package is None:
        return "Please choose a lunch package."
    if len(days) == 0:
        return "Please choose at least one camp day."
    if len(days) > package["lunches"]:
        extra = len(days) - package["lunches"]
        return (
            f"The {package['name']} includes {package['lunches']} lunches, "
            f"but {len(days)} days are selected. "
            f"Please unselect {extra} {'day' if extra == 1 else 'days'}."
        )
    return None


# ---------- The in-progress order (stored in the session) ----------
#
# session["order"] looks like this:
#   {
#       "status": "in_progress",
#       "package_id": "6-day",
#       "days": ["Day 1", "Day 3"],
#       "meals": {
#           "Day 1": {"meal_id": "cheese-pizza", "price_cents": 1100},
#       },
#   }
# A day only appears in "meals" once a meal has been chosen for it.


def clean_meals(raw_meals, days):
    """Keep only meal choices for the given days that match a real menu item.

    The price is always copied from MEALS, never from what was stored or sent.
    """
    if not isinstance(raw_meals, dict):
        return {}
    meals = {}
    for day in days:
        entry = raw_meals.get(day)
        meal = find_meal(entry.get("meal_id")) if isinstance(entry, dict) else None
        if meal is not None:
            meals[day] = {"meal_id": meal["id"], "price_cents": meal["price_cents"]}
    return meals


def meals_from_choices(choices, days):
    """Turn {day: meal_id} into the saved format, with prices looked up in MEALS."""
    return clean_meals({day: {"meal_id": meal_id} for day, meal_id in choices.items()}, days)


def save_order(package, days, meals):
    """Save the package, days, and meal choices together as one in-progress order."""
    session["order"] = {
        "status": "in_progress",
        "package_id": package["id"],
        "days": days,
        "meals": meals,
    }


def load_order():
    """Read the in-progress order from the session and check it again.

    Returns (order, None) if it is usable, or (None, error_message) if not.
    The session is signed, but we still check it against PACKAGES, CAMP_DAYS,
    and MEALS so bad data can never reach the meal page.
    """
    saved = session.get("order")
    if not isinstance(saved, dict):
        return None, "Please choose a lunch package and camp days before choosing meals."

    package = find_package(saved.get("package_id"))
    days = clean_days(saved.get("days"))
    error = check_package_selection(package, days)
    if error:
        return None, error

    order = {
        "package": package,
        "days": days,
        "meals": clean_meals(saved.get("meals"), days),
    }
    return order, None


def read_meal_choices(form, days):
    """Read the meal choices sent from the meal page.

    Returns (choices, error, problem_days):
      choices      - {day: meal_id} for every day that has a real menu item
      error        - a message to show the parent, or None if everything is valid
      problem_days - days to highlight on the page

    Only the meal ID for each selected day is read. Anything else the browser
    sends (meal names, prices, extra days) is ignored or rejected.
    """
    choices = {}
    missing = []
    not_on_menu = []
    more_than_one = []

    for day in days:
        values = form.getlist(meal_field_name(day))
        if len(values) == 0 or values[0] == "":
            missing.append(day)
        elif len(values) > 1:
            more_than_one.append(day)
        elif find_meal(values[0]) is None:
            not_on_menu.append(day)
        else:
            choices[day] = values[0]

    # Meal fields for days that are not in the order should never be sent.
    allowed_fields = {meal_field_name(day) for day in days}
    extra_fields = [key for key in form if key.startswith("meal-") and key not in allowed_fields]

    if extra_fields:
        error = (
            "Meals can only be chosen for the camp days in your order. "
            "To add a day, go back to your package and days."
        )
        return choices, error, []
    if more_than_one:
        return choices, f"Please choose only one meal for {join_days(more_than_one)}.", more_than_one
    if not_on_menu:
        return choices, f"Please choose a meal from the menu for {join_days(not_on_menu)}.", not_on_menu
    if missing:
        return choices, f"Please choose a meal for {join_days(missing)}.", missing
    return choices, None, []


# ---------- Pages ----------

@app.route("/", methods=["GET", "POST"])
def index():
    """Page 1: choose a lunch package and camp days."""
    selected_package_id = None
    selected_days = []
    error = None

    # A POST request means the parent pressed the "Confirm Selection" button.
    if request.method == "POST":
        selected_package_id = request.form.get("package")
        # getlist() collects every checked "days" checkbox into a list.
        # clean_days() keeps only real camp days and removes duplicates.
        selected_days = clean_days(request.form.getlist("days"))

        package = find_package(selected_package_id)
        error = check_package_selection(package, selected_days)

        if error is None:
            # Keep any meals already chosen for days that are still selected,
            # so changing the package or days doesn't erase them.
            previous = session.get("order")
            previous_meals = previous.get("meals") if isinstance(previous, dict) else None
            save_order(package, selected_days, clean_meals(previous_meals, selected_days))

            day_count = len(selected_days)
            flash(
                f"Lunch package selection confirmed: {package['name']} with "
                f"{day_count} camp {'day' if day_count == 1 else 'days'} selected.",
                "package-confirmed",
            )
            # Redirecting (instead of showing a page) means refreshing the
            # meal page won't ask the browser to send this form again.
            return redirect(url_for("meals"))
    else:
        # Coming back to this page: show the package and days already in the
        # order, so nothing is lost.
        saved = session.get("order")
        if isinstance(saved, dict):
            if find_package(saved.get("package_id")) is not None:
                selected_package_id = saved.get("package_id")
            selected_days = clean_days(saved.get("days"))

        # A message sent here from the meal page (for example, "choose a package first").
        errors = get_flashed_messages(category_filter=["error"])
        if errors:
            error = errors[0]

    return render_template(
        "index.html",
        packages=PACKAGES,
        camp_days=CAMP_DAYS,
        selected_package_id=selected_package_id,
        selected_days=selected_days,
        error=error,
    )


@app.route("/meals", methods=["GET", "POST"])
def meals():
    """Page 2: choose one meal for each selected camp day."""
    order, order_error = load_order()
    if order is None:
        # No valid package and days yet, so send the parent back to page 1.
        flash(order_error, "error")
        return redirect(url_for("index"))

    package = order["package"]
    days = order["days"]
    # The meal shown as chosen for each day: {day: meal_id}
    choices = {day: entry["meal_id"] for day, entry in order["meals"].items()}
    error = None
    problem_days = []

    if request.method == "POST":
        submitted, error, problem_days = read_meal_choices(request.form, days)

        if request.form.get("action") == "back":
            # "Back to Package & Days": keep the valid choices made so far
            # (even if some days are still empty) and go back to page 1.
            choices.update(submitted)
            save_order(package, days, meals_from_choices(choices, days))
            return redirect(url_for("index"))

        if error is None:
            # Everything is valid. Look up each meal's price on the server and save.
            save_order(package, days, meals_from_choices(submitted, days))
            day_count = len(days)
            flash(
                f"Meal choices saved for all {day_count} camp "
                f"{'day' if day_count == 1 else 'days'}. "
                f"Your {package['name']} order is in progress.",
                "meals-saved",
            )
            return redirect(url_for("meals"))

        # Something is wrong: show the page again with the parent's valid
        # choices still selected and the error message near the save button.
        choices = submitted

    # Messages sent from a redirect (package confirmed, or meals saved).
    package_message = None
    success = None
    for category, message in get_flashed_messages(with_categories=True):
        if category == "package-confirmed":
            package_message = message
        elif category == "meals-saved":
            success = message

    day_rows = [
        {
            "day": day,
            "field": meal_field_name(day),
            "selected": choices.get(day),
            "has_problem": day in problem_days,
        }
        for day in days
    ]

    return render_template(
        "meals.html",
        package=package,
        days=days,
        day_rows=day_rows,
        meals=MEALS,
        chosen_count=len(choices),
        package_message=package_message,
        error=error,
        success=success,
    )


# This lets you start the app with "python app.py".
# debug=True reloads the server when you save a file. Turn it off before deploying.
if __name__ == "__main__":
    app.run(debug=True)
