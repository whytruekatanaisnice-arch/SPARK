"""File-backed showcase data used only when the demo fallback is active."""
import json
import os
import threading
from pathlib import Path
from typing import Any, Callable, TypeVar
from uuid import uuid4

from app.config import settings

T = TypeVar("T")
_DATA_FILE = Path(__file__).resolve().parents[1] / "demo_data.json"
_LOCK = threading.RLock()
_fallback_active = False


def set_fallback_active(active: bool) -> None:
    global _fallback_active
    _fallback_active = active


def is_enabled() -> bool:
    return settings.DEMO_FALLBACK_ENABLED and _fallback_active


def _read() -> dict[str, Any]:
    try:
        with _DATA_FILE.open(encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Unable to load demo data from {_DATA_FILE}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Demo data in {_DATA_FILE} must be a JSON object")
    return data


def _save(data: dict[str, Any]) -> None:
    temporary_file = _DATA_FILE.with_suffix(".json.tmp")
    try:
        with temporary_file.open("w", encoding="utf-8", newline="\n") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temporary_file, _DATA_FILE)
    except OSError as exc:
        raise RuntimeError(f"Unable to save demo data to {_DATA_FILE}: {exc}") from exc


def read_data() -> dict[str, Any]:
    with _LOCK:
        return _read()


def change_data(change: Callable[[dict[str, Any]], T]) -> T:
    with _LOCK:
        data = _read()
        result = change(data)
        _save(data)
        return result


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in user.items() if key not in {"password", "password_hash"}}


def authenticate(email: str, password: str) -> dict[str, Any] | None:
    user = next(
        (item for item in read_data().get("users", []) if item["email"].casefold() == email.casefold()),
        None,
    )
    if user is None or user.get("password") != password or not user.get("is_active", True):
        return None
    return public_user(user)


def find_user(user_id: str) -> dict[str, Any] | None:
    user = next((item for item in read_data().get("users", []) if item["id"] == user_id), None)
    return public_user(user) if user else None


def check_password(user_id: str, password: str) -> bool:
    user = next((item for item in read_data().get("users", []) if item["id"] == user_id), None)
    return bool(user and user.get("password") == password)


def update_user(user_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
    def update(data: dict[str, Any]) -> dict[str, Any] | None:
        user = next((item for item in data.get("users", []) if item["id"] == user_id), None)
        if user is None:
            return None
        user.update(values)
        return public_user(user)

    return change_data(update)


def collection(name: str) -> list[dict[str, Any]]:
    return read_data().setdefault(name, [])


def get_record(name: str, record_id: str) -> dict[str, Any] | None:
    return next((item for item in collection(name) if item["id"] == record_id), None)


def create_record(name: str, values: dict[str, Any]) -> dict[str, Any]:
    record = {"id": str(uuid4()), **values}

    def update(data: dict[str, Any]) -> dict[str, Any]:
        data.setdefault(name, []).append(record)
        return record

    return change_data(update)


def update_record(name: str, record_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
    def update(data: dict[str, Any]) -> dict[str, Any] | None:
        record = next((item for item in data.setdefault(name, []) if item["id"] == record_id), None)
        if record is None:
            return None
        record.update(values)
        return record

    return change_data(update)


def delete_record(name: str, record_id: str) -> bool:
    def update(data: dict[str, Any]) -> bool:
        items = data.setdefault(name, [])
        for index, item in enumerate(items):
            if item["id"] == record_id:
                del items[index]
                return True
        return False

    return change_data(update)
