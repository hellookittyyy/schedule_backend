# 0001 — API fixes for the Mosaic redesign

| | |
|---|---|
| Status | Draft 2026-11-20 — not started |
| Repo | `schedule_backend` (Django + DRF), baseline `2b6cd1a` + untracked `api/migrations/0020_add_class_types.py` |
| Source | Open items (a)–(e) of frontend plan [`schedule_frontend/docs/plans/0001-mosaic-redesign.md`](../../../schedule_frontend/docs/plans/0001-mosaic-redesign.md) §10 «Not done / open» |
| Deploy | Push to `main` → `.github/workflows/deploy.yml` (`git reset --hard`, `pip install`, `migrate`, restart). Every merged phase goes live, so work goes on a branch. |

## 1. Goal

Fix the five backend gaps the frontend currently works around, without breaking the existing frontend contract. Every change adds to the API or fixes an error response. No field or route the frontend uses today is removed or renamed.

## 2. Findings (checked in code, 2026-11-20)

| # | Symptom (frontend plan) | Actual cause |
|---|---|---|
| a | Editing a semester that has lessons returns 500 | `SemesterSerializer.update()` (`api/serializers/schedule.py`) **always** calls `instance.synchronize_slots()` without `force_delete`, even for a name-only edit. `Semester.synchronize_slots()` (`api/models/schedule.py`) raises `ValueError` when lessons exist, and nothing catches it, so the response is 500. The `confirm_schedule_deletion` flag the UI sends is never read. |
| b | `/class_types/` returns 404 | **Not the migration.** The route is registered as `class-types` (`api/urls.py`), but the frontend calls `/class_types/`, the same snake_case style as `room_types`, `study_plans` and `semester_constraints`. The local DB already has class types. Migration `0020_add_class_types` is only a data seed (get_or_create of 4 names) and is still untracked. |
| c | No stream filter on `/lessons/`; `study_plan_details.stream` is a name only | `LessonFilter` (`api/filters.py`) has `group_id` → `study_plan__group__id` only. `StudyPlanDepthSerializer` exposes `group`, `stream` and `teacher` as names, with no ids. `public.js` works around this with 2 + N requests: lessons by `group_id`, `/study_plans/?stream=` for each of the group's streams, then an unfiltered lessons request filtered client-side by plan id. |
| d | Deleting a room type in use returns an HTML 500 | `Room.room_type` is `on_delete=PROTECT`. DRF's default handler does not handle `django.db.models.ProtectedError`, so Django serves its HTML error page. The same issue hits every other PROTECT FK: `StudyPlan.group`, `StudyPlan.stream`, `StudyPlan.class_type`. |
| e | `/lessons/` has no teacher-id filter | `LessonFilter.teacher_name` is `icontains` on the name. The public `?t=` link has only the name, so it matches exactly on the client. |

Found along the way:

- (f) `SemesterViewSet.current` returns `status.HTTP_404_NOT_FOUND`, but `status` is never imported (`api/views/schedule.py`). With no semesters this raises `NameError` → 500.
- (g) `SemesterViewSet.sync_slots` with `force_delete` deletes unlocked lessons itself, then calls `synchronize_slots()` without `force_delete`. If any locked lesson remains, it raises → 400. Its pre-check uses `study_plan__semester`, while the model uses `time_slot__semester`.
- (h) `synchronize_slots()` deletes the time slots that no longer exist (`exclude(id__in=valid_slot_ids)`). `Lesson.time_slot` is `CASCADE`, so **locked** lessons on those slots are deleted silently.
- `api/tests.py` is empty: there are no tests.
- (i) Models and migrations have drifted. `TimeSlot.Meta.unique_together = ['semester', 'date', 'period_number']` (added in `53a94e3`) has no migration, so the DB has no such constraint. `makemigrations --check` wants `0021_alter_timeslot_unique_together`. The local DB already has one duplicate: semester 4, 2026-02-13, period 1 → slots 641 (4 lessons), 985 and 986 (no lessons). A plain `AlterUniqueTogether` would fail on `migrate`. The `except TimeSlot.MultipleObjectsReturned` branch in `synchronize_slots()` deletes **all** the duplicates and, through `CASCADE`, their lessons.

## 3. Decisions

1. **Additive API.** New filters and new `*_id` fields. Old names (`group_id`, `teacher_name`, `class-types`, name strings in `study_plan_details`) stay, so the deployed frontend keeps working before its follow-up ships.
2. **Conflict status for blocked deletes and blocked edits is 409** with a JSON body `{"detail": "<Ukrainian message>", "code": "<machine code>"}`. The frontend already reads `detail` (`assets/js/api.js`) and already branches on 409 for semesters.
3. **Semester edit with an existing schedule** (confirmed by the user 2026-11-20):
   - Re-sync slots only when `start_date`, `end_date` or the generation config actually changed. A name-only edit or an `is_current` change never touches the schedule.
   - If a re-sync is needed and lessons exist: answer 409 `schedule_exists` unless `confirm_schedule_deletion: true` is sent.
   - With the flag: in one transaction, delete **all** lessons of the semester (matches the UI text «повного видалення поточного розкладу»), then re-sync slots. Locked lessons are not kept, because their slots may no longer exist (h).
