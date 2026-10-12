"""
Summer Camp Lunch Package Registration - Tucker Road Ice Rink
Issue #2: Select a Lunch Package

This small Flask app shows the three lunch packages, lets a parent pick one,
and lets them choose camp days up to that package's limit.

The browser (static/script.js) enforces the limit as the parent clicks, and
this file checks it again on the server. We check twice because anything done
only in the browser can be skipped (for example, if JavaScript is turned off).

Nothing is saved yet. A database will be added in a later issue.
"""

from flask import Flask, render_template, request

app = Flask(__name__)

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


def find_package(package_id):
    """Return the package that matches package_id, or None if there is no match."""
    for package in PACKAGES:
        if package["id"] == package_id:
            return package
    return None


@app.route("/", methods=["GET", "POST"])
def index():
    # Values we send to the template. They start empty for a first visit.
    selected_package_id = None
    selected_days = []
    error = None
    success = None

    # A POST request means the parent pressed the "Confirm Selection" button.
    if request.method == "POST":
        selected_package_id = request.form.get("package")
        # getlist() collects every checked "days" checkbox into a list.
        # We only keep values that are real camp days, ignoring anything else.
        selected_days = [day for day in request.form.getlist("days") if day in CAMP_DAYS]

        package = find_package(selected_package_id)
        day_count = len(selected_days)

        # These messages match the ones in script.js, so the parent sees the
        # same wording whether the browser or the server catches the problem.
        if package is None and day_count == 0:
            error = "Please choose a lunch package and at least one camp day."
        elif package is None:
            error = "Please choose a lunch package."
        elif day_count == 0:
            error = "Please choose at least one camp day."
        elif day_count > package["lunches"]:
            extra = day_count - package["lunches"]
            error = (
                f"The {package['name']} includes {package['lunches']} lunches, "
                f"but {day_count} days are selected. "
                f"Please unselect {extra} {'day' if extra == 1 else 'days'}."
            )
        else:
            success = (
                f"Lunch package selection confirmed: {package['name']} with "
                f"{day_count} camp {'day' if day_count == 1 else 'days'} selected."
            )

    return render_template(
        "index.html",
        packages=PACKAGES,
        camp_days=CAMP_DAYS,
        selected_package_id=selected_package_id,
        selected_days=selected_days,
        error=error,
        success=success,
    )


# This lets you start the app with "python app.py".
# debug=True reloads the server when you save a file. Turn it off before deploying.
if __name__ == "__main__":
    app.run(debug=True)
