"""Схема цепочки KALIOPA из Route Lab как часть программы.

`nova_route_spec.json` — копия шаблона Route Lab
(`tools/route-editor/templates/kaliopa-clean.json`). Nova читает её при
генерации PAC и сверяет две вещи:

* целостность самой схемы (узлы, связи, порты слотов);
* структуру собранного PAC — порядок правил, наличие `FindProxyForURLEx`,
  режим `hybrid`/`full` и отсутствие холодных резервов 1375/1378/1379/1380.

Проверка ничего не меняет: расхождения только пишутся в журнал. Так правка
маршрутов, ломающая описанную цепочку, видна сразу, а не после того, как
что-то перестало открываться.
"""

from __future__ import annotations

import json
import os
import sys

SPEC_FILENAME = "nova_route_spec.json"
SPEC_SCHEMA = "kaliopa.route-lab/1"

# Порты, закреплённые за узлами схемы. Совпадают с контрактом PAC/слотов:
# 1369 PAC, 1370 WARP/MASQUE/VLESS-proxy, 1371 Opera HTTP, 1372 Telegram relay,
# 1374 TLS-терминатор, 1375/1378 Tor, 1379/1380 VLESS. Меняются только вместе
# с nova_vpn_slots.py и PAC.
REQUIRED_PORTS = {
    "pac": "1369",
    "warp": "1370",
    "opera": "1371",
    "relay": "1372",
    "dns": "53",
    "tor": "1375",
    "xray": "1379",
    "tls_term": "1374",
}
REQUIRED_NODES = ("pac", "warp", "opera", "relay", "dns", "direct", "tor", "xray")
RESERVE_PORTS = (1375, 1378, 1379, 1380)
ALLOWED_TYPES = {"device", "app", "pac", "proxy", "relay", "tls", "dns", "edge", "server"}
ALLOWED_STYLES = {"solid", "reserve", "dns"}

# Устойчивая часть политики, которую описывает схема. Меняется вместе с
# шаблоном Route Lab, а не «по вкусу»: эти значения определяют, попадёт ли
# EU/YouTube на Opera 1371 и останется ли PAC гибридным.
EXPECTED_SETTINGS = (
    ("browser", "auto", "routes.browser"),
    ("telegram", "warp", "routes.telegram"),
    ("ai_apps", "opera", "routes.ai_apps"),
)


def _roots():
    """Каталоги, где может лежать JSON: source, onedir, contents-directory."""
    roots = []
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        roots.append(meipass)
    here = os.path.dirname(os.path.abspath(__file__))
    roots.extend((here, os.path.dirname(here)))
    seen = set()
    for root in roots:
        if root and root not in seen:
            seen.add(root)
            yield root


def spec_path():
    """Путь к действующей схеме или пустая строка."""
    for root in _roots():
        for candidate in (
            os.path.join(root, SPEC_FILENAME),
            os.path.join(root, "resources", SPEC_FILENAME),
        ):
            if os.path.isfile(candidate):
                return candidate
    return ""