4. **Route name**: register `class_types` as the main route, and keep `class-types` as an alias with its own basename.

## 4. Phases

Each phase is one PR into `main` with tests. Phases 1–4 do not depend on each other after phase 0.

### Phase 0 — Prep (½ day)
- Branch from `main`.
- `0020_add_class_types.py`: commit it (decided by the user 2026-11-20; done, with a no-op reverse). It is idempotent (`get_or_create`) and seeds a fresh DB. On the current local DB it would add nothing new, because «Практична» already exists. Its reverse deletes the 4 names; make the reverse a no-op so that rolling back never deletes class types that study plans use (`PROTECT`).
- Migration `0021` for the `TimeSlot` unique constraint (item i), in one migration file:
  1. `RunPython` dedupe: for each `(semester, date, period_number)` group with more than one slot, keep the slot with the most lessons (tie → lowest id). Move the other slots' lessons to it. If a moved lesson would break `Lesson.unique_together (room, time_slot)`, set its `time_slot` to `NULL` (unplaced) instead of deleting it. Then delete the empty duplicates. Log the counts. Reverse: no-op.
  2. `AlterUniqueTogether(name='timeslot', unique_together={('semester', 'date', 'period_number')})`.
  - Remove the `MultipleObjectsReturned` branch from `synchronize_slots()`. It can no longer happen, and it deleted lessons.
  - Before the deploy: run the duplicate query on the production DB (`SELECT semester_id, date, period_number, COUNT(*) FROM api_timeslot GROUP BY 1,2,3 HAVING COUNT(*) > 1`) and take a DB backup. `deploy.yml` runs `migrate` on push.
  - Test: two duplicate slots with lessons, including a room clash → after migrating, one slot remains, no lesson is deleted, and the clashing lesson is unplaced.
- Test scaffold: `api/tests/` package with `APITestCase` and small factories (semester with config, group, stream, teacher, subject, class type, room type, room, study plan, lesson). Run with `python manage.py test api`.

**Done when:** `0020` is committed, `0021` applies cleanly on a copy of the local DB, `makemigrations --check` is clean, the scaffold runs green, and CI/deploy is unchanged.

### Phase 1 — Class types route, `current` import (¼ day) — items b, f
- `api/urls.py`: `router.register(r'class_types', ClassTypeViewSet, basename='class_type')` plus the existing `class-types` registration as an alias.
- `api/views/schedule.py`: `from rest_framework import status`.
- Tests: `GET /api/class_types/` → 200 list; `GET /api/class-types/` → 200; `GET /api/semesters/current/` on an empty DB → 404 JSON.

**Done when:** the frontend study-plans page loads the real class types (no 5-type fallback).

### Phase 2 — Protected deletes return 409 (½ day) — item d
- New `api/exceptions.py` with `exception_handler(exc, context)`: call DRF's handler first. If it returns `None` and `exc` is `ProtectedError` or `RestrictedError`, return 409 with `detail` and `code: "protected"`, plus `blocked_by`: a list of `{model: verbose_name_plural, count}` built from `exc.protected_objects`.
- Messages per model (Ukrainian), e.g. «Тип аудиторії використовують аудиторії (3). Спочатку змініть їм тип.». A generic message covers anything else.
- `config/settings.py`: `REST_FRAMEWORK = {'EXCEPTION_HANDLER': 'api.exceptions.exception_handler', ...}`. Merge with any existing `REST_FRAMEWORK` dict; none exists today.
- Tests: deleting a room type with a room → 409 JSON and the row still exists. Same for a group or stream used by a study plan and a class type used by a study plan. Deleting an unused room type → 204.

**Done when:** no `DELETE` in the API returns an HTML page for a protected FK.

### Phase 3 — Semester edit with an existing schedule (1–1½ days) — items a, g, h
- `SemesterSerializer`:
  - add `confirm_schedule_deletion = BooleanField(write_only=True, required=False, default=False)`;
  - in `update()`, compare the old and new `start_date`, `end_date` and config (normalise `generation_config` the same way `synchronize_slots` does). Skip the re-sync if nothing changed;
  - if a re-sync is needed and `Lesson.objects.filter(study_plan__semester=instance).exists()` is true without the flag, raise a 409 (a custom `APIException` subclass `ScheduleExists`, `status_code = 409`, `default_code = 'schedule_exists'`) **before** saving anything;
  - with the flag: `transaction.atomic()` → delete the semester's lessons → `super().update()` → `synchronize_slots(force_delete=True)`;
  - `create()` is unchanged (no lessons can exist).
