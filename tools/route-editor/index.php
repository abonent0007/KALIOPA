<?php
declare(strict_types=1);

/**
 * KALIOPA Route Lab — визуальный редактор цепочки пакетов.
 *
 * Один PHP-файл: отдаёт страницу и принимает JSON графа (save/list/load/delete).
 * Данные лежат в routes/*.json рядом; это локальный инструмент, не сервис.
 */

$DATA_DIR = __DIR__ . DIRECTORY_SEPARATOR . 'routes';
if (!is_dir($DATA_DIR)) {
    @mkdir($DATA_DIR, 0775, true);
}

function k_graph_error(array $data): ?string
{
    if (!isset($data['nodes'], $data['edges']) || !is_array($data['nodes']) || !is_array($data['edges'])) {
        return 'нужны массивы nodes и edges';
    }
    if (count($data['nodes']) > 200 || count($data['edges']) > 400) {
        return 'слишком большой граф';
    }
    $ids = [];
    foreach ($data['nodes'] as $node) {
        if (!is_array($node) || !isset($node['id'], $node['type'], $node['label'])) {
            return 'у узла нет id/type/label';
        }
        $id = (string)$node['id'];
        if (!preg_match('/^[A-Za-z0-9_-]{1,64}$/', $id) || isset($ids[$id])) {
            return 'некорректный или повторный id узла: ' . $id;
        }
        $ids[$id] = true;
        foreach (['x', 'y'] as $field) {
            if (isset($node[$field]) && !is_numeric($node[$field])) {
                return 'координата ' . $field . ' не число';
            }
        }
    }
    foreach ($data['edges'] as $edge) {
        if (!is_array($edge) || !isset($edge['id'], $edge['from'], $edge['to'])) {
            return 'у связи нет id/from/to';
        }
        if (!preg_match('/^[A-Za-z0-9_-]{1,64}$/', (string)$edge['id'])) {
            return 'некорректный id связи';
        }
        if (!isset($ids[(string)$edge['from']]) || !isset($ids[(string)$edge['to']])) {
            return 'связь ссылается на несуществующий узел';
        }
    }
    return null;
}

if (isset($_GET['action']) && $_GET['action'] !== '') {
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    $action = (string)$_GET['action'];
    try {
        if ($action === 'list') {
            $files = [];
            foreach (glob($DATA_DIR . DIRECTORY_SEPARATOR . '*.json') ?: [] as $path) {
                $files[] = [
                    'file' => basename($path),
                    'name' => pathinfo($path, PATHINFO_FILENAME),
                    'savedAt' => date('c', (int)filemtime($path)),
                    'size' => (int)filesize($path),
                ];
            }
            usort($files, static fn(array $a, array $b): int => strcmp($b['savedAt'], $a['savedAt']));
            echo json_encode(['ok' => true, 'files' => $files], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
            exit;
        }

        if ($action === 'load') {
            $file = basename((string)($_GET['file'] ?? ''));
            if (!preg_match('/^[A-Za-z0-9._-]+\.json$/', $file)) {
                throw new RuntimeException('некорректное имя файла');
            }
            $path = $DATA_DIR . DIRECTORY_SEPARATOR . $file;
            if (!is_file($path)) {
                throw new RuntimeException('файл не найден');
            }
            echo file_get_contents($path);
            exit;
        }

        if ($action === 'save') {
            if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
                throw new RuntimeException('save принимает только POST');
            }
            $raw = file_get_contents('php://input', false, null, 0, 1024 * 1024);
            $data = json_decode((string)$raw, true);
            if (!is_array($data)) {
                throw new RuntimeException('тело не JSON: ' . json_last_error_msg());
            }
            $error = k_graph_error($data);
            if ($error !== null) {
                throw new RuntimeException($error);
            }
            $name = trim((string)($data['name'] ?? 'route'));
            $slug = strtolower((string)preg_replace('/[^A-Za-z0-9._-]+/', '-', $name));
            $slug = trim($slug, '-_.');
            if ($slug === '') {
                $slug = 'route-' . date('Ymd-His');
            }
            $file = $slug . '.json';
            $path = $DATA_DIR . DIRECTORY_SEPARATOR . $file;
            $tmp = $path . '.tmp';
            $json = json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
            if ($json === false || file_put_contents($tmp, $json) === false) {
                throw new RuntimeException('не удалось записать файл');
            }
            if (!@rename($tmp, $path)) {
                @unlink($tmp);
                throw new RuntimeException('не удалось переключить файл');
            }
            echo json_encode([
                'ok' => true,
                'file' => $file,
                'name' => pathinfo($file, PATHINFO_FILENAME),
                'savedAt' => date('c'),
            ], JSON_UNESCAPED_UNICODE);
            exit;
        }

        if ($action === 'delete') {
            if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
                throw new RuntimeException('delete принимает только POST');
            }
            $file = basename((string)($_GET['file'] ?? ''));
            if (!preg_match('/^[A-Za-z0-9._-]+\.json$/', $file)) {
                throw new RuntimeException('некорректное имя файла');
            }
            $path = $DATA_DIR . DIRECTORY_SEPARATOR . $file;
            if (is_file($path) && !@unlink($path)) {
                throw new RuntimeException('файл не удалён');
            }
            echo json_encode(['ok' => true], JSON_UNESCAPED_UNICODE);
            exit;
        }

        throw new RuntimeException('неизвестное действие: ' . $action);
    } catch (Throwable $exc) {
        http_response_code(400);
        echo json_encode(['ok' => false, 'error' => $exc->getMessage()], JSON_UNESCAPED_UNICODE);
        exit;
    }
}
?>
<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>KALIOPA · Route Lab</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Syne:wght@600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="assets/app.css">
</head>
<body>
<div class="ambient ambient-a"></div>
<div class="ambient ambient-b"></div>

