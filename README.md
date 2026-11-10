# summer-camp-lunch-package-registration
Software engineering project for managing summer camp lunch package registrations and orders.

Built with Python, Flask, Flask-SQLAlchemy, HTML, CSS, and vanilla JavaScript.

## Pages

1. **Register a camper** (`/register`) – camper name and parent/guardian contact information, saved in the database.
2. **Choose a lunch package** (`/`) – a 4-, 6-, or 12-day package and the camp days.
3. **Choose daily meals** (`/meals`) – one meal for each selected day.

The package and meal pages send you to the registration page until a camper is registered.

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

## Using Supabase (PostgreSQL)

1. In Supabase, open **Connect** for the project and copy a PostgreSQL connection string.
2. Put it in `.env` (or the hosting service's environment settings) as `DATABASE_URL`, with
   your real database password filled in, and add `?sslmode=require` to the end if it isn't there.
3. Set `SECRET_KEY` too.
4. Create the tables once:

   ```
   flask --app app init-db
   ```

`init-db` only creates tables that don't exist yet. It never deletes or replaces
tables or data, so it is safe to run again. Normal startup never changes the
deployed database's tables. (Changing columns in an existing table later will
need a migration tool such as Flask-Migrate.)

## Run the tests

```
python -m unittest discover tests
```

Each test uses its own temporary SQLite database that is deleted afterwards, so
tests never touch the development or Supabase database.
