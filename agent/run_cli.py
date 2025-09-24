from agent.llm import interpret
from agent.executor import Executor
from json import dumps

if __name__ == "__main__":
    print("Введите задачу (пример: Нарисуй квадрат 1000x1000 в AutoCAD на слое Pipes):")
    task = input("> ").strip() or "Нарисуй квадрат 1000x1000 в AutoCAD на слое Pipes"

    # получаем план от LLM
    plan = interpret(task)

    print("\n=== План ===")
    print(dumps(plan.model_dump(), indent=2, ensure_ascii=False))

    print("\n=== Исполнение ===")
    # варианты:
    #   replan_mode="never"     → без репланов
    #   replan_mode="on_error"  → реплан только при ошибке (рекомендуется)
    #   replan_mode="each_step" → реплан после каждого шага
    executor = Executor(replan_mode="on_error", max_replans=3)
    executor.run(plan)
