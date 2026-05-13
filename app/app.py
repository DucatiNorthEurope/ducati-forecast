import io
import os
import secrets
from datetime import date
from functools import wraps

from flask import (Flask, request, redirect, url_for, render_template,
                   session, flash)

from . import db
from . import parsers
from . import seed_data

app = Flask(__name__)
app.teardown_appcontext(db.close_conn)


class _PrefixMiddleware:
    """Strip a URL prefix from incoming PATH_INFO so Flask routes match their
    decorator paths, while keeping url_for output prefixed via SCRIPT_NAME."""

    def __init__(self, wsgi_app, prefix):
        self.wsgi_app = wsgi_app
        self.prefix = prefix.rstrip("/")

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        if self.prefix and path.startswith(self.prefix):
            environ["PATH_INFO"] = path[len(self.prefix):] or "/"
            environ["SCRIPT_NAME"] = environ.get("SCRIPT_NAME", "") + self.prefix
        return self.wsgi_app(environ, start_response)


_url_prefix = os.environ.get("URL_PREFIX", "").rstrip("/")
if _url_prefix:
    app.wsgi_app = _PrefixMiddleware(app.wsgi_app, _url_prefix)


def _bootstrap():
    """Run once on startup: init DB, seed map, ensure secret key + admin password."""
    db.init_db()
    raw = db._connect()
    cur = raw.cursor()
    cur.execute(db.q("SELECT value FROM settings WHERE key=?"), ("secret_key",))
    row = cur.fetchone()
    if row is None:
        sk = secrets.token_hex(32)
        cur.execute(db.q("INSERT INTO settings(key,value) VALUES(?,?)"),
                    ("secret_key", sk))
    else:
        sk = row["value"]
    cur.execute(db.q("SELECT value FROM settings WHERE key=?"), ("admin_password",))
    row = cur.fetchone()
    if row is None:
        ap = os.environ.get("ADMIN_PASSWORD", "admin")
        cur.execute(db.q("INSERT INTO settings(key,value) VALUES(?,?)"),
                    ("admin_password", ap))
        if ap == "admin":
            print(f"[bootstrap] default admin password set to: 'admin' — change it via /admin/dealers")

    # seed material map via a tiny shim that uses q() too
    class _SeedShim:
        def execute(self, sql, params=()):
            cur.execute(db.q(sql), params)
            return cur
        def commit(self):
            raw.commit()
    seed_data.seed(_SeedShim())
    raw.commit()
    raw.close()
    app.secret_key = sk


_bootstrap()


# ----- auth helpers ---------------------------------------------------

def current_dealer():
    pw = session.get("dealer_pw")
    if not pw:
        return None
    return db.get_conn().execute(
        "SELECT * FROM dealers WHERE password=?", (pw,)
    ).fetchone()


def is_admin():
    return session.get("admin") is True


def dealer_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not current_dealer():
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not is_admin():
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapper


# ----- login / logout -------------------------------------------------

