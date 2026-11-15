"""
Summer Camp Lunch Package Registration - Tucker Road Ice Rink
Issue #1: Register a Camper
Issue #2: Select a Lunch Package
Issue #3: Choose Daily Meals
Issue #4: Review Order and Total
Issue #5: Track Lunch Orders
Issue #6: Manage Daily Orders

Page 1 ("/register") saves the camper and the parent or guardian's contact
information in the database. Page 2 ("/") lets the parent pick one lunch
package and the camp days they need. Page 3 ("/meals") lets them pick one
meal for each of those days. Page 4 ("/review") shows the whole order and
its total, and confirming it saves the order in the database. The status
page ("/order-status") shows how many lunches are ordered, completed, and
remaining, and the status of each one. If the café can't make a lunch, the
parent can choose a different meal for just that day.

Café attendants use "/cafe" (after entering the café passcode) to see each
camp day's lunches and update their status.

The browser (static/register.js, static/script.js, and static/meals.js) checks
choices as the parent types and clicks, and this file checks everything again
on the server. We check twice because anything done only in the browser can be
skipped or changed.

What is stored where:
  - The database holds camper and contact information (see models.py).
  - Flask's session holds only the camper's database ID, the in-progress
    lunch order (package, days, and meal IDs), and the ID of the last
    confirmed order. No names, emails, or phone numbers are ever put in
    the session.
  - Confirmed orders and their daily lunches are saved in the database.

To start the app:  flask --app app run --debug   (or: python app.py)
"""

import hmac
import os
import secrets
from functools import wraps

import click
from flask import (
    Blueprint,
    Flask,
    abort,
    current_app,
    flash,
    get_flashed_messages,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask.cli import with_appcontext
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from models import Camper, DailyLunch, Guardian, LunchHistory, Order, db
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
        # The shared passcode café attendants enter to open the daily-orders
        # page. If it isn't set, the café pages stay locked.
        app.config["CAFE_PASSCODE"] = os.environ.get("CAFE_PASSCODE", "").strip()
    else:
        app.config.update(test_config)

    # "Lax" tells browsers not to send the session cookie with forms posted
    # from other websites, so another site can't submit changes for a parent
    # or café attendant who is signed in here.
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")

    # pool_pre_ping checks a connection still works before using it.
    # Hosted databases like Supabase close connections that sit idle.
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}

    db.init_app(app)
    app.register_blueprint(bp)
    app.cli.add_command(init_db_command)
    app.add_template_filter(format_price, "price")
    app.context_processor(navigation_context)
    app.register_error_handler(404, page_not_found)
    app.register_error_handler(405, method_not_allowed)

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
        session.pop("last_order_id", None)
        session.pop("return_to_review", None)
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


# ---------- Returning after "Edit camper & contact information" ----------
#
# The edit link adds ?next=<name> (for example ?next=status) so that Save
# Changes and Cancel go back to the page the parent came from. Only the names
# below are accepted. Anything else, including a full web address, is ignored
# and the parent goes to the package page as before.

EDIT_RETURN_PAGES = {
    "package": "main.index",
    "meals": "main.meals",
    "review": "main.review",
    "confirmation": "main.order_confirmed",
    "status": "main.order_status",
}

# The return name each parent page puts on its edit link. The change-meal page
# needs a lunch number, so it returns to the status page instead.
EDIT_RETURN_BY_PAGE = {
    "main.index": "package",
    "main.meals": "meals",
    "main.review": "review",
    "main.order_confirmed": "confirmation",
    "main.order_status": "status",
    "main.change_meal": "status",
}


def edit_return_name(value):
    """Return value if it's one of the allowed return names, otherwise None."""
    return value if value in EDIT_RETURN_PAGES else None


def edit_return_url(name):
    """The page to go to after editing; the package page if name isn't allowed."""
    return url_for(EDIT_RETURN_PAGES.get(name, "main.index"))


def take_camper_updated_message():
    """The "information updated" message waiting to be shown, or None.

    The camper bar calls this, so the message appears on whichever page the
    parent returns to after editing.
    """
    messages = get_flashed_messages(category_filter=["camper-updated"])
    return messages[-1] if messages else None


def navigation_context():
    """Values every template can use (Flask adds these automatically)."""
    return {
        # Footer: "Café daily orders" instead of "Café staff sign in" once signed in.
        "cafe_signed_in": cafe_signed_in(),
        # Camper bar: which page the edit link should come back to.
        "edit_return": EDIT_RETURN_BY_PAGE.get(request.endpoint),
        "camper_updated_message": take_camper_updated_message,
    }


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


