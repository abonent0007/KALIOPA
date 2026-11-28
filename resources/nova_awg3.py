"""Конструктор AWG 1.5/2.0/3.0/3.1 для Cloudflare WARP.

Порт логики веб-генератора https://awgconfig.com (HereIamGosu/amnezia-config-gen,
лицензия AGPL-3.0): профили, WARP-safe ограничения, CSP-полезные нагрузки и цепочки
I2..I5. Сетевой регистратор и Cloudflare-API здесь не нужны — личность берётся
из уже зарегистрированной `warp_identity.json`.

Профили:
- legacy (1.5) и awg2 (2.0) собирает `nova_warp_generator.build_warp_conf`;
- awg3 (3.0) — клиентские тайминги, диапазоны, ContentPaddingAddition;
- awg31 (3.1) — то же + опциональный DisableCookies.

WARP-safe: S1..S4=0, H1..H4=1..4 зафиксированы, RandomTrailers и
HeaderProtectionKey недоступны (стандартный WireGuard-peer Cloudflare).
"""

from __future__ import annotations

__all__ = [
    "PROFILES",
    "TIMING_DEFAULTS",
    "TIMING_RANGES",
    "CONTENT_PADDING_DEFAULT",
    "KEEPALIVE_DEFAULT",
    "normalize_mode",
    "profile",
    "enforce_warp_safe",
    "random_timing",
    "build_interface",
    "build_config",
    "normalize_options",
    "generate_cps",
    "cps_payload",
    "sip_pair",
    "stun_payload",
    "dtls_payload",
    "dns_template",
    "generate_i2_i5",
    "WARP_ENDPOINT_PREFIXES_V4",
    "WARP_ENDPOINT_PREFIXES_V6",
]

import os
import random
import re
import struct
import zlib

# ── профили ────────────────────────────────────────────────────────────────────
PROFILES = {
    "legacy": {"id": "legacy", "version": "1.5", "timings": None},
    "awg2": {"id": "awg2", "version": "2.0", "timings": None},
    "awg3": {"id": "awg3", "version": "3.0", "timings": True},
    "awg31": {"id": "awg31", "version": "3.1", "timings": True, "disable_cookies": True},
}

TIMING_DEFAULTS = {
    "RekeyAfterTime": "100-120",
    "RekeyTimeout": "3-7",
    "RejectAfterTime": "150-180",
    "KeepaliveTimeout": "5-15",
    "MaxHandshakeAttempts": "15-20",
}
TIMING_RANGES = {key: tuple(int(part) for part in value.split("-"))
                 for key, value in TIMING_DEFAULTS.items()}
CONTENT_PADDING_DEFAULT = "10-100"
KEEPALIVE_DEFAULT = "25-35"

_MODE_ALIASES = {
    "legacy": "legacy", "1.5": "legacy", "awg2": "awg2", "2": "awg2", "v2": "awg2",
    "awg3": "awg3", "awg3.0": "awg3", "3": "awg3", "3.0": "awg3", "v3": "awg3",
    "awg31": "awg31", "awg3.1": "awg31", "3.1": "awg31", "v3.1": "awg31",
}


def normalize_mode(value) -> str:
    return _MODE_ALIASES.get(str(value or "").strip().lower(), "legacy")


def profile(mode) -> dict:
    return PROFILES[normalize_mode(mode)]


def enforce_warp_safe(data: dict) -> dict:
    """WARP-safe:  Stock WireGuard framing + опциональный DisableCookies (только 3.1)."""
    out = dict(data)
    out.update({"S1": 0, "S2": 0, "S3": 0, "S4": 0,
                "H1": "1", "H2": "2", "H3": "3", "H4": "4"})
    out.pop("HeaderProtectionKey", None)
    if str(out.get("RandomTrailers", "") or "").lower() == "on":
        raise ValueError("RandomTrailers недоступен для Cloudflare WARP")
    mode = out.get("mode", "awg31")
    cookies = out.get("DisableCookies")
    if cookies is not None and normalize_mode(mode) != "awg31":
        raise ValueError("DisableCookies доступен только в AWG 3.1")
    if cookies is not None:
        cookies = str(cookies).lower()
        if cookies not in ("on", "off"):
            raise ValueError("DisableCookies должен быть on или off")
        if cookies == "off":
            cookies = None
    out["DisableCookies"] = cookies
    return out


