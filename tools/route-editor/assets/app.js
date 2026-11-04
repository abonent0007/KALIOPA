(() => {
  "use strict";

  const TYPES = {
    device: { label: "Устройство", icon: "PC", color: "device" },
    app: { label: "Приложение", icon: "AP", color: "app" },
    pac: { label: "PAC / прокси", icon: "PX", color: "pac" },
    proxy: { label: "Прокси / VPN", icon: "VPN", color: "proxy" },
    relay: { label: "Релей", icon: "RL", color: "relay" },
    tls: { label: "TLS-терминатор", icon: "TLS", color: "tls" },
    dns: { label: "DNS", icon: "DNS", color: "dns" },
    edge: { label: "Внешний узел", icon: "ED", color: "edge" },
    server: { label: "Сервер", icon: "SRV", color: "server" },
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  const state = {
    version: 1,
    name: "KALIOPA current route",
    notes: "",
    nodes: [],
    edges: [],
    selected: null,
    connectFrom: null,
    zoom: 1,
    activeTab: "json",
    nextId: 1,
  };

  const history = { past: [], future: [] };
  const stage = $("#stage");
  const nodesHost = $("#nodes");
  const edgeLayer = $("#edgeLayer");
  const stageScroll = $("#stageScroll");
  let toastTimer = null;
  let saveTimer = null;

  const esc = (value) => String(value ?? "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");

  function uid(prefix) {
    let id;
    do {
      id = `${prefix}-${state.nextId++}`;
    } while (state.nodes.some((n) => n.id === id) || state.edges.some((e) => e.id === id));
    return id;
  }

  function node(id) {
    return state.nodes.find((n) => n.id === id) || null;
  }

  function edge(id) {
    return state.edges.find((e) => e.id === id) || null;
  }

  function typeInfo(type) {
    return TYPES[type] || TYPES.edge;
  }

  function makeNode(id, type, label, sub, x, y, extra = {}) {
    return {
      id,
      type,
      label,
      sub,
      x: Number(x) || 0,
      y: Number(y) || 0,
      host: extra.host || "",
      port: extra.port || "",
      note: extra.note || "",
      tags: Array.isArray(extra.tags) ? extra.tags : [],
    };
  }

  function makeEdge(id, from, to, transport, order, condition = "", style = "solid", label = "") {
    return { id, from, to, transport, order: Number(order) || 1, condition, style, label };
  }

  // ---------------------------------------------------------------------------
  // Presets: реальные порты и развилки KALIOPA 1.44.2.x
  // ---------------------------------------------------------------------------
  const PRESETS = {
    current: () => ({
      name: "KALIOPA current route",
      notes: "Текущая схема: браузер через PAC, WARP/MASQUE и Opera EU; Telegram через релей 1372 и WARP; DNS отдельным служебным путём.",
      nodes: [
        makeNode("device", "device", "Это устройство", "Windows · локальный трафик", 60, 390, { tags: ["host"] }),
        makeNode("app", "app", "Браузер / Telegram", "Chrome · Telegram Desktop", 60, 140),
        makeNode("pac", "pac", "PAC / системный прокси", "127.0.0.1:1369 · nova.pac", 310, 260, { host: "127.0.0.1", port: "1369" }),
        makeNode("dns", "dns", "DNS-слой", "NRPT · DoH 127.0.0.1:53", 310, 650, { host: "127.0.0.1", port: "53", note: "NRPT для AI-доменов; DoH включается NOVA_DOH_GLOBAL=1" }),
        makeNode("warp", "proxy", "WARP / MASQUE", "SOCKS5 127.0.0.1:1370", 570, 90, { host: "127.0.0.1", port: "1370" }),
        makeNode("opera", "proxy", "Opera EU", "HTTP 127.0.0.1:1371", 570, 320, { host: "127.0.0.1", port: "1371" }),
        makeNode("tor", "proxy", "Tor", "SOCKS5 1375 · HTTP 1378", 570, 550, { host: "127.0.0.1", port: "1375" }),
        makeNode("relay", "relay", "Telegram relay", "SOCKS5/HTTP 127.0.0.1:1372", 570, 760, { host: "127.0.0.1", port: "1372" }),
        makeNode("cf", "edge", "Cloudflare edge", "MASQUE · 162.159.198.x", 850, 90, { note: "CF MASQUE / WARP egress" }),
        makeNode("operaEdge", "edge", "Opera VPN edge", "77.111.247.19:443 · SE", 850, 320, { host: "77.111.247.19", port: "443", note: "EU endpoint; ChatGPT идёт через этот выход" }),
        makeNode("torNet", "edge", "Tor network", "exit node · SOCKS/HTTP", 850, 550),
        makeNode("tgdc", "edge", "Telegram DC", "149.154.167.x:443", 850, 760, { note: "DC2/DC5, MTProto" }),
        makeNode("target", "server", "Конечный сервер", "example.com:443 · TLS", 1150, 205, { host: "example.com", port: "443" }),
        makeNode("tgTarget", "server", "Telegram", "DC / media", 1150, 760),
      ],
      edges: [
        makeEdge("e-device-app", "device", "app", "локальный процесс", 0),
        makeEdge("e-app-pac", "app", "pac", "системный прокси / PAC", 1),
        makeEdge("e-pac-warp", "pac", "warp", "SOCKS5 1370", 2, "RU / YouTube / fallback"),
        makeEdge("e-warp-cf", "warp", "cf", "MASQUE · UDP 443", 3),
        makeEdge("e-cf-target", "cf", "target", "TLS 443", 4),
        makeEdge("e-pac-opera", "pac", "opera", "HTTP 1371", 5, "EU / ai_apps"),
        makeEdge("e-opera-edge", "opera", "operaEdge", "HTTP CONNECT / TLS", 6),
        makeEdge("e-opera-target", "operaEdge", "target", "TLS 443", 7),
        makeEdge("e-pac-tor", "pac", "tor", "SOCKS5 1375", 8, "резерв", "reserve"),
        makeEdge("e-tor-net", "tor", "torNet", "SOCKS5", 9, "резерв", "reserve"),
        makeEdge("e-tor-target", "torNet", "target", "TLS 443", 10, "резерв", "reserve"),
        makeEdge("e-app-relay", "app", "relay", "SOCKS5 1372 · Telegram", 11),
        makeEdge("e-relay-warp", "relay", "warp", "WARP-socks", 12),
        makeEdge("e-warp-dc", "warp", "tgdc", "MTProto", 13),
        makeEdge("e-dc-tg", "tgdc", "tgTarget", "MTProto", 14),
        makeEdge("e-device-dns", "device", "dns", "DNS-запрос", 15, "", "dns"),
        makeEdge("e-dns-target", "dns", "target", "DNS-ответ", 16, "", "dns"),
      ],
    }),
    browser: () => ({
      name: "Browser via Opera EU",
      notes: "Браузер: PAC → Opera EU 1371 → SE edge → целевой сайт. ChatGPT и Gemini используют ai_apps=opera.",
      nodes: [
        makeNode("device", "device", "Это устройство", "Windows", 60, 320),
        makeNode("app", "app", "Браузер", "Chrome", 60, 120),
        makeNode("pac", "pac", "PAC", "127.0.0.1:1369", 310, 220, { host: "127.0.0.1", port: "1369" }),
        makeNode("opera", "proxy", "Opera EU", "HTTP 127.0.0.1:1371", 570, 220, { host: "127.0.0.1", port: "1371" }),
        makeNode("edge", "edge", "Opera VPN edge", "77.111.247.19:443 · SE", 830, 220, { host: "77.111.247.19", port: "443" }),
        makeNode("target", "server", "Конечный сервер", "example.com:443", 1110, 220, { host: "example.com", port: "443" }),
      ],
      edges: [
        makeEdge("e-device-app", "device", "app", "локальный процесс", 0),
        makeEdge("e-app-pac", "app", "pac", "PAC", 1),
        makeEdge("e-pac-opera", "pac", "opera", "HTTP 1371", 2, "EU / ai_apps"),
        makeEdge("e-opera-edge", "opera", "edge", "HTTP CONNECT / TLS", 3),
        makeEdge("e-edge-target", "edge", "target", "TLS 443", 4),
      ],
    }),
    telegram: () => ({
      name: "Telegram relay",
      notes: "Telegram Desktop: SOCKS5/HTTP 1372 → WARP-socks → Telegram DC. Opera/Tor-HTTP для MTProto исключены.",
      nodes: [
        makeNode("device", "device", "Это устройство", "Windows", 60, 300),
        makeNode("app", "app", "Telegram Desktop", "SOCKS5 127.0.0.1:1372", 60, 100, { host: "127.0.0.1", port: "1372" }),
        makeNode("relay", "relay", "Telegram relay", "127.0.0.1:1372", 330, 200, { host: "127.0.0.1", port: "1372" }),
        makeNode("tls", "tls", "TLS terminator", "127.0.0.1:1374 · опция", 330, 430, { host: "127.0.0.1", port: "1374", note: "WSS/маскировка; в текущем пути не обязателен" }),
        makeNode("warp", "proxy", "WARP / MASQUE", "SOCKS5 127.0.0.1:1370", 600, 200, { host: "127.0.0.1", port: "1370" }),
        makeNode("dc", "edge", "Telegram DC", "149.154.167.x:443", 860, 200),
        makeNode("tg", "server", "Telegram", "DC / media", 1120, 200),
      ],
      edges: [
        makeEdge("e-device-app", "device", "app", "локальный процесс", 0),
        makeEdge("e-app-relay", "app", "relay", "SOCKS5 1372", 1),
        makeEdge("e-relay-warp", "relay", "warp", "WARP-socks", 2),
        makeEdge("e-warp-dc", "warp", "dc", "MTProto", 3),
        makeEdge("e-dc-tg", "dc", "tg", "MTProto", 4),
        makeEdge("e-relay-tls", "relay", "tls", "TLS 1374", 5, "опция", "reserve"),
      ],
    }),
    vless: () => ({
      name: "VLESS profile",
      notes: "Свой VLESS-профиль: nova-xray слушает 1379/1380, если выбран вторичным слотом; при выборе основным — 1370.",
      nodes: [
        makeNode("device", "device", "Это устройство", "Windows", 60, 330),
        makeNode("app", "app", "Приложение", "Chrome / Telegram", 60, 120),
        makeNode("xray", "proxy", "VLESS / nova-xray", "SOCKS5 1379 · HTTP 1380", 330, 220, { host: "127.0.0.1", port: "1379" }),
        makeNode("edge", "edge", "VLESS edge", "REALITY / TLS · host:443", 620, 220),
        makeNode("target", "server", "Конечный сервер", "example.com:443", 900, 220, { host: "example.com", port: "443" }),
      ],
      edges: [
        makeEdge("e-device-app", "device", "app", "локальный процесс", 0),
        makeEdge("e-app-xray", "app", "xray", "SOCKS5 1379 / HTTP 1380", 1),
        makeEdge("e-xray-edge", "xray", "edge", "VLESS · REALITY", 2),
        makeEdge("e-edge-target", "edge", "target", "TLS 443", 3),
      ],
    }),
    blank: () => ({
      name: "KALIOPA custom route",
      notes: "Опиши в комментарии, что должно измениться в программе.",
      nodes: [
        makeNode("device", "device", "Это устройство", "Windows", 90, 300),
        makeNode("target", "server", "Конечный сервер", "host:port", 620, 300),
      ],
      edges: [],
    }),
  };

  function loadPreset(key, record = true) {
    const preset = (PRESETS[key] || PRESETS.current)();
    if (record) pushHistory();
    state.name = preset.name;
    state.notes = preset.notes;
    state.nodes = preset.nodes;
    state.edges = preset.edges;
    state.selected = null;
    state.connectFrom = null;
    state.nextId = 1 + Math.max(
      0,
      ...state.nodes.map((n) => Number(String(n.id).split("-").pop()) || 0),
      ...state.edges.map((e) => Number(String(e.id).split("-").pop()) || 0),
    );
    syncMetaInputs();
    renderAll();
    markDirty();
  }

  // ---------------------------------------------------------------------------
  // History
  // ---------------------------------------------------------------------------
  function snapshot() {
    return JSON.stringify({
      name: state.name,
      notes: state.notes,
      nodes: state.nodes,
      edges: state.edges,
    });
  }

  function pushHistory() {
    const snap = snapshot();
    if (history.past[history.past.length - 1] === snap) return;
    history.past.push(snap);
    if (history.past.length > 60) history.past.shift();
    history.future.length = 0;
  }

  function restore(snap) {
    const data = JSON.parse(snap);
    state.name = data.name || "";
    state.notes = data.notes || "";
    state.nodes = data.nodes || [];
    state.edges = data.edges || [];
    state.selected = null;
    state.connectFrom = null;
    syncMetaInputs();
    renderAll();
    markDirty();
  }

  function undo() {
    if (!history.past.length) return;
    history.future.push(snapshot());
    restore(history.past.pop());
  }

  function redo() {
    if (!history.future.length) return;
    history.past.push(snapshot());
    restore(history.future.pop());
  }

  // ---------------------------------------------------------------------------
  // Geometry + rendering
  // ---------------------------------------------------------------------------
  function stagePoint(clientX, clientY) {
    const rect = stage.getBoundingClientRect();
    return {
      x: (clientX - rect.left) / state.zoom,
      y: (clientY - rect.top) / state.zoom,
    };
  }

  function nodeBox(id) {
    const el = nodesHost.querySelector(`.node[data-id="${CSS.escape(id)}"]`);
    const n = node(id);
    if (!n) return null;
    const h = el ? el.offsetHeight : 88;
    return { x: n.x, y: n.y, w: el ? el.offsetWidth : 204, h };
  }

  function edgePath(a, b) {
    if (!a || !b) return "";
    const x1 = a.x + a.w;
    const y1 = a.y + a.h / 2;
    const x2 = b.x;
    const y2 = b.y + b.h / 2;
    const dx = Math.max(36, Math.abs(x2 - x1) * 0.46);
    return `M ${x1.toFixed(1)} ${y1.toFixed(1)} C ${(x1 + dx).toFixed(1)} ${y1.toFixed(1)}, ${(x2 - dx).toFixed(1)} ${y2.toFixed(1)}, ${x2.toFixed(1)} ${y2.toFixed(1)}`;
  }

  function edgeClass(e) {
    let cls = "edge-line";
    if (e.style === "reserve") cls += " reserve";
    if (e.style === "dns") cls += " dns";
    if (state.selected && state.selected.kind === "edge" && state.selected.id === e.id) cls += " selected animated";
    return cls;
  }

  function renderNodes() {
    nodesHost.innerHTML = "";
    for (const n of state.nodes) {
      const info = typeInfo(n.type);
      const el = document.createElement("div");
      el.className = `node ${info.color}`;
      el.dataset.id = n.id;
      if (state.selected && state.selected.kind === "node" && state.selected.id === n.id) el.classList.add("selected");
      el.style.left = `${n.x}px`;
      el.style.top = `${n.y}px`;
      el.innerHTML = `
        <div class="node-head">
          <div class="node-icon">${esc(info.icon)}</div>
          <div>
            <div class="node-type">${esc(info.label)}</div>
            <div class="node-label">${esc(n.label)}</div>
          </div>
        </div>
        <div class="node-body">
          <div class="node-sub">${esc(n.sub || "—")}</div>
          <div class="node-tags">${(n.tags || []).map((tag) => `<span class="node-tag">${esc(tag)}</span>`).join("")}</div>
        </div>
        <div class="node-foot">
          <span class="port-label">in</span>
          <span class="port in" data-port="in" title="Вход"></span>
          <span class="port out" data-port="out" title="Выход"></span>
          <span class="port-label">out</span>
        </div>`;
      nodesHost.appendChild(el);
      wireNode(el, n);
    }
  }

  function renderEdges() {
    edgeLayer.innerHTML = "";
    for (const e of state.edges) {
      const a = nodeBox(e.from);
      const b = nodeBox(e.to);
      if (!a || !b) continue;
      const d = edgePath(a, b);
      const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
      group.dataset.id = e.id;
      group.setAttribute("class", "edge-group");

      const hit = document.createElementNS("http://www.w3.org/2000/svg", "path");
      hit.setAttribute("d", d);
      hit.setAttribute("class", "edge-hit");
      hit.addEventListener("click", (event) => {
        event.stopPropagation();
        selectEdge(e.id);
      });

      const line = document.createElementNS("http://www.w3.org/2000/svg", "path");
      line.setAttribute("d", d);
      line.setAttribute("class", edgeClass(e));
      line.setAttribute("marker-end", "url(#arrow)");
      group.appendChild(line);
      group.appendChild(hit);

      try {
        const len = line.getTotalLength();
        const mid = line.getPointAtLength(len * 0.5);
        const badge = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        badge.setAttribute("x", String(mid.x - 10));
        badge.setAttribute("y", String(mid.y - 10));
        badge.setAttribute("width", "20");
        badge.setAttribute("height", "18");
        badge.setAttribute("rx", "5");
        badge.setAttribute("class", "edge-badge");
        badge.addEventListener("click", (event) => {
          event.stopPropagation();
          selectEdge(e.id);
        });
        group.appendChild(badge);
        const order = document.createElementNS("http://www.w3.org/2000/svg", "text");
        order.setAttribute("x", String(mid.x));
        order.setAttribute("y", String(mid.y + 2));
        order.setAttribute("class", "edge-order");
        order.textContent = String(e.order);
        group.appendChild(order);
        const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
        const lp = line.getPointAtLength(len * 0.62);
        label.setAttribute("x", String(lp.x));
        label.setAttribute("y", String(lp.y - 7));
        label.setAttribute("class", `edge-label${state.selected && state.selected.kind === "edge" && state.selected.id === e.id ? " selected" : ""}`);
        label.textContent = e.condition || e.transport || "";
        group.appendChild(label);
      } catch (_) {
        // SVG path еще не измерим при первом рендере — бейдж появится после layout.
      }
      edgeLayer.appendChild(group);
    }
  }

  function renderAll() {
    renderNodes();
    requestAnimationFrame(renderEdges);
    renderInspector();
    renderCode();
    renderStatus();
  }

  function renderStatus() {
    $("#statusNodes").textContent = `${state.nodes.length} узлов`;
    $("#statusEdges").textContent = `${state.edges.length} связей`;
    $("#statusSelection").textContent = state.selected
      ? state.selected.kind === "node"
        ? `узел: ${node(state.selected.id)?.label || "?"}`
        : `связь: ${edge(state.selected.id)?.transport || "?"}`
      : "—";
    $("#zoomValue").textContent = `${Math.round(state.zoom * 100)}%`;
    $("#selectionBadge").textContent = state.selected
      ? state.selected.kind === "node" ? (node(state.selected.id)?.label || "узел") : "связь"
      : "ничего не выбрано";
    const summary = buildChains();
    $("#routeSummary").innerHTML = `<b>${summary.length}</b> маршрут(ов) · ${state.nodes.length} узлов · ${state.edges.length} связей`;
  }

  function wireNode(el, n) {
    const head = el.querySelector(".node-head");
    head.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      if (event.target.closest(".port")) return;
      event.preventDefault();
      selectNode(n.id, false);
      pushHistory();
      const start = stagePoint(event.clientX, event.clientY);
      const ox = n.x;
      const oy = n.y;
      let moved = false;
      el.classList.add("dragging");
      const move = (ev) => {
        const p = stagePoint(ev.clientX, ev.clientY);
        const dx = p.x - start.x;
        const dy = p.y - start.y;
        if (Math.abs(dx) + Math.abs(dy) > 2) moved = true;
        n.x = Math.round(ox + dx);
        n.y = Math.round(oy + dy);
        el.style.left = `${n.x}px`;
        el.style.top = `${n.y}px`;
        renderEdges();
        renderStatus();
      };
      const up = () => {
        el.classList.remove("dragging");
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
        if (moved) {
          markDirty();
        }
      };
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
    });

    el.addEventListener("click", (event) => {
      if (event.target.closest(".port")) return;
      selectNode(n.id);
    });

    el.querySelector(".port.out").addEventListener("click", (event) => {
      event.stopPropagation();
      startConnect(n.id);
    });
    el.querySelector(".port.in").addEventListener("click", (event) => {
      event.stopPropagation();
      finishConnect(n.id);
    });
  }

  function selectNode(id, rerender = true) {
    state.selected = { kind: "node", id };
    state.connectFrom = null;
    if (rerender) renderAll();
    else {
      $$(".node").forEach((el) => el.classList.toggle("selected", el.dataset.id === id));
      renderInspector();
      renderStatus();
    }
  }

  function selectEdge(id) {
    state.selected = { kind: "edge", id };
    state.connectFrom = null;
    renderAll();
  }

  function startConnect(id) {
    state.connectFrom = id;
    state.selected = { kind: "node", id };
    renderNodes();
    requestAnimationFrame(() => {
      renderEdges();
      const el = nodesHost.querySelector(`.node[data-id="${CSS.escape(id)}"] .port.out`);
      if (el) el.classList.add("armed");
      $("#connectHint").classList.add("active");
      $("#connectHint").innerHTML = "Выбери <b>in</b> у принимающего узла · Esc — отмена";
    });
    renderInspector();
  }

  function finishConnect(toId) {
    if (!state.connectFrom) return;
    if (state.connectFrom === toId) {
      state.connectFrom = null;
      renderAll();
      return;
    }
    if (state.edges.some((e) => e.from === state.connectFrom && e.to === toId)) {
      toast("Такая связь уже есть", true);
      state.connectFrom = null;
      renderAll();
      return;
    }
    pushHistory();
    const maxOrder = state.edges.reduce((max, e) => Math.max(max, Number(e.order) || 0), 0);
    const edgeId = uid("edge");
    state.edges.push(makeEdge(edgeId, state.connectFrom, toId, "TCP", maxOrder + 1));
    state.selected = { kind: "edge", id: edgeId };
    state.connectFrom = null;
    $("#connectHint").classList.remove("active");
    $("#connectHint").innerHTML = "Клик по <b>out</b>, затем по <b>in</b> — создать связь";
    renderAll();
    markDirty();
    toast("Связь добавлена");
  }

  // ---------------------------------------------------------------------------
  // Inspector
  // ---------------------------------------------------------------------------
  function renderInspector() {
    const host = $("#inspector");
    if (!state.selected) {
      host.innerHTML = `<div class="empty-inspector"><b>Выбери узел или связь.</b><br>Тяни узел за заголовок. Соединяй порты out → in. Снизу — JSON и маршрут.</div>`;
      return;
    }
    if (state.selected.kind === "node") {
      const n = node(state.selected.id);
      if (!n) { state.selected = null; renderInspector(); return; }
      const options = Object.entries(TYPES).map(([key, info]) =>
        `<option value="${key}"${n.type === key ? " selected" : ""}>${esc(info.label)}</option>`).join("");
      host.innerHTML = `
        <label class="field"><span>Название</span><input data-field="label" value="${esc(n.label)}"></label>
        <label class="field"><span>Тип</span><select data-field="type">${options}</select></label>
        <label class="field"><span>Подпись / адрес</span><input data-field="sub" value="${esc(n.sub)}"></label>
        <div class="field-row">
          <label class="field"><span>Host</span><input data-field="host" value="${esc(n.host)}"></label>
          <label class="field"><span>Port</span><input data-field="port" value="${esc(n.port)}"></label>
        </div>
        <label class="field"><span>Заметка</span><textarea data-field="note" rows="3">${esc(n.note)}</textarea></label>
        <div class="inspector-actions">
          <button class="btn tiny" id="duplicateNode" type="button">Дублировать</button>
          <button class="btn tiny danger" id="deleteNode" type="button">Удалить</button>
        </div>`;
      $$("[data-field]", host).forEach((input) => {
        input.addEventListener("input", () => {
          const field = input.dataset.field;
          if (field === "type") n.type = input.value;
          else n[field] = input.value;
          markDirty();
          renderNodes();
          requestAnimationFrame(renderEdges);
          renderCode();
          renderStatus();
        });
      });
      $("#duplicateNode", host).addEventListener("click", () => {
        pushHistory();
        const copy = { ...n, id: uid("node"), x: n.x + 36, y: n.y + 36, label: `${n.label} · копия` };
        state.nodes.push(copy);
        selectNode(copy.id);
        markDirty();
      });
      $("#deleteNode", host).addEventListener("click", () => deleteSelected());
      return;
    }

    const e = edge(state.selected.id);
    if (!e) { state.selected = null; renderInspector(); return; }
    const from = node(e.from);
    const to = node(e.to);
    host.innerHTML = `
      <div class="edge-route"><b>${esc(from?.label || e.from)}</b><br><span>→</span> ${esc(to?.label || e.to)}</div>
      <label class="field"><span>Транспорт</span><input data-field="transport" value="${esc(e.transport)}" placeholder="SOCKS5 / HTTP / MASQUE"></label>
      <label class="field"><span>Порт / условие</span><input data-field="condition" value="${esc(e.condition)}" placeholder="RU / EU / ai_apps"></label>
      <label class="field"><span>Подпись на линии</span><input data-field="label" value="${esc(e.label)}"></label>
      <div class="field-row">
        <label class="field"><span>Порядок</span><input data-field="order" type="number" value="${esc(e.order)}"></label>
        <label class="field"><span>Стиль</span><select data-field="style">
          <option value="solid"${e.style === "solid" ? " selected" : ""}>основной</option>
          <option value="reserve"${e.style === "reserve" ? " selected" : ""}>резерв</option>
          <option value="dns"${e.style === "dns" ? " selected" : ""}>DNS</option>
        </select></label>
      </div>
      <div class="inspector-actions"><button class="btn tiny danger" id="deleteEdge" type="button">Удалить связь</button></div>`;
    $$("[data-field]", host).forEach((input) => {
      input.addEventListener("input", () => {
        const field = input.dataset.field;
        e[field] = field === "order" ? Math.max(0, Number(input.value) || 0) : input.value;
        markDirty();
        requestAnimationFrame(renderEdges);
        renderCode();
        renderStatus();
      });
    });
    $("#deleteEdge", host).addEventListener("click", () => deleteSelected());
  }

  function deleteSelected() {
    if (!state.selected) return;
    pushHistory();
    if (state.selected.kind === "node") {
      const id = state.selected.id;
      state.nodes = state.nodes.filter((n) => n.id !== id);
      state.edges = state.edges.filter((e) => e.from !== id && e.to !== id);
    } else {
      state.edges = state.edges.filter((e) => e.id !== state.selected.id);
    }
    state.selected = null;
    renderAll();
    markDirty();
  }

  // ---------------------------------------------------------------------------
  // Code output
  // ---------------------------------------------------------------------------
  function exportState() {
    return {
      schema: "kaliopa.route-lab/1",
      version: 1,
      name: state.name.trim() || "route",
      notes: state.notes.trim(),
      nodes: state.nodes.map((n) => ({
        id: n.id, type: n.type, label: n.label, sub: n.sub || "",
        x: Math.round(n.x), y: Math.round(n.y),
        host: n.host || "", port: n.port || "", note: n.note || "",
        tags: n.tags || [],
      })),
      edges: state.edges.map((e) => ({
        id: e.id, from: e.from, to: e.to,
        transport: e.transport || "", condition: e.condition || "",
        label: e.label || "", order: Number(e.order) || 0,
        style: e.style || "solid",
      })),
    };
  }

  function buildChains() {
    const starts = state.nodes.filter((n) => n.type === "device");
    const startNodes = starts.length ? starts : state.nodes.slice(0, 1);
    const chains = [];
    const visit = (current, pathNodes, pathEdges, seen) => {
      const outgoing = state.edges
        .filter((e) => e.from === current.id)
        .sort((a, b) => (Number(a.order) || 0) - (Number(b.order) || 0));
      if (!outgoing.length) {
        if (pathNodes.length > 1) chains.push({ nodes: pathNodes, edges: pathEdges });
        return;
      }
      for (const e of outgoing) {
        if (seen.has(e.to)) continue;
        const next = node(e.to);
        if (!next) continue;
        visit(next, pathNodes.concat(next), pathEdges.concat(e), new Set([...seen, e.to]));
      }
    };
    for (const start of startNodes) {
      visit(start, [start], [], new Set([start.id]));
    }
    return chains.slice(0, 24);
  }

  function routeText() {
    const chains = buildChains();
    if (!chains.length) return "Маршрутов нет: соедини узлы (out → in) или загрузи пресет.";
    return chains.map((chain, index) => {
      const lines = [`Маршрут ${index + 1} · ${chain.nodes.length} узлов`];
      chain.nodes.forEach((n, i) => {
        const incoming = chain.edges[i - 1];
        lines.push(`  ${String(i + 1).padStart(2, "0")}  ${n.label}${n.sub ? `  [${n.sub}]` : ""}`);
        if (incoming) {
          const via = incoming.condition || incoming.transport || "связь";
          lines.push(`      └─ ${via} ──▶`);
        }
      });
      return lines.join("\n");
    }).join("\n\n");
  }

  function toolPrompt() {
    return [
      "Ниже конфигурация цепочки KALIOPA из Route Lab.",
      "Нужно внести её в программу, не ломая текущую логику.",
      "Узлы: type/label/sub/host/port/note; связи: from/to/transport/condition/order/style.",
      "",
      "```json",
      JSON.stringify(exportState(), null, 2),
      "```",
    ].join("\n");
  }

  function renderCode() {
    const code = $("#code");
    if (state.activeTab === "route") code.textContent = routeText();
    else if (state.activeTab === "prompt") code.textContent = toolPrompt();
    else code.textContent = JSON.stringify(exportState(), null, 2);
    $$(".tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.tab === state.activeTab));
  }

  function markDirty() {
    $("#savedState").textContent = "черновик";
    $("#statusDot").classList.remove("saved");
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      try { localStorage.setItem("kaliopa-route-draft", JSON.stringify(exportState())); } catch (_) {}
    }, 250);
  }

  // ---------------------------------------------------------------------------
  // PHP save/load
  // ---------------------------------------------------------------------------
  async function refreshFiles() {
    const select = $("#loadSelect");
    try {
      const response = await fetch("?action=list", { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("HTTP " + response.status);
      const data = await response.json();
      const current = select.value;
      select.innerHTML = '<option value="">Загрузить…</option>';
      for (const file of data.files || []) {
        const option = document.createElement("option");
        option.value = file.file;
        option.textContent = `${file.name} · ${new Date(file.savedAt).toLocaleString()}`;
        select.appendChild(option);
      }
      if (current) select.value = current;
      $("#statusPhp").textContent = "PHP: сохранение доступно";
    } catch (_) {
      $("#statusPhp").textContent = "PHP недоступен — только скачивание";
    }
  }

  async function saveConfig() {
    const payload = JSON.stringify(exportState(), null, 2);
    try {
      const response = await fetch("?action=save", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: payload,
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || "save failed");
      $("#savedState").textContent = `сохранено · ${data.name}`;
      $("#statusDot").classList.add("saved");
      await refreshFiles();
      $("#loadSelect").value = data.file;
      toast(`Сохранено: ${data.file}`);
    } catch (error) {
      downloadJson();
      toast("PHP не сохранил — JSON скачан. " + error.message, true);
    }
  }

  function applyGraph(data, record = true) {
    if (!data || !Array.isArray(data.nodes) || !Array.isArray(data.edges)) {
      throw new Error("в JSON нет массивов nodes/edges");
    }
    if (record) pushHistory();
    state.name = data.name || "KALIOPA template";
    state.notes = data.notes || "";
    state.nodes = data.nodes;
    state.edges = data.edges;
    state.selected = null;
    state.connectFrom = null;
    state.nextId = 1 + Math.max(
      0,
      ...state.nodes.map((n) => Number(String(n.id).split("-").pop()) || 0),
      ...state.edges.map((e) => Number(String(e.id).split("-").pop()) || 0),
    );
    syncMetaInputs();
    renderAll();
    markDirty();
  }

  async function loadTemplate(record = true) {
    try {
      const response = await fetch("templates/kaliopa-clean.json", { cache: "no-store" });
      if (!response.ok) throw new Error("HTTP " + response.status);
      applyGraph(await response.json(), record);
      $("#savedState").textContent = "шаблон Kaliopa";
      $("#statusDot").classList.add("saved");
      return true;
    } catch (error) {
      toast("Шаблон Kaliopa не загружен: " + error.message, true);
      return false;
    }
  }

  async function loadFile(file) {
    if (!file) return;
    try {
      const response = await fetch(`?action=load&file=${encodeURIComponent(file)}`, { headers: { Accept: "application/json" } });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "load failed");
      applyGraph(data, true);
      $("#savedState").textContent = `загружено · ${file.replace(/\.json$/, "")}`;
      $("#statusDot").classList.add("saved");
      toast(`Загружено: ${file}`);
    } catch (error) {
      toast("Не удалось загрузить: " + error.message, true);
    }
  }

  async function deleteFile() {
    const file = $("#loadSelect").value;
    if (!file) return;
    if (!confirm(`Удалить сохранённую схему ${file}?`)) return;
    try {
      const response = await fetch(`?action=delete&file=${encodeURIComponent(file)}`, { method: "POST" });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || "delete failed");
      await refreshFiles();
      toast(`Удалено: ${file}`);
    } catch (error) {
      toast("Не удалось удалить: " + error.message, true);
    }
  }

  function downloadJson() {
    const blob = new Blob([JSON.stringify(exportState(), null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = (state.name || "kaliopa-route").replace(/[^\w.-]+/g, "-") + ".json";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function copyCode() {
    const text = $("#code").textContent;
    navigator.clipboard?.writeText(text).then(
      () => toast("Скопировано"),
      () => {
        const area = document.createElement("textarea");
        area.value = text;
        document.body.appendChild(area);
        area.select();
        document.execCommand("copy");
        area.remove();
        toast("Скопировано");
      },
    );
  }

  function toast(message, error = false) {
    const el = $("#toast");
    el.textContent = message;
    el.classList.toggle("error", Boolean(error));
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("show"), 2600);
  }

  // ---------------------------------------------------------------------------
  // Zoom / layout
  // ---------------------------------------------------------------------------
  function setZoom(value) {
    state.zoom = Math.max(0.35, Math.min(1.6, value));
    stage.style.transform = `scale(${state.zoom})`;
    $("#zoomValue").textContent = `${Math.round(state.zoom * 100)}%`;
  }

  function fitView() {
    if (!state.nodes.length) return setZoom(1);
    const minX = Math.min(...state.nodes.map((n) => n.x));
    const minY = Math.min(...state.nodes.map((n) => n.y));
    const maxX = Math.max(...state.nodes.map((n) => n.x + 220));
    const maxY = Math.max(...state.nodes.map((n) => n.y + 120));
    const width = Math.max(1, maxX - minX + 120);
    const height = Math.max(1, maxY - minY + 120);
    const scale = Math.max(0.4, Math.min(1.25, Math.min(stageScroll.clientWidth / width, stageScroll.clientHeight / height)));
    setZoom(scale);
    stageScroll.scrollTo({ left: Math.max(0, minX * scale - 40), top: Math.max(0, minY * scale - 40), behavior: "smooth" });
  }

  function autoLayout() {
    pushHistory();
    const incoming = new Map(state.nodes.map((n) => [n.id, 0]));
    for (const e of state.edges) incoming.set(e.to, (incoming.get(e.to) || 0) + 1);
    const roots = state.nodes.filter((n) => n.type === "device" || (incoming.get(n.id) || 0) === 0);
    const depth = new Map();
    const queue = roots.map((n) => [n, 0]);
    while (queue.length) {
      const [n, d] = queue.shift();
      if ((depth.get(n.id) ?? -1) >= d) continue;
      depth.set(n.id, d);
      for (const e of state.edges.filter((x) => x.from === n.id)) {
        const next = node(e.to);
        if (next) queue.push([next, d + 1]);
      }
    }
    const groups = new Map();
    for (const n of state.nodes) {
      const d = depth.get(n.id) ?? 0;
      if (!groups.has(d)) groups.set(d, []);
      groups.get(d).push(n);
    }
    for (const [d, items] of groups) {
      items.sort((a, b) => a.label.localeCompare(b.label, "ru"));
      items.forEach((n, index) => {
        n.x = 60 + d * 270;
        n.y = 90 + index * 132;
      });
    }
    renderAll();
    markDirty();
    setTimeout(fitView, 50);
  }

  // ---------------------------------------------------------------------------
  // Init + events
  // ---------------------------------------------------------------------------
  function syncMetaInputs() {
    $("#configName").value = state.name;
    $("#configNotes").value = state.notes;
  }

  function bind() {
    $("#palette").addEventListener("click", (event) => {
      const button = event.target.closest("[data-type]");
      if (!button) return;
      const type = button.dataset.type;
      const info = typeInfo(type);
      pushHistory();
      const rect = stageScroll.getBoundingClientRect();
      const x = Math.round((stageScroll.scrollLeft + rect.width * 0.42) / state.zoom);
      const y = Math.round((stageScroll.scrollTop + rect.height * 0.3) / state.zoom);
      const n = makeNode(uid("node"), type, info.label, "новый узел", Math.max(20, x), Math.max(20, y));
      state.nodes.push(n);
      selectNode(n.id);
      markDirty();
    });

    $$(".preset").forEach((button) => {
      button.addEventListener("click", () => {
        if (state.nodes.length && !confirm("Заменить текущую схему пресетом?")) return;
        if (button.dataset.preset === "kaliopa") {
          loadTemplate();
          return;
        }
        loadPreset(button.dataset.preset);
      });
    });

    $("#btnNew").addEventListener("click", () => {
      if (state.nodes.length && !confirm("Очистить схему?")) return;
      loadPreset("blank");
      toast("Новая схема");
    });
    $("#btnSave").addEventListener("click", saveConfig);
    $("#loadSelect").addEventListener("change", (event) => loadFile(event.target.value));
    $("#deleteSaved").addEventListener("click", deleteFile);
    $("#btnCopy").addEventListener("click", copyCode);
    $("#btnDownload").addEventListener("click", downloadJson);
    $("#btnHelp").addEventListener("click", () => $("#helpDialog").showModal());
    $("#closeHelp").addEventListener("click", () => $("#helpDialog").close());

    $$(".tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        state.activeTab = tab.dataset.tab;
        renderCode();
      });
    });

    $("#configName").addEventListener("input", (event) => {
      state.name = event.target.value;
      markDirty();
      renderCode();
    });
    $("#configNotes").addEventListener("input", (event) => {
      state.notes = event.target.value;
      markDirty();
      renderCode();
    });

    $("#zoomIn").addEventListener("click", () => setZoom(state.zoom * 1.1));
    $("#zoomOut").addEventListener("click", () => setZoom(state.zoom / 1.1));
    $("#fitView").addEventListener("click", fitView);
    $("#autoLayout").addEventListener("click", autoLayout);
    $("#undoBtn").addEventListener("click", undo);
    $("#redoBtn").addEventListener("click", redo);

    stageScroll.addEventListener("click", (event) => {
      if (event.target === stageScroll || event.target === stage || event.target === nodesHost) {
        state.selected = null;
        state.connectFrom = null;
        renderAll();
      }
    });

    document.addEventListener("keydown", (event) => {
      const tag = (event.target.tagName || "").toLowerCase();
      const typing = tag === "input" || tag === "textarea" || tag === "select";
      if (event.key === "Escape") {
        state.connectFrom = null;
        renderAll();
      }
      if (typing) return;
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
        event.preventDefault();
        undo();
      } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "y") {
        event.preventDefault();
        redo();
      } else if (event.key === "Delete" || event.key === "Backspace") {
        event.preventDefault();
        deleteSelected();
      }
    });

    // Pan with middle mouse or space is intentionally omitted: canvas scroll is native.
    setZoom(1);
    refreshFiles();
  }

  // Открываем готовый шаблон Kaliopa; при отсутствии файла — старый current.
  async function init() {
    bind();
    const loaded = await loadTemplate(false);
    if (!loaded) loadPreset("current", false);
    if (location.hash === "#draft") {
      try {
        const raw = localStorage.getItem("kaliopa-route-draft");
        if (raw) {
          applyGraph(JSON.parse(raw), false);
          toast("Черновик восстановлен");
        }
      } catch (_) {}
    }
    setTimeout(fitView, 160);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
