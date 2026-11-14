"""
Database models for Issue #1: Register a Camper.

A "model" is a Python class that matches a database table. Each attribute
below becomes a column. SQLAlchemy turns Python code like Camper(...) into
the right SQL for SQLite (on your computer) or PostgreSQL (Supabase).

Tables:
  guardians     - the parent or guardian's contact information
  campers       - each camper, linked to one guardian by guardian_id
  orders        - a confirmed lunch order for one camper (Issue #4)
  daily_lunches - one row per camp day in an order, with the meal chosen

This matches the class diagram, where a parent/guardian (User) manages
zero or more Campers, a Camper has Orders, and an Order contains 1 to 12
DailyLunches.
"""

from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

# One shared database object. app.py connects it to the Flask app.
db = SQLAlchemy()

# Longest values we accept. registration.py uses these to validate the form,
# so the form rules and the column sizes can never disagree.
NAME_MAX_LENGTH = 50
GUARDIAN_NAME_MAX_LENGTH = 100
EMAIL_MAX_LENGTH = 254  # the longest a real email address can be
PHONE_LENGTH = 12       # phone numbers are saved as +1 and 10 digits, e.g. +14105550123


class Guardian(db.Model):
    """A parent or guardian and how to contact them."""

    __tablename__ = "guardians"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(GUARDIAN_NAME_MAX_LENGTH))
    email: Mapped[str] = mapped_column(String(EMAIL_MAX_LENGTH))
    phone: Mapped[str] = mapped_column(String(PHONE_LENGTH))
    # The database fills these in automatically.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    campers: Mapped[list["Camper"]] = relationship(back_populates="guardian")


class Camper(db.Model):
    """A child attending camp. Each camper belongs to one guardian."""

    __tablename__ = "campers"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH))
    last_name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH))
    guardian_id: Mapped[int] = mapped_column(ForeignKey("guardians.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    guardian: Mapped[Guardian] = relationship(back_populates="campers")
    orders: Mapped[list["Order"]] = relationship(back_populates="camper")

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class Order(db.Model):
    """A confirmed lunch order for one camper."""

    __tablename__ = "orders"
    # Lets daily_lunches point at (order, camper) together. See DailyLunch below.
    __table_args__ = (UniqueConstraint("id", "camper_id", name="uq_orders_id_camper"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    camper_id: Mapped[int] = mapped_column(ForeignKey("campers.id"))
    # The package's ID from PACKAGES in app.py, e.g. "6-day".
    package_id: Mapped[str] = mapped_column(String(20))
    # The total in cents (3400 = $34.00), added up from the daily lunches.
    total_cents: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="confirmed")
    # A random code made when the parent opens the review page. It is unique,
    # so if "Confirm Order" is sent twice, the database refuses a second order.
    confirmation_token: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    camper: Mapped[Camper] = relationship(back_populates="orders")
    # The lunches in this order, sorted in the order they were added (by camp day).
    daily_lunches: Mapped[list["DailyLunch"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="DailyLunch.id"
    )


class DailyLunch(db.Model):
    """One camp day in an order and the meal chosen for it."""

    __tablename__ = "daily_lunches"
    __table_args__ = (
        # Each lunch belongs to an order, and its camper must be that order's
        # camper. (PostgreSQL checks this. SQLite skips foreign key checks
        # unless they are turned on, but the app always sets both together.)
        ForeignKeyConstraint(
            ["order_id", "camper_id"], ["orders.id", "orders.camper_id"],
            name="fk_daily_lunches_order_camper",
        ),
        # A camper can only have one lunch per camp day, across ALL orders.
        # The database refuses a second one, even if two orders are confirmed
        # at the same moment.
        UniqueConstraint("camper_id", "camp_day", name="uq_daily_lunches_camper_day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column()
    # Copied from the order, so the database can check one lunch per camper per day.
    camper_id: Mapped[int] = mapped_column()
    # "Day 1" through "Day 12" until the official camp dates are entered.
    camp_day: Mapped[str] = mapped_column(String(20))
    # The meal's ID from MEALS in app.py, e.g. "cheese-pizza".
    meal_id: Mapped[str] = mapped_column(String(40))
    # The price when the order was placed, so later menu price changes
    # don't change orders that were already confirmed.
    price_cents: Mapped[int] = mapped_column(Integer)
    # "ordered" for now. The café will mark lunches "completed" (Issue #6).
    status: Mapped[str] = mapped_column(String(20), default="ordered")

    order: Mapped[Order] = relationship(back_populates="daily_lunches")
