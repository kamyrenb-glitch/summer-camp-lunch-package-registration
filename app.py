"""
Summer Camp Lunch Package Registration - Tucker Road Ice Rink
Issue #1: Register a Camper
Issue #2: Select a Lunch Package
Issue #3: Choose Daily Meals

Page 1 ("/register") saves the camper and the parent or guardian's contact
information in the database. Page 2 ("/") lets the parent pick one lunch
package and the camp days they need. Page 3 ("/meals") lets them pick one
meal for each of those days.

The browser (static/register.js, static/script.js, and static/meals.js) checks
choices as the parent types and clicks, and this file checks everything again
on the server. We check twice because anything done only in the browser can be
skipped or changed.

What is stored where:
  - The database holds camper and contact information (see models.py).
  - Flask's session holds only the camper's database ID and the in-progress
    lunch order (package, days, and meal IDs). No names, emails, or phone
    numbers are ever put in the session.

To start the app:  flask --app app run --debug   (or: python app.py)
"""

import os
import secrets
from functools import wraps

import click
from flask import (
    Blueprint,
    Flask,
    flash,
    get_flashed_messages,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask.cli import with_appcontext
from sqlalchemy.exc import SQLAlchemyError

from models import Camper, Guardian, db
from registration import FIELDS, error_summary, format_phone, normalize_phone, validate_registration

# All of the pages live in this "blueprint". create_app() attaches it to the app.
# In templates, pages are named like url_for("main.index").
bp = Blueprint("main", __name__)

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


# ---------- Settings: database and secret key ----------

def get_database_url(instance_path):
    """Pick which database to use.

    - If the DATABASE_URL environment variable is set (for example, the
      Supabase PostgreSQL connection string), use it.
    - Otherwise, use a local SQLite file in the instance/ folder. This is only
      for development on your own computer.
    """
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        # Supabase gives URLs starting with "postgresql://" (some hosts use
        # "postgres://"). Tell SQLAlchemy to use the psycopg2 driver from
        # requirements.txt, since newer SQLAlchemy versions otherwise look for
        # a different driver.
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                url = "postgresql+psycopg2://" + url[len(prefix):]
        return url
    return "sqlite:///" + os.path.join(instance_path, "lunch_dev.db")


def get_secret_key(instance_path):
    """Return the key used to sign the session cookie.

    - If the SECRET_KEY environment variable is set, use it.
    - When using a deployed database (DATABASE_URL is set), SECRET_KEY is
      required, so the app stops with a clear message instead of running unsafely.
    - For local development, make a random key once and keep it in
      instance/dev_secret_key (git ignores this folder), so you stay
      registered when the server restarts.
    """
    key = os.environ.get("SECRET_KEY", "").strip()
    if key:
        return key
    if os.environ.get("DATABASE_URL", "").strip():
        raise RuntimeError(
            "SECRET_KEY must be set when DATABASE_URL is set. "
            "See .env.example and the README."
        )
    key_file = os.path.join(instance_path, "dev_secret_key")
    if not os.path.exists(key_file):
        with open(key_file, "w", encoding="utf-8") as file:
            file.write(secrets.token_hex(32))
    with open(key_file, encoding="utf-8") as file:
        return file.read().strip()


@click.command("init-db")
@with_appcontext
def init_db_command():
    """Create any database tables that don't exist yet.

    Safe to run more than once: create_all() only adds missing tables.
    It never deletes tables or data.
    """
    db.create_all()
    click.echo("Database tables are ready.")


def create_app(test_config=None):
    """Build and configure the Flask app.

    The "flask" command finds this function automatically. Tests call it with
    test_config to use their own temporary database.
    """
    app = Flask(__name__, instance_relative_config=True)

    if test_config is None:
        # The instance/ folder holds files that belong to this computer only.
        os.makedirs(app.instance_path, exist_ok=True)
        app.config["SQLALCHEMY_DATABASE_URI"] = get_database_url(app.instance_path)
        app.config["SECRET_KEY"] = get_secret_key(app.instance_path)
    else:
        app.config.update(test_config)

    # pool_pre_ping checks a connection still works before using it.
    # Hosted databases like Supabase close connections that sit idle.
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}

    db.init_app(app)
    app.register_blueprint(bp)
    app.cli.add_command(init_db_command)
    app.add_template_filter(format_price, "price")

    # For the local SQLite file only, create missing tables automatically so
    # the app works right away. A deployed database is set up once with
    # "flask --app app init-db" instead (see the README).
    using_local_sqlite = test_config is None and not os.environ.get("DATABASE_URL", "").strip()
    if using_local_sqlite:
        with app.app_context():
            db.create_all()

    return app


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


