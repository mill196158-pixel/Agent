from __future__ import annotations
from typing import List, Tuple, Dict, Any, Optional, Iterable, Set
import math
import time

from pyautocad import Autocad, APoint, aDouble

# =====================================================
# НАСТРОЙКИ / ТОЧНОСТИ
# =====================================================

# геометрические допуски по умолчанию
_POS_TOL = 1e-6            # допуск на совпадение точек (единицы чертежа)
_ANG_TOL_DEG = 1.0         # допуск на прямой угол (в градусах)
_REL_LEN_TOL = 0.02        # относительный допуск равенства сторон (2%)
_MIN_SIDE = 1e-6           # минимальная сторона квадрата (чтобы отсеять мусор)

# =====================================================
# ВНУТРЕННИЕ ХЕЛПЕРЫ: COM/AutoCAD
# =====================================================

def _get_acad(retries: int = 5, sleep_sec: float = 0.2) -> Autocad:
    """Создает/возвращает подключение к AutoCAD через COM (с ретраями)."""
    last_err = None
    for _ in range(retries):
        try:
            return Autocad(create_if_not_exists=True)
        except Exception as e:
            last_err = e
            time.sleep(sleep_sec)
    # если упорно не удаётся — пробросим исключение
    raise RuntimeError(f"AutoCAD COM init failed: {last_err}")

def _doc():
    return _get_acad().doc

def _ms():
    return _doc().ModelSpace

def _object_name(e) -> str:
    try:
        name = getattr(e, "ObjectName", "") or ""
        return str(name)
    except Exception:
        return ""

def _is_type(e, contains: str) -> bool:
    return contains.lower() in _object_name(e).lower()

# =====================================================
# ВНУТРЕННИЕ ХЕЛПЕРЫ: ГЕОМЕТРИЯ
# =====================================================

def _dist(p: Tuple[float, float], q: Tuple[float, float]) -> float:
    return math.hypot(p[0] - q[0], p[1] - q[1])

def _near(a: float, b: float, rel_tol: float = _REL_LEN_TOL, abs_tol: float = _POS_TOL) -> bool:
    if abs(a - b) <= abs_tol:
        return True
    # защита от деления на 0
    m = max(abs(a), abs(b), abs_tol)
    return abs(a - b) / m <= rel_tol

def _angle_deg(a: Tuple[float, float], b: Tuple[float, float], c: Tuple[float, float]) -> float:
    """Угол ABC в градусах."""
    v1 = (a[0]-b[0], a[1]-b[1])
    v2 = (c[0]-b[0], c[1]-b[1])
    n1 = math.hypot(*v1) or 1.0
    n2 = math.hypot(*v2) or 1.0
    v1 = (v1[0]/n1, v1[1]/n1)
    v2 = (v2[0]/n2, v2[1]/n2)
    dot = max(-1.0, min(1.0, v1[0]*v2[0] + v1[1]*v2[1]))
    return math.degrees(math.acos(dot))

def _bbox_from_points_3d(pts3: List[Tuple[float, float, float]]):
    if not pts3:
        return None
    xs = [p[0] for p in pts3]; ys = [p[1] for p in pts3]; zs = [p[2] for p in pts3]
    return ( (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)) )

def _bbox_from_points_2d(pts2: List[Tuple[float, float]]):
    if not pts2:
        return None
    xs = [p[0] for p in pts2]; ys = [p[1] for p in pts2]
    return ( (min(xs), min(ys)), (max(xs), max(ys)) )

def _poly_area_xy(pts2: List[Tuple[float, float]]) -> float:
    if len(pts2) < 3:
        return 0.0
    s = 0.0
    n = len(pts2)
    for i in range(n):
        x1, y1 = pts2[i]
        x2, y2 = pts2[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) * 0.5

def _centroid(pts2: List[Tuple[float, float]]):
    """Центроид многоугольника. Использует подписанную площадь (устойчив к CW/CCW)."""
    if len(pts2) < 3:
        x = sum(p[0] for p in pts2) / max(1, len(pts2))
        y = sum(p[1] for p in pts2) / max(1, len(pts2))
        return (x, y)
    signed_sum = 0.0
    cx_num = 0.0
    cy_num = 0.0
    n = len(pts2)
    for i in range(n):
        x1, y1 = pts2[i]
        x2, y2 = pts2[(i + 1) % n]
        cross = x1 * y2 - x2 * y1
        signed_sum += cross
        cx_num += (x1 + x2) * cross
        cy_num += (y1 + y2) * cross
    A = signed_sum / 2.0
    if abs(A) <= _POS_TOL:
        x = sum(p[0] for p in pts2) / n
        y = sum(p[1] for p in pts2) / n
        return (x, y)
    cx = cx_num / (6.0 * A)
    cy = cy_num / (6.0 * A)
    return (cx, cy)

