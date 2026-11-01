"""До трёх вариантов Proton-конфига из одного узла (порты + AWG-junk).

Источники (proton-generation / proton-convert) предлагают один и тот же узел в нескольких
вариантах: разные порты endpoint и разные наборы junk-параметров. Когда один порт режется,
второй часто проходит — это дешёвый способ поднять шанс соединения без нового аккаунта.

Модуль не трогает ключи и Endpoint-адрес: меняются только порт и Jc/Jmin/Jmax.
"""

import re

DEFAULT_PORTS = (443, 1194, 4500)
JUNK_SETS = (
    (3, 30, 120),
    (5, 60, 150),
    (8, 90, 200),
)

_ENDPOINT = re.compile(r"^Endpoint\s*=\s*([^\s:]+):(\d+)\s*$", re.M)
_JUNK = re.compile(r"^J(c|min|max)\s*=\s*\d+\s*$", re.M)


def variant_ports(count=3, ports=DEFAULT_PORTS):
    """Не больше count портов, без повторов, в заданном порядке."""
    out = []
    for port in ports:
        try:
            value = int(port)
        except (TypeError, ValueError):
            continue
        if value not in out:
            out.append(value)
        if len(out) >= int(count):
            break
    return out


def build_variants(conf_text, count=3, ports=DEFAULT_PORTS, junk_sets=JUNK_SETS):
    """Список текстов .conf: тот же узел, разные порты и junk-наборы.

    Возвращает [] для конфига без Endpoint или без [Interface] — такой файл не наш.
    """
    text = str(conf_text or "")
    match = _ENDPOINT.search(text)
    if not match or "[Interface]" not in text:
        return []
    host = match.group(1)
    variants = []
    for index, port in enumerate(variant_ports(count, ports)):
        body = _ENDPOINT.sub(f"Endpoint = {host}:{port}", text, count=1)
        if junk_sets:
            jc, jmin, jmax = junk_sets[index % len(junk_sets)]
            body = _JUNK.sub("", body)
            interface_end = body.find("[Peer]")
            block = f"Jc = {jc}\nJmin = {jmin}\nJmax = {jmax}\n"
            if interface_end > 0:
                body = body[:interface_end] + block + body[interface_end:]
            else:
                body = body.rstrip() + "\n" + block
        variants.append(body)
    return variants
