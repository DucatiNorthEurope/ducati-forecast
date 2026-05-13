# Bike availability dashboard

A small local web app that lets dealers see country-level bike availability for the next 12 months. Admin uploads the plan and orders workbooks via the browser.

## Run it

```
./run.sh
```

On first launch this creates a Python venv, installs dependencies, and starts the server at <http://127.0.0.1:5050>. The default admin password is `admin` — change it from `/admin/dealers` after logging in.

(Port 5050 is used because macOS's AirPlay Receiver claims port 5000. Override with `PORT=xxxx ./run.sh` if needed.)

## Where things live

- `data/dashboard.db` — SQLite database (dealers, mapping, plan, orders, settings).
- `data/uploads/` — copies of the last uploaded xlsx files.

To back up, copy `data/dashboard.db` somewhere safe.

## First-time setup

1. Run `./run.sh`, open <http://127.0.0.1:5000>, log in with password `admin`.
2. **Admin → Upload**: drop the plan and orders xlsx files.
3. **Admin → Mapping**: any new Material prefixes that need a plan model will be highlighted at the top in amber — assign each to a plan row (or set to "Ignored").
4. **Admin → Dealers**: add dealer rows with their password, name, country, and (optionally) dealer code to enable the "your orders" panel.
5. Change the admin password at the bottom of the Dealers page.

Each subsequent week: re-upload the two xlsx files from the same Admin → Upload page. The data is replaced; mappings and dealer passwords are preserved.