def _is_square_vertices(verts: List[Tuple[float, float]],
                        ang_tol_deg: float = _ANG_TOL_DEG,
                        rel_len_tol: float = _REL_LEN_TOL,
                        min_side: float = _MIN_SIDE) -> bool:
    """Проверяет, что 4 вершины образуют квадрат (порядок по контуру!)."""
    if len(verts) != 4:
        return False
    # стороны
    sides = [
        _dist(verts[0], verts[1]),
        _dist(verts[1], verts[2]),
        _dist(verts[2], verts[3]),
        _dist(verts[3], verts[0]),
    ]
    if any(s < min_side for s in sides):
        return False
    # равенство сторон
    s_mean = sum(sides) / 4.0
    if any(not _near(s, s_mean, rel_tol=rel_len_tol) for s in sides):
        return False
    # углы ≈ 90°
    angs = [
        _angle_deg(verts[3], verts[0], verts[1]),
        _angle_deg(verts[0], verts[1], verts[2]),
        _angle_deg(verts[1], verts[2], verts[3]),
        _angle_deg(verts[2], verts[3], verts[0]),
    ]
    if any(abs(a - 90.0) > ang_tol_deg for a in angs):
        return False
    return True

def _is_rectangle_vertices(verts,
                           ang_tol_deg: float = _ANG_TOL_DEG,
                           rel_len_tol: float = _REL_LEN_TOL,
                           min_side: float = _MIN_SIDE):
    if len(verts) != 4:
        return False
    sides = [
        _dist(verts[0], verts[1]),
        _dist(verts[1], verts[2]),
        _dist(verts[2], verts[3]),
        _dist(verts[3], verts[0]),
    ]
    if any(s < min_side for s in sides):
        return False
    # прямые углы
    angs = [
        _angle_deg(verts[3], verts[0], verts[1]),
        _angle_deg(verts[0], verts[1], verts[2]),
        _angle_deg(verts[1], verts[2], verts[3]),
        _angle_deg(verts[2], verts[3], verts[0]),
    ]
    if any(abs(a - 90.0) > ang_tol_deg for a in angs):
        return False
    # противоположные стороны ≈ равны
    return _near(sides[0], sides[2], rel_tol=rel_len_tol) and _near(sides[1], sides[3], rel_tol=rel_len_tol)