<header class="topbar">
  <div class="brand">
    <div class="brand-mark" aria-hidden="true">
      <span></span><span></span><span></span>
    </div>
    <div>
      <h1>KALIOPA <em>/ route lab</em></h1>
      <p>визуальная цепочка пакетов · редактор конфигурации</p>
    </div>
  </div>
  <div class="top-actions">
    <span class="status-dot" id="statusDot"></span>
    <span class="saved-state" id="savedState">черновик</span>
    <button class="btn ghost" id="btnNew" type="button">Новая</button>
    <button class="btn ghost" id="btnHelp" type="button">?</button>
    <button class="btn primary" id="btnSave" type="button">Сохранить JSON</button>
  </div>
</header>

<main class="workspace">
  <aside class="rail rail-left">
    <section class="rail-block">
      <div class="rail-kicker">Палитра</div>
      <p class="rail-hint">Клик — добавить узел. Порт <b>out</b> → <b>in</b> соединяет.</p>
      <div class="node-palette" id="palette">
        <button class="palette-item" data-type="device" type="button"><i class="dot device"></i>Устройство</button>
        <button class="palette-item" data-type="app" type="button"><i class="dot app"></i>Приложение</button>
        <button class="palette-item" data-type="pac" type="button"><i class="dot pac"></i>PAC / прокси</button>
        <button class="palette-item" data-type="proxy" type="button"><i class="dot proxy"></i>Прокси / VPN</button>
        <button class="palette-item" data-type="relay" type="button"><i class="dot relay"></i>Релей</button>
        <button class="palette-item" data-type="tls" type="button"><i class="dot tls"></i>TLS-терминатор</button>
        <button class="palette-item" data-type="dns" type="button"><i class="dot dns"></i>DNS</button>
        <button class="palette-item" data-type="edge" type="button"><i class="dot edge"></i>Внешний узел</button>
        <button class="palette-item" data-type="server" type="button"><i class="dot server"></i>Сервер</button>
      </div>
    </section>

    <section class="rail-block">
      <div class="rail-kicker">Пресеты</div>
      <div class="preset-list">
        <button class="preset" data-preset="current" type="button"><b>Текущая KALIOPA</b><span>браузер + Telegram + DNS</span></button>
        <button class="preset" data-preset="browser" type="button"><b>Браузер через Opera</b><span>ChatGPT / EU / YouTube</span></button>
        <button class="preset" data-preset="telegram" type="button"><b>Telegram-релей</b><span>1372 → WARP → DC</span></button>
        <button class="preset" data-preset="vless" type="button"><b>VLESS-профиль</b><span>nova-xray 1379/1380</span></button>
        <button class="preset" data-preset="blank" type="button"><b>Пустая схема</b><span>устройство + сервер</span></button>
      </div>
    </section>

    <section class="rail-block legend">
      <div class="rail-kicker">Слои</div>
      <div><i class="line solid"></i> основной путь</div>
      <div><i class="line dashed"></i> резерв / опция</div>
      <div><i class="line dotted"></i> DNS / служебное</div>
    </section>
  </aside>

  <section class="stage-shell">
    <div class="stage-toolbar">
      <div class="tool-group">
        <button class="tool" id="zoomOut" type="button" title="Уменьшить">−</button>
        <span class="zoom-value" id="zoomValue">100%</span>
        <button class="tool" id="zoomIn" type="button" title="Увеличить">+</button>
        <button class="tool" id="fitView" type="button">Fit</button>
      </div>
      <div class="tool-group">
        <button class="tool" id="autoLayout" type="button">Авто-сетка</button>
        <button class="tool" id="undoBtn" type="button" title="Ctrl+Z">↶</button>
        <button class="tool" id="redoBtn" type="button" title="Ctrl+Y">↷</button>
      </div>
      <div class="connect-hint" id="connectHint">Клик по <b>out</b>, затем по <b>in</b> — создать связь</div>
      <select class="load-select" id="loadSelect" aria-label="Загрузить сохранённую схему">
        <option value="">Загрузить…</option>
      </select>
      <button class="tool danger" id="deleteSaved" type="button" title="Удалить выбранный сохранённый файл">⌫</button>
    </div>

    <div class="stage-scroll" id="stageScroll">
      <div class="stage" id="stage">
        <svg class="wires" id="wires" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#6cf5cd"></path>
            </marker>
            <filter id="glow" x="-30%" y="-30%" width="160%" height="160%">
              <feGaussianBlur stdDeviation="3" result="blur"></feGaussianBlur>
              <feMerge><feMergeNode in="blur"></feMergeNode><feMergeNode in="SourceGraphic"></feMergeNode></feMerge>
            </filter>
          </defs>
          <g id="edgeLayer"></g>
        </svg>
        <div class="nodes" id="nodes"></div>
      </div>
    </div>
  </section>

  <aside class="rail rail-right">
    <section class="inspector-head">
      <div class="rail-kicker">Инспектор</div>
      <span class="selection-badge" id="selectionBadge">ничего не выбрано</span>
    </section>
    <div class="inspector-body" id="inspector"></div>

    <section class="rail-block meta-block">
      <div class="rail-kicker">Схема</div>
      <label class="field"><span>Имя</span><input id="configName" type="text" value="KALIOPA current route"></label>
      <label class="field"><span>Комментарий для агента</span><textarea id="configNotes" rows="4" placeholder="Что нужно изменить в программе?"></textarea></label>
      <div class="route-summary" id="routeSummary"></div>
    </section>
  </aside>