# ---------- Reviewing and confirming the order ----------

def days_missing_meals(order):
    """Return the camp days in the order that don't have a meal yet."""
    return [day for day in order["days"] if day not in order["meals"]]


def order_lines(order):
    """List each camp day with its meal and price, for the review page.

    The meal name and price are looked up in MEALS on the server.
    """
    lines = []
    for day in order["days"]:
        meal = find_meal(order["meals"][day]["meal_id"])
        lines.append({"day": day, "meal_name": meal["name"], "price_cents": meal["price_cents"]})
    return lines


def calculate_total_cents(lines):
    """Add up the price of every lunch, in cents."""
    return sum(line["price_cents"] for line in lines)


def find_confirmed_order(camper, token):
    """Return this camper's order that was saved with this confirmation code, if any."""
    if not token:
        return None
    return db.session.scalar(
        db.select(Order).filter_by(camper_id=camper.id, confirmation_token=token)
    )


def already_ordered_days(camper, days):
    """Return which of these camp days already have a confirmed lunch for this camper."""
    taken = set(db.session.scalars(
        db.select(DailyLunch.camp_day).where(
            DailyLunch.camper_id == camper.id, DailyLunch.camp_day.in_(days)
        )
    ))
    return [day for day in days if day in taken]


def save_confirmed_order(camper, order, token):
    """Save the order and its daily lunches in the database.

    Returns (saved_order, conflict_days):
      - (order, [])   the order was saved, or had already been saved
      - (None, days)  nothing was saved because the camper already has a
                      confirmed lunch on these days
      - (None, [])    nothing was saved for another reason

    If an order with this confirmation code was already saved (for example,
    "Confirm Order" was clicked twice), that order is returned instead of
    saving a second copy. The database also refuses a duplicate order code
    and a second lunch for the same camper on the same day, so even two
    requests arriving at the same moment can't get around these rules.
    """
    existing = find_confirmed_order(camper, token)
    if existing is not None:
        return existing, []

    conflicts = already_ordered_days(camper, order["days"])
    if conflicts:
        return None, conflicts

    lines = order_lines(order)
    new_order = Order(
        camper=camper,
        package_id=order["package"]["id"],
        total_cents=calculate_total_cents(lines),
        status="confirmed",
        confirmation_token=token,
        daily_lunches=[
            DailyLunch(
                camper_id=camper.id,
                camp_day=day,
                meal_id=order["meals"][day]["meal_id"],
                price_cents=line["price_cents"],
                status="ordered",
            )
            for day, line in zip(order["days"], lines)
        ],
    )
    db.session.add(new_order)
    try:
        # The order and all its lunches are saved together, or not at all.
        db.session.commit()
    except IntegrityError:
        # Another request got there first. Nothing from this request was saved.
        db.session.rollback()
        existing = find_confirmed_order(camper, token)
        if existing is not None:
            # It was this same order (a double click), so use that one.
            return existing, []
        # Otherwise another order took one of these days.
        return None, already_ordered_days(camper, order["days"])
    return new_order, []


# ---------- Editing the order from the review page ----------
#
# session["return_to_review"] is True while the parent is changing the order
# after leaving the review page with "Change package or days" or "Change meals".
# The package and meal pages then show an "Editing your order" bar with a
# "Return to Review" button. Opening the review page again ends it.


def remember_return_to_review():
    """Note that the parent came from the review page (its links add ?return_to=review)."""
    if request.method == "GET" and request.args.get("return_to") == "review":
        session["return_to_review"] = True


def end_return_to_review():
    session.pop("return_to_review", None)


def review_bar(camper, page):
    """Return what the "Editing your order" bar needs, or None if it shouldn't show.

    page is "package" or "meals".
      missing_days - saved days that still need a meal. The review page
                     won't open until they have one, so the bar says so.
      saved_state  - what is saved right now, written the same way edit-bar.js
                     describes the page (e.g. "package=6-day&days=Day 2"), so it
                     can tell whether there are unsaved changes.
    """
    if session.get("return_to_review") is not True:
        return None
    order, _ = load_order(camper)
    if order is None:
        return None

    if page == "package":
        parts = [f"package={order['package']['id']}"] + [f"days={day}" for day in order["days"]]
    else:
        parts = [
            f"{meal_field_name(day)}={order['meals'][day]['meal_id']}"
            for day in order["days"]
            if day in order["meals"]
        ]

    missing = days_missing_meals(order)
    return {"missing_days": missing, "missing_text": join_days(missing), "saved_state": "&".join(parts)}