# ---------- The registered camper ----------
#
# session["camper_id"] holds only the camper's database ID (a number).
# Everything else about the camper is looked up in the database.


def get_current_camper():
    """Return the Camper for this browser session, or None if not registered.

    The ID comes from the signed session cookie, but we still check that it is
    a whole number and that the camper really exists in the database.
    """
    camper_id = session.get("camper_id")
    # bool is a kind of int in Python, so rule it out on purpose.
    if not isinstance(camper_id, int) or isinstance(camper_id, bool):
        return None
    camper = db.session.get(Camper, camper_id)
    if camper is None:
        # The record is gone, so the session (and its order) no longer makes sense.
        session.pop("camper_id", None)
        session.pop("order", None)
    return camper


def registration_required(view):
    """Send the parent to the registration page if no camper is registered yet.

    Put @registration_required above a page function. The page then receives
    the registered camper as its "camper" argument.
    """
    @wraps(view)
    def wrapped(*args, **kwargs):
        camper = get_current_camper()
        if camper is None:
            flash("Please register your camper before ordering lunches.", "info")
            return redirect(url_for("main.register"))
        return view(camper, *args, **kwargs)

    return wrapped


# ---------- The in-progress order (stored in the session) ----------
#
# session["order"] looks like this:
#   {
#       "status": "in_progress",
#       "camper_id": 7,
#       "package_id": "6-day",
#       "days": ["Day 1", "Day 3"],
#       "meals": {
#           "Day 1": {"meal_id": "cheese-pizza", "price_cents": 1100},
#       },
#   }
# A day only appears in "meals" once a meal has been chosen for it.
# "camper_id" ties the order to the registered camper's database record.


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


def save_order(camper, package, days, meals):
    """Save the package, days, and meal choices together as one in-progress order."""
    session["order"] = {
        "status": "in_progress",
        "camper_id": camper.id,
        "package_id": package["id"],
        "days": days,
        "meals": meals,
    }


def get_saved_order(camper):
    """Return the raw saved order if it belongs to this camper, or None."""
    saved = session.get("order")
    if isinstance(saved, dict) and saved.get("camper_id") == camper.id:
        return saved
    return None


def load_order(camper):
    """Read the in-progress order from the session and check it again.

    Returns (order, None) if it is usable, or (None, error_message) if not.
    The session is signed, but we still check it against PACKAGES, CAMP_DAYS,
    and MEALS so bad data can never reach the meal page.
    """
    saved = get_saved_order(camper)
    if saved is None:
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

@bp.route("/register", methods=["GET", "POST"])
def register():
    """Register a camper, or edit the registered camper's information."""
    # If this browser already registered a camper, this page edits that record.
    # The camper is found only from the session, never from an ID in the form.
    camper = get_current_camper()
    errors = {}
    summary = None

    if request.method == "POST":
        values, errors = validate_registration(request.form)

        if not errors:
            phone = normalize_phone(values["guardian_phone"])
            email = values["guardian_email"].lower()
            is_new = camper is None
            try:
                if is_new:
                    guardian = Guardian(full_name=values["guardian_name"], email=email, phone=phone)
                    camper = Camper(
                        first_name=values["camper_first_name"],
                        last_name=values["camper_last_name"],
                        guardian=guardian,
                    )
                    db.session.add(camper)
                else:
                    # Update the same records instead of making new ones.
                    camper.first_name = values["camper_first_name"]
                    camper.last_name = values["camper_last_name"]
                    camper.guardian.full_name = values["guardian_name"]
                    camper.guardian.email = email
                    camper.guardian.phone = phone
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
                summary = "We couldn't save your information right now. Please try again."
            else:
                if is_new:
                    session["camper_id"] = camper.id
                    # A new camper starts with a fresh order.
                    session.pop("order", None)
                    flash(f"Thanks! {camper.full_name} is registered. Next, choose a lunch package.", "registered")
                else:
                    # The package, days, and meals in the order are kept as they are.
                    flash("Camper and contact information updated.", "registered")
                return redirect(url_for("main.index"))
        else:
            summary = error_summary(errors)
    elif camper is not None:
        # Editing: fill the form from the database.
        values = {
            "camper_first_name": camper.first_name,
            "camper_last_name": camper.last_name,
            "guardian_name": camper.guardian.full_name,
            "guardian_email": camper.guardian.email,
            "guardian_phone": format_phone(camper.guardian.phone),
        }
    else:
        values = {name: "" for name, _, _ in FIELDS}

    infos = get_flashed_messages(category_filter=["info"])

    return render_template(
        "register.html",
        editing=camper is not None,
        values=values,
        errors=errors,
        summary=summary,
        max_lengths={name: max_length for name, _, max_length in FIELDS},
        info=infos[0] if infos else None,
    )