def random_timing(rng: random.Random, field: str) -> str:
    """Дипазон тайминга из профиля (строка) или случайное значение в диапазоне."""
    low, high = TIMING_RANGES[field]
    return str(rng.randint(low, high))


def _address_line(ipv4, ipv6, plain_address=False) -> str:
    if not ipv6:
        return f"Address = {ipv4}" if plain_address else f"Address = {ipv4}/32"
    if plain_address:
        return f"Address = {ipv4}, {ipv6}"
    return f"Address = {ipv4}/32, {ipv6}/128"


def build_interface(*, identity: dict, mode="awg3", client_ipv4="", client_ipv6="",
                    plain_address=False, dns_line="", junk=(4, 40, 70),
                    i1="", extra_cps=None, timings=None, disable_cookies=None) -> str:
    """[Interface] по правилам выбранного профиля (WARP-safe для 3.x)."""
    name = normalize_mode(mode)
    jc, jmin, jmax = junk
    lines = ["[Interface]", f"PrivateKey = {identity.get('private_key', '')}"]
    lines.append(_address_line(client_ipv4, client_ipv6, plain_address))
    lines.append(f"DNS = {dns_line or '1.1.1.1, 1.0.0.1'}")
    lines.append(f"Jc = {jc}")
    lines.append(f"Jmin = {jmin}")
    lines.append(f"Jmax = {jmax}")
    if name in ("awg3", "awg31"):
        safe = enforce_warp_safe({
            "mode": name,
            "S1": 0, "S2": 0, "S3": 0, "S4": 0,
            "H1": "1", "H2": "2", "H3": "3", "H4": "4",
            "DisableCookies": disable_cookies,
        })
        timings = dict(timings or TIMING_DEFAULTS)
        lines += [f"S{k} = {safe[f'S{k}']}" for k in (1, 2, 3, 4)]
        lines += [f"H{k} = {safe[f'H{k}']}" for k in (1, 2, 3, 4)]
        if i1:
            lines.append(f"I1 = {i1}")
            for field in ("I2", "I3", "I4", "I5"):
                value = (extra_cps or {}).get(field)
                if value:
                    lines.append(f"{field} = {value}")
        if timings.get("ContentPaddingAddition"):
            lines.append(f"ContentPaddingAddition = {timings['ContentPaddingAddition']}")
        for field in ("RekeyAfterTime", "RekeyTimeout", "RejectAfterTime",
                      "KeepaliveTimeout", "MaxHandshakeAttempts"):
            lines.append(f"{field} = {timings.get(field, TIMING_DEFAULTS[field])}")
        if safe.get("DisableCookies"):
            lines.append(f"DisableCookies = {safe['DisableCookies']}")
        lines.append("MTU = 1280")
        return "\n".join(lines)
    # legacy / awg2: сток-параметры S/H, I1 без таймингов
    lines += [f"S{k} = 0" for k in (1, 2, 3, 4)]
    lines += [f"H{k} = {k}" for k in (1, 2, 3, 4)]
    if i1:
        lines.append(f"I1 = {i1}")
        for field in ("I2", "I3", "I4", "I5"):
            value = (extra_cps or {}).get(field)
            if value:
                lines.append(f"{field} = {value}")
    lines.append("MTU = 1280")
    return "\n".join(lines)


def build_config(identity: dict, host: str, port: int, **interface_options) -> str:
    """Полный .conf: [Interface] + [Peer] Cloudflare WARP."""
    interface = build_interface(identity=identity, **interface_options)
    addresses = ", ".join(a for a in (identity.get("ipv4", ""), identity.get("ipv6", ""))
                          if a)
    lines = [
        interface,
        "",
        "[Peer]",
        f"PublicKey = {identity.get('peer_public_key', '')}",
        "AllowedIPs = 0.0.0.0/0, ::/0",
        f"Endpoint = {host}:{port}",
    ]
    return "\n".join(lines) + "\n"


