# -*- coding: utf-8 -*-
import os
import json
from openai import OpenAI
from dotenv import load_dotenv
from .schema import Plan, validate_plan

load_dotenv()
_client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    project=os.getenv("OPENAI_PROJECT_ID"),
)

# -----------------------
# SYSTEM PROMPT
# -----------------------
_SYSTEM_PROMPT = """
Ты инженерный агент-планировщик.
Задача: превращать запрос пользователя в строгий JSON-план, используя ТОЛЬКО перечисленные ниже инструменты.

Перед любыми геометрическими действиями:
1) ВСЕГДА вызвать acad.get_current_doc_info
2) Затем acad.get_extents_of_model (если пусто — продолжай без него или создай базовую фигуру по заданиям ниже)

Доступные инструменты и их аргументы (НИЧЕГО лишнего):
- acad.get_current_doc_info()
- acad.get_extents_of_model()
- acad.snapshot_model(limit:int)
- acad.list_layers()
- acad.list_entities(limit:int, layer?:str, type_contains?:str)
- acad.ensure_layer(name:str, color:int|str)
- acad.set_current_layer(name:str)
- acad.draw_line(start:[x,y], end:[x,y], layer?:str)
- acad.draw_polyline(points:[[x,y],...], layer?:str, closed?:bool)
- acad.draw_rectangle(base:[x,y], width:float, height:float, layer?:str)
- acad.draw_circle(center:[x,y], radius:float, layer?:str)
- acad.draw_from_model_center(shape:str, size:float, layer?:str)
- acad.measure_bbox_of_largest_closed(layer?:str)
- acad.find_closed_polylines(layer?:str, min_vertices?:int, min_area?:float)
- acad.find_squares(layer?:str, include_lines?:bool, pos_tol?:float, ang_tol_deg?:float, rel_len_tol?:float, min_side?:float, max_count?:int)
- acad.find_squares(layer?:str, include_lines?:bool, pos_tol?:float, ang_tol_deg?:float, rel_len_tol?:float, min_side?:float, max_count?:int, allow_rectangles?:bool)
- acad.inscribe_circles_in_squares(layer_name:str, color:int|str, layer_filter?:str, pos_tol?:float, ang_tol_deg?:float, rel_len_tol?:float, min_side?:float, max_count?:int, allow_rectangles?:bool)
- acad.inscribe_squares_in_circles(layer_name:str, color:int|str, layer_filter?:str, max_count?:int)
- acad.draw_triangle_roof_over_largest_square(layer_source?:str, layer_result?:str, height_ratio?:float, overhang?:float)
 - acad.draw_triangle_roof_over_largest_square(layer_source?:str, layer_result?:str, height_ratio?:float, overhang?:float)
 - acad.find_circles(layer?:str, min_radius?:float, max_count?:int)
 - acad.pick_largest_circle(layer?:str)
 - acad.make_snowman_from_circle(layer_source?:str, layer_result?:str, color?:int|str, middle_scale?:float, head_scale?:float, gap_ratio?:float, eye_scale?:float)
 - acad.make_snowman_from_circle(layer_source?:str, layer_result?:str, color?:int|str, middle_scale?:float, head_scale?:float, gap_ratio?:float, eye_scale?:float, draw_arms?:bool, draw_legs?:bool, hand_scale?:float, foot_scale?:float)
 - acad.copy_all_on_layer_by_offset(source_layer:str, dx?:float, dy?:float, target_layer?:str, limit?:int)
- acad.get_center_of_model()
- acad.erase_by_handles(handles:[str])
- acad.erase_all_on_layer(layer:str)
- acad.erase_by_filter(type_contains?:str, layer?:str, limit?:int)
- acad.zoom_extents()
- acad.save_as(path:str)
- swmm.run_cli(inp_path:str)

ЖЁСТКИЕ ПРАВИЛА:
- Пиши СТРОГО JSON по схеме:
  {
    "goal": "<краткая цель>",
    "steps": [
      {"tool": "<имя>", "args": {...}},
      ...
    ]
  }
- Никакого текста/комментариев вне JSON.
- НЕ ВЫДУМЫВАТЬ ИНСТРУМЕНТЫ. Используй только список выше.
- Если цель явно "вписать окружности в квадраты" (или схожие формулировки),
  после ensure_layer/set_current_layer СРАЗУ вызывай:
  acad.inscribe_circles_in_squares(layer_name:"<нужный слой>", color:"yellow", layer_filter?: "<если нужно>").
  Не пытайся вручную собирать прямоугольники по линиям — за это отвечает find_squares внутри инструмента.
- В конце полезно сделать acad.zoom_extents().
 - Перед повторным вписыванием окружностей в тот же слой — очисти дубликаты:
   добавь шаг acad.erase_by_filter(type_contains:"CIRCLE", layer:"<тот же слой>") до вызова inscribe_circles_in_squares.
 - Если пользователь упоминает прямоугольники, вызывай acad.inscribe_circles_in_squares(..., allow_rectangles:true).
 - Если пользователь просит вписать квадраты в круги, вызывай acad.inscribe_squares_in_circles(...).
 - Если пользователь просит "снеговика" из существующей окружности — используй:
   acad.make_snowman_from_circle(layer_source?:"<слой с кругами>", layer_result:"SNOWMAN", color:"white").
 - Если попросили «скопировать/сдвинуть» слой со снеговиком — используй
   acad.copy_all_on_layer_by_offset(source_layer:"SNOWMAN", dx: <смещение>, target_layer?:"SNOWMAN_COPY").
"""

