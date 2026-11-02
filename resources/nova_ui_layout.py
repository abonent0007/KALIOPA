"""Геометрия фона главного экрана: изображение вписывается в окно.

Раньше `background.png` рисовался в натуральную величину от левого верхнего угла,
а кнопки считались от размеров окна. Пока фон был ровно 360x270, это совпадало;
после замены на 967x540 картинка обрезалась, а компоновка «от углов» съезжала.

`contain_rect` возвращает прямоугольник, в который картинка вписана целиком с
сохранением пропорций и центрированием. UI считает отступы от его углов, поэтому
любой размер и любое соотношение сторон фона дают одинаковую компоновку.
"""

__all__ = ["contain_rect", "corner_points"]


def _positive(value, fallback=1):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float(fallback)
    return number if number > 0 else float(fallback)


def contain_rect(src_w, src_h, dst_w, dst_h):
    """(x, y, width, height) вписанного прямоугольника, по центру dst."""
    dst_w = _positive(dst_w)
    dst_h = _positive(dst_h)
    try:
        src_w = float(src_w)
        src_h = float(src_h)
    except (TypeError, ValueError):
        return 0, 0, int(round(dst_w)), int(round(dst_h))
    if src_w <= 0 or src_h <= 0:
        return 0, 0, int(round(dst_w)), int(round(dst_h))
    scale = min(dst_w / src_w, dst_h / src_h)
    width = max(1, int(round(src_w * scale)))
    height = max(1, int(round(src_h * scale)))
    x = int(round((dst_w - width) / 2.0))
    y = int(round((dst_h - height) / 2.0))
    return x, y, width, height


def corner_points(rect, margin=10):
    """Опорные точки UI относительно прямоугольника фона."""
    x, y, width, height = (float(value) for value in rect)
    margin = max(0.0, float(margin))
    return {
        "left": x + margin,
        "right": x + width - margin,
        "top": y + margin,
        "bottom": y + height - margin,
        "center_x": x + width / 2.0,
        "center_y": y + height / 2.0,
    }
