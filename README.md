# summer-camp-lunch-package-registration
Software engineering project for managing summer camp lunch package registrations and orders.

Built with Python, Flask, Flask-SQLAlchemy, HTML, CSS, and vanilla JavaScript.

## Pages

1. **Register a camper** (`/register`) – camper name and parent/guardian contact information, saved in the database.
2. **Choose a lunch package** (`/`) – a 4-, 6-, or 12-day package and the camp days.
3. **Choose daily meals** (`/meals`) – one meal for each selected day.
4. **Review order and total** (`/review`) – check every day, meal, and price, then confirm. Confirmed orders are saved in the database.
5. **Order status** (`/order-status`) – how many lunches are ordered, completed, remaining, and unavailable, and each lunch's status and café notes.
6. **Choose a different meal** (`/order-status/lunches/<id>/change-meal`) – when the café marks a lunch unavailable, the parent picks a new meal for just that day.

The parent pages send you to the registration page until a camper is registered.

### Café pages

- **Café sign in** (`/cafe/login`) – café attendants enter the shared café passcode (`CAFE_PASSCODE`).
- **Daily lunch orders** (`/cafe`) – every lunch for one camp day, with the camper, meal, order number, and status. Attendants change each lunch's status here.

## Lunch statuses

| Status (in the database) | Shown as | Meaning |
| --- | --- | --- |
| `ordered` | Ordered | Saved, not started yet. Every new lunch starts here. |
| `preparing` | Preparing | The café is making it. |
| `completed` | Completed | The camper received it. |
| `unavailable` | Unavailable | The café can't make it. The attendant must write a reason, which the parent sees. |

The café can change a lunch from Ordered to Preparing, Completed, or Unavailable,
and from Preparing to Completed or Unavailable. To fix a mistake, it can also
move Preparing back to Ordered, Completed back to Preparing, and Unavailable back
to Ordered. When a parent picks a different meal for an unavailable lunch, the
lunch goes back to Ordered and the order total is updated if the price changed.

## Database tables

| Table | What it holds |
| --- | --- |
| `guardians` | Parent or guardian name, email, and phone |
| `campers` | Camper name, linked to a guardian |
| `orders` | A confirmed order: camper, package, total (in cents), status |
| `daily_lunches` | One row per camp day in an order: the meal, its price (in cents), and its status |
| `lunch_history` | Every status change, café note, and meal swap for a lunch. Never deleted, so café notes are kept after a parent picks a different meal. |

## Run it on your computer

```
python -m venv venv
venv\Scripts\activate            (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt
flask --app app run --debug
```

Then open http://127.0.0.1:5000.

With no settings at all, the app uses a local SQLite database file at
`instance/lunch_dev.db` and creates its tables automatically. It also creates a
random development secret key in `instance/dev_secret_key`. The `instance/`
folder is ignored by git.

## Settings (environment variables)

Copy `.env.example` to a new file named `.env` and fill in values. `.env` is
ignored by git, so real passwords and keys are never committed.

| Variable | What it is |
| --- | --- |
| `SECRET_KEY` | A long random string that signs the session cookie. Required when `DATABASE_URL` is set. Create one with `python -c "import secrets; print(secrets.token_hex(32))"`. |
| `DATABASE_URL` | The PostgreSQL connection string for the deployed database. If it is not set, the local SQLite file is used. |
| `CAFE_PASSCODE` | The shared passcode café attendants enter to open `/cafe`. If it is not set, the café pages stay locked. Share it only with café staff. |

## Using Supabase (PostgreSQL)

1. In Supabase, open **Connect** for the project and copy a PostgreSQL connection string.
2. Put it in `.env` (or the hosting service's environment settings) as `DATABASE_URL`, with
   your real database password filled in, and add `?sslmode=require` to the end if it isn't there.
3. Set `SECRET_KEY` and `CAFE_PASSCODE` too.
4. Create the tables once:

   ```
   flask --app app init-db
   ```

`init-db` only creates tables that don't exist yet. It never deletes or replaces
tables or data, so it is safe to run again. **Run it again after updating to a
version that adds tables** (for example, the `orders` and `daily_lunches`
tables for order review, or the `lunch_history` table for the café pages). The local SQLite database gets new tables
automatically when the app starts. Normal startup never changes the
deployed database's tables. (Changing columns in an existing table later will
need a migration tool such as Flask-Migrate.)

## Run the tests

```
python -m unittest discover tests
```

Each test uses its own temporary SQLite database that is deleted afterwards, so
tests never touch the development or Supabase database.
