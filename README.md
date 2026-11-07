# COMP 3613 Library Workshops (Phase 2 starter)

Flawed baseline **0.2.0** built on [uwidcit/faststart](https://github.com/uwidcit/faststart) (`96ccfce`).

FastStart provides the SSR shell, JWT cookie auth, SQLModel, `manage.py`, and Render/Docker wiring. The library scenario adds domain models/services (rooms, workshop bookings, same-slot conflict resolution) and a JSON API under `/api` (see `/docs`).

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py init
python manage.py run
```

## Seeded API accounts

| Email | Password | Role |
| --- | --- | --- |
| `coord@example.com` | `coord-dev` | coordinator |
| `admin@example.com` | `admin-dev` | admin |
| `lecturer1@example.com` | `lect-dev` | lecturer |
| `lecturer2@example.com` | `lect-dev` | lecturer |

JSON login: `POST /api/auth/login` with `{"email","password"}`. Booking endpoints identify the actor with an `X-User-Id` header (demo auth).

## Student brief

See [`ASSIGNMENT.md`](ASSIGNMENT.md) and [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md).

## Tests

```bash
python -m pytest tests -q
```