# Library Workshops — student brief

Scenario slug: `library`  
Starter version: `0.2.0` (FastStart base)

You inherit a runnable FastStart app with a flawed workshop-booking domain API under `/api`. Stakeholder interviews (Phase 1) should surface who the users are and what “done” means; public acceptance criteria live in [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md).

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py init
python manage.py run
```

Open http://127.0.0.1:5000 — SSR auth shell from FastStart; scenario JSON under `/api` and OpenAPI at `/docs`.

## Expectations

1. Run the app, explore `/docs`, and map behaviour to elicitable requirements.
2. Find and fix defects (functional, conflict/capacity policy, testing, authorization).
3. Pay special attention to **same-slot conflict resolution** (`app/services/conflicts.py`). The current approach mixes capacity, first-come, and override rules in nested conditionals — replace it with a clearer design (the **Strategy** pattern is a strong fit; defend alternatives if you choose one).
4. Add meaningful tests; shallow starter tests are not enough for a grade.
5. Keep the FastStart layered architecture (routes → services → repositories → models) when you extend or fix behaviour.
6. Use GitHub + Trello for work tracking outside the interview platform.

Private defect manifests and hidden regression tests are instructor-only and are never committed here.