def lines_from_saved_order(saved_order):
    """List a confirmed order's lunches (from the database) for display."""
    return [
        {
            "day": lunch.camp_day,
            "meal_name": (find_meal(lunch.meal_id) or {"name": lunch.meal_id})["name"],
            "price_cents": lunch.price_cents,
        }
        for lunch in saved_order.daily_lunches
    ]


# ---------- Pages ----------

@bp.route("/register", methods=["GET", "POST"])
def register():
    """Register a camper, or edit the registered camper's information."""
    # If this browser already registered a camper, this page edits that record.
    # The camper is found only from the session, never from an ID in the form.
    camper = get_current_camper()
    errors = {}
    summary = None
    # Where Save Changes and Cancel go when editing (see EDIT_RETURN_PAGES).
    # It comes from the link (?next=) or the form's hidden field, and is only
    # used if it's one of the allowed names.
    return_name = edit_return_name(request.values.get("next")) if camper is not None else None

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
                    session.pop("last_order_id", None)
                    session.pop("return_to_review", None)
                    flash(f"Thanks! {camper.full_name} is registered. Next, choose a lunch package.", "registered")
                    return redirect(url_for("main.index"))
                # Editing: the package, days, and meals in the order are kept
                # as they are. Go back to the page the parent came from.
                flash("Camper and contact information updated.", "camper-updated")
                return redirect(edit_return_url(return_name))
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
        return_name=return_name,
        cancel_url=edit_return_url(return_name),
    )


@bp.route("/", methods=["GET", "POST"])
@registration_required
def index(camper):
    """Choose a lunch package and camp days."""
    remember_return_to_review()
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
        review_bar=review_bar(camper, "package"),
    )


@bp.route("/meals", methods=["GET", "POST"])
@registration_required
def meals(camper):
    """Choose one meal for each selected camp day."""
    remember_return_to_review()
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
                return redirect(url_for("main.register", next="meals"))
            return redirect(url_for("main.index"))

        if error is None:
            # Everything is valid. Look up each meal's price on the server and save.
            save_order(camper, package, days, meals_from_choices(submitted, days))
            if action == "save-review":
                # "Save and Return to Review" from the "Editing your order" bar.
                return redirect(url_for("main.review"))
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

    # Messages sent from a redirect (package confirmed, meals saved, or the
    # review page saying some days still need a meal).
    package_message = None
    success = None
    for category, message in get_flashed_messages(with_categories=True):
        if category == "package-confirmed":
            package_message = message
        elif category == "meals-saved":
            success = message
        elif category == "error":
            error = message
            problem_days = days_missing_meals(order)

    # Show "Review Order" once every day has a saved meal (and nothing is wrong).
    ready_for_review = error is None and not days_missing_meals(order)

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
        ready_for_review=ready_for_review,
        review_bar=review_bar(camper, "meals"),
    )


@bp.route("/review", methods=["GET", "POST"])
@registration_required
def review(camper):
    """Review the whole order and its total, then confirm it."""
    # A POST means "Confirm Order" was pressed. If an order was already saved
    # with this confirmation code (a second click, or the browser sending the
    # form again), just show that order instead of saving another one.
    token = request.form.get("confirmation_token", "") if request.method == "POST" else ""
    already_saved = find_confirmed_order(camper, token)
    if already_saved is not None:
        session.pop("order", None)
        end_return_to_review()
        session["last_order_id"] = already_saved.id
        return redirect(url_for("main.order_confirmed"))

    order, order_error = load_order(camper)
    if order is None:
        flash(order_error, "error")
        return redirect(url_for("main.index"))

    missing = days_missing_meals(order)
    if missing:
        flash(f"Please choose a meal for {join_days(missing)} before reviewing your order.", "error")
        return redirect(url_for("main.meals"))

    saved = get_saved_order(camper)
    expected_token = saved.get("confirmation_token")

    if request.method == "POST":
        # The code in the form must match the order in the session. If it
        # doesn't, the order changed (for example, in another tab) after this
        # review page was opened, so show the latest version instead.
        if not isinstance(expected_token, str) or token != expected_token:
            flash("Your order changed since this page was opened. Please review it again.", "error")
            return redirect(url_for("main.review"))

        try:
            confirmed, conflict_days = save_confirmed_order(camper, order, token)
        except SQLAlchemyError:
            db.session.rollback()
            confirmed, conflict_days = None, []
        if conflict_days:
            # Nothing was saved. The review page shows which days are taken.
            return redirect(url_for("main.review"))
        if confirmed is None:
            flash("We couldn't save your order right now. Please try again.", "error")
            return redirect(url_for("main.review"))

        # The order is in the database now, so the in-progress copy is done.
        session.pop("order", None)
        end_return_to_review()
        session["last_order_id"] = confirmed.id
        return redirect(url_for("main.order_confirmed"))

    # Give this version of the order a new confirmation code. (save_order()
    # starts a fresh order without one whenever the package, days, or meals change.)
    if not isinstance(expected_token, str):
        saved["confirmation_token"] = secrets.token_urlsafe(32)
        session.modified = True  # tells Flask the session changed inside the dict

    # The parent is back on the review page, so any editing trip is over.
    end_return_to_review()

    errors = get_flashed_messages(category_filter=["error"])
    lines = order_lines(order)

    # A camper can only have one lunch per camp day, so point out any day
    # that is already in one of this camper's confirmed orders.
    conflict_days = already_ordered_days(camper, order["days"])
    for line in lines:
        line["conflict"] = line["day"] in conflict_days
    conflict_message = None
    if conflict_days:
        conflict_message = (
            f"{camper.full_name} already has a confirmed lunch on {join_days(conflict_days)}. "
            f"Each camper can have only one lunch per day, so please choose different camp days."
        )

    return render_template(
        "review.html",
        camper=camper,
        package=order["package"],
        lines=lines,
        total_cents=calculate_total_cents(lines),
        confirmation_token=saved["confirmation_token"],
        error=errors[-1] if errors else None,
        conflict_message=conflict_message,
    )


