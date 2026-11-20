# schedule_backend

Django + Django REST Framework API for the schedule system. The frontend lives in the sibling repo `../schedule_frontend` (see `../CLAUDE.md` for how the two fit together).

## Run locally (Windows)

The virtualenv is `.venv` (Python 3.14), not `venv` as the README says.

```powershell
.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py test api
```

- API root: `http://127.0.0.1:8000/api/`; Django admin: `/admin/`.
- Settings come from `.env` (loaded by `python-dotenv`); `.env.example` holds the **production** values, so don't copy it as-is for local work.
- Database: SQLite `db.sqlite3` (git-ignored). Back it up before migrations or destructive commands, e.g. `db.sqlite3.bak-<date>-<reason>`.
- Management commands in `api/management/commands/`: `populate_db`, `populate_exams`, `fix_timeslots`, `inspect_db`.

## Layout

- `config/`: settings, root URLs (`/admin/`, `/api/`).
- `api/models|serializers|views/`: split by domain (groups, rooms, schedule, study_plans, subjects, teachers).
- `api/urls.py`: DRF router. Route names are snake_case (`room_types`, `study_plans`, `class_types`, `semester_constraints`); `class-types` is kept only as a legacy alias. Keep new routes snake_case to match what the frontend calls.
- `api/filters.py`: django-filter `FilterSet`s (e.g. `LessonFilter`).
- `api/services/`: schedule generator and study-plan logic.
- `api/tests/`: `APITestCase` suite with factories in `factories.py`; run `manage.py test api`.
- `api/exceptions.py`: DRF exception handler (adds `code` to error bodies, protected deletes → 409).

## API contract rules

The frontend (`../schedule_frontend/assets/js/api.js`) depends on this API. Changes should **add** fields, routes or filters; never rename or remove anything the frontend uses without changing the frontend in the same piece of work. Errors must be JSON (DRF style `{"detail": ...}`), never Django's HTML error page: the frontend treats an HTML response as a broken route.

## Git and deploy

- **A push to `main` deploys to production** (`.github/workflows/deploy.yml`: SSH, `git reset --hard`, `migrate`, restart). Work on a branch; never push or merge to `main` without the user's explicit go-ahead.
- Commit style: conventional commits (`feat(scope): ...`, `fix: ...`, `docs(plan): ...`).

## Plans

Plans live in `docs/plans/NNNN-short-name.md` (numbered per repo). Each one has a header table (Status, Repo/branch, Source, Scope). Keep the Status line current as phases land. A plan driven by frontend work links to the frontend plan it comes from.