# ── опции конструктора ─────────────────────────────────────────────────────────
DEFAULT_OPTIONS = {
    "mode": "awg3",
    "ipv6": True,
    "count": 1,
    "port": 2408,
    "endpoint_mode": "auto",      # auto | hostname | manual
    "endpoint_host": "",
    "dns": "1.1.1.1, 1.0.0.1",
    "cps_protocol": "auto",       # auto | static | sip | stun | dns | dtls | quic
    "extra_cps": True,
    "disable_cookies": False,
}

_PROTOCOLS = ("auto", "static", "sip", "stun", "dns", "dtls", "quic")
_DNS_RE = re.compile(r"^[A-Za-z0-9.:_-]{1,64}$")


def _clamp(value, default, low, high):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def normalize_options(raw) -> dict:
    """Опции окна конструктора безопасные для генерации; неизвестное — дефолт."""
    data = raw if isinstance(raw, dict) else {}
    opts = dict(DEFAULT_OPTIONS)
    raw_mode = str(data.get("mode") or "").strip().lower()
    opts["mode"] = normalize_mode(raw_mode) if raw_mode else DEFAULT_OPTIONS["mode"]
    opts["ipv6"] = bool(data.get("ipv6", True))
    opts["count"] = _clamp(data.get("count"), 1, 1, 20)
    opts["port"] = _clamp(data.get("port"), 2408, 1, 65535)
    endpoint_mode = str(data.get("endpoint_mode") or "auto").strip().lower()
    opts["endpoint_mode"] = endpoint_mode if endpoint_mode in ("auto", "hostname", "manual") else "auto"
    opts["endpoint_host"] = str(data.get("endpoint_host") or "").strip()[:255]
    parts = [part.strip() for part in str(data.get("dns") or "").replace(";", ",").split(",")]
    clean = [part for part in parts if part and _DNS_RE.match(part)]
    opts["dns"] = ", ".join(clean[:4]) or DEFAULT_OPTIONS["dns"]
    protocol = str(data.get("cps_protocol") or "auto").strip().lower()
    opts["cps_protocol"] = protocol if protocol in _PROTOCOLS else "auto"
    opts["extra_cps"] = bool(data.get("extra_cps", True))
    opts["disable_cookies"] = bool(data.get("disable_cookies")) and opts["mode"] == "awg31"
    return opts


def generate_cps(protocol: str, rng: random.Random, *, extra=None) -> tuple[str, dict]:
    """I1 выбранным протоколом + цепочки I2..I5 (если включены).

    Возвращает `(i1, extra_cps)`; пустой i1 означает «строку I1 не пишем».
    """
    name = str(protocol or "auto").strip().lower()
    if name not in _PROTOCOLS:
        name = "auto"
    extra = dict(extra or {})
    if name == "sip":
        i1, i2 = sip_pair(rng)
        extra.setdefault("I2", i2)
        return i1, extra
    if name == "stun":
        return stun_payload(rng), extra
    if name == "dtls":
        return dtls_payload(rng), extra
    if name == "dns":
        return dns_template(rng), extra
    if name == "quic":
        try:
            import nova_quic_initial
            sni = nova_quic_initial.pick_sni(rng.randrange(len(nova_quic_initial.WHITE_SNI)))
            value = nova_quic_initial.build_i1(sni)
        except Exception:
            value = ""
        return value, extra
    if name == "static":
        return cps_payload(rng), extra
    order = ["static", "sip", "stun"]
    rng.shuffle(order)
    for candidate in order:
        i1, extra = generate_cps(candidate, rng, extra=extra)
        if i1:
            return i1, extra
    return "", extra