@bp.route("/order-confirmed")
@registration_required
def order_confirmed(camper):
    """Show the order that was just confirmed, read back from the database."""
    order_id = session.get("last_order_id")
    saved_order = None
    if isinstance(order_id, int) and not isinstance(order_id, bool):
        saved_order = db.session.get(Order, order_id)
    # Only show an order that belongs to this browser's camper.
    if saved_order is None or saved_order.camper_id != camper.id:
        return redirect(url_for("main.index"))

    lines = lines_from_saved_order(saved_order)
    return render_template(
        "confirmation.html",
        camper=camper,
        saved_order=saved_order,
        package=find_package(saved_order.package_id),
        lines=lines,
        total_cents=saved_order.total_cents,
    )


# ---------- Tracking lunches (Issue #5) ----------

# The four daily lunch statuses and the words parents see. A new lunch is
# "ordered"; the café changes it in Issue #6. Issue #6 must save exactly
# these values.
LUNCH_STATUS_LABELS = {
    "ordered": "Ordered",
    "preparing": "Preparing",
    "completed": "Completed",
    "unavailable": "Unavailable",
}

# Older names for two statuses, from before the names above were chosen.
# If any are still in the database, they are shown as the new status.
OLD_STATUS_NAMES = {
    "cooking": "preparing",
    "cannot_complete": "unavailable",
}


def canonical_status(status):
    """Return the current name for a status, e.g. "cooking" -> "preparing"."""
    return OLD_STATUS_NAMES.get(status, status)


def lunch_status_label(status):
    """Turn a database status into the words parents see, e.g. "preparing" -> "Preparing".

    A status that isn't one of the four is still shown, with its words
    capitalized (for example "on_hold" -> "On Hold").
    """
    status = canonical_status(status)
    if status in LUNCH_STATUS_LABELS:
        return LUNCH_STATUS_LABELS[status]
    return status.replace("_", " ").title()


def lunch_status_class(status):
    """CSS class for a status badge, e.g. "status-unavailable"."""
    status = canonical_status(status)
    if status in LUNCH_STATUS_LABELS:
        return "status-" + status
    return "status-other"


def count_lunches(lunches):
    """Count lunches ordered, completed, remaining, and unavailable.

    - ordered:     every saved lunch
    - completed:   status "completed"
    - unavailable: status "unavailable" (the café couldn't make it)
    - remaining:   everything else, which is still to be made
                   ("ordered", "preparing", or any other status)

    So ordered = completed + remaining + unavailable.
    """
    statuses = [canonical_status(lunch.status) for lunch in lunches]
    ordered = len(statuses)
    completed = statuses.count("completed")
    unavailable = statuses.count("unavailable")
    return {
        "ordered": ordered,
        "completed": completed,
        "unavailable": unavailable,
        "remaining": ordered - completed - unavailable,
        # Lunches that can still be made or were made, for the progress bar.
        "available": ordered - unavailable,
    }


def camp_day_position(day):
    """Sort key so "Day 2" comes before "Day 10"."""
    return CAMP_DAYS.index(day) if day in CAMP_DAYS else len(CAMP_DAYS)


