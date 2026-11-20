"""DRF exception handler: adds ``code`` to error bodies and answers protected deletes with 409."""

from django.db.models.deletion import ProtectedError, RestrictedError
from django.http import Http404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from api.models import Room, StudyPlan

PROTECTED_MESSAGES = {
    Room: "Тип аудиторії використовують аудиторії ({n}). Спочатку змініть їм тип.",
    StudyPlan: "Цей об'єкт використовують навчальні плани ({n}). Спочатку приберіть його з навчальних планів.",
}
FALLBACK_MESSAGE = "Об'єкт не можна видалити: його використовують інші записи ({n}: {models})."


def _group_by_model(objects):
    counts = {}
    for obj in objects:
        name = str(obj._meta.verbose_name_plural)
        counts[name] = counts.get(name, 0) + 1
    return [{"model": name, "count": counts[name]} for name in sorted(counts)]


def _protected_message(objects, total, blocked_by):
    blocker_model = type(objects[0]) if objects else None
    if blocker_model in PROTECTED_MESSAGES and len(blocked_by) == 1:
        return PROTECTED_MESSAGES[blocker_model].format(n=total)
    models = ", ".join(entry["model"] for entry in blocked_by)
    return FALLBACK_MESSAGE.format(n=total, models=models)


def _protected_response(exc):
    if isinstance(exc, ProtectedError):
        objects = list(exc.protected_objects)
    else:
        objects = list(exc.restricted_objects)

    total = len(objects)
    blocked_by = _group_by_model(objects)
    detail = _protected_message(objects, total, blocked_by)

    return Response(
        {"detail": detail, "code": "protected", "blocked_by": blocked_by},
        status=status.HTTP_409_CONFLICT,
    )


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)

    if response is not None:
        data = response.data
        if isinstance(data, dict) and isinstance(data.get("detail"), str):
            get_codes = getattr(exc, "get_codes", None)
            if get_codes is not None:
                code = get_codes()
            elif isinstance(exc, Http404):
                code = "not_found"
            else:
                code = None
            if isinstance(code, str):
                data["code"] = code
        return response

    if isinstance(exc, (ProtectedError, RestrictedError)):
        return _protected_response(exc)

    return None