def load(path=None):
    """Прочитать схему; исключение — только если файла нет или он битый."""
    target = str(path or spec_path())
    if not target:
        raise FileNotFoundError("схема Route Lab не найдена: %s" % SPEC_FILENAME)
    with open(target, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("схема Route Lab: корень должен быть объектом")
    return data


def summary(spec):
    nodes = spec.get("nodes") if isinstance(spec, dict) else []
    edges = spec.get("edges") if isinstance(spec, dict) else []
    return {
        "name": str((spec or {}).get("name") or ""),
        "nodes": len(nodes) if isinstance(nodes, list) else 0,
        "edges": len(edges) if isinstance(edges, list) else 0,
    }


def validate(spec):
    """Проверить целостность схемы. Возвращает список русских замечаний."""
    issues = []
    if not isinstance(spec, dict):
        return ["схема не является объектом"]
    if spec.get("schema") != SPEC_SCHEMA:
        issues.append("schema должен быть %r" % SPEC_SCHEMA)
    if not str(spec.get("name") or "").strip():
        issues.append("у схемы нет имени")

    nodes = spec.get("nodes")
    edges = spec.get("edges")
    if not isinstance(nodes, list) or not nodes:
        issues.append("nodes пуст")
        nodes = []
    if not isinstance(edges, list) or not edges:
        issues.append("edges пуст")
        edges = []

    by_id = {}
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            issues.append("узел #%d не объект" % (index + 1))
            continue
        node_id = str(node.get("id") or "").strip()
        if not node_id:
            issues.append("узел #%d без id" % (index + 1))
            continue
        if node_id in by_id:
            issues.append("повторный id узла: %s" % node_id)
            continue
        by_id[node_id] = node
        node_type = str(node.get("type") or "").strip().lower()
        if node_type not in ALLOWED_TYPES:
            issues.append("узел %s: неизвестный type %r" % (node_id, node_type))
        port = str(node.get("port") or "").strip()
        if port and (not port.isdigit() or not 1 <= int(port) <= 65535):
            issues.append("узел %s: некорректный port %r" % (node_id, port))

    for node_id in REQUIRED_NODES:
        if node_id not in by_id:
            issues.append("нет обязательного узла %s" % node_id)
    for node_id, port in REQUIRED_PORTS.items():
        node = by_id.get(node_id)
        if isinstance(node, dict) and str(node.get("port") or "").strip() != port:
            issues.append("узел %s должен слушать %s" % (node_id, port))

    edge_ids = set()
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            issues.append("связь #%d не объект" % (index + 1))
            continue
        edge_id = str(edge.get("id") or "").strip()
        if not edge_id:
            issues.append("связь #%d без id" % (index + 1))
        elif edge_id in edge_ids:
            issues.append("повторный id связи: %s" % edge_id)
        else:
            edge_ids.add(edge_id)
        for side in ("from", "to"):
            target = str(edge.get(side) or "").strip()
            if not target:
                issues.append("связь %s: пустой %s" % (edge_id or index + 1, side))
            elif target not in by_id:
                issues.append("связь %s: %s ссылается на неизвестный узел %s" % (edge_id or index + 1, side, target))
        order = edge.get("order")
        if not isinstance(order, int) or order < 1:
            issues.append("связь %s: order должен быть целым >= 1" % (edge_id or index + 1))
        style = str(edge.get("style") or "").strip().lower()
        if style not in ALLOWED_STYLES:
            issues.append("связь %s: неизвестный style %r" % (edge_id or index + 1, style))
    return issues


def _js_var(text, name):
    marker = 'var %s = "' % name
    start = text.find(marker)
    if start < 0:
        return ""
    start += len(marker)
    end = text.find('"', start)
    return text[start:end] if end >= 0 else ""


def _secondary_mode(settings):
    if not isinstance(settings, dict):
        return ""
    secondary = settings.get("secondary")
    if not isinstance(secondary, dict):
        return ""
    return str(secondary.get("mode") or "").strip().lower()


def settings_issues(settings):
    """Сверить живые настройки с устойчивой частью схемы.

    Пустые настройки не считаются расхождением: файла может ещё не быть.
    """
    if not isinstance(settings, dict) or not settings:
        return []
    issues = []
    secondary = settings.get("secondary") if isinstance(settings.get("secondary"), dict) else {}
    mode = str(secondary.get("mode") or "").strip().lower()
    if mode != "opera":
        issues.append("secondary.mode должен быть opera, сейчас %r" % mode)
    region = str(settings.get("opera_region") or "").strip().upper()
    if region != "US":
        issues.append("opera_region должен быть US, сейчас %r" % region)
    routes = settings.get("routes") if isinstance(settings.get("routes"), dict) else {}
    for key, expected, label in EXPECTED_SETTINGS:
        actual = str(routes.get(key) or "").strip().lower()
        if actual == expected:
            continue
        if key == "browser":
            issues.append(
                "%s должен быть %s (PAC hybrid), сейчас %r: PAC уйдёт в full/off, "
                "и eu/youtube не попадут на 1371" % (label, expected, actual))
        else:
            issues.append("%s должен быть %s, сейчас %r" % (label, expected, actual))
    return issues


# Порядок правил в гибридном FindProxyForURL. Сравниваются позиции первых
# вхождений; `isLocalDirect(host))` — вызов, а не объявление функции.
_ORDER_RULES = (
    ("matchDomain(user_direct,", "user_direct"),
    ("matchDomain(user_ru,", "user_ru"),
    ("matchDomain(exclude,", "exclude"),
    ("isLocalDirect(host))", "локальные TLD"),
    ("matchDomain(ai_apps,", "ai_apps"),
    ("matchDomain(youtube,", "youtube"),
    ("matchDomain(ru,", "ru"),
)
_ORDER_PAIRS = (
    ("user_direct", "локальные TLD"),
    ("user_ru", "локальные TLD"),
    ("exclude", "локальные TLD"),
    ("локальные TLD", "ai_apps"),
    ("ai_apps", "youtube"),
    ("youtube", "ru"),
)
# В режиме full гибридный блок остаётся в файле мёртвым кодом, поэтому
# проверяется только живая ветка: DIRECT-исключения до ai_apps, ai_apps до
# возврата pac_full_route.
_FULL_ORDER_RULES = (
    ("matchDomain(user_direct,", "user_direct"),
    ("matchDomain(exclude,", "exclude"),
    ("isLocalDirect(host))", "локальные TLD"),
    ("matchDomain(ai_apps,", "ai_apps"),
)
_FULL_ORDER_PAIRS = (
    ("user_direct", "локальные TLD"),
    ("exclude", "локальные TLD"),
    ("локальные TLD", "ai_apps"),
)


def _positions(text, rules, issues):
    found = {}
    for marker, label in rules:
        index = text.find(marker)
        if index < 0:
            issues.append("PAC не содержит правило %s" % label)
        else:
            found[label] = index
    return found


def _order_issues(issues, positions, pairs):
    for earlier, later in pairs:
        if earlier in positions and later in positions and positions[earlier] > positions[later]:
            issues.append("правило «%s» стоит после «%s»" % (earlier, later))


def pac_issues(pac, settings=None):
    """Структурные расхождения PAC со схемой. Режимы слотов не учитываются."""
    text = str(pac or "")
    if not text:
        return ["PAC пуст"]
    issues = []
    if "function FindProxyForURL(" not in text:
        issues.append("PAC не содержит FindProxyForURL")
    if "function FindProxyForURLEx(" not in text:
        issues.append("PAC не содержит FindProxyForURLEx (WinINET останется без PROXY)")
    mode = _js_var(text, "pac_mode")
    if mode not in ("hybrid", "full", "off"):
        issues.append("неизвестный режим PAC: %r" % mode)

    if mode == "full":
        positions = _positions(text, _FULL_ORDER_RULES, issues)
        _order_issues(issues, positions, _FULL_ORDER_PAIRS)
        full_route = _js_var(text, "pac_full_route")
        if not full_route:
            issues.append("full-PAC: pac_full_route пуст")
        ret = text.find("return pac_full_route")
        if ret < 0:
            issues.append("full-PAC не возвращает pac_full_route")
        elif "ai_apps" in positions and positions["ai_apps"] > ret:
            issues.append("full-PAC: ai_apps разбирается после возврата pac_full_route")
    elif mode == "hybrid":
        positions = _positions(text, _ORDER_RULES, issues)
        _order_issues(issues, positions, _ORDER_PAIRS)

    # Google AI и opencode.ai идут на основной слот раньше строки ai_apps:
    # иначе явно выбранная Opera (1371) вернёт Gemini капчу, а opencode — 502,
    # когда 1371 не смог подняться через WARP.
    ai_primary_pos = text.find("matchDomain(ai_primary,")
    if ai_primary_pos >= 0:
        ai_apps_pos = text.find("matchDomain(ai_apps,")
        if ai_apps_pos >= 0 and ai_primary_pos > ai_apps_pos:
            issues.append("правило «ai_primary» стоит после «ai_apps»")

    if _secondary_mode(settings) not in ("tor", "profile"):
        for port in RESERVE_PORTS:
            if "127.0.0.1:%d" % port in text:
                issues.append("PAC содержит холодный резерв 127.0.0.1:%d" % port)
    return issues


def check(path=None, settings=None, pac=""):
    """Полная проверка: схема + настройки + PAC. Возвращает словарь отчёта."""
    report = {"spec": "", "summary": {"name": "", "nodes": 0, "edges": 0},
              "issues": [], "settings_issues": [], "pac_issues": []}
    try:
        spec = load(path)
    except (OSError, ValueError) as exc:
        report["issues"] = [str(exc)]
        return report
    report["spec"] = str(path or spec_path())
    report["summary"] = summary(spec)
    report["issues"] = validate(spec)
    report["settings_issues"] = settings_issues(settings)
    report["pac_issues"] = pac_issues(pac, settings)
    return report