def meal_name(meal_id):
    """The menu name for a meal ID (or the ID itself if it's no longer on the menu)."""
    meal = find_meal(meal_id)
    return meal["name"] if meal else meal_id


def current_cafe_note(lunch):
    """The café's note explaining why this lunch is unavailable right now, or None.

    Only the most recent change counts, so a note from an earlier time the
    lunch was unavailable is never shown as the current reason. A lunch can be
    unavailable without a note if its status was set outside the café page.
    """
    if canonical_status(lunch.status) != "unavailable" or not lunch.history:
        return None
    latest = lunch.history[-1]
    if latest.changed_by == "cafe" and latest.to_status == "unavailable" and latest.note:
        return latest.note
    return None


def parent_history_lines(lunch):
    """What a parent sees about past changes to a lunch, oldest first.

    For example:
      "Pepperoni Pizza + Fries + Drink was unavailable. Café note: Out of pepperoni."
      "You changed this lunch to Cheese Pizza + Fries + Drink."
    """
    lines = []
    for entry in lunch.history:
        if entry.changed_by == "cafe" and entry.to_status == "unavailable" and entry.note:
            lines.append({"kind": "note", "meal": meal_name(entry.from_meal_id), "note": entry.note})
        elif entry.changed_by == "parent" and entry.from_meal_id != entry.to_meal_id:
            lines.append({"kind": "swap", "meal": meal_name(entry.to_meal_id)})
    return lines


@bp.route("/order-status")
@registration_required
def order_status(camper):
    """Show every confirmed order for this camper and the status of each lunch.

    The orders are found only from the camper in this browser's session, never
    from an order number in the URL, so a parent can't open another camper's
    orders. Everything is read from the database each time the page opens, so
    updates from the café appear when the parent refreshes.
    """
    saved_orders = db.session.scalars(
        db.select(Order).where(Order.camper_id == camper.id).order_by(Order.id)
    ).all()

    orders = []
    all_lunches = []
    for saved_order in saved_orders:
        lunches = sorted(saved_order.daily_lunches, key=lambda lunch: camp_day_position(lunch.camp_day))
        all_lunches.extend(lunches)
        package = find_package(saved_order.package_id)
        orders.append({
            "id": saved_order.id,
            "package_name": package["name"] if package else saved_order.package_id,
            "total_cents": saved_order.total_cents,
            "counts": count_lunches(lunches),
            "rows": [
                {
                    "lunch_id": lunch.id,
                    "day": lunch.camp_day,
                    "meal_name": meal_name(lunch.meal_id),
                    "status_label": lunch_status_label(lunch.status),
                    "status_class": lunch_status_class(lunch.status),
                    # Only an unavailable lunch can get a different meal.
                    "can_change_meal": canonical_status(lunch.status) == "unavailable",
                    # Whether the café explained why it's unavailable; if not,
                    # the page shows a general message instead.
                    "has_current_note": current_cafe_note(lunch) is not None,
                    "history": parent_history_lines(lunch),
                }
                for lunch in lunches
            ],
        })

    # A message after choosing a different meal (or why it couldn't be changed).
    message = None
    for category, text in get_flashed_messages(with_categories=True):
        if category in ("meal-changed", "meal-not-changed"):
            message = {"text": text, "is_error": category == "meal-not-changed"}

    response = make_response(render_template(
        "status.html",
        camper=camper,
        orders=orders,
        counts=count_lunches(all_lunches),
        on_status_page=True,
        message=message,
    ))
    # Ask the browser not to keep a copy, so Back/Refresh always shows the
    # latest statuses from the database.
    response.headers["Cache-Control"] = "no-store"
    return response


# ---------- Choosing a different meal for an unavailable lunch (Issue #6) ----------

def find_campers_lunch(camper, lunch_id):
    """Return this camper's lunch with this ID, or stop with "Not Found".

    The ID comes from the URL, so it is checked against the camper in the
    session. Another camper's lunch looks exactly like one that doesn't exist.
    """
    lunch = db.session.get(DailyLunch, lunch_id)
    if lunch is None or lunch.camper_id != camper.id or lunch.order.camper_id != camper.id:
        abort(404)
    return lunch