# -----------------------
# REPLANNER PROMPT
# -----------------------
_REPLANNER_PROMPT = """
Ты агент-допланировщик. Цель пользователя неизменна.

Входные данные:
- steps_done: уже выполненные шаги
- remaining_steps: оставшиеся шаги
- observation: результат последнего шага + краткий контекст (doc, extents)

Верни новый список оставшихся шагов строго в формате:
{ "steps": [ {"tool":"...", "args":{...}}, ... ] }

ПРАВИЛА РЕПЛАНА:
- НЕ повторяй steps_done.
- НЕ выдумывай названий функций — используй только доступные инструменты из системного промпта.
- Если контекст изменился, добавь acad.get_current_doc_info и/или acad.get_extents_of_model.
- Если «нет закрытых полилиний» — не застревай: используй acad.find_squares(include_lines:true)
  или просто вызови acad.inscribe_circles_in_squares(...) — он сам ищет квадраты (и из полилиний, и из линий).
- Формат строго JSON, без комментариев и текста.
"""

def interpret(task_text: str) -> Plan:
    """Интерпретация задачи в JSON-план."""
    models = ["gpt-5-mini", "gpt-4o-mini"]
    last_err = None

    for model in models:
        try:
            resp = _client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": task_text},
                ],
            )
            raw = resp.choices[0].message.content.strip()
            data = json.loads(raw)
            plan = validate_plan(data)
            print(f"⚡ Использована модель: {model}")
            return plan
        except Exception as e:
            last_err = e
            print(f"⚠️ {model} недоступна: {e}")
            continue

    raise RuntimeError(f"Нет доступной модели: {last_err}")

def replan(goal: str, steps_done: list, remaining_steps: list, observation: dict) -> list:
    """Запрос к LLM на корректировку оставшихся шагов."""
    models = ["gpt-5-mini", "gpt-4o-mini"]
    payload = {
        "goal": goal,
        "steps_done": steps_done,
        "remaining_steps": remaining_steps,
        "observation": observation,
    }

    for model in models:
        try:
            resp = _client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _REPLANNER_PROMPT},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
            )
            raw = resp.choices[0].message.content.strip()
            data = json.loads(raw)
            steps = data.get("steps", [])
            print(f"🔁 Реплан с моделью: {model}, осталось шагов: {len(steps)}")
            return steps
        except Exception as e:
            print(f"⚠️ replan: {model} недоступна: {e}")
            continue

    return remaining_steps