</main>

<section class="dock">
  <div class="dock-head">
    <div class="tabs" role="tablist">
      <button class="tab active" data-tab="json" type="button">JSON конфигурация</button>
      <button class="tab" data-tab="route" type="button">Маршрут</button>
      <button class="tab" data-tab="prompt" type="button">Для агента</button>
    </div>
    <div class="dock-actions">
      <button class="btn tiny" id="btnCopy" type="button">Копировать</button>
      <button class="btn tiny" id="btnDownload" type="button">Скачать .json</button>
    </div>
  </div>
  <pre class="code" id="code" tabindex="0"></pre>
</section>

<div class="statusbar">
  <span id="statusNodes">0 узлов</span>
  <span id="statusEdges">0 связей</span>
  <span id="statusSelection">—</span>
  <span class="spacer"></span>
  <span id="statusPhp">PHP: сохранение доступно</span>
  <span class="status-mono">KALIOPA / route lab</span>
</div>

<div class="toast" id="toast" role="status" aria-live="polite"></div>

<dialog class="help-dialog" id="helpDialog">
  <div class="help-head"><h2>Route Lab</h2><button class="btn ghost" id="closeHelp" type="button">×</button></div>
  <div class="help-body">
    <p><b>Соединение:</b> клик по синему порту <b>out</b> справа у узла, затем по порту <b>in</b> слева у другого узла. <kbd>Esc</kbd> отменяет.</p>
    <p><b>Редактирование:</b> тяни узел за заголовок, меняй поля справа. <kbd>Delete</kbd> удаляет выбранное, <kbd>Ctrl</kbd>+<kbd>Z</kbd> / <kbd>Ctrl</kbd>+<kbd>Y</kbd> — отмена/повтор.</p>
    <p><b>Вывод:</b> внизу — JSON, маршрут и готовый текст для агента. Сохрани JSON в PHP-хранилище или скачай файл.</p>
    <p><b>Запуск:</b> <code>php -S 127.0.0.1:8099 -t tools/route-editor</code>, открыть <code>http://127.0.0.1:8099/</code>. Без PHP страница тоже работает, но сохранение на сервер недоступно.</p>
  </div>
</dialog>

<script src="assets/app.js"></script>
</body>
</html>