@app.route("/", methods=["GET"])
def login():
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login_post():
    pw = request.form.get("password", "").strip()
    if not pw:
        flash("Enter a password.", "error")
        return redirect(url_for("login"))
    admin_pw = db.get_setting("admin_password")
    if pw == admin_pw:
        session.clear()
        session["admin"] = True
        return redirect(url_for("admin_home"))
    dealer = db.get_conn().execute(
        "SELECT * FROM dealers WHERE password=?", (pw,)
    ).fetchone()
    if dealer:
        session.clear()
        session["dealer_pw"] = pw
        return redirect(url_for("dealer_view"))
    flash("Unknown password.", "error")
    return redirect(url_for("login"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ----- dealer view ----------------------------------------------------

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _rolling_months(start=None, n=12):
    """Return list of (year, month) tuples for the next n months, starting from this month."""
    today = start or date.today()
    y, m = today.year, today.month
    out = []
    for _ in range(n):
        out.append((y, m))
        m += 1
        if m == 13:
            m = 1
            y += 1
    return out


@app.route("/dealer")
@dealer_required
def dealer_view():
    dealer = current_dealer()
    con = db.get_conn()

    months = _rolling_months(n=12)
    months_keys = [(y, m) for (y, m) in months]

    # DUK-wide forecast: read the DUK_26 / DUK_27 rollup sheets directly (Ross sometimes
    # adjusts these manually so they don't equal the UK + SWE + NOR sum).
    placeholders = ",".join(["(?,?)"] * len(months_keys))
    flat = [v for ym in months_keys for v in ym]
    plan_rows = con.execute(
        f"SELECT plan_super, plan_model, year, month, qty "
        f"FROM plan "
        f"WHERE country='DUK' AND (year,month) IN ({placeholders}) "
        f"ORDER BY plan_super, plan_model, year, month",
        flat,
    ).fetchall()

    # All open Demo / Courtesy / End-customer orders across UK, SWE, NOR.
    # Sorted by order creation date so the FIFO allocation below is deterministic.
    order_rows = con.execute(
        "SELECT o.material_prefix, o.bike_type, o.end_customer_status, "
        "       o.order_creation_date, mm.plan_super, mm.plan_model "
        "FROM orders o "
        "LEFT JOIN material_map mm ON mm.material_prefix = o.material_prefix "
        "WHERE o.country IN ('UK','SWE','NOR') "
        "  AND ( o.bike_type IN ('Demo','Courtesy') OR o.end_customer_status='Yes' ) "
        "ORDER BY COALESCE(o.order_creation_date, '9999-12-31'), o.material_prefix"
    ).fetchall()

    # Embargoed plan models — hide entirely from dealer view.
    embargoed = {r["plan_model"] for r in con.execute(
        f"SELECT plan_model FROM embargoes "
        f"WHERE manually_hidden=1 OR (embargo_until IS NOT NULL AND embargo_until > {db.today_sql()})"
    ).fetchall()}

    # Join orders to plan rows by plan_model only.
    grid = {}        # plan_model -> {(y,m): {forecast, committed}}
    super_for = {}   # plan_model -> representative plan_super (display only)
    queue_for = {}   # plan_model -> list of orders to allocate (in creation-date order)

    for r in plan_rows:
        key = r["plan_model"]
        grid.setdefault(key, {})[(r["year"], r["month"])] = {"forecast": r["qty"], "committed": 0}
        super_for.setdefault(key, r["plan_super"])

    unmapped_orders = 0
    for r in order_rows:
        if not r["plan_model"]:
            unmapped_orders += 1
            continue
        super_for.setdefault(r["plan_model"], r["plan_super"])
        queue_for.setdefault(r["plan_model"], []).append(None)  # 1 token per order; FIFO is by SQL order

    # Ensure every month in the window has a cell, even for models with no plan forecast.
    for p_model in set(grid) | set(queue_for):
        monthly = grid.setdefault(p_model, {})
        for ym in months_keys:
            monthly.setdefault(ym, {"forecast": 0, "committed": 0})

    # Allocate orders FIFO (by creation date) into the first month with remaining capacity.
    # Every committed order (demo + customer) consumes one slot; ignore confirmed delivery date.
    for p_model, monthly in grid.items():
        for _ in queue_for.get(p_model, []):
            placed = False
            for ym in months_keys:
                if monthly[ym]["forecast"] - monthly[ym]["committed"] > 0:
                    monthly[ym]["committed"] += 1
                    placed = True
                    break
            if not placed:
                monthly[months_keys[-1]]["committed"] += 1

    rows = []
    for p_model, monthly in sorted(grid.items(), key=lambda x: (super_for.get(x[0]) or "", x[0])):
        if p_model in embargoed:
            continue
        cells = []
        soonest = None
        for ym in months_keys:
            d = monthly.get(ym, {"forecast": 0, "committed": 0})
            available = d["forecast"] - d["committed"]
            cells.append({"year": ym[0], "month": ym[1], "forecast": d["forecast"],
                          "committed": d["committed"], "available": available})
            if soonest is None and available >= 1:
                soonest = ym
        rows.append({"plan_super": super_for.get(p_model), "plan_model": p_model,
                     "cells": cells, "soonest": soonest})

    # dealer's own committed orders
    own_orders = []
    if dealer["dealer_code"]:
        own_orders = con.execute(
            "SELECT order_number, bike_model, bike_color, bike_type, "
            "       end_customer_status, request_date, confirmed_delivery_date "
            "FROM orders WHERE dealer_code=? "
            "ORDER BY confirmed_delivery_date",
            (dealer["dealer_code"],),
        ).fetchall()

    last_import = con.execute(
        "SELECT imported_at FROM imports ORDER BY id DESC LIMIT 1"
    ).fetchone()

    return render_template(
        "dealer.html",
        dealer=dealer,
        rows=rows,
        months=months,
        month_names=MONTH_NAMES,
        own_orders=own_orders,
        last_import=last_import["imported_at"] if last_import else None,
        unmapped_orders=unmapped_orders,
    )


# ----- admin: home ----------------------------------------------------

@app.route("/admin")
@admin_required
def admin_home():
    con = db.get_conn()
    last_import = con.execute(
        "SELECT * FROM imports ORDER BY id DESC LIMIT 1"
    ).fetchone()
    unmapped = con.execute(
        "SELECT COUNT(*) AS c FROM material_map WHERE status='unmapped'"
    ).fetchone()["c"]
    dealer_count = con.execute("SELECT COUNT(*) AS c FROM dealers").fetchone()["c"]
    order_count = con.execute("SELECT COUNT(*) AS c FROM orders").fetchone()["c"]
    plan_count = con.execute("SELECT COUNT(*) AS c FROM plan").fetchone()["c"]
    return render_template(
        "admin_home.html",
        last_import=last_import,
        unmapped=unmapped,
        dealer_count=dealer_count,
        order_count=order_count,
        plan_count=plan_count,
    )


# ----- admin: upload --------------------------------------------------

@app.route("/admin/upload", methods=["GET", "POST"])
@admin_required
def admin_upload():
    if request.method == "GET":
        return render_template("admin_upload.html")

    plan_file = request.files.get("plan_file")
    orders_file = request.files.get("orders_file")
    if not plan_file or not orders_file:
        flash("Both files are required.", "error")
        return redirect(url_for("admin_upload"))

    try:
        plan_rows = parsers.parse_plan(io.BytesIO(plan_file.stream.read()))
        order_rows = parsers.parse_orders(io.BytesIO(orders_file.stream.read()))
    except Exception as e:
        flash(f"Parse failed: {e}", "error")
        return redirect(url_for("admin_upload"))

    con = db.get_conn()
    con.execute("DELETE FROM plan")
    con.execute("DELETE FROM orders")
    con.executemany(
        "INSERT INTO plan(country, plan_super, plan_model, year, month, qty) "
        "VALUES(?,?,?,?,?,?)",
        plan_rows,
    )
    con.executemany(
        "INSERT INTO orders(order_number, material_prefix, material_full, bike_super_model, "
        "bike_model, bike_color, bike_type, end_customer_status, country, dealer, dealer_code, "
        "request_date, order_creation_date, confirmed_delivery_date, order_status_group) "
        "VALUES(:order_number,:material_prefix,:material_full,:bike_super_model,:bike_model,"
        ":bike_color,:bike_type,:end_customer_status,:country,:dealer,:dealer_code,"
        ":request_date,:order_creation_date,:confirmed_delivery_date,:order_status_group)",
        order_rows,
    )

    # auto-add any unseen Material prefixes to material_map with status='unmapped'
    seen_prefixes = {o["material_prefix"] for o in order_rows if o["material_prefix"]}
    existing = {r["material_prefix"] for r in con.execute(
        "SELECT material_prefix FROM material_map").fetchall()}
    new_prefixes = seen_prefixes - existing
    for p in sorted(new_prefixes):
        con.execute(
            "INSERT INTO material_map(material_prefix, status) VALUES(?, 'unmapped')",
            (p,),
        )

    unmapped_total = con.execute(
        "SELECT COUNT(*) AS c FROM material_map WHERE status='unmapped' "
        "AND material_prefix IN (SELECT DISTINCT material_prefix FROM orders)"
    ).fetchone()["c"]

    con.execute(
        "INSERT INTO imports(plan_filename, orders_filename, plan_rows, order_rows, unmapped_count) "
        "VALUES(?,?,?,?,?)",
        (plan_file.filename, orders_file.filename, len(plan_rows), len(order_rows), unmapped_total),
    )
    con.commit()

    msg = f"Imported {len(plan_rows)} plan rows and {len(order_rows)} orders."
    if new_prefixes:
        msg += f" {len(new_prefixes)} new Material prefix(es) detected — review on the mapping page."
    flash(msg, "ok")
    return redirect(url_for("admin_home"))


# ----- admin: mapping -------------------------------------------------

@app.route("/admin/mapping", methods=["GET"])
@admin_required
def admin_mapping():
    con = db.get_conn()
    # Show all rows, putting unmapped first
    rows = con.execute(
        f"SELECT mm.*, "
        f"(SELECT COUNT(*) FROM orders o WHERE o.material_prefix = mm.material_prefix) AS order_count, "
        f"(SELECT {db.group_concat_distinct('bike_model')} FROM orders o "
        f"  WHERE o.material_prefix = mm.material_prefix) AS bike_models "
        f"FROM material_map mm "
        f"ORDER BY CASE status WHEN 'unmapped' THEN 0 WHEN 'active' THEN 1 ELSE 2 END, "
        f"mm.material_prefix"
    ).fetchall()
    plan_models = con.execute(
        "SELECT DISTINCT plan_super, plan_model FROM plan "
        "ORDER BY plan_super, plan_model"
    ).fetchall()
    return render_template("admin_mapping.html", rows=rows, plan_models=plan_models)


@app.route("/admin/mapping/update", methods=["POST"])
@admin_required
def admin_mapping_update():
    prefix = request.form["prefix"]
    plan_combo = request.form.get("plan_combo", "")
    status = request.form.get("status", "active")
    if status == "ignored":
        plan_super, plan_model = None, None
    elif plan_combo:
        plan_super, plan_model = plan_combo.split(" || ", 1)
        status = "active"
    else:
        plan_super, plan_model = None, None
        status = "unmapped"
    db.get_conn().execute(
        "UPDATE material_map SET plan_super=?, plan_model=?, status=?, "
        "updated_at=CURRENT_TIMESTAMP WHERE material_prefix=?",
        (plan_super, plan_model, status, prefix),
    )
    db.get_conn().commit()
    return redirect(url_for("admin_mapping"))


@app.route("/admin/mapping/delete", methods=["POST"])
@admin_required
def admin_mapping_delete():
    prefix = request.form["prefix"]
    db.get_conn().execute("DELETE FROM material_map WHERE material_prefix=?", (prefix,))
    db.get_conn().commit()
    return redirect(url_for("admin_mapping"))


# ----- admin: embargoes -----------------------------------------------

@app.route("/admin/embargoes", methods=["GET"])
@admin_required
def admin_embargoes():
    con = db.get_conn()
    plan_models = con.execute(
        "SELECT DISTINCT plan_super, plan_model FROM plan "
        "WHERE plan_model IS NOT NULL "
        "ORDER BY plan_super, plan_model"
    ).fetchall()
    embargoes = {
        r["plan_model"]: r
        for r in con.execute("SELECT * FROM embargoes").fetchall()
    }
    return render_template("admin_embargoes.html",
                           plan_models=plan_models, embargoes=embargoes,
                           today=date.today().isoformat())


@app.route("/admin/embargoes/bulk", methods=["POST"])
@admin_required
def admin_embargoes_bulk():
    action = request.form.get("action")
    selected = request.form.getlist("selected")
    embargo_until = request.form.get("embargo_until", "").strip() or None

    if not selected:
        flash("Tick at least one model first.", "error")
        return redirect(url_for("admin_embargoes"))

    con = db.get_conn()
    if action == "set_date":
        if not embargo_until:
            flash("Pick a date before assigning.", "error")
            return redirect(url_for("admin_embargoes"))
        for pm in selected:
            con.execute(
                "INSERT INTO embargoes(plan_model, embargo_until, manually_hidden) "
                "VALUES(?, ?, 0) "
                "ON CONFLICT(plan_model) DO UPDATE SET "
                "  embargo_until=excluded.embargo_until, "
                "  manually_hidden=0, "
                "  updated_at=CURRENT_TIMESTAMP",
                (pm, embargo_until),
            )
        flash(f"Embargoed {len(selected)} model(s) until {embargo_until}.", "ok")
    elif action == "always_hide":
        for pm in selected:
            con.execute(
                "INSERT INTO embargoes(plan_model, embargo_until, manually_hidden) "
                "VALUES(?, NULL, 1) "
                "ON CONFLICT(plan_model) DO UPDATE SET "
                "  manually_hidden=1, "
                "  updated_at=CURRENT_TIMESTAMP",
                (pm,),
            )
        flash(f"{len(selected)} model(s) now hidden indefinitely.", "ok")
    elif action == "unembargo":
        placeholders = ",".join(["?"] * len(selected))
        con.execute(f"DELETE FROM embargoes WHERE plan_model IN ({placeholders})", selected)
        flash(f"Cleared embargo on {len(selected)} model(s).", "ok")
    else:
        flash("Unknown action.", "error")
    con.commit()
    return redirect(url_for("admin_embargoes"))


# ----- admin: dealers -------------------------------------------------

KNOWN_COUNTRIES = ["UK", "SWE", "NOR"]


@app.route("/admin/dealers", methods=["GET"])
@admin_required
def admin_dealers():
    con = db.get_conn()
    rows = con.execute("SELECT * FROM dealers ORDER BY country, name").fetchall()
    dealer_codes = con.execute(
        "SELECT DISTINCT dealer_code, dealer FROM orders "
        "WHERE dealer_code IS NOT NULL ORDER BY dealer"
    ).fetchall()
    admin_pw = db.get_setting("admin_password")
    return render_template("admin_dealers.html", rows=rows, dealer_codes=dealer_codes,
                           countries=KNOWN_COUNTRIES, admin_pw=admin_pw)


@app.route("/admin/dealers/save", methods=["POST"])
@admin_required
def admin_dealers_save():
    dealer_id = request.form.get("id", "").strip()
    password = request.form["password"].strip()
    name = request.form["name"].strip()
    country = request.form["country"].strip()
    dealer_code = request.form.get("dealer_code", "").strip() or None
    con = db.get_conn()
    if dealer_id:
        con.execute(
            "UPDATE dealers SET password=?, name=?, country=?, dealer_code=? WHERE id=?",
            (password, name, country, dealer_code, dealer_id),
        )
    else:
        try:
            con.execute(
                "INSERT INTO dealers(password,name,country,dealer_code) VALUES(?,?,?,?)",
                (password, name, country, dealer_code),
            )
        except db.sqlite3.IntegrityError:
            flash("That password is already in use.", "error")
            return redirect(url_for("admin_dealers"))
    con.commit()
    return redirect(url_for("admin_dealers"))


@app.route("/admin/dealers/delete", methods=["POST"])
@admin_required
def admin_dealers_delete():
    db.get_conn().execute("DELETE FROM dealers WHERE id=?", (request.form["id"],))
    db.get_conn().commit()
    return redirect(url_for("admin_dealers"))


@app.route("/admin/dealers/admin_password", methods=["POST"])
@admin_required
def admin_set_admin_password():
    new_pw = request.form["admin_password"].strip()
    if not new_pw:
        flash("Admin password cannot be empty.", "error")
        return redirect(url_for("admin_dealers"))
    db.set_setting("admin_password", new_pw)
    flash("Admin password updated.", "ok")
    return redirect(url_for("admin_dealers"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5050"))
    app.run(host="127.0.0.1", port=port, debug=False)