def change_lunch_meal(lunch, new_meal):
    """Swap an unavailable lunch's meal, put it back to "ordered", and update the order total.

    Returns (old_total_cents, new_total_cents), or None if the lunch changed
    first (for example, the café updated it, or the form was sent twice).
    The update only happens if the lunch is still unavailable with the same
    meal, so two requests can't both change it.
    """
    old_status = lunch.status
    old_meal_id = lunch.meal_id
    order = lunch.order
    old_total = order.total_cents

    result = db.session.execute(
        db.update(DailyLunch)
        .where(
            DailyLunch.id == lunch.id,
            DailyLunch.status == old_status,
            DailyLunch.meal_id == old_meal_id,
        )
        .values(meal_id=new_meal["id"], price_cents=new_meal["price_cents"], status="ordered")
    )
    if result.rowcount != 1:
        db.session.rollback()
        return None

    db.session.add(LunchHistory(
        daily_lunch_id=lunch.id,
        changed_by="parent",
        from_status=canonical_status(old_status),
        to_status="ordered",
        from_meal_id=old_meal_id,
        to_meal_id=new_meal["id"],
    ))
    # Add up the order again from its lunches, so the total always matches.
    db.session.flush()
    new_total = db.session.scalar(
        db.select(db.func.sum(DailyLunch.price_cents)).where(DailyLunch.order_id == order.id)
    )
    order.total_cents = new_total
    db.session.commit()
    return old_total, new_total


@bp.route("/order-status/lunches/<int:lunch_id>/change-meal", methods=["GET", "POST"])
@registration_required
def change_meal(camper, lunch_id):
    """Let a parent pick a different meal for one lunch the café marked unavailable."""
    lunch = find_campers_lunch(camper, lunch_id)

    # Only unavailable lunches can be changed here. Completed, preparing, and
    # ordered lunches can't, even if someone types this page's address.
    if canonical_status(lunch.status) != "unavailable":
        flash(
            f"The {lunch.camp_day} lunch can't be changed here because its status is "
            f"{lunch_status_label(lunch.status)}.",
            "meal-not-changed",
        )
        return redirect(url_for("main.order_status"))

    # The unavailable meal isn't offered again.
    choices = [meal for meal in MEALS if meal["id"] != lunch.meal_id]
    error = None
    selected = None

    if request.method == "POST":
        selected = request.form.get("meal", "")
        new_meal = find_meal(selected)
        if new_meal is None or new_meal["id"] == lunch.meal_id:
            error = "Please choose one of the meals listed."
            selected = None
        else:
            day = lunch.camp_day
            try:
                totals = change_lunch_meal(lunch, new_meal)
            except SQLAlchemyError:
                db.session.rollback()
                totals = None
            if totals is None:
                flash(f"The {day} lunch was already updated, so nothing was changed. "
                      "Check its status below.", "meal-not-changed")
                return redirect(url_for("main.order_status"))
            old_total, new_total = totals
            total_text = (
                f"Your order total is now {format_price(new_total)}."
                if new_total != old_total
                else f"Your order total is still {format_price(new_total)}."
            )
            flash(f"{day} changed to {new_meal['name']}. It is back to Ordered. {total_text}", "meal-changed")
            return redirect(url_for("main.order_status"))

    return render_template(
        "change_meal.html",
        camper=camper,
        lunch=lunch,
        current_meal_name=meal_name(lunch.meal_id),
        current_price_cents=lunch.price_cents,
        cafe_note=current_cafe_note(lunch),
        choices=choices,
        selected=selected,
        error=error,
        order_total_cents=lunch.order.total_cents,
    )


# ---------- Café daily orders (Issue #6) ----------
#
# Café attendants enter a shared passcode (the CAFE_PASSCODE setting) once,
# and the session remembers it. There are no separate accounts.

# Which status changes the café can make. Every new lunch is "ordered".
# The last two lines let an attendant undo a mistake.
CAFE_STATUS_CHANGES = {
    "ordered": ("preparing", "completed", "unavailable"),
    "preparing": ("completed", "unavailable", "ordered"),
    "completed": ("preparing",),
    "unavailable": ("ordered",),
}

CAFE_NOTE_MAX_LENGTH = 300


def cafe_button_label(current, new):
    """The words on the button that changes a lunch from current to new status."""
    if new == "preparing":
        return "Start Preparing" if current == "ordered" else "Back to Preparing"
    if new == "completed":
        return "Mark Completed"
    if new == "unavailable":
        return "Mark Unavailable"
    return "Back to Ordered"


def cafe_signed_in():
    """True if this browser entered the café passcode (and a passcode is set up)."""
    return bool(current_app.config.get("CAFE_PASSCODE")) and session.get("cafe_attendant") is True


