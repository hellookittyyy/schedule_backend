# 0001 — API fixes for the Mosaic redesign

| | |
|---|---|
| Status | Backend done 2026-11-20 — phases 0–4 landed (`70b55a6`..`0b4c54f`), `0020`/`0021` applied to the local DB. Frontend follow-up (§5) not started. |
| Repo | `schedule_backend` (Django + DRF), baseline `813f44b` on branch `api-redesign-gaps` |
| Source | Open items (a)–(e) of frontend plan [`schedule_frontend/docs/plans/0001-mosaic-redesign.md`](../../../schedule_frontend/docs/plans/0001-mosaic-redesign.md) §10 «Not done / open» |
| Scope | **Local only.** Work and test against the local backend and `db.sqlite3`. Production is very old and out of scope: it will be updated in full once all the work is done. Push to `main` deploys (`.github/workflows/deploy.yml`), so work stays on branch `api-redesign-gaps` and nothing is pushed or merged to `main`. |

## 1. Goal

Fix the five backend gaps the frontend currently works around, without breaking the existing frontend contract. Every change adds to the API or fixes an error response. No field or route the frontend uses today is removed or renamed.

## 2. Findings (checked in code, 2026-11-20)

| # | Symptom (frontend plan) | Actual cause |
|---|---|---|
| a | Editing a semester that has lessons returns 500 | `SemesterSerializer.update()` (`api/serializers/schedule.py`) **always** calls `instance.synchronize_slots()` without `force_delete`, even for a name-only edit. `Semester.synchronize_slots()` (`api/models/schedule.py`) raises `ValueError` when lessons exist, and nothing catches it, so the response is 500. The `confirm_schedule_deletion` flag the UI sends is never read. |
| b | `/class_types/` returns 404 | **Not the migration.** The route is registered as `class-types` (`api/urls.py`), but the frontend calls `/class_types/`, the same snake_case style as `room_types`, `study_plans` and `semester_constraints`. The local DB already has class types. Migration `0020_add_class_types` is only a data seed (get_or_create of 4 names); it is committed (`2d0fdbd`) but not yet applied locally. |
| c | No stream filter on `/lessons/`; `study_plan_details.stream` is a name only | `LessonFilter` (`api/filters.py`) has `group_id` → `study_plan__group__id` only. `StudyPlanDepthSerializer` exposes `group`, `stream` and `teacher` as names, with no ids. `public.js` works around this with 2 + N requests: lessons by `group_id`, `/study_plans/?stream=` for each of the group's streams, then an unfiltered lessons request filtered client-side by plan id. |
| d | Deleting a room type in use returns an HTML 500 | `Room.room_type` is `on_delete=PROTECT`. DRF's default handler does not handle `django.db.models.ProtectedError`, so Django serves its HTML error page. The same happens for `StudyPlan.stream` and `StudyPlan.class_type`. `StudyPlan.group` is the exception: `GroupViewSet.destroy` (`api/views/groups.py:48-55`) catches `ProtectedError`/`IntegrityError` and returns 400 `{"error": …}` (not `detail`). |
| e | `/lessons/` has no teacher-id filter | `LessonFilter.teacher_name` is `icontains` on the name. The public `?t=` link has only the name, so it matches exactly on the client. |

Found along the way:

- (f) `SemesterViewSet.current` returns `status.HTTP_404_NOT_FOUND`, but `status` is never imported (`api/views/schedule.py`). With no semesters this raises `NameError` → 500.
- (g) `SemesterViewSet.sync_slots` with `force_delete` deletes unlocked lessons itself, then calls `synchronize_slots()` without `force_delete`. If any locked lesson remains, it raises → 400. Its pre-check uses `study_plan__semester`, while the model uses `time_slot__semester`.
- (h) `synchronize_slots()` deletes the time slots that no longer exist (`exclude(id__in=valid_slot_ids)`). `Lesson.time_slot` is `CASCADE`, so **locked** lessons on those slots are deleted silently.
- `api/tests.py` holds only the generated placeholder: there are no tests.
- `synchronize_slots()` reads only `time_schedule` and `weekends` from the semester config. `dates_excluded`, `dates_included`, `day_time_excluded` and `date_time_excluded` are stored but never read by the backend (the generator reads only constraint configs). Making them work is out of scope.
- (i) Models and migrations have drifted. `TimeSlot.Meta.unique_together = ['semester', 'date', 'period_number']` (added in `53a94e3`) has no migration, so the DB has no such constraint. `makemigrations --check` wants `0021_alter_timeslot_unique_together`. The local DB has one clash: semester 4, 2026-02-13, period 1 → slots 641 (08:30, 4 lessons), 985 (15:10, no lessons) and 986 (16:40, no lessons). 985 and 986 are **not copies** of 641: they are periods 5 and 6 saved with the wrong period number. A plain `AlterUniqueTogether` would fail on `migrate`. The `except TimeSlot.MultipleObjectsReturned` branch in `synchronize_slots()` deletes **all** the clashing slots and, through `CASCADE`, their lessons.

## 3. Decisions

1. **Additive API.** New filters and new `*_id` fields. Old names (`group_id`, `teacher_name`, `class-types`, name strings in `study_plan_details`) stay, so the local frontend keeps working before its follow-up ships.
2. **Conflict status for blocked deletes and blocked edits is 409** with a JSON body `{"detail": "<Ukrainian message>", "code": "<machine code>"}`. DRF puts only `detail` in the body, so the custom exception handler (phase 2) adds `code` to every error response whose `detail` is a string. The frontend already reads `detail` (`assets/js/api.js`) and already branches on 409 for semesters.
3. **Semester edit with an existing schedule** (confirmed by the user 2026-11-20):
   - Re-sync slots only when a slot input changed: `start_date`, `end_date`, or the config's `time_schedule` or `weekends` (ruled 2026-11-20). Changes to other config keys are saved without a re-sync. A name-only edit or an `is_current` change never touches the schedule.
   - If a re-sync is needed and lessons exist: answer 409 `schedule_exists` unless `confirm_schedule_deletion: true` is sent.
   - With the flag **and** a re-sync needed: in one transaction, delete **all** lessons of the semester (matches the UI text «повного видалення поточного розкладу»), then re-sync slots. Locked lessons are not kept, because their slots may no longer exist (h).
   - When no re-sync is needed, the flag is ignored and no lesson is deleted. The current UI sends the flag on every save of a semester that has a schedule, renames included (`schedule_frontend/admin/semesters/semester.js:547-549`).
4. **Route name**: register `class_types` as the main route, and keep `class-types` as an alias with its own basename.
5. **Locked lessons in a forced slot sync** (ruled 2026-11-20): `synchronize_slots(force_delete=True)` deletes unlocked lessons and keeps locked ones. Before it deletes the slots that no longer exist, it unplaces the locked lessons on them (`time_slot = NULL`), so no locked lesson is deleted silently (h). This applies to `sync_slots`; the confirmed semester edit (decision 3) has already deleted all lessons by then.

## 4. Phases

Each phase is one commit (or PR) into `api-redesign-gaps` with tests, never into `main` (see Scope). Phases 1, 2 and 4 do not depend on each other after phase 0. Phase 3 needs phase 2's exception handler for the `code` field.