- `Semester.synchronize_slots()`: keep the `ValueError` guard for direct callers, but use one lesson query (`study_plan__semester`) everywhere. Wrap the guard and the deletion in the same `atomic()` block as the slot rebuild.
- `SemesterViewSet.sync_slots`: pass `force_delete=True` through, instead of deleting lessons itself and then calling without the flag (g). Map `ValueError` → 409, not 400.
- Response of a confirmed edit: the normal semester JSON plus `deleted_lessons: <n>` (read-only, only on this response), so the UI can toast it.
- Tests:
  - name-only `PATCH` with lessons → 200, lessons untouched;
  - `PUT` with changed dates and lessons, no flag → 409 `schedule_exists`, DB unchanged (dates, slots, lessons);
  - the same with the flag → 200, 0 lessons, slots match the new range;
  - changed config, no lessons → 200, slots rebuilt;
  - `sync_slots` with a locked lesson and `force_delete` → 200.

**Done when:** the frontend semester page shows its «⚠️ Увага!» confirm on 409, and «Так, видалити та змінити» succeeds. The 500 toast branch in `semester.js` is no longer reachable.

### Phase 4 — Lesson filters and ids for the public page (1 day) — items c, e
- `StudyPlanDepthSerializer`: add read-only `group_id`, `stream_id`, `teacher_id`, `subject_id`, `class_type_id` (`source='group_id'` etc., nullable where the FK is). Keep the name fields.
- `LessonFilter`:
  - `teacher_id` → `study_plan__teacher_id` (exact);
  - `stream_id` → `study_plan__stream_id`;
  - `for_group` → lessons a group attends: `Q(study_plan__group_id=v) | Q(study_plan__stream__groups=v)`, with `.distinct()`. This replaces the frontend's 2 + N requests with one;
  - keep `group_id` (own-group plans only) and `teacher_name` unchanged.
- `LessonViewSet.queryset`: `select_related('time_slot', 'room', 'study_plan__subject', 'study_plan__teacher', 'study_plan__group', 'study_plan__stream', 'study_plan__class_type')`. The public page and the schedule grid serialise many lessons, and today every one of them costs about 6 queries.
- Tests: a group in a stream gets its own and its stream's lessons from `for_group`, with no duplicates. Two streams with the same name don't leak into each other. `teacher_id` doesn't match a teacher whose name contains another's name. Query count for 20 lessons stays constant (`assertNumQueries`).

**Done when:** `GET /api/lessons/?for_group=N&date_from=…&date_to=…` returns everything the public page shows for group N in one request.

## 5. Frontend follow-up (separate change in `schedule_frontend`, after each phase is deployed)

- Phase 1: drop the `/class_types/` fallback comment and the 5-type fallback in `admin/study-plans/study-plan.js`. Keep a graceful error.
- Phase 2: `admin/rooms` room-type delete can show `errText(err)` directly. Remove the HTML-500 special case.
- Phase 3: `admin/semesters/semester.js`: remove the 5xx «бекенд поки не дозволяє…» toast, and show `deleted_lessons` in the success toast.
- Phase 4: `js/public.js`: `lessonsQuery` uses `for_group` / `teacher_id`, and the `streamPlanIds` cache and the client-side exact-name match are removed. The `?t=` link stays name-based, or adds the id (frontend decision).
- Update frontend plan 0001 §10 items (a)–(e) as each one closes.

## 6. Open questions for the user

1. Is the production DB in the same state as local (class types present, 0019 applied)? `deploy.yml` runs `migrate` on every push, so committing 0020 applies it there too.

## 7. Risks

- **Deploy on push to `main`**: each phase goes live at once, with `migrate`. Only phase 0 has migrations: `0020` (data only) and `0021` (dedupe + unique constraint; back up the production DB first).
- **Frontend contract**: all changes are additive. The one behaviour change is a name-only semester edit, which no longer rebuilds slots. Today such an edit re-runs `update_or_create` for every slot of the semester and resets `is_available=True` on all of them.
- **No existing tests**: the regression risk is covered only by the new tests plus `schedule_frontend/docs/regression-checklist.md` run against a local backend.

## 8. Estimate

About 3½–4½ working days.

## Revision log

| Date | Baseline | Change |
|---|---|---|
| 2026-11-20 | `2b6cd1a` | First draft from frontend plan 0001 §10 (a)–(e), causes checked in code. |
| 2026-11-20 | `2b6cd1a` | User confirmed decision 3: a confirmed semester edit deletes all lessons, locked ones included. |
| 2026-11-20 | `2b6cd1a` | User decided to commit migration 0020; its reverse made a no-op. |
| 2026-11-20 | `a0d0a12` | Added item (i): missing `TimeSlot` unique migration, with dedupe, to phase 0. |
