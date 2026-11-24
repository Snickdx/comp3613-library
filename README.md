# COMP 3613 Library Workshops (Phase 2 starter)

Flawed baseline **0.2.0** built on [uwidcit/faststart](https://github.com/uwidcit/faststart) (`96ccfce`).

FastStart provides the SSR shell, JWT cookie auth, SQLModel, `manage.py`, and Render/Docker wiring. The library scenario adds domain models/services (rooms, workshop bookings, same-slot conflict resolution) and a JSON API under `/api` (see `/docs`).

## Quick start

```text
python -m venv .venv
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # Windows: Copy-Item .env.example .env
python manage.py init
python manage.py run
```

Open http://127.0.0.1:5000 — SSR auth shell; scenario JSON under `/api` and OpenAPI at `/docs`.

## Seeded API accounts

| Email | Password | Role |
| --- | --- | --- |
| `coord@example.com` | `coord-dev` | coordinator |
| `admin@example.com` | `admin-dev` | admin |
| `lecturer1@example.com` | `lect-dev` | lecturer |
| `lecturer2@example.com` | `lect-dev` | lecturer |

JSON login: `POST /api/auth/login` with `{"email","password"}`. The response includes a bearer access token; send it as `Authorization: Bearer <access_token>` when creating, cancelling, or overriding bookings. The API derives the caller's identity from the signed token, not from a user ID supplied by the client.

## Student brief

See [`ASSIGNMENT.md`](ASSIGNMENT.md) and [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md).

## Tests

```bash
python -m pytest tests -q
```