### Phase 0 — Prep (½ day)
- Done: branch `api-redesign-gaps` exists, and `0020_add_class_types.py` is committed (`2d0fdbd`) with a no-op reverse, so rolling back never deletes class types that study plans use (`PROTECT`). It is idempotent (`get_or_create`) and seeds a fresh DB; on the current local DB it adds nothing new.
- Migration `0021` for the `TimeSlot` unique constraint (item i), in one migration file:
  1. `RunPython` renumber: for each slot whose `start_time` matches a **different** entry of its semester's `time_schedule` (config normalised as in `synchronize_slots`), set `period_number` to that entry's 1-based position. Locally this moves slot 985 → 5 and 986 → 6. Log the count.
  2. `RunPython` dedupe of true copies only: for each `(semester, date, period_number, start_time)` group with more than one slot, keep the slot with the most lessons (tie → lowest id). Move the other slots' lessons to it. If a moved lesson would break `Lesson.unique_together (room, time_slot)`, set its `time_slot` to `NULL` (unplaced) instead of deleting it. Then delete the empty copies. Log the counts. If a `(semester, date, period_number)` clash is still left (different start times that match no config entry), stop the migration with the slot ids rather than guess. Reverse of both steps: no-op.
  3. `AlterUniqueTogether(name='timeslot', unique_together={('semester', 'date', 'period_number')})`.
  - Remove the `MultipleObjectsReturned` branch from `synchronize_slots()`. It can no longer happen, and it deleted lessons.
  - Back up the local `db.sqlite3` before applying it. The clash check is `SELECT semester_id, date, period_number, COUNT(*) FROM api_timeslot GROUP BY 1,2,3 HAVING COUNT(*) > 1`; run it again when production is updated later (out of scope here).
  - Tests: (1) two slots with the same date and period but different start times, each matching a config entry → both kept, renumbered, no lesson moved; (2) two true copies with lessons, including a room clash → one slot remains, no lesson is deleted, and the clashing lesson is unplaced.
- Test scaffold: delete `api/tests.py` (a `tests.py` next to a `tests/` package makes test discovery fail with an `ImportError`). Add the `api/tests/` package with `APITestCase` and small factories (semester with config, group, stream, teacher, subject, class type, room type, room, study plan, lesson). Run with `python manage.py test api`.

**Done when:** `0021` applies cleanly on a copy of the local DB (slots 985/986 renumbered, 641 and its 4 lessons unchanged), `makemigrations --check` is clean, the scaffold runs green, and CI/deploy is unchanged.

### Phase 1 — Class types route, `current` import (¼ day) — items b, f
- `api/urls.py`: `router.register(r'class_types', ClassTypeViewSet, basename='class_type')` plus the existing `class-types` registration as an alias.
- `api/views/schedule.py`: `from rest_framework import status`.
- Tests: `GET /api/class_types/` → 200 list; `GET /api/class-types/` → 200; `GET /api/semesters/current/` on an empty DB → 404 JSON.

**Done when:** the frontend study-plans page loads the real class types (no 5-type fallback).

### Phase 2 — Protected deletes return 409 (½ day) — item d
- New `api/exceptions.py` with `exception_handler(exc, context)`:
  - call DRF's handler first. If it returns a response whose `detail` is a string, add `code` from `exc.get_codes()` (decision 2);
  - if it returns `None` and `exc` is `ProtectedError` or `RestrictedError`, return 409 with `detail` and `code: "protected"`, plus `blocked_by`: a list of `{model: verbose_name_plural, count}` built from `exc.protected_objects` (`ProtectedError`) or `exc.restricted_objects` (`RestrictedError`; no `RESTRICT` FK exists today).
- Messages per model (Ukrainian), e.g. «Тип аудиторії використовують аудиторії (3). Спочатку змініть їм тип.». A generic message covers anything else.
- `api/views/groups.py:48-55`: remove the `GroupViewSet.destroy` override, so group deletes go through the handler. The frontend's `UI.errorText` reads `detail` before `error` (`schedule_frontend/assets/js/ui.js:355-356`), so the groups page needs no change.
- `config/settings.py`: `REST_FRAMEWORK = {'EXCEPTION_HANDLER': 'api.exceptions.exception_handler', ...}`. Merge with any existing `REST_FRAMEWORK` dict; none exists today.
- Tests: deleting a room type with a room → 409 JSON with `code: "protected"`, and the row still exists. Same for a group or stream used by a study plan and a class type used by a study plan. Deleting an unused room type → 204. A 404 response carries `code: "not_found"`.

