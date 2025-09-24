import threading
import time
import inspect
from typing import Dict, Any, List, Literal, Optional

from .schema import Plan
from .tools import TOOLS
from .config import STEP_RETRIES
from .utils.watchdog import start_watchdog
from . import llm


ReplanMode = Literal["never", "on_error"]


class Executor:
    """
    Исполняет пошаговый план (Plan), используя функции из TOOLS.

    Особенности:
    - Автофильтрация аргументов через inspect.signature (устойчивость к "мусорным" полям от LLM)
    - Многократные попытки выполнения (STEP_RETRIES)
    - Реплан:
        * "never"    — без репланов
        * "on_error" — реплан только при провале шага или непонятном результате (по умолчанию)
    - Watchdog и безопасная остановка
    - История шагов self.history
    """

    def __init__(
        self,
        reporter=print,
        replan_mode: ReplanMode = "on_error",
        max_replans: int = 3,
    ):
        self.report = reporter
        self._stop = threading.Event()
        self._watchdog = None

        self.replan_mode: ReplanMode = replan_mode
        self.max_replans = max_replans
        self._replans_done = 0

        self.history: List[Dict[str, Any]] = []

    # ------------------------------
    # Публичные методы
    # ------------------------------

    def stop(self):
        """Прервать исполнение"""
        self._stop.set()

    def run(self, plan: Plan) -> bool:
        """Запустить исполнение плана"""
        self._replans_done = 0
        self.report(f"🚀 Старт исполнения: {plan.goal}")
        self._watchdog = start_watchdog(self._stop, self.report)

        # нормализуем шаги: pydantic.Step → dict
        remaining: List[Dict[str, Any]] = [
            s.model_dump() if hasattr(s, "model_dump") else dict(s)
            for s in plan.steps
        ]
        steps_done: List[Dict[str, Any]] = []

        step_idx = 0
        while step_idx < len(remaining):
            if self._stop.is_set():
                self.report("⏹ Остановлено пользователем")
                return False

            step = remaining[step_idx]
            tool = step.get("tool")
            args = step.get("args", {}) or {}

            ok, result = self._run_step(
                idx=len(steps_done) + 1,
                total_from_here=len(steps_done) + len(remaining) - step_idx,
                tool=tool,
                args=args,
            )

            steps_done.append({"tool": tool, "args": args, "ok": ok, "result": result})
            self.history.append(steps_done[-1])

            if not ok or not self._is_result_clear(result):
                # провал или результат "непонятный"
                if self.replan_mode == "on_error" and self._replans_done < self.max_replans:
                    new_remaining = self._do_replan(
                        plan.goal,
                        steps_done,
                        remaining[step_idx + 1 :],
                        last_result=result,
                    )
                    if new_remaining is not None:
                        remaining = remaining[: step_idx + 1] + new_remaining
                        step_idx += 1
                        continue
                self.report(f"❌ Шаг провален или непонятен: {tool}")
                return False

            step_idx += 1

        self.report("✅ Выполнено")
        return True

    # ------------------------------
    # Внутренние методы
    # ------------------------------

    def _normalize_args(self, fn, args: Dict[str, Any]) -> Dict[str, Any]:
        """Отсечь лишние аргументы от LLM (устойчивость к мусору)"""
        try:
            sig = inspect.signature(fn)
            allowed = sig.parameters.keys()
            return {k: v for k, v in args.items() if k in allowed}
        except Exception:
            return args

    def _is_result_clear(self, result: Dict[str, Any]) -> bool:
        """
        Проверка: понятный ли результат.
        - ok=False → непонятно
        - есть reason=... → тоже подозрительно, просим LLM уточнить
        """
        if not isinstance(result, dict):
            return False
        if not result.get("ok", False):
            return False
        if "reason" in result and result.get("reason"):
            return False
        return True

    def _run_step(self, idx: int, total_from_here: int, tool: str, args: Dict[str, Any]):
        """Выполнить один шаг"""
        self.report(f" [{idx}/~{idx+total_from_here-1}] {tool} {args}")
        fn = TOOLS.get(tool)
        if not fn:
            return False, {"error": f"unknown tool {tool}"}

        last_err = None
        for attempt in range(1, STEP_RETRIES + 1):
            try:
                safe_args = self._normalize_args(fn, args or {})
                res = fn(**safe_args)
                if not (isinstance(res, dict) and res.get("ok")):
                    raise RuntimeError(f"step returned {res}")
                self.report(f"  → ok ({attempt})")
                return True, res
            except Exception as e:
                last_err = str(e)
                self.report(f"  ! ошибка попытка {attempt}: {e}")
                time.sleep(0.4)

        return False, {"error": last_err}

    def _do_replan(
        self,
        goal: str,
        steps_done: List[Dict[str, Any]],
        remaining_steps: List[Dict[str, Any]],
        last_result: Dict[str, Any],
    ) -> Optional[List[Dict[str, Any]]]:
        """Выполнить репланирование (с чтением свежего контекста из AutoCAD). Вернуть новый remaining или None."""
        try:
            doc_info = TOOLS.get("acad.get_current_doc_info", lambda: {"ok": False})()
            extents = TOOLS.get("acad.get_extents_of_model", lambda: {"ok": False})()

            obs = {
                "last_result": last_result,
                "doc": doc_info.get("doc") if isinstance(doc_info, dict) and doc_info.get("ok") else None,
                "extents": extents if isinstance(extents, dict) and extents.get("ok") else None,
            }

            new_remaining = llm.replan(
                goal=goal,
                steps_done=steps_done,
                remaining_steps=remaining_steps,
                observation=obs,
            )
            if isinstance(new_remaining, list):
                self._replans_done += 1
                self.report(
                    f"🔁 Реплан выполнен: новых шагов {len(new_remaining)} "
                    f"(реплан {self._replans_done}/{self.max_replans})"
                )
                return new_remaining
            return None
        except Exception as e:
            self.report(f"ℹ️ Реплан пропущен: {e}")
            return None