def build_many(identity: dict, endpoints, options, rng=None) -> list[str]:
    """Несколько конфигов по списку `(host, port)`; опции нормализуются."""
    opts = normalize_options(options)
    rng = rng or random.Random()
    i1, extra = generate_cps(opts["cps_protocol"], rng)
    if opts["extra_cps"]:
        extra.update(generate_i2_i5(rng))
    timings = {key: random_timing(rng, key) for key in TIMING_DEFAULTS}
    timings["ContentPaddingAddition"] = str(rng.randint(10, 100))
    out = []
    for host, port in endpoints or ():
        out.append(build_config(
            identity, str(host), int(port),
            mode=opts["mode"],
            client_ipv4=identity.get("ipv4", ""),
            client_ipv6=identity.get("ipv6", "") if opts["ipv6"] else "",
            dns_line=opts["dns"], junk=(4, 40, 70),
            i1=i1, extra_cps=extra, timings=timings,
            disable_cookies="on" if opts["disable_cookies"] else None,
        ))
    return out


# ── CSP-полезные нагрузки и цепочки ─────────────────────────────────────────────
# Пул проверенных бинарных .payload Cloudflare WARP (AGPL-3.0, awgconfig).
WARP_CPS_PAYLOADS = [
    "<b 0xce000000010897a297ecc34cd6dd000044d0ec2e2e1ea2991f467ace4222129b5a098823784694b4897b9986ae0b7280135fa85e196d9ad980b150122129ce2a9379531b0fd3e871ca5fdb883c369832f730e272d7b8b74f393f9f0fa43f11e510ecb2219a52984410c204cf875585340c62238e14ad04dff382f2c200e0ee22fe743b9c6b8b043121c5710ec289f471c91ee414fca8b8be8419ae8ce7ffc53837f6ade262891895f3f4cecd31bc93ac5599e18e4f01b472362b8056c3172b513051f8322d1062997ef4a383b01706598d08d48c221d30e74c7ce000cdad36b706b1bf9b0607c32ec4b3203a4ee21ab64df336212b9758280803fcab14933b0e7ee1e04a7becce3e2633f4852585c567894a5f9efe9706a151b615856647e8b7dba69ab357b3982f554549bef9256111b2d67afde0b496f16962d4957ff654232aa9e845b61463908309cfd9de0a6abf5f425f577d7e5f6440652aa8da5f73588e82e9470f3b21b27b28c649506ae1a7f5f15b876f56abc4615f49911549b9bb39dd804fde182bd2dcec0c33bad9b138ca07d4a4a1650a2c2686acea05727e2a78962a840ae428f55627516e73c83dd8893b02358e81b524b4d99fda6df52b3a8d7a5291326e7ac9d773c5b43b8444554ef5aea104a738ed650aa979674bbed38da58ac29d87c29d387d80b526065baeb073ce65f075ccb56e47533aef357dceaa8293a523c5f6f790be90e4731123d3c6152a70576e90b4ab5bc5ead01576c68ab633ff7d36dcde2a0b2c68897e1acfc4d6483aaaeb635dd63c96b2b6a7a2bfe042f6aed82e5363aa850aace12ee3b1a93f30d8ab9537df483152a5527faca21efc9981b304f11fc95336f5b9637b174c5a0659e2b22e159a9fed4b8e93047371175b1d6d9cc8ab745f3b2281537d1c75fb9451871864efa5d184c38c185fd203de206751b92620f7c369e031d2041e152040920ac2c5ab5340bfc9d0561176abf10a147287ea90758575ac6a9f5ac9f390d0d5b23ee12af583383d994e22c0cf42383834bcd3ada1b3825a0664d8f3fb678261d57601ddf94a8a68a7c273a18c08aa99c7ad8c6c42eab67718843597ec9930457359dfdfbce024afc2dcf9348579a57d8d3490b2fa99f278f1c37d87dad9b221acd575192ffae1784f8e60ec7cee4068b6b988f0433d96d6a1b1865f4e155e9fe020279f434f3bf1bd117b717b92f6cd1cc9bea7d45978bcc3f24bda631a36910110a6ec06da35f8966c9279d130347594f13e9e07514fa370754d1424c0a1545c5070ef9fb2acd14233e8a50bfc5978b5bdf8bc1714731f798d21e2004117c61f2989dd44f0cf027b27d4019e81ed4b5c31db347c4a3a4d85048d7093cf16753d7b0d15e078f5c7a5205dc2f87e330a1f716738dce1c6180e9d02869b5546f1c4d2748f8c90d9693cba4e0079297d22fd61402dea32ff0eb69ebd65a5d0b687d87e3a8b2c42b648aa723c7c7daf37abcc4bb85caea2ee8f55bec20e913b3324ab8f5c3304f820d42ad1b9f2ffc1a3af9927136b4419e1e579ab4c2ae3c776d293d397d575df181e6cae0a4ada5d67ecea171cca3288d57c7bbdaee3befe745fb7d634f70386d873b90c4d6c6596bb65af68f9e5121e67ebf0d89d3c909ceedfb32ce9575a7758ff080724e1ab5d5f43074ecb53a479af21ed03d7b6899c36631c0166f9d47e5e1d4528a5d3d3f744029c4b1c190cbfbad06f5f83f7ad0429fa9a2719c56ffe3783460e166de2d8>",
    "<b 0xc7000000010809a1ed4edbbe7615000044d017a61a0d774f04290f119e701ef0035df2b0ed571b0b575e6a07246b856eb6ec036fef07f1e07b861251ad737abeb67e64be714c1dcd865312b1b6c35c089c997aeb5c18f808696fe97289513945d84ca846467603e94e44224877f2c1d3261e4ac18740be4bd064369c94fc08978d99b54bf615250998639010c1284248e1d73004b81fcb20b559d8a17eced7eab3964b5b88ca7a3b8579fc8c1c934189e77143b4ac434138114b1048651b56545b87acbef0952763538f3ddeb37cfc6d58b4881c3b719d7ff78f6ee1324a2914a32381c05a64c700466d280be007253bb030d179c4f1b3dc221e1974e2ee6d6e2b9e8d709159b5ef22e1783dbba845c20ca1c83b066c73835920ad70b806df0aee0351e3fc9ab1e42e8b2a30fe235ff0612eee19744949cecee0463b76514ad90c1f7ceaa557c18586ab561d49482e73c85d0143785da14a441bf82f78783b61cccd44aecb1947516e79b5ca5a6b3a8aed6040fae0eeabdc55a88dc19ade832d99fca90c7a629cacc07192d7e47e3c6a271b95b0ea3392562a06a1cab79f40ea92916ebee197b7b5f14b251824e1ed20ff2ca80b1f03a43e45157589bc61b978e97851025b3b7ccc17d291e1cb60fe48a5c26829dce11dd23c2e73265a9ebf8617c985e4fee4681e863f990061f4dea465a7d2524bd0edcf4b48d4b8f25fc359b15babd2637284a4774077dca60091f1a781cfee1bef9713dd5943a579d7470bc5970542fbb27fdf77880a8d8751b1f642c7a3f019a05ab94bf63d3525ef34e9290b5c8d477f2714e6d6e3e4d35c1983f5e16fda57fcdf071b513f8f088dbe8d5a97577d17a5383a496c3f313adfdd47c962bbaebd6aa13b46439eb742622c29ca067db0ec1853064c3cbbffe0a215a19fce47d49703ed58ebbd89721172d256d1cf30188106fb2f863186511401fad54d087aa2fb3d1b85768db386bd7102e8060ac157bac011acdcdae2799b9aee1467c3424013455bd028fcaacdc3c77d28ea199967d617ea7d0d0815f3cc407934a76d1293dccba210d1709a13e5dd67c9ba47cd113f5bdd740358eff13164159fd09bc2f7ec6cfa64d9df7e2e2f88706b0ff3a92ccf6f078456cfe0bdd89292cfe2680badc1eac9f7d36efe8eb6912c7b164508d13e6c0911c15f73c233cbe4fc70ff2ade1e1be4bbb738e0939159e2078a9438f05b756a003371f4861481c38f1cdd2d7b06deb62869e9fe79a8abaa920646fa2e8fa28f0d80c136376c7b56046bae4c05c0cdf64efb8c47bbfc5a1a4c0b045061ef0d71618e0d206a1d7f245fd5c03191b152673ba8dff8e1b8de7c50234a93cba91e3888adb228cc02beded4b1c0946797d3ef02dec2edb6ad0ac21f89f4be364c317da7c22440e9f358d512203f4b7ab20388af68b8915d0152db2c8a0687bfaea870f7529bb92a22b35bd79bc6d490591406346ecd78342ee3563c4883a8251679691c2d4e963397e24653520795511b018915374c954bddb940a9d7a16d1c8bd798fc7dbfb0599a7074e13f87e14efa8d511bb2579ec029b1bda18fe971b30fbe19e986ff2686a69bf3f1bb929de93ae70345ebca998b11e0a2b41890cba628d8f6e7c4e94790735e5299b4ff07cd3080f7d53c9cbe1911d2cd5925b3213e033c272506a87886cf761a283a779564d3241e3c28f632e166b5d756e1786ce077614c4444e3f2aed5decb3613b925ea3e558c21d4faf8ba54edd0f3a5d4>",
    "<b 0xc10000000114367096bb0fb3f58f3a3fb8aaacd61d63a1c8a40e14f7374b8a62dccba6431716c3abf6f5afbcfb39bd008000047c32e268567c652e6f4db58bff759bc8c5aaca183b87cb4d22938fe7d8dca22a679a79e4d9ee62e4bbb3a380dd78d4e8e48f26b38a1d42d76b371a5a9a0444827a69d1ab5872a85749f65a4104e931740b4dc1e2dd77733fc7fac4f93011cd622f2bb47e85f71992e2d585f8dc765a7a12ddeb879746a267393ad023d267c4bd79f258703e27345155268bd3cc0506ebd72e2e3c6b5b0f005299cd94b67ddabe30389c4f9b5c2d512dcc298c14f14e9b7f931e1dc397926c31fbb7cebfc668349c218672501031ecce151d4cb03c4c660b6c6fe7754e75446cd7de09a8c81030c5f6fb377203f551864f3d83e27de7b86499736cbbb549b2f37f436db1cae0a4ea39930f0534aacdd1e3534bc87877e2afabe959ced261f228d6362e6fd277c88c312d966c8b9f67e4a92e757773db0b0862fb8108d1d8fa262a40a1b4171961f0704c8ba314da2482ac8ed9bd28d4b50f7432d89fd800c25a50c5e2f5c0710544fef5273401116aa0572366d8e49ad758fcb29e6a92912e644dbe227c247cb3417eabfab2db16796b2fba420de3b1dc94e8361f1f324a331ddaf1e626553138860757fd0bf687566108b77b70fb9f8f8962eca599c4a70ed373666961a8cb506b96756d9e28b94122b20f16b54f118c0e603ce0b831efea614ad836df6cf9affbdd09596412547496967da758cec9080295d853b0861670b71d9abde0d562b1a6de82782a5b0c14d297f27283a895abc889a5f6703f0e6eb95f67b2da45f150d0d8ab805612d570c2d5cb6997ac3a7756226c2f5c8982ffbd480c5004b0660a3c9468945efde90864019a2b519458724b55d766e16b0da25c0557c01f3c11ddeb024b62e303640e17fdd57dedb3aeb4a2c1b7c93059f9c1d7118d77caac1cd0f6556e46cbc991c1bb16970273dea833d01e5090d061a0c6d25af2415cd2878af97f6d0e7f1f936247b394ecb9bd484da6be936dee9b0b92dc90101a1b4295e97a9772f2263eb09431995aa173df4ca2abd687d87706f0f93eaa5e13cbe3b574fa3cfe94502ace25265778da6960d561381769c24e0cbd7aac73c16f95ae74ff7ec38124f7c722b9cb151d4b6841343f29be8f35145e1b27021056820fed77003df8554b4155716c8cf6049ef5e318481460a8ce3be7c7bfac695255be84dc491c19e9dedc449dd3471728cd2a3ee51324ccb3eef121e3e08f8e18f0006ea8957371d9f2f739f0b89e4db11e5c6430ada61572e589519fbad4498b460ce6e4407fc2d8f2dd4293a50a0cb8fcaaf35cd9a8cc097e3603fbfa08d9036f52b3e7fcce11b83ad28a4ac12dba0395a0cc871cefd1a2856fffb3f28d82ce35cf80579974778bab13d9b3578d8c75a2d196087a2cd439aff2bb33f2db24ac175fff4ed91d36a4cdbfaf3f83074f03894ea40f17034629890da3efdbb41141b38368ab532209b69f057ddc559c19bc8ae62bf3fd564c9a35d9a83d14a95834a92bae6d9a29ae5e8ece07910d16433e4c6230c9bd7d68b47de0de9843988af6dc88b5301820443bd4d0537778bf6b4c1dd067fcf14b81015f2a67c7f2a28f9cb7e0684d3cb4b1c24d9b343122a086611b489532f1c3a26779da1706c6759d96d8ab>",
]


