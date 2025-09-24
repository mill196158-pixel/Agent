# -*- coding: utf-8 -*-
from . import acad as _acad
from . import swmm as _swmm

# Основной реестр инструментов, доступных LLM.
TOOLS = {
    # AutoCAD — рисование
    "acad.ensure_layer": _acad.ensure_layer,
    "acad.set_current_layer": _acad.set_current_layer,
    "acad.draw_line": _acad.draw_line,
    "acad.draw_polyline": _acad.draw_polyline,
    "acad.draw_rectangle": _acad.draw_rectangle,
    "acad.draw_circle": _acad.draw_circle,
    "acad.draw_from_model_center": _acad.draw_from_model_center,
    "acad.draw_triangle_roof_over_largest_square": _acad.draw_triangle_roof_over_largest_square,
    "acad.find_circles": _acad.find_circles,
    "acad.pick_largest_circle": _acad.pick_largest_circle,
    "acad.make_snowman_from_circle": _acad.make_snowman_from_circle,
    "acad.copy_all_on_layer_by_offset": _acad.copy_all_on_layer_by_offset,

    # AutoCAD — чтение/контекст
    "acad.get_current_doc_info": _acad.get_current_doc_info,
    "acad.snapshot_model": _acad.snapshot_model,
    "acad.list_layers": _acad.list_layers,
    "acad.list_entities": _acad.list_entities,
    "acad.get_extents_of_model": _acad.get_extents_of_model,
    "acad.get_center_of_model": _acad.get_center_of_model,
    "acad.find_closed_polylines": _acad.find_closed_polylines,
    "acad.measure_bbox_of_largest_closed": _acad.measure_bbox_of_largest_closed,

    # ВАЖНО: поиски квадратов и готовое действие «вписать окружности»
    "acad.find_squares": _acad.find_squares,
    "acad.inscribe_circles_in_squares": _acad.inscribe_circles_in_squares,
    "acad.inscribe_squares_in_circles": _acad.inscribe_squares_in_circles,

    # AutoCAD — удаление
    "acad.erase_by_handles": _acad.erase_by_handles,
    "acad.erase_all_on_layer": _acad.erase_all_on_layer,
    "acad.erase_by_filter": _acad.erase_by_filter,

    # Утилиты
    "acad.zoom_extents": _acad.zoom_extents,
    "acad.save_as": _acad.save_as,

    # SWMM
    "swmm.run_cli": _swmm.run_cli,
}

# --- Защита от «выдуманных» имен, которые модель могла использовать раньше ---
# Мягкие алиасы: возвращают тот же формат, что find_squares
def _alias_find_rectangles_from_lines(**kwargs):
    # Игнорируем любые «креативные» аргументы и делаем то, что реально нужно.
    return _acad.find_squares(include_lines=True)

def _alias_measure_bboxes_of_rectangles(**kwargs):
    return _acad.find_squares(include_lines=True)

TOOLS["acad.find_rectangles_from_lines"] = _alias_find_rectangles_from_lines
TOOLS["acad.measure_bboxes_of_rectangles"] = _alias_measure_bboxes_of_rectangles
