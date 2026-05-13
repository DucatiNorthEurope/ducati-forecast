import sqlite3
from pathlib import Path
from flask import g

DB_PATH = Path(__file__).parent / "data" / "dashboard.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS dealers (
    id INTEGER PRIMARY KEY,
    password TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    country TEXT NOT NULL,
    dealer_code TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS material_map (
    id INTEGER PRIMARY KEY,
    material_prefix TEXT UNIQUE NOT NULL,
    plan_super TEXT,
    plan_model TEXT,
    status TEXT DEFAULT 'active',
    notes TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS plan (
    id INTEGER PRIMARY KEY,
    country TEXT NOT NULL,
    plan_super TEXT,
    plan_model TEXT NOT NULL,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    qty INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_plan_lookup ON plan(country, plan_model, year, month);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY,
    order_number TEXT,
    material_prefix TEXT,
    material_full TEXT,
    bike_super_model TEXT,
    bike_model TEXT,
    bike_color TEXT,
    bike_type TEXT,
    end_customer_status TEXT,
    country TEXT,
    dealer TEXT,
    dealer_code TEXT,
    request_date TEXT,
    order_creation_date TEXT,
    confirmed_delivery_date TEXT,
    order_status_group TEXT
);
CREATE INDEX IF NOT EXISTS idx_orders_lookup ON orders(country, material_prefix);
CREATE INDEX IF NOT EXISTS idx_orders_dealer ON orders(dealer_code);

CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY,
    imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
    plan_filename TEXT,
    orders_filename TEXT,
    plan_rows INTEGER,
    order_rows INTEGER,
    unmapped_count INTEGER
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS embargoes (
    plan_model TEXT PRIMARY KEY,
    embargo_until TEXT,        -- ISO date; hidden while today < this date
    manually_hidden INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def get_conn():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_conn(_e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    con.commit()
    con.close()


def get_setting(key, default=None):
    row = get_conn().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key, value):
    con = get_conn()
    con.execute(
        "INSERT INTO settings(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    con.commit()