def cps_payload(rng: random.Random) -> str:
    return rng.choice(WARP_CPS_PAYLOADS)


def sip_pair(rng: random.Random) -> tuple[str, str]:
    """Живой SIP-диалог: I1 = INVITE, I2 = 100 Trying (warpCpsPayloads.js)."""
    branch = f"z9hG4bK{rng.randint(100000000, 999999999)}"
    call_id = f"{rng.randint(100000000, 999999999)}@pc33.atlanta.com"
    tag = f"{rng.randint(1000000000, 9999999999)}"
    cseq = rng.randint(10000, 99999)
    invite = "\r\n".join([
        "INVITE sip:bob@biloxi.com SIP/2.0",
        f"Via: SIP/2.0/UDP pc33.atlanta.com;branch={branch}",
        "Max-Forwards: 70",
        "To: Bob <sip:bob@biloxi.com>",
        f"From: Alice <sip:alice@atlanta.com>;tag={tag}",
        f"Call-ID: {call_id}",
        f"CSeq: {cseq} INVITE",
        "Contact: <sip:alice@pc33.atlanta.com>",
        "Content-Type: application/sdp",
        "Content-Length: 0",
        "", "",
    ])
    trying = "\r\n".join([
        "SIP/2.0 100 Trying",
        f"Via: SIP/2.0/UDP pc33.atlanta.com;branch={branch}",
        "To: Bob <sip:bob@biloxi.com>",
        f"From: Alice <sip:alice@atlanta.com>;tag={tag}",
        f"Call-ID: {call_id}",
        f"CSeq: {cseq} INVITE",
        "Content-Length: 0",
        "", "",
    ])
    to_hex = lambda text: text.encode("utf-8").hex()  # noqa: E731
    return f"<b 0x{to_hex(invite)}>", f"<b 0x{to_hex(trying)}>"