def cafe_required(view):
    """Send anyone who hasn't entered the café passcode to the café sign-in page."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not cafe_signed_in():
            return redirect(url_for("main.cafe_login"))
        return view(*args, **kwargs)

    return wrapped


@bp.route("/cafe/login", methods=["GET", "POST"])
def cafe_login():
    """Café attendants enter the shared passcode here."""
    passcode = current_app.config.get("CAFE_PASSCODE", "")
    error = None
    if request.method == "POST":
        entered = request.form.get("passcode", "")
        # compare_digest takes the same time whether or not the start matches,
        # so the passcode can't be guessed one letter at a time.
        if passcode and hmac.compare_digest(entered.encode(), passcode.encode()):
            session["cafe_attendant"] = True
            return redirect(url_for("main.cafe_orders"))
        error = "That passcode isn't right. Please try again."
    elif cafe_signed_in():
        return redirect(url_for("main.cafe_orders"))

    return render_template("cafe_login.html", error=error, passcode_set_up=bool(passcode))


@bp.route("/cafe/logout", methods=["POST"])
def cafe_logout():
    session.pop("cafe_attendant", None)
    session.pop("cafe_update", None)
    return redirect(url_for("main.cafe_login"))


def cafe_day_page(day, errors=None, reasons=None):
    """Build the café page for one camp day.

    errors and reasons (both {lunch_id: text}) are used to show a lunch's form
    again with its problem, after an attendant leaves out a required note.
    """
    errors = errors or {}
    reasons = reasons or {}

    rows = db.session.execute(
        db.select(DailyLunch, Camper)
        .join(Camper, Camper.id == DailyLunch.camper_id)
        .where(DailyLunch.camp_day == day)
        .order_by(Camper.last_name, Camper.first_name, DailyLunch.id)
    ).all()

    # How many lunches each day has, for the day buttons.
    day_counts = dict(db.session.execute(
        db.select(DailyLunch.camp_day, db.func.count()).group_by(DailyLunch.camp_day)
    ).all())

    # A message about the lunch that was just updated, shown on its card.
    update = session.pop("cafe_update", None)
    updated_id = update.get("lunch_id") if isinstance(update, dict) else None

    lunches = []
    status_totals = {status: 0 for status in LUNCH_STATUS_LABELS}
    meal_totals = {}
    for lunch, camper in rows:
        status = canonical_status(lunch.status)
        if status in status_totals:
            status_totals[status] += 1
        if status != "unavailable":
            name = meal_name(lunch.meal_id)
            meal_totals[name] = meal_totals.get(name, 0) + 1
        lunches.append({
            "id": lunch.id,
            "camper_name": camper.full_name,
            "meal_name": meal_name(lunch.meal_id),
            "order_id": lunch.order_id,
            "status": lunch.status,
            "status_label": lunch_status_label(lunch.status),
            "status_class": lunch_status_class(lunch.status),
            "actions": [
                {"status": new, "label": cafe_button_label(status, new)}
                for new in CAFE_STATUS_CHANGES.get(status, ())
            ],
            "history": [
                {"meal": meal_name(entry.from_meal_id), "note": entry.note}
                for entry in lunch.history
                if entry.changed_by == "cafe" and entry.note
            ],
            "parent_swaps": [
                {"from": meal_name(entry.from_meal_id), "to": meal_name(entry.to_meal_id)}
                for entry in lunch.history
                if entry.changed_by == "parent" and entry.from_meal_id != entry.to_meal_id
            ],
            "message": update.get("message") if updated_id == lunch.id else None,
            "message_is_error": bool(update.get("is_error")) if updated_id == lunch.id else False,
            "error": errors.get(lunch.id),
            "reason": reasons.get(lunch.id, ""),
        })

    response = make_response(render_template(
        "cafe.html",
        day=day,
        camp_days=CAMP_DAYS,
        day_counts=day_counts,
        lunches=lunches,
        status_totals=status_totals,
        status_labels=LUNCH_STATUS_LABELS,
        meal_totals=sorted(meal_totals.items()),
        note_max_length=CAFE_NOTE_MAX_LENGTH,
    ))
    # Always show the latest statuses, never a copy the browser kept.
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.route("/cafe")
@cafe_required
def cafe_orders():
    """Show one camp day's lunches for the café (Day 1 unless another day is chosen)."""
    day = request.args.get("day", CAMP_DAYS[0])
    if day not in CAMP_DAYS:
        day = CAMP_DAYS[0]
    return cafe_day_page(day)