def _order_loop(points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Упорядочить 4 точки по контуру (для наборов из линий). Простой способ: начать с левой-нижней и идти по ближнему."""
    if len(points) != 4:
        return points
    pts = points[:]
    # старт: левая-низняя
    pts.sort(key=lambda p: (p[0], p[1]))
    start = pts[0]
    rest = pts[1:]
    # выберем два ближайших шага по периметру
    # жадно: выбираем ближайшую, потом снова ближайшую к последней
    ordered = [start]
    current = start
    for _ in range(3):
        rest.sort(key=lambda p: _dist(current, p))
        nxt = rest.pop(0)
        ordered.append(nxt)
        current = nxt
    return ordered

# =====================================================
# ВЫТЯГИВАНИЕ ГЕОМЕТРИИ ИЗ ENTITIES
# =====================================================

def _coords_from_polyline(e) -> List[Tuple[float, float, float]]:
    """Достать координаты из Polyline/LWPolyline как список (x,y,z)."""
    # Пытаемся как 3D
    try:
        arr = list(e.Coordinates)  # x,y,z,x,y,z...
        pts = [(float(arr[i]), float(arr[i+1]), float(arr[i+2])) for i in range(0, len(arr), 3)]
        return pts
    except Exception:
        pass
    # Пытаемся как 2D
    try:
        arr = list(e.Coordinates)
        pts2d = [(float(arr[i]), float(arr[i+1]), 0.0) for i in range(0, len(arr), 2)]
        return pts2d
    except Exception:
        return []

def _polyline_is_closed(e) -> bool:
    try:
        return bool(e.Closed)
    except Exception:
        # проверим по первой/последней точке
        pts3 = _coords_from_polyline(e)
        if pts3:
            return (abs(pts3[0][0]-pts3[-1][0]) <= _POS_TOL) and (abs(pts3[0][1]-pts3[-1][1]) <= _POS_TOL)
        return False

def _polyline_vertices_2d_ordered(e) -> List[Tuple[float, float]]:
    pts3 = _coords_from_polyline(e)
    if not pts3:
        return []
    pts2 = [(p[0], p[1]) for p in pts3]
    # если дублируется последняя точка — уберём
    if len(pts2) >= 2 and _dist(pts2[0], pts2[-1]) <= _POS_TOL:
        pts2 = pts2[:-1]
    return pts2

def _get_bbox_entity(e):
    """Попытаться получить bbox для объекта e."""
    name = _object_name(e)
    # Polyline
    if "polyline" in name.lower():
        pts3 = _coords_from_polyline(e)
        return _bbox_from_points_3d(pts3)
    # Line
    if "line" in name.lower() and "polyline" not in name.lower():
        try:
            sp = e.StartPoint; ep = e.EndPoint
            return _bbox_from_points_3d([(float(sp[0]), float(sp[1]), float(sp[2])),
                                         (float(ep[0]), float(ep[1]), float(ep[2]))])
        except Exception:
            return None
    # Circle
    if "circle" in name.lower():
        try:
            c = e.Center; r = float(e.Radius)
            return ((c[0]-r, c[1]-r, 0.0), (c[0]+r, c[1]+r, 0.0))
        except Exception:
            return None
    # Hatch/Solid/BlockRef — попытаемся через bounding box по координатам/методу
    # Try COM: GetBoundingBox (может не работать одинаково во всех версиях)
    try:
        # pyautocad может не поддержать ссылочные параметры,
        # поэтому просто попробуем доступ к Extents (не всегда есть)
        # fallback: нет — вернём None
        if hasattr(e, "GetBoundingBox"):
            # попытка — не везде корректно работает через python
            # оставим как потенциальный хук, но без жёсткой зависимости
            pass
    except Exception:
        pass
    return None

# =====================================================
# БАЗОВЫЕ РИСОВАЛКИ
# =====================================================

def _color_to_aci(color: Any) -> int:
    """Преобразовать строковый цвет в ACI или пропустить int."""
    if isinstance(color, int):
        return color
    if isinstance(color, str):
        c = color.strip().lower()
        table = {
            "red": 1, "желтый": 2, "yellow": 2, "green": 3, "cyan": 4,
            "blue": 5, "magenta": 6, "white": 7, "black": 7,
        }
        return table.get(c, 7)
    return 7

def ensure_layer(name: str, color: Any = 3, **kwargs):
    acad = _get_acad()
    layers = acad.doc.Layers
    try:
        layer = layers.Item(name)
    except Exception:
        layer = layers.Add(name)
    # попытка выставить цвет
    try:
        layer.Color = _color_to_aci(color)
    except Exception:
        pass
    return {"ok": True, "layer": name}

def set_current_layer(name: str, **kwargs):
    acad = _get_acad()
    acad.doc.ActiveLayer = acad.doc.Layers.Item(name)
    return {"ok": True, "layer": name}

def _to_3d_flat(points_2d: List[Tuple[float, float]]) -> List[float]:
    flat: List[float] = []
    for x, y in points_2d:
        flat.extend([float(x), float(y), 0.0])
    return flat

def draw_line(start: Tuple[float, float], end: Tuple[float, float], layer: str | None = None, **kwargs):
    ms = _ms()
    e = ms.AddLine(APoint(float(start[0]), float(start[1])),
                   APoint(float(end[0]), float(end[1])))
    if layer:
        e.Layer = layer
    time.sleep(0.02)
    return {"ok": True, "handle": getattr(e, "Handle", None)}

def draw_polyline(points: List[Tuple[float, float]],
                  layer: str | None = None,
                  closed: bool = True,
                  **kwargs):
    """Создает полилинию по точкам. Если closed и контур не замкнут — замкнём."""
    pts = list(points)
    if closed and pts and _dist(pts[0], pts[-1]) > _POS_TOL:
        pts.append(pts[0])
    ms = _ms()
    flat3d = _to_3d_flat(pts)
    pl = ms.AddPolyline(aDouble(*flat3d))
    try:
        pl.Closed = closed
    except Exception:
        pass
    if layer:
        pl.Layer = layer
    return {"ok": True, "handle": getattr(pl, "Handle", None)}

def draw_rectangle(base: Tuple[float, float], width: float, height: float, layer: str | None = None, **kwargs):
    x, y = float(base[0]), float(base[1])
    w, h = float(width), float(height)
    pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    return draw_polyline(pts, layer=layer, closed=True)

def draw_circle(center: Tuple[float, float], radius: float, layer: str | None = None, **kwargs):
    ms = _ms()
    c = ms.AddCircle(APoint(float(center[0]), float(center[1])), float(radius))
    if layer:
        c.Layer = layer
    return {"ok": True, "handle": getattr(c, "Handle", None)}

def zoom_extents(**kwargs):
    acad = _get_acad()
    time.sleep(0.2)
    acad.app.ZoomExtents()
    return {"ok": True}

def save_as(path: str, **kwargs):
    acad = _get_acad()
    acad.doc.SaveAs(path)
    return {"ok": True, "path": path}

# =====================================================
# ЧТЕНИЕ / АНАЛИТИКА / КОНТЕКСТ
# =====================================================

def get_current_doc_info(retries: int = 10, sleep_sec: float = 0.2, **kwargs):
    """Надёжно получить имя/путь текущего DWG. Дожидается, если документ ещё не готов."""
    acad = _get_acad()
    doc = None
    last_err = None
    for _ in range(retries):
        try:
            doc = acad.doc
            if doc is not None and getattr(doc, "Name", None):
                break
            app = acad.app
            if hasattr(app, "ActiveDocument"):
                doc = app.ActiveDocument
                if doc is not None and getattr(doc, "Name", None):
                    break
        except Exception as e:
            last_err = e
        time.sleep(sleep_sec)

    if doc is None:
        return {"ok": False, "error": f"no_active_document: {last_err}"}

    info = {
        "name": getattr(doc, "Name", None),
        "fullpath": getattr(doc, "FullName", None),
        "saved": bool(getattr(doc, "Saved", True)),
    }
    return {"ok": True, "doc": info}

def list_layers(limit: int | None = None, **kwargs) -> Dict[str, Dict[str, Any]]:
    acad = _get_acad()
    layers = {}
    count = acad.doc.Layers.Count
    if limit is not None:
        count = min(count, int(limit))
    for i in range(count):
        l = acad.doc.Layers.Item(i)
        layers[l.Name] = {
            "name": l.Name,
            "on": getattr(l, "LayerOn", True),
            "frozen": getattr(l, "Freeze", False),
            "locked": getattr(l, "Lock", False),
        }
    return {"ok": True, "layers": layers}

def list_entities(limit: int = 100,
                  layer: str | None = None,
                  type_contains: str | None = None,
                  **kwargs):
    ms = _ms()
    res = []
    count = 0
    type_filter = (type_contains or "").lower()
    for e in ms:
        if layer and getattr(e, "Layer", None) != layer:
            continue
        if type_filter and type_filter not in _object_name(e).lower():
            continue
        res.append({
            "handle": getattr(e, "Handle", None),
            "type": _object_name(e),
            "layer": getattr(e, "Layer", None),
        })
        count += 1
        if count >= limit:
            break
    return {"ok": True, "entities": res}

def get_extents_of_model(**kwargs):
    """Границы модели по типовым объектам (Polyline/Line/Circle); если совсем пусто — ok=False."""
    ms = _ms()
    minx = miny = float("inf")
    maxx = maxy = float("-inf")
    any_found = False

    for e in ms:
        bbox = _get_bbox_entity(e)
        if bbox:
            any_found = True
            (x1, y1, _), (x2, y2, _) = bbox
            minx, miny = min(minx, x1), min(miny, y1)
            maxx, maxy = max(maxx, x2), max(maxy, y2)

    if not any_found:
        return {"ok": False, "reason": "no_entities"}

    return {"ok": True,
            "min": (minx, miny),
            "max": (maxx, maxy),
            "center": ((minx + maxx) / 2.0, (miny + maxy) / 2.0)}

def get_center_of_model(**kwargs):
    ext = get_extents_of_model()
    if not ext.get("ok"):
        return {"ok": False, "reason": "empty_model"}
    return {"ok": True, "center": ext["center"]}

def snapshot_model(limit: int = 20,
                   layer: str | None = None,
                   type_contains: str | None = None,
                   **kwargs):
    """Снимок контекста: документ, экстенты, слои (имена) и N объектов (тип/слой/handle)."""
    doc = get_current_doc_info()
    ext = get_extents_of_model()
    layers = list(list_layers().get("layers", {}).keys())
    ents = list_entities(limit=limit, layer=layer, type_contains=type_contains).get("entities", [])
    return {
        "ok": True,
        "doc": doc.get("doc"),
        "extents": ext if ext.get("ok") else None,
        "layers": layers,
        "entities": ents,
    }

# =====================================================
# ПОИСК МНОГОУГОЛЬНИКОВ / КВАДРАТОВ НЕЗАВИСИМО ОТ ТИПА
# =====================================================

def _find_loops_from_lines(lines: List[Dict[str, Any]],
                           pos_tol: float = _POS_TOL) -> List[List[Tuple[float, float]]]:
    """
    Собирает замкнутые контуры из набора LINE (только 4-реберные циклы).
    Возвращает список контуров как упорядоченные 4 точки.
    """
    # извлекаем сегменты
    segs: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
    for d in lines:
        e = d["entity"]
        try:
            sp = e.StartPoint; ep = e.EndPoint
            p1 = (float(sp[0]), float(sp[1]))
            p2 = (float(ep[0]), float(ep[1]))
            segs.append((p1, p2))
        except Exception:
            continue

    # граф по точкам (схлопнем близкие точки)
    # нормализатор точки
    def key_pt(p):
        return (round(p[0]/pos_tol)*pos_tol, round(p[1]/pos_tol)*pos_tol)

    adj: Dict[Tuple[float,float], Set[Tuple[float,float]]] = {}
    for p1, p2 in segs:
        k1, k2 = key_pt(p1), key_pt(p2)
        adj.setdefault(k1, set()).add(k2)
        adj.setdefault(k2, set()).add(k1)

    loops: Set[Tuple[Tuple[float,float], ...]] = set()

    # для каждого ребра — попробуем обойти цикл длиной 4
    for p1, p2 in segs:
        k1, k2 = key_pt(p1), key_pt(p2)
        # все соседи k2 (кроме k1)
        for k3 in adj.get(k2, []):
            if k3 == k1:
                continue
            # соседи k3, кроме k2
            for k4 in adj.get(k3, []):
                if k4 in (k2, k1):
                    continue
                # замыкается ли на k1?
                if k1 in adj.get(k4, []):
                    quad = [k1, k2, k3, k4]
                    # нормализуем порядок (чтобы не ловить дубликаты)
                    # сдвинем так, чтобы минимальная лексикографически точка была первой
                    min_i = min(range(4), key=lambda i: quad[i])
                    ordered = quad[min_i:] + quad[:min_i]
                    loops.add(tuple(ordered))

    # преобразуем в списки «реальных» точек (ключи уже округлены)
    res: List[List[Tuple[float, float]]] = []
    for loop in loops:
        pts = [(float(x), float(y)) for (x, y) in loop]
        pts = _order_loop(pts)
        res.append(pts)
    return res

def find_closed_polylines(layer: str | None = None,
                          min_vertices: int = 3,
                          min_area: float = 0.0,
                          **kwargs):
    """Найти замкнутые полилинии (Polyline/LWPolyline). Возвращает вершины и bbox."""
    ms = _ms()
    found = []
    for e in ms:
        name = _object_name(e)
        if "polyline" not in name.lower():
            continue
        if layer and getattr(e, "Layer", None) != layer:
            continue
        if not _polyline_is_closed(e):
            continue
        verts2 = _polyline_vertices_2d_ordered(e)
        if len(verts2) < min_vertices:
            continue
        area = _poly_area_xy(verts2)
        if area < min_area:
            continue
        bbox = _bbox_from_points_2d(verts2)
        found.append({
            "handle": getattr(e, "Handle", None),
            "layer": getattr(e, "Layer", None),
            "vertices": verts2,
            "area": area,
            "bbox": bbox,
        })
    return {"ok": True, "polylines": found}

def find_squares(layer: str | None = None,
                 include_lines: bool = True,
                 pos_tol: float = _POS_TOL,
                 ang_tol_deg: float = _ANG_TOL_DEG,
                 rel_len_tol: float = _REL_LEN_TOL,
                 min_side: float = _MIN_SIDE,
                 max_count: int = 2000,
                 allow_rectangles: bool = False,
                 **kwargs):
    """
    Универсальный поиск квадратов:
    - замкнутые полилинии (Polyline/LWPolyline) с 4 вершинами
    - 4 соединенные LINE, образующие цикл
    - (опционально) грубое распознавание по bbox других сущностей — выключено, чтобы не ловить ложные
    Возвращает список:
    {
      "source": "polyline"|"lines",
      "handles": [..],          # сущности, из которых квадрат собран
      "vertices": [(x,y),...],  # 4 вершины по контуру (порядок)
      "center": (cx,cy),
      "side": S,
      "bbox": ((minx,miny),(maxx,maxy))
    }
    """
    ms = _ms()
    squares: List[Dict[str, Any]] = []

    # 1) Полилинии
    polys = find_closed_polylines(layer=layer, min_vertices=4, min_area=min_side*min_side).get("polylines", [])
    for poly in polys:
        vs = poly["vertices"]
        if len(vs) == 4 and (
            _is_square_vertices(vs, ang_tol_deg=ang_tol_deg, rel_len_tol=rel_len_tol, min_side=min_side) or
            (allow_rectangles and _is_rectangle_vertices(vs, ang_tol_deg=ang_tol_deg, rel_len_tol=rel_len_tol, min_side=min_side))
        ):
            center = _centroid(vs)
            side = min(_dist(vs[0], vs[1]), _dist(vs[1], vs[2]))
            squares.append({
                "source": "polyline",
                "handles": [poly["handle"]],
                "vertices": vs,
                "center": center,
                "side": side,
                "bbox": poly["bbox"]
            })
            if len(squares) >= max_count:
                return {"ok": True, "squares": squares}

    # 2) Ломаные из LINE
    if include_lines:
        # соберём все линии (и по нужному слою, если задан)
        line_datas: List[Dict[str, Any]] = []
        for e in ms:
            if layer and getattr(e, "Layer", None) != layer:
                continue
            nm = _object_name(e).lower()
            if "line" in nm and "polyline" not in nm:
                line_datas.append({"entity": e, "handle": getattr(e, "Handle", None)})

        loops = _find_loops_from_lines(line_datas, pos_tol=pos_tol)
        for vs in loops:
            if len(vs) == 4 and (
                _is_square_vertices(vs, ang_tol_deg=ang_tol_deg, rel_len_tol=rel_len_tol, min_side=min_side) or
                (allow_rectangles and _is_rectangle_vertices(vs, ang_tol_deg=ang_tol_deg, rel_len_tol=rel_len_tol, min_side=min_side))
            ):
                center = _centroid(vs)
                side = min(_dist(vs[0], vs[1]), _dist(vs[1], vs[2]))
                bbox = _bbox_from_points_2d(vs)
                # handles для линий — не трекаем точно какие 4 дали этот луп (дорого),
                # но можно приблизительно собрать любые 4, которые соединяются в эти вершины (упрощённо пропустим)
                squares.append({
                    "source": "lines",
                    "handles": [],
                    "vertices": vs,
                    "center": center,
                    "side": side,
                    "bbox": bbox
                })
                if len(squares) >= max_count:
                    return {"ok": True, "squares": squares}

    return {"ok": True, "squares": squares}

def pick_largest_closed_polyline(layer: str | None = None, **kwargs):
    res = find_closed_polylines(layer=layer, min_vertices=3, min_area=_MIN_SIDE * _MIN_SIDE)
    polys = res.get("polylines", [])
    if not polys:
        return {"ok": False, "reason": "no_closed_polylines"}
    polys.sort(key=lambda p: p.get("area", 0.0), reverse=True)
    return {"ok": True, "polyline": polys[0]}

def measure_bbox_of_largest_closed(layer: str | None = None, **kwargs):
    pick = pick_largest_closed_polyline(layer=layer)
    if not pick.get("ok"):
        return {"ok": False, "reason": pick.get("reason")}
    bbox = pick["polyline"]["bbox"]
    (minx, miny), (maxx, maxy) = bbox
    return {"ok": True, "min": (minx, miny), "max": (maxx, maxy),
            "width": maxx - minx, "height": maxy - miny,
            "center": ((minx + maxx)/2.0, (miny + maxy)/2.0)}

# =====================================================
# ДЕЙСТВИЯ НАД ГЕОМЕТРИЕЙ ВЫСОКОГО УРОВНЯ
# =====================================================

def inscribe_circles_in_squares(layer_name: str = "CIRCLES_YELLOW",
                                color: Any = 2,
                                layer_filter: str | None = None,
                                pos_tol: float = _POS_TOL,
                                ang_tol_deg: float = _ANG_TOL_DEG,
                                rel_len_tol: float = _REL_LEN_TOL,
                                min_side: float = _MIN_SIDE,
                                max_count: int = 2000,
                                allow_rectangles: bool = False,
                                **kwargs):
    """
    Находит квадраты в модели (независимо от того, полилиния это или набор линий)
    и вписывает в каждый окружность в слой layer_name.
    """
    ensure_layer(layer_name, color=color)
    try:
        set_current_layer(layer_name)
    except Exception:
        pass

    found = find_squares(layer=layer_filter,
                         include_lines=True,
                         pos_tol=pos_tol,
                         ang_tol_deg=ang_tol_deg,
                         rel_len_tol=rel_len_tol,
                         min_side=min_side,
                         max_count=max_count,
                         allow_rectangles=allow_rectangles)
    if not found.get("ok"):
        return {"ok": False, "reason": "find_squares_failed"}

    inserted = 0
    for sq in found["squares"]:
        c = sq["center"]
        # радиус по короткой стороне
        try:
            r = min(
                _dist(sq["vertices"][0], sq["vertices"][1]),
                _dist(sq["vertices"][1], sq["vertices"][2])
            ) / 2.0
        except Exception:
            r = sq.get("side", 0.0) / 2.0
        try:
            draw_circle(c, r, layer=layer_name)
            inserted += 1
        except Exception:
            # не спотыкаемся об один неудачный круг
            pass

    return {"ok": True, "inserted": inserted, "layer": layer_name}

def inscribe_squares_in_circles(layer_name: str = "CIRCLES_YELLOW",
                                color: Any = 2,
                                layer_filter: str | None = None,
                                max_count: int = 5000,
                                **kwargs):
    """
    Находит окружности (опционально по слою layer_filter) и вписывает в каждую квадрат
    в слой layer_name. Квадрат ось-ориентированный, сторона = r * sqrt(2).
    """
    ensure_layer(layer_name, color=color)
    try:
        set_current_layer(layer_name)
    except Exception:
        pass

    ms = _ms()
    inserted = 0
    for e in ms:
        nm = _object_name(e).lower()
        if "circle" not in nm:
            continue
        if layer_filter and getattr(e, "Layer", None) != layer_filter:
            continue
        try:
            c = e.Center
            r = float(e.Radius)
            cx, cy = float(c[0]), float(c[1])
            half = r / math.sqrt(2.0)
            base = (cx - half, cy - half)
            size = half * 2.0
            draw_rectangle(base, size, size, layer=layer_name)
            inserted += 1
            if inserted >= max_count:
                break
        except Exception:
            continue

    return {"ok": True, "inserted": inserted, "layer": layer_name}

def draw_triangle_roof_over_largest_square(layer_source: str | None = None,
                                           layer_result: str | None = None,
                                           height_ratio: float = 0.5,
                                           overhang: float = 0.0,
                                           **kwargs):
    """
    Строит треугольную "крышу" над самым большим квадратом.
    1) Пытается найти крупнейшую замкнутую полилинию
    2) Если не найдено — использует find_squares(include_lines=True),
       поэтому сработает и для квадратов, собранных из LINE.
    height_ratio — высота крыши в долях высоты;
    overhang — свес по X с каждой стороны.
    """
    bbox = None
    pick = pick_largest_closed_polyline(layer=layer_source)
    if pick.get("ok"):
        bbox = pick["polyline"].get("bbox")
    if not bbox:
        # fallback: используем крупный квадрат из find_squares (включая линии)
        fs = find_squares(layer=layer_source, include_lines=True)
        if not fs.get("ok"):
            return {"ok": False, "reason": "find_squares_failed"}
        sqs = fs.get("squares", [])
        if not sqs:
            return {"ok": False, "reason": "no_squares"}
        # выбрать по площади bbox
        def bbox_area(b):
            (x1, y1), (x2, y2) = b
            return max(0.0, (x2 - x1) * (y2 - y1))
        best = max(sqs, key=lambda s: bbox_area(s.get("bbox") or _bbox_from_points_2d(s.get("vertices", [])) or ((0,0),(0,0))))
        bbox = best.get("bbox") or _bbox_from_points_2d(best.get("vertices", []))
        if not bbox:
            return {"ok": False, "reason": "no_bbox"}

    (minx, miny), (maxx, maxy) = bbox
    h = maxy - miny
    apex_h = h * float(height_ratio)

    x_left = minx - float(overhang)
    x_right = maxx + float(overhang)
    y_top = maxy
    x_mid = (minx + maxx) / 2.0
    apex = (x_mid, y_top + apex_h)

    pts = [(x_left, y_top), (x_right, y_top), apex, (x_left, y_top)]
    return draw_polyline(pts, layer=layer_result or layer_source, closed=True)

def find_circles(layer: str | None = None,
                 min_radius: float = 0.0,
                 max_count: int = 5000,
                 **kwargs):
    """Найти окружности с центром/радиусом и bbox."""
    ms = _ms()
    circles = []
    for e in ms:
        nm = _object_name(e).lower()
        if "circle" not in nm:
            continue
        if layer and getattr(e, "Layer", None) != layer:
            continue
        try:
            c = e.Center
            r = float(e.Radius)
            if r < float(min_radius):
                continue
            cx, cy = float(c[0]), float(c[1])
            bbox = ((cx - r, cy - r), (cx + r, cy + r))
            circles.append({
                "handle": getattr(e, "Handle", None),
                "layer": getattr(e, "Layer", None),
                "center": (cx, cy),
                "radius": r,
                "bbox": bbox,
            })
            if len(circles) >= max_count:
                break
        except Exception:
            continue
    return {"ok": True, "circles": circles}

def pick_largest_circle(layer: str | None = None, **kwargs):
    """Вернуть окружность с максимальным радиусом."""
    res = find_circles(layer=layer)
    cs = res.get("circles", [])
    if not cs:
        return {"ok": False, "reason": "no_circles"}
    cs.sort(key=lambda c: c.get("radius", 0.0), reverse=True)
    return {"ok": True, "circle": cs[0]}

def make_snowman_from_circle(layer_source: str | None = None,
                             layer_result: str | None = None,
                             color: Any = "white",
                             middle_scale: float = 0.7,
                             head_scale: float = 0.5,
                             gap_ratio: float = 0.1,
                             eye_scale: float = 0.12,
                             draw_arms: bool = True,
                             draw_legs: bool = True,
                             hand_scale: float = 0.12,
                             foot_scale: float = 0.12,
                             **kwargs):
    """
    Строит снеговика на основе существующей окружности:
    - выбирает самую большую окружность на layer_source (или среди всех)
    - рисует три круга по вертикали: база=R, середина=R*middle_scale, голова=R*head_scale
    - между кругами зазор gap_ratio*R
    - рисует два глазика на голове (кружки радиуса R_head*eye_scale)
    """
    ensure_layer(layer_result or layer_source or "SNOWMAN", color=color)
    try:
        set_current_layer(layer_result or layer_source or "SNOWMAN")
    except Exception:
        pass

    pick = pick_largest_circle(layer=layer_source)
    if not pick.get("ok"):
        return {"ok": False, "reason": pick.get("reason")}
    base = pick["circle"]
    cx, cy = base["center"]
    R = float(base["radius"])
    gap = float(gap_ratio) * R

    R_mid = float(middle_scale) * R
    R_head = float(head_scale) * R

    # центры по Y
    c_base = (cx, cy)
    c_mid = (cx, cy + R + gap + R_mid)
    c_head = (cx, c_mid[1] + R_mid + gap + R_head)

    draw_circle(c_base, R, layer=layer_result or layer_source)
    draw_circle(c_mid, R_mid, layer=layer_result or layer_source)
    draw_circle(c_head, R_head, layer=layer_result or layer_source)

    # глазки
    eye_r = max(R_head * float(eye_scale), _MIN_SIDE)
    eye_dx = R_head * 0.3
    eye_dy = R_head * 0.15
    draw_circle((c_head[0] - eye_dx, c_head[1] + eye_dy), eye_r, layer=layer_result or layer_source)
    draw_circle((c_head[0] + eye_dx, c_head[1] + eye_dy), eye_r, layer=layer_result or layer_source)

    # ручки (веточки): по диагонали от средней сферы, плюс круглые ладошки
    if draw_arms:
        arm_len = R_mid * 1.2
        up = R_mid * 0.3
        # left
        p1l = (c_mid[0] - R_mid * 0.9, c_mid[1] + up * 0.2)
        p2l = (p1l[0] - arm_len, p1l[1] + up)
        draw_line(p1l, p2l, layer=layer_result or layer_source)
        draw_circle(p2l, max(R_head * float(hand_scale), _MIN_SIDE), layer=layer_result or layer_source)
        # right
        p1r = (c_mid[0] + R_mid * 0.9, c_mid[1] + up * 0.2)
        p2r = (p1r[0] + arm_len, p1r[1] + up)
        draw_line(p1r, p2r, layer=layer_result or layer_source)
        draw_circle(p2r, max(R_head * float(hand_scale), _MIN_SIDE), layer=layer_result or layer_source)

    # ножки (лапки): диагональные линии от низа базы и круглые стопы
    if draw_legs:
        leg_len = R * 0.7
        base_y = c_base[1] - R
        # left
        l1 = (c_base[0] - R * 0.35, base_y + R * 0.2)
        l2 = (l1[0] - R * 0.5, l1[1] - leg_len)
        draw_line(l1, l2, layer=layer_result or layer_source)
        draw_circle(l2, max(R * float(foot_scale), _MIN_SIDE), layer=layer_result or layer_source)
        # right
        r1 = (c_base[0] + R * 0.35, base_y + R * 0.2)
        r2 = (r1[0] + R * 0.5, r1[1] - leg_len)
        draw_line(r1, r2, layer=layer_result or layer_source)
        draw_circle(r2, max(R * float(foot_scale), _MIN_SIDE), layer=layer_result or layer_source)

    return {"ok": True, "base_circle": base}

def copy_all_on_layer_by_offset(source_layer: str,
                                dx: float = 1000.0,
                                dy: float = 0.0,
                                target_layer: str | None = None,
                                limit: int | None = None,
                                **kwargs):
    """Дублирует все объекты слоя source_layer со смещением (dx,dy). Опционально меняет слой у копий."""
    ms = _ms()
    copied = 0
    for e in ms:
        try:
            if getattr(e, "Layer", None) != source_layer:
                continue
            if limit is not None and copied >= int(limit):
                break
            e2 = None
            try:
                e2 = e.Copy()
            except Exception:
                # в некоторых версиях COM Copy может отсутствовать
                pass
            if e2 is None:
                # попробуем через Add... нельзя генерализовать без типов; тогда просто скипнем
                continue
            try:
                e2.Move(APoint(0.0, 0.0, 0.0), APoint(float(dx), float(dy), 0.0))
            except Exception:
                # запасной вариант через перемещение оригинала и обратное смещение — не трогаем оригинал
                pass
            if target_layer:
                try:
                    e2.Layer = target_layer
                except Exception:
                    pass
            copied += 1
        except Exception:
            continue
    return {"ok": True, "copied": copied}

def draw_from_model_center(shape: str = "circle",
                           size: float = 1000.0,
                           layer: str | None = None,
                           **kwargs):
    """Рисуем фигуру от центра текущей модели (пример контекстного действия)."""
    c = get_center_of_model()
    if not c.get("ok"):
        return {"ok": False, "reason": "empty_model"}
    cx, cy = c["center"]
    if shape.lower() == "circle":
        return draw_circle((cx, cy), size/2.0, layer=layer)
    if shape.lower() == "square":
        half = size / 2.0
        return draw_rectangle((cx - half, cy - half), size, size, layer=layer)
    return {"ok": False, "reason": "unknown_shape"}

# =====================================================
# УДАЛЕНИЕ / ОЧИСТКА
# =====================================================

def erase_by_handles(handles: List[str], **kwargs):
    acad = _get_acad()
    count = 0
    for h in handles:
        if not h:
            continue
        try:
            e = acad.doc.HandleToObject(h)
            e.Delete()
            count += 1
        except Exception:
            pass
    return {"ok": True, "deleted": count}

def erase_all_on_layer(layer: str, **kwargs):
    ms = _ms()
    handles = []
    for e in ms:
        if getattr(e, "Layer", None) == layer:
            handles.append(getattr(e, "Handle", None))
    return erase_by_handles(handles)

def erase_by_filter(type_contains: str | None = None,
                    layer: str | None = None,
                    limit: Optional[int] = None,
                    **kwargs):
    ms = _ms()
    handles: List[str] = []
    for e in ms:
        if type_contains and type_contains.lower() not in _object_name(e).lower():
            continue
        if layer and getattr(e, "Layer", None) != layer:
            continue
        handles.append(getattr(e, "Handle", None))
        if limit and len(handles) >= limit:
            break
    return erase_by_handles(handles)