@bp.route("/", methods=["GET", "POST"])
@registration_required
def index(camper):
    """Choose a lunch package and camp days."""
    selected_package_id = None
    selected_days = []
    error = None
    notice = None

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
            previous = get_saved_order(camper)
            previous_meals = previous.get("meals") if previous else None
            save_order(camper, package, selected_days, clean_meals(previous_meals, selected_days))

            day_count = len(selected_days)
            flash(
                f"Lunch package selection confirmed: {package['name']} with "
                f"{day_count} camp {'day' if day_count == 1 else 'days'} selected.",
                "package-confirmed",
            )
            # Redirecting (instead of showing a page) means refreshing the
            # meal page won't ask the browser to send this form again.
            return redirect(url_for("main.meals"))
    else:
        # Coming back to this page: show the package and days already in the
        # order, so nothing is lost.
        saved = get_saved_order(camper)
        if saved is not None:
            if find_package(saved.get("package_id")) is not None:
                selected_package_id = saved.get("package_id")
            selected_days = clean_days(saved.get("days"))

        # Messages sent here from another page (for example, "choose a package
        # first"). If more than one is waiting, show the newest.
        errors = get_flashed_messages(category_filter=["error"])
        if errors:
            error = errors[-1]
        notices = get_flashed_messages(category_filter=["registered"])
        if notices:
            notice = notices[-1]

    return render_template(
        "index.html",
        camper=camper,
        packages=PACKAGES,
        camp_days=CAMP_DAYS,
        selected_package_id=selected_package_id,
        selected_days=selected_days,
        error=error,
        notice=notice,
    )


@bp.route("/meals", methods=["GET", "POST"])
@registration_required
def meals(camper):
    """Choose one meal for each selected camp day."""
    order, order_error = load_order(camper)
    if order is None:
        # No valid package and days yet, so send the parent back to the package page.
        flash(order_error, "error")
        return redirect(url_for("main.index"))

    package = order["package"]
    days = order["days"]
    # The meal shown as chosen for each day: {day: meal_id}
    choices = {day: entry["meal_id"] for day, entry in order["meals"].items()}
    error = None
    problem_days = []

    if request.method == "POST":
        submitted, error, problem_days = read_meal_choices(request.form, days)
        action = request.form.get("action")

        if action in ("back", "edit-camper"):
            # "Back to Package & Days" or "Edit camper & contact information":
            # keep the valid choices made so far (even if some days are still
            # empty) before leaving the page.
            choices.update(submitted)
            save_order(camper, package, days, meals_from_choices(choices, days))
            if action == "edit-camper":
                return redirect(url_for("main.register"))
            return redirect(url_for("main.index"))

        if error is None:
            # Everything is valid. Look up each meal's price on the server and save.
            save_order(camper, package, days, meals_from_choices(submitted, days))
            day_count = len(days)
            flash(
                f"Meal choices saved for all {day_count} camp "
                f"{'day' if day_count == 1 else 'days'}. "
                f"Your {package['name']} order is in progress.",
                "meals-saved",
            )
            return redirect(url_for("main.meals"))

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
        camper=camper,
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
    # Read settings from a .env file, if there is one. ("flask run" does this by itself.)
    from dotenv import load_dotenv

    load_dotenv()
    create_app().run(debug=True)
