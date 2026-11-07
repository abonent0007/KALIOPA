"""Всплывающие подсказки для кнопок и кликабельных индикаторов Nova.

Одна подсказка на приложение: при наведении через 400 мс рядом с курсором
появляется тёмная плашка с объяснением. Работает и для обычных tk-кнопок
(`attach`/`attach_tree`), и для канвасных кнопок Nova (`attach_canvas_item`,
`attach_widget`).

Почему отдельный модуль: кнопки создаются в трёх местах (главное окно,
«Профили», «Маршрутизация») и в двух стилях (tk.Widget и Canvas). Один
Tooltip-объект держит единый вид, задержку и правило «одна подсказка за раз»,
а `describe()` даёт осмысленный текст даже там, где подпись не занесена в
словарь вручную.
"""

from __future__ import annotations

__all__ = [
    "BUTTON_HINTS",
    "Tooltip",
    "attach",
    "attach_tree",
    "attach_widget",
    "attach_canvas_item",
    "describe",
]

import tkinter as tk

BG = "#16211B"
FG = "#E5F7E8"
BORDER = "#3A5A44"
DELAY_MS = 420
WRAP_PX = 340

# Подписи кнопок → объяснение. Сюда попадает всё, что встречается в главном
# окне, «Профилях» и «Маршрутизации»; для остальных работает describe().
BUTTON_HINTS = {
    # главное окно
    "Подключить": "Подключиться: Nova поднимет выбранный VPN-слот.",
    "Отключить": "Отключить VPN и вернуть прямое подключение.",
    "Профили": "Профили: серверы, подписки, генератор WARP.",
    "⚙ Настройки": "Настройки маршрутизации: VPN-слоты, приложения, списки.",
    "Показать лог": "Показать журнал Nova поверх окна.",
    "Скрыть лог": "Свернуть журнал Nova.",
    # «Профили»: общие действия
    "Проверить": "Проверить выбранный профиль настоящим запросом через туннель.",
    "Проверить список": "Проверить все профили списка по очереди.",
    "Обновить профили": "Перевыпустить или обновить профили текущей вкладки.",
    "Папка": "Открыть папку с файлами профилей.",
    "Удалить": "Удалить выбранный профиль (файл остаётся в корзине, если она есть).",
    "Переименовать": "Переименовать выбранный профиль.",
    "Закрыть": "Закрыть окно.",
    # «Профили»: WARP / Proton / MASQUE
    "Сгенерировать": "Создать один WARP-профиль в Custom AWG: локальная регистрация, "
                     "скан точки входа, проверка туннеля перед записью.",
    "Настройки…": "Параметры генератора WARP: пресет, DNS, MTU, keepalive, SNI, джанк.",
    "Сгенерировать свои": "Перевыпустить набор WARP-профилей в AWG Cloudflare.",
    "Выпустить профили": "Выпустить профили Proton для этой учётной записи.",
    "Зарегистрировать": "Зарегистрировать новое устройство MASQUE в Cloudflare.",
    "Перевыпустить": "Выпустить профили заново, не трогая текущее подключение.",
    # «Профили»: подписки
    "Добавить…": "Добавить новую подписку по ссылке.",
    "Период…": "Настроить, как часто обновлять подписку.",
    "Вкл/выкл": "Включить или приостановить обновление подписки.",
    "Обновить сейчас": "Скачать подписку немедленно.",
    # «Профили»: импорт и Tor
    "Импорт файла…": "Импортировать профиль или подписку из файла.",
    "Вставить из буфера": "Импортировать профиль из текста в буфере обмена.",
    "Подключить Tor": "Поднять Tor и направить трафик через него.",
    "Новая цепочка": "Сменить цепочку Tor (новый выходной узел).",
    "Обновить мосты": "Получить свежие мосты для Tor.",
    # «Маршрутизация»
    "Сохранить": "Сохранить настройки и применить их без перезапуска.",
    "Отмена": "Закрыть без сохранения изменений.",
    "Сбросить": "Вернуть значения по умолчанию.",
    "Применить": "Применить настройки сейчас.",
    "Открыть": "Открыть выбранный элемент.",
    "Настройки": "Настройки маршрутизации: VPN-слоты, приложения, списки.",
}

_PREFIX_HINTS = (
    ("подключить", "Подключиться через выбранный профиль или слот."),
    ("отключить", "Отключить выбранный слот или туннель."),
    ("проверить", "Проверить профиль или список настоящим запросом."),
    ("обновить", "Обновить данные с внешнего источника."),
    ("перевыпустить", "Выпустить профили заново."),
    ("импорт", "Импортировать профиль."),
    ("удалить", "Удалить выбранное."),
    ("сохранить", "Сохранить изменения."),
    ("закрыть", "Закрыть окно."),
)


def describe(text: str) -> str:
    """Human hint for a button label; never empty."""
    label = " ".join(str(text or "").split())
    if not label:
        return ""
    if label in BUTTON_HINTS:
        return BUTTON_HINTS[label]
    low = label.lower().lstrip("⚙ ")
    for prefix, hint in _PREFIX_HINTS:
        if low.startswith(prefix):
            return hint
    return f"Кнопка «{label}»."


