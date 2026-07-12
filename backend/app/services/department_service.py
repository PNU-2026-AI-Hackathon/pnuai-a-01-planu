"""Department autocomplete and validation backed by generated JSON."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable


class DepartmentDataError(ValueError):
    pass


def _search_key(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


class DepartmentService:
    def __init__(self, department_file: str | Path, *, aliases_file: str | Path | None = None):
        self.department_file = Path(department_file)
        self.aliases_file = Path(aliases_file) if aliases_file else None
        self._departments: tuple[str, ...] = ()
        self._aliases: dict[str, str] = {}
        self.reload()

    @property
    def departments(self) -> list[str]:
        return list(self._departments)

    def reload(self) -> None:
        try:
            payload = json.loads(self.department_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DepartmentDataError("학과 목록을 읽을 수 없습니다.") from exc
        if isinstance(payload, dict):
            payload = payload.get("departments")
        departments = _extract_departments(payload)
        if not departments:
            raise DepartmentDataError("학과 목록 JSON에서 학과명을 찾을 수 없습니다.")
        cleaned = {item.strip() for item in departments if item.strip()}
        self._departments = tuple(sorted(cleaned, key=lambda item: (_search_key(item), item)))
        self._aliases = {}
        if self.aliases_file and self.aliases_file.exists():
            try:
                aliases = json.loads(self.aliases_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise DepartmentDataError("학과 별칭 목록을 읽을 수 없습니다.") from exc
            if not isinstance(aliases, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in aliases.items()):
                raise DepartmentDataError("department_alias.json은 문자열 매핑이어야 합니다.")
            self._aliases = {_search_key(k): v.strip() for k, v in aliases.items()}

    def normalize(self, department: str) -> str | None:
        key = _search_key(department)
        if not key:
            return None
        canonical_by_key = {_search_key(item): item for item in self._departments}
        canonical = canonical_by_key.get(key)
        if canonical:
            return canonical
        alias_target = self._aliases.get(key)
        return canonical_by_key.get(_search_key(alias_target)) if alias_target else None

    def is_valid(self, department: str) -> bool:
        return self.normalize(department) is not None

    def validate(self, department: str) -> str:
        canonical = self.normalize(department)
        if canonical is None:
            raise ValueError("유효하지 않은 학과입니다. 제공된 학과 목록에서 선택해 주세요.")
        return canonical

    def search(self, keyword: str = "", *, limit: int = 20) -> list[str]:
        if limit < 1:
            return []
        key = _search_key(keyword)
        matches = [item for item in self._departments if key in _search_key(item)]
        # Exact/prefix matches are more useful than arbitrary substrings.
        matches.sort(key=lambda item: (
            0 if _search_key(item) == key else 1 if _search_key(item).startswith(key) else 2,
            len(item), item,
        ))
        return matches[:limit]


def load_departments(path: str | Path) -> list[str]:
    return DepartmentService(path).departments


def search_departments(departments: Iterable[str], keyword: str = "", *, limit: int = 20) -> list[str]:
    key = _search_key(keyword)
    result = sorted(
        {item.strip() for item in departments if item.strip() and key in _search_key(item)},
        key=lambda item: (0 if _search_key(item).startswith(key) else 1, len(item), item),
    )
    return result[:max(0, limit)]


def _extract_departments(payload: object) -> list[str]:
    if isinstance(payload, list) and all(isinstance(item, str) for item in payload):
        return [item for item in payload if item.strip()]
    if isinstance(payload, list) and all(isinstance(item, dict) for item in payload):
        departments: list[str] = []
        for group in payload:
            values = group.get("departments")
            if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
                raise DepartmentDataError("departments.json의 departments는 문자열 배열이어야 합니다.")
            departments.extend(item for item in values if item.strip())
        return departments
    raise DepartmentDataError("학과 목록 JSON은 문자열 배열 또는 college/departments 배열이어야 합니다.")