def _crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def _stun_attribute(kind: int, value: bytes) -> bytes:
    padding = b"\x00" * ((4 - len(value) % 4) % 4)
    return struct.pack(">HH", kind, len(value)) + value + padding


def stun_payload(rng: random.Random) -> str:
    software = rng.choice(["libwebrtc", "Cisco-libsrtp", "pjnath", "twilio-srtp",
                           "cloudflare-stun"])
    username = (f"{os.urandom(4).hex()}:{os.urandom(4).hex()}".encode())
    base = (_stun_attribute(0x8022, software.encode())
            + _stun_attribute(0x0006, username)
            + _stun_attribute(0x0024, struct.pack(">I", rng.randint(1000000, 2130706431)))
            + _stun_attribute(0x802A, os.urandom(8))
            + _stun_attribute(0x0025, b""))
    target_length = rng.randint(100, 220)
    padding_needed = max(0, target_length - 20 - len(base) - 8)
    padding = (_stun_attribute(0x0026, os.urandom(padding_needed - padding_needed % 4))
               if padding_needed > 0 else b"")
    attributes = base + padding
    message_length = len(attributes) + 8
    partial = (struct.pack(">HHI", 0x0001, message_length, 0x2112A442)
               + os.urandom(12) + attributes)
    fingerprint = _stun_attribute(0x8028,
                                  struct.pack(">I", (_crc32(partial) ^ 0x5354554E) & 0xFFFFFFFF))
    body = partial + fingerprint
    chunks = [body[i:i + 1000] for i in range(0, len(body), 1000)]
    return "".join(f"<b 0x{chunk.hex()}>" for chunk in chunks)