class Tooltip:
    """One reusable tooltip window."""

    def __init__(self):
        self._window = None
        self._label = None
        self._after_id = None
        self._text = ""
        self._root = None

    def _ensure_root(self, widget):
        root = self._root
        if root is not None:
            try:
                if root.winfo_exists():
                    return root
            except tk.TclError:
                pass
        try:
            self._root = widget.winfo_toplevel()
        except tk.TclError:
            self._root = None
        return self._root

    def _ensure(self):
        if self._window is not None:
            return self._window
        window = tk.Toplevel()
        window.withdraw()
        window.overrideredirect(True)
        try:
            window.attributes("-topmost", True)
        except tk.TclError:
            pass
        window.configure(bg=BORDER, padx=1, pady=1)
        self._label = tk.Label(
            window, text="", justify="left", wraplength=WRAP_PX, bg=BG, fg=FG,
            font=("Segoe UI", 9), padx=8, pady=5, anchor="w",
        )
        self._label.pack()
        self._window = window
        return window

    def schedule(self, text: str, x_root: int, y_root: int) -> None:
        if not text:
            return
        self._text = text
        self.cancel()
        root = self._root
        if root is None:
            return
        try:
            self._after_id = root.after(DELAY_MS, lambda: self._show(x_root, y_root))
        except Exception:
            self._after_id = None

    def _show(self, x_root: int, y_root: int) -> None:
        self._after_id = None
        if not self._text:
            return
        try:
            window = self._ensure()
            if self._label is None:
                return
            self._label.configure(text=self._text)
            window.update_idletasks()
            width = window.winfo_reqwidth()
            height = window.winfo_reqheight()
            screen_w = window.winfo_screenwidth()
            screen_h = window.winfo_screenheight()
            x = min(max(0, int(x_root) + 14), max(0, screen_w - width - 8))
            y = min(max(0, int(y_root) + 20), max(0, screen_h - height - 8))
            window.geometry(f"+{x}+{y}")
            window.deiconify()
            window.lift()
        except tk.TclError:
            self._window = None

    def hide(self) -> None:
        self.cancel()
        self._text = ""
        if self._window is not None:
            try:
                self._window.withdraw()
            except tk.TclError:
                self._window = None

    def cancel(self) -> None:
        if self._after_id is not None:
            try:
                if self._root is not None:
                    self._root.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None


_TOOLTIP = Tooltip()


def attach_widget(widget, text: str) -> bool:
    """Bind a tooltip to a whole widget (tk.Button, CanvasButton, RoundedButton)."""
    hint = describe(text)
    if not hint:
        return False
    try:
        if getattr(widget, "_nova_tooltip_hint", None) == hint:
            return True
        widget._nova_tooltip_hint = hint
    except Exception:
        pass
    _TOOLTIP._ensure_root(widget)

    def on_enter(event):
        _TOOLTIP.schedule(hint, event.x_root, event.y_root)
    def on_leave(_event):
        _TOOLTIP.hide()
    def on_press(_event):
        _TOOLTIP.hide()
    try:
        widget.bind("<Enter>", on_enter, add="+")
        widget.bind("<Leave>", on_leave, add="+")
        widget.bind("<ButtonPress-1>", on_press, add="+")
        return True
    except tk.TclError:
        return False


def attach(widget, text: str) -> bool:
    """Alias used by call sites that pass an explicit hint."""
    hint = str(text or "").strip()
    if not hint:
        return attach_widget(widget, "")
    try:
        if getattr(widget, "_nova_tooltip_hint", None) == hint:
            return True
        widget._nova_tooltip_hint = hint
    except Exception:
        pass
    _TOOLTIP._ensure_root(widget)

    def on_enter(event):
        _TOOLTIP.schedule(hint, event.x_root, event.y_root)
    def on_leave(_event):
        _TOOLTIP.hide()
    def on_press(_event):
        _TOOLTIP.hide()
    try:
        widget.bind("<Enter>", on_enter, add="+")
        widget.bind("<Leave>", on_leave, add="+")
        widget.bind("<ButtonPress-1>", on_press, add="+")
        return True
    except tk.TclError:
        return False


def attach_canvas_item(canvas, item_id, text: str, raw: bool = False) -> bool:
    """Bind a tooltip to one canvas item (region pills draw their own widgets)."""
    hint = str(text or "").strip() if raw else describe(text)
    if not hint:
        return False
    _TOOLTIP._ensure_root(canvas)
    try:
        canvas.tag_bind(item_id, "<Enter>",
                        lambda event: _TOOLTIP.schedule(hint, event.x_root, event.y_root),
                        add="+")
        canvas.tag_bind(item_id, "<Leave>", lambda _e: _TOOLTIP.hide(), add="+")
        return True
    except tk.TclError:
        return False


_SKIP_CLASSES = {
    "Label", "Button", "TButton", "Radiobutton", "Checkbutton", "Menubutton",
    "Scrollbar", "Listbox", "Menu", "Entry", "Text", "Canvas",
}


def attach_tree(root, hints=None, _depth: int = 0) -> int:
    """Attach hints to every standard button under `root`. Returns the count."""
    if root is None or _depth > 8:
        return 0
    count = 0
    try:
        children = root.winfo_children()
    except tk.TclError:
        return 0
    for child in children:
        try:
            klass = child.winfo_class()
        except tk.TclError:
            continue
        if klass in ("Button", "TButton", "Radiobutton", "Checkbutton", "Menubutton"):
            try:
                text = str(child.cget("text") or "")
            except tk.TclError:
                text = ""
            hint = (hints or {}).get(text) or describe(text)
            if hint and attach(child, hint):
                count += 1
        elif klass not in _SKIP_CLASSES:
            count += attach_tree(child, hints, _depth + 1)
    return count
