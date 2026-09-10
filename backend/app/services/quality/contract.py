"""Контракт проверки качества — общий для всех пайплайнов.

Одна проверка = функция (subject, payload) -> Iterable[CheckOutcome].
Она НЕ печатает, НЕ пишет в БД и НЕ ходит в сеть: только смотрит на данные и
выносит вердикт. Всё остальное делает runner.

🔴 Почему status разделён на ok/fail/skip, а не bool:
   ревизор, которому нечего было проверить, обязан быть виден отдельно.
   Реальный случай проекта — проверка «успешно» вернула checked: 0 и месяцами
   охраняла пустоту. `skip` — это не «ок», это «я ничего не знаю».
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable


class Status(str, Enum):
    OK = "ok"        # проверка отработала, дефекта нет
    FAIL = "fail"    # проверка отработала, дефект есть
    SKIP = "skip"    # проверка не выносила вердикта — НЕ считается за «ок»


class Severity(str, Enum):
    HARD = "hard"    # данные не могли существовать: арифметика, невозможные соотношения
    SOFT = "soft"    # подозрительно, требует глаз: расхождение с источником, свежесть


@dataclass(frozen=True)
class CheckOutcome:
    check_id: str            # стабильный id: 'fin.balance_identity'
    subject: str             # что проверяли: 'SBER'
    status: Status
    severity: Severity = Severity.SOFT
    message: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def failed(self) -> bool:
        return self.status is Status.FAIL

    @property
    def skipped_by_design(self) -> bool:
        """Пропуск-норма (субъект законно вне охвата), а не пропуск-слепота."""
        return self.status is Status.SKIP and bool(self.evidence.get("by_design"))

    def as_dict(self) -> dict[str, Any]:
        return {"check_id": self.check_id, "subject": self.subject,
                "status": self.status.value, "severity": self.severity.value,
                "message": self.message, "evidence": self.evidence}


@dataclass(frozen=True)
class Check:
    """Описание проверки: id, человеческое название и сама функция."""
    check_id: str
    title: str
    severity: Severity
    fn: Callable[[str, dict], Iterable[CheckOutcome]]
    # Что чинит эта проверка — ссылка на реальный инцидент, чтобы через полгода
    # было понятно, зачем она существует и можно ли её выключать.
    rationale: str = ""

    def run(self, subject: str, payload: dict) -> list[CheckOutcome]:
        try:
            return list(self.fn(subject, payload))
        except Exception as exc:  # проверка не имеет права уронить прогон
            return [CheckOutcome(self.check_id, subject, Status.SKIP, self.severity,
                                 f"проверка упала: {type(exc).__name__}: {exc}"[:300],
                                 {"crashed": True})]


def ok(check: Check, subject: str, message: str = "", **evidence) -> CheckOutcome:
    return CheckOutcome(check.check_id, subject, Status.OK, check.severity, message, evidence)


def fail(check: Check, subject: str, message: str, **evidence) -> CheckOutcome:
    return CheckOutcome(check.check_id, subject, Status.FAIL, check.severity, message, evidence)


def skip(check: Check, subject: str, message: str = "нет данных", *,
         by_design: bool = False, **evidence) -> CheckOutcome:
    """Пропуск. 🔴 У пропуска ДВЕ РАЗНЫЕ природы, и путать их нельзя:

    by_design=False — «проверять было НЕЧЕМ»: данных нет, формат не распознан,
        проза без чисел. Это слепая зона, её надо чинить, и она обязана снижать
        покрытие — иначе прогон отчитается зелёным о пустоте.
    by_design=True  — «проверять по смыслу НЕ НУЖНО»: субъект законно вне охвата
        (реестр адресов не обязан быть свежим, у банка нет строки «выручка»).
        Это норма, её надо объяснять, и покрытие она снижать не должна —
        иначе показатель штрафует за правильное устройство системы.

    Различение появилось 11.09.2026 в разборе с сессией «SEO: свежесть»:
    report-slugs.json попал в находки как «протухший», хотя его назначение —
    ровно НЕ меняться."""
    return CheckOutcome(check.check_id, subject, Status.SKIP, check.severity, message,
                        {**evidence, "by_design": by_design} if by_design else evidence)