**Done when:** no `DELETE` in the API returns an HTML page or a non-409 status for a protected FK.

### Phase 3 — Semester edit with an existing schedule (1–1½ days) — items a, g, h — after phase 2
- `SemesterSerializer`:
  - add `confirm_schedule_deletion = BooleanField(write_only=True, required=False, default=False)`. Because of the default it is always in `validated_data`, so both `create()` and `update()` pop it before calling `super()` (otherwise `Semester(**validated_data)` raises `TypeError`);
  - in `update()`, compare the old and new slot inputs: `start_date`, `end_date`, and the config's `time_schedule` and `weekends` (normalise `generation_config` the same way `synchronize_slots` does). Skip the re-sync if none changed, whatever the flag says;
  - if a re-sync is needed and `Lesson.objects.filter(study_plan__semester=instance).exists()` is true without the flag, raise a 409 (a custom `APIException` subclass `ScheduleExists`, `status_code = 409`, `default_code = 'schedule_exists'`; phase 2's handler puts the code in the body) **before** saving anything;
  - if a re-sync is needed and the flag is set: `transaction.atomic()` → delete the semester's lessons → `super().update()` → `synchronize_slots(force_delete=True)`;
  - `create()` otherwise unchanged (no lessons can exist).
- `Semester.synchronize_slots()`: keep the `ValueError` guard for direct callers, but use one lesson query (`study_plan__semester`) everywhere. Before deleting the slots that no longer exist, unplace the locked lessons on them (decision 5). Wrap the guard, the deletion, the unplacing and the slot rebuild in one `atomic()` block.
- `SemesterViewSet.sync_slots`: pass `force_delete=True` through, instead of deleting lessons itself and then calling without the flag (g). Map `ValueError` → 409, not 400. Its hand-built 409 bodies get `code: "schedule_exists"` too.
- Response of a confirmed edit: the normal semester JSON plus `deleted_lessons: <n>` (read-only, only on this response), so the UI can toast it.
- Tests:
  - `POST` a new semester, with and without `generation_config` → 201;
  - name-only `PATCH` with lessons → 200, lessons untouched;
  - name-only `PUT` with lessons **and** `confirm_schedule_deletion: true` → 200, lessons untouched, no `deleted_lessons`;
  - `PUT` changing only `dates_excluded`, with lessons, no flag → 200, lessons and slots untouched;
  - `PUT` with changed dates and lessons, no flag → 409 with `code: "schedule_exists"`, DB unchanged (dates, slots, lessons);
  - the same with the flag → 200, 0 lessons, slots match the new range;
  - changed config, no lessons → 200, slots rebuilt;
  - `sync_slots` with a locked lesson and `force_delete` → 200; the locked lesson still exists, on its slot if the slot survived, unplaced if it did not.

**Done when:** the frontend semester page shows its «⚠️ Увага!» confirm on 409, and «Так, видалити та змінити» succeeds. The 500 toast branch in `semester.js` is no longer reachable.

### Phase 4 — Lesson filters and ids for the public page (1 day) — items c, e
- `StudyPlanDepthSerializer`: add read-only `group_id`, `stream_id`, `teacher_id`, `subject_id`, `class_type_id` by listing them in `Meta.fields` (DRF builds read-only fields from the model attributes; `group_id`/`stream_id` come out `null` when unset). Do not declare them with `source='group_id'`: DRF rejects a `source` equal to the field name with an `AssertionError`. Keep the name fields.
- `LessonFilter`:
  - `teacher_id` → `study_plan__teacher_id` (exact);
  - `stream_id` → `study_plan__stream_id`;
  - `for_group` → lessons a group attends: `Q(study_plan__group_id=v) | Q(study_plan__stream__groups=v)`, with `.distinct()`. This replaces the frontend's 2 + N requests with one;
  - keep `group_id` (own-group plans only) and `teacher_name` unchanged.
- `LessonViewSet.queryset`: `select_related('time_slot', 'room', 'study_plan__subject', 'study_plan__teacher', 'study_plan__group', 'study_plan__stream', 'study_plan__class_type')`. The public page and the schedule grid serialise many lessons, and today every one of them costs about 6 queries.
- Tests: the `*_id` fields are present and `null` where the FK is unset. A group in a stream gets its own and its stream's lessons from `for_group`, with no duplicates. Two streams with the same name don't leak into each other. `teacher_id` doesn't match a teacher whose name contains another's name. Query count for 20 lessons stays constant (`assertNumQueries`).

**Done when:** `GET /api/lessons/?for_group=N&date_from=…&date_to=…` returns everything the public page shows for group N in one request.

## 5. Frontend follow-up (separate change in `schedule_frontend`, after each phase works locally)

- Phase 1: drop the `/class_types/` fallback comment and the 5-type fallback in `admin/study-plans/study-plan.js`. Keep a graceful error.
- Phase 2: `admin/rooms` room-type delete can show `errText(err)` directly. Remove the HTML-500 special case. Groups and streams need no change (`UI.errorText` reads `detail` first).
- Phase 3: `admin/semesters/semester.js`:
  - stop asking before every save of a semester that has a schedule (`semester.js:547-549`); save first and show the confirm only on a 409 `schedule_exists`, so a rename no longer warns about deleting the schedule;
  - remove the 5xx «бекенд поки не дозволяє…» toast and update the comment at `semester.js:168`;
  - show `deleted_lessons` in the success toast.
- Phase 3: `docs/regression-checklist.md`: add «перейменування семестру з розкладом зберігає заняття».
- Phase 4: `js/public.js`: `lessonsQuery` uses `for_group` / `teacher_id`, and the `streamPlanIds` cache and the client-side exact-name match are removed. The `?t=` link stays name-based, or adds the id (frontend decision).
- Update frontend plan 0001 §10 items (a)–(e) as each one closes.

## 6. Open questions for the user

None. (Production state was resolved 2026-11-20: out of scope, updated in full after the work is done. Re-sync triggers and locked lessons in a forced sync were ruled 2026-11-20: decisions 3 and 5.)

## 7. Risks

- **Accidental deploy**: a push or merge to `main` deploys with `migrate`. Keep all work on `api-redesign-gaps` and never push or merge it to `main` until production is updated in full. Only phase 0 has migrations: `0020` (data only) and `0021` (renumber + dedupe + unique constraint; back up the local DB first).
- **Frontend contract**: all changes are additive, plus three error responses that change shape: protected deletes become 409 JSON, group deletes move from 400 `error` to 409 `detail`, and error bodies gain `code`. The one behaviour change is a semester edit that changes no slot input, which no longer rebuilds slots. Today such an edit re-runs `update_or_create` for every slot of the semester and resets `is_available=True` on all of them.
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
| 2026-11-20 | `b4a5c3d` | Scope set to local only; production is out of scope and will be updated in full later. |
| 2026-11-20 | `813f44b` | Review rulings: `create()` pops the flag; flag ignored without a re-sync; phases land on `api-redesign-gaps`, not `main`; group delete override removed; `*_id` via `Meta.fields`; handler adds `code` (phase 3 after 2); `restricted_objects`; delete `api/tests.py`; header moved; `0021` renumbers mislabelled slots before deduping true copies; re-sync only on dates/`time_schedule`/`weekends` (A1); forced sync unplaces locked lessons (B1, decision 5). |
| 2026-11-20 | `c269aef` | Phases 0–4 implemented (`70b55a6`..`0b4c54f`), 31 tests green; `0021` applied locally (slots 985/986 → periods 5/6, no lessons moved). |