def dtls_payload(rng: random.Random) -> str:
    host = b"cloudflare.com"
    server_name = b"\x00" + struct.pack(">H", len(host)) + host

    def tls_ext(kind: int, value: bytes) -> bytes:
        return struct.pack(">HH", kind, len(value)) + value

    sn = struct.pack(">H", len(server_name)) + server_name
    ext = (tls_ext(0x0000, sn)
           + tls_ext(0x000A, struct.pack(">HHH", 4, 0x001D, 0x0017))
           + tls_ext(0x000B, b"\x01\x00")
           + tls_ext(0x000E, struct.pack(">HHB", 2, 0x0007, 0))
           + tls_ext(0x000D, struct.pack(">HHH", 0x0403, 0x0804, 0x0401))
           + tls_ext(0x0017, b""))
    ciphers = struct.pack(">HHHH", 0xC02B, 0xC02F, 0xC00A, 0xC014)
    body = (struct.pack(">H", 0xFEFD) + os.urandom(32) + b"\x00\x00"
            + struct.pack(">H", len(ciphers)) + ciphers + b"\x01\x00"
            + struct.pack(">H", len(ext)) + ext)
    length = struct.pack(">I", len(body))[1:]
    handshake = b"\x01" + length + b"\x00\x00\x00" + length + body
    packet = b"\x16" + struct.pack(">H", 0xFEFD) + b"\x00" * 8 + struct.pack(">H", len(handshake)) + handshake
    chunks = [packet[i:i + 1000] for i in range(0, len(packet), 1000)]
    return "".join(f"<b 0x{chunk.hex()}>" for chunk in chunks)