@bp.route("/cafe/lunches/<int:lunch_id>/status", methods=["POST"])
@cafe_required
def cafe_update_status(lunch_id):
    """Change one lunch's status. Everything is checked against the database."""
    lunch = db.session.get(DailyLunch, lunch_id)
    if lunch is None:
        abort(404)

    day = lunch.camp_day  # always return to the lunch's own day, not one sent by the browser
    current = canonical_status(lunch.status)
    new_status = request.form.get("status", "")
    # The status the attendant saw when the page was drawn. If it no longer
    # matches the database, someone else changed this lunch in the meantime.
    expected = request.form.get("expected_status", "")
    reason = request.form.get("reason", "").strip()
    camper = db.session.get(Camper, lunch.camper_id)

    if expected != lunch.status:
        session["cafe_update"] = {
            "lunch_id": lunch.id,
            "message": f"Not changed: this lunch was already updated to {lunch_status_label(lunch.status)}.",
            "is_error": True,
        }
        return redirect(url_for("main.cafe_orders", day=day, _anchor=f"lunch-{lunch.id}"))

    if new_status not in CAFE_STATUS_CHANGES.get(current, ()):
        session["cafe_update"] = {
            "lunch_id": lunch.id,
            "message": f"Not changed: a lunch that is {lunch_status_label(lunch.status)} can't be changed that way.",
            "is_error": True,
        }
        return redirect(url_for("main.cafe_orders", day=day, _anchor=f"lunch-{lunch.id}"))

    if new_status == "unavailable":
        if not reason:
            return cafe_day_page(day, errors={lunch.id: "Please explain why this lunch is unavailable. "
                                                        "The parent will see this note."})
        if len(reason) > CAFE_NOTE_MAX_LENGTH:
            return cafe_day_page(
                day,
                errors={lunch.id: f"Please keep the note to {CAFE_NOTE_MAX_LENGTH} characters or fewer."},
                reasons={lunch.id: reason},
            )
    else:
        reason = None  # notes are only kept for unavailable lunches

    # Only update if the status is still what we just read, so two attendants
    # can't both change the same lunch at once.
    result = db.session.execute(
        db.update(DailyLunch)
        .where(DailyLunch.id == lunch.id, DailyLunch.status == lunch.status)
        .values(status=new_status)
    )
    if result.rowcount != 1:
        db.session.rollback()
        session["cafe_update"] = {
            "lunch_id": lunch.id,
            "message": "Not changed: this lunch was just updated by someone else.",
            "is_error": True,
        }
        return redirect(url_for("main.cafe_orders", day=day, _anchor=f"lunch-{lunch.id}"))

    db.session.add(LunchHistory(
        daily_lunch_id=lunch.id,
        changed_by="cafe",
        from_status=current,
        to_status=new_status,
        from_meal_id=lunch.meal_id,
        to_meal_id=lunch.meal_id,
        note=reason,
    ))
    db.session.commit()

    session["cafe_update"] = {
        "lunch_id": lunch.id,
        "message": f"Updated: {camper.full_name}'s {day} lunch is now {lunch_status_label(new_status)}.",
    }
    return redirect(url_for("main.cafe_orders", day=day, _anchor=f"lunch-{lunch.id}"))


# ---------- Error pages (404 and 405) ----------

def error_page(status_code, heading, message):
    """A page in the site's style with one safe way to continue.

    It says the same thing whatever was asked for, so it never reveals whether
    another camper's lunch or order exists.
    """
    in_cafe = request.path.startswith("/cafe")
    if in_cafe and cafe_signed_in():
        action = {"href": url_for("main.cafe_orders"), "label": "Back to Café Daily Orders"}
    else:
        try:
            camper = get_current_camper()
            has_orders = camper is not None and bool(camper.orders)
        except SQLAlchemyError:
            db.session.rollback()
            has_orders = False
        if has_orders:
            action = {"href": url_for("main.order_status"), "label": "View Order Status"}
        else:
            action = {"href": url_for("main.index"), "label": "Return to Lunch Registration"}

    return render_template(
        "error.html",
        heading=heading,
        message=message,
        action=action,
        in_cafe=in_cafe,
    ), status_code


def page_not_found(error):
    return error_page(
        404,
        "Page not found",
        "We couldn't find that page. The link may be out of date or typed incorrectly.",
    )


def method_not_allowed(error):
    return error_page(
        405,
        "This page can't be opened that way",
        "This address can't be opened directly. Please use the buttons on the site instead.",
    )


# This lets you start the app with "python app.py".
# debug=True reloads the server when you save a file. Turn it off before deploying.
if __name__ == "__main__":
    # Read settings from a .env file, if there is one. ("flask run" does this by itself.)
    from dotenv import load_dotenv

    load_dotenv()
    create_app().run(debug=True)
