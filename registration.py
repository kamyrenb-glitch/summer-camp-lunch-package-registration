"""
Form rules for Issue #1: Register a Camper.

validate_registration() checks the five registration fields and returns
cleaned-up values plus an error message for each field that has a problem.
static/register.js uses the same rules and messages in the browser, but only
these server-side checks can be trusted.
"""

import re

from models import EMAIL_MAX_LENGTH, GUARDIAN_NAME_MAX_LENGTH, NAME_MAX_LENGTH

# The form fields, in the order they appear on the page.
# Each one has: the field name, a short label, and the longest value allowed.
FIELDS = [
    ("camper_first_name", "Camper first name", NAME_MAX_LENGTH),
    ("camper_last_name", "Camper last name", NAME_MAX_LENGTH),
    ("guardian_name", "Parent or guardian full name", GUARDIAN_NAME_MAX_LENGTH),
    ("guardian_email", "Email address", EMAIL_MAX_LENGTH),
    ("guardian_phone", "Phone number", 25),  # room for formatting like "+1 (410) 555-0123"
]

# Shown when a required field is left empty.
REQUIRED_MESSAGES = {
    "camper_first_name": "Enter the camper's first name.",
    "camper_last_name": "Enter the camper's last name.",
    "guardian_name": "Enter the parent or guardian's full name.",
    "guardian_email": "Enter an email address.",
    "guardian_phone": "Enter a phone number.",
}

EMAIL_MESSAGE = "Enter a valid email address, like name@example.com."
PHONE_MESSAGE = "Enter a 10-digit U.S. phone number, like (410) 555-0123."

# Something@something.something, with no spaces and only one @.
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")

# Only digits, spaces, dashes, dots, parentheses, and a leading plus sign.
PHONE_CHARACTERS = re.compile(r"^\+?[\d\s().-]+$")


def normalize_phone(raw_phone):
    """Turn a U.S. phone number into one format, e.g. "(410) 555-0123" -> "+14105550123".

    Returns None if it isn't a valid U.S. number.
    """
    if not PHONE_CHARACTERS.match(raw_phone):
        return None
    digits = re.sub(r"\D", "", raw_phone)
    # A leading 1 is the U.S. country code, so "1 410 555 0123" is fine too.
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return None
    # U.S. area codes and exchanges (the first 3 digits of each part) never start with 0 or 1.
    if digits[0] in "01" or digits[3] in "01":
        return None
    return "+1" + digits


def format_phone(saved_phone):
    """Show a saved phone number nicely: "+14105550123" -> "(410) 555-0123"."""
    digits = saved_phone[-10:]
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"


def validate_registration(form):
    """Check the registration form.

    Returns (values, errors):
      values - every field with surrounding spaces removed (to refill the form)
      errors - {field_name: message} for each field with a problem; empty if all valid

    Only the five fields above are read. Anything else the browser sends,
    such as a hidden ID, is ignored.
    """
    values = {}
    errors = {}

    for name, label, max_length in FIELDS:
        value = form.get(name, "").strip()
        values[name] = value
        if value == "":
            errors[name] = REQUIRED_MESSAGES[name]
        elif len(value) > max_length:
            errors[name] = f"{label} must be {max_length} characters or fewer."

    email = values["guardian_email"]
    if "guardian_email" not in errors and not EMAIL_PATTERN.match(email):
        errors["guardian_email"] = EMAIL_MESSAGE

    if "guardian_phone" not in errors and normalize_phone(values["guardian_phone"]) is None:
        errors["guardian_phone"] = PHONE_MESSAGE

    return values, errors


def error_summary(errors):
    """The message shown near the button, e.g. "Please fix the 2 fields marked above."."""
    count = len(errors)
    return f"Please fix the {count} {'field' if count == 1 else 'fields'} marked above."