def dns_template(rng: random.Random) -> str:
    name = rng.choice(["cloudflare.com", "google.com", "icloud.com"])
    labels = b"".join(bytes([len(label)]) + label.encode("ascii")
                      for label in name.split(".")) + b"\x00"
    question = labels + struct.pack(">HH", 1, 1)
    answer = struct.pack(">HHHIH", 0xC00C, 1, 1, 300, 4) + b"\x01\x01\x01\x01"
    body = struct.pack(">HHHHH", 0x8180, 1, 1, 0, 0) + question + answer
    return f"<r 2><b 0x{body.hex()}>"


def generate_i2_i5(rng: random.Random) -> dict:
    """Цепочки I2..I5 из runtime-тегов (amneziawg-go v0.2.15+)."""
    def tag_b(size):
        return f"<b 0x{os.urandom(size).hex()}>"

    def tag_r(low, high):
        return f"<r {rng.randint(low, high)}>"

    return {
        "I2": f"{tag_b(rng.randint(4, 9))}<t>{tag_r(48, 120)}",
        "I3": f"{tag_r(8, 24)}{tag_b(rng.randint(2, 5))}{tag_r(40, 96)}",
        "I4": f"<t>{tag_r(24, 64)}{tag_b(rng.randint(3, 7))}{tag_r(16, 48)}",
        "I5": f"{tag_b(rng.randint(6, 13))}{tag_r(64, 140)}",
    }


# Сети, которые нельзя отдавать в AllowedIPs сплит-пресетов: через них живёт
# сам эндпоинт WARP (awgconfig, decision No. 18).
WARP_ENDPOINT_PREFIXES_V4 = ("162.159.192.0/24", "162.159.193.0/24",
                             "162.159.195.0/24", "162.159.204.0/24")
WARP_ENDPOINT_PREFIXES_V6 = ("2606:4700:d0::/48", "2606:4700:d1::/48")
