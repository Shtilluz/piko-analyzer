"""
Built-in help / instruction panel.

Content is stored as HTML strings, one per language.
Language switch rebuilds the browser content instantly.
"""

from __future__ import annotations

from PySide6.QtCore    import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextBrowser

from analyzer.i18n import get_language, on_language_changed

# ================================================================ #
# HTML content — English                                             #
# ================================================================ #

_EN = """\
<!DOCTYPE html>
<html>
<head>
<style>
  body  { font-family: Segoe UI, Arial, sans-serif; font-size: 13px;
          background: #1e1e2e; color: #cdd6f4; margin: 16px; }
  h1    { color: #89b4fa; border-bottom: 1px solid #45475a; padding-bottom: 6px; }
  h2    { color: #89dceb; margin-top: 22px; }
  h3    { color: #a6e3a1; margin-top: 14px; margin-bottom: 4px; }
  code  { background: #313244; padding: 1px 5px; border-radius: 3px;
          font-family: Courier New, monospace; color: #f38ba8; }
  pre   { background: #313244; padding: 10px; border-radius: 6px;
          font-family: Courier New, monospace; font-size: 12px; color: #cdd6f4; }
  .tip  { background: #2a2d3e; border-left: 4px solid #f9e2af;
          padding: 8px 12px; margin: 8px 0; border-radius: 3px; }
  .warn { background: #2a2d3e; border-left: 4px solid #f38ba8;
          padding: 8px 12px; margin: 8px 0; border-radius: 3px; }
  ul li { margin: 3px 0; }
  table { border-collapse: collapse; width: 100%; }
  th    { background: #313244; padding: 5px 10px; text-align: left; }
  td    { padding: 4px 10px; border-bottom: 1px solid #313244; }
</style>
</head>
<body>

<h1>PIKO SmartControl Protocol Analyzer — User Guide</h1>

<p>This tool captures raw signal edges from the PIKO SmartControl bus,
identifies packet structure, and helps you reverse-engineer the protocol
<b>without any prior assumptions</b> about what the bytes mean.</p>

<!-- ============================================================ -->
<h2>1. Hardware Setup</h2>

<p>You need an <b>Arduino Nano</b> (or Uno/Pro Mini) and a
<b>6N137</b> high-speed optocoupler for galvanic isolation.</p>

<h3>Wiring</h3>
<pre>
PIKO SmartControl bus ──► 6N137 (input side)
                              │
                         6N137 (output side, open-collector)
                              │
                         pull-up 4.7kΩ to +5V
                              │
                         Arduino D2 (INT0, hardware interrupt)
</pre>

<div class="warn">
  <b>Warning:</b> Always use galvanic isolation (6N137 or similar).
  Never connect the bus directly to the Arduino — you risk destroying
  both the Arduino and the PIKO command station.
</div>

<h3>Arduino Firmware</h3>
<p>Flash the included firmware <code>arduino/piko_capture/piko_capture.ino</code>
to the Arduino. It uses hardware interrupt INT0 on pin D2 to capture
every signal edge with microsecond precision.</p>

<p>Default UART speed: <code>115200 baud</code>. Change <code>Serial.begin()</code>
in the firmware and select the same baud rate in the app.</p>

<!-- ============================================================ -->
<h2>2. Connecting in the App</h2>

<ol>
  <li>Connect the Arduino via USB.</li>
  <li>Click <b>↺</b> to refresh the port list.</li>
  <li>Select the correct COM port and baud rate (default 115200).</li>
  <li>Click <b>Connect</b>. The status indicator turns green.</li>
  <li>Click <b>Start Raw Capture</b> — the Arduino starts sending edges.</li>
</ol>

<div class="tip">
  <b>Tip:</b> If nothing happens after Connect, check the <b>Log</b> tab.
  Common causes: wrong COM port, wrong baud rate, firmware not flashed.
</div>

<!-- ============================================================ -->
<h2>3. Understanding the Packet Table</h2>

<p>The top section shows all unique packet structures captured so far,
sorted by frequency. Each row is a distinct byte sequence.</p>

<table>
  <tr><th>Column</th><th>Meaning</th></tr>
  <tr><td><b>Packet (hex)</b></td><td>Byte content in hexadecimal</td></tr>
  <tr><td><b>Count</b></td><td>How many times this exact packet was received</td></tr>
  <tr><td><b>%</b></td><td>Share of this packet in total traffic</td></tr>
  <tr><td><b>Last seen (µs)</b></td><td>Arduino timestamp of last reception</td></tr>
</table>

<div class="tip">
  <b>Tip:</b> A packet appearing in ≥95% of traffic is the "idle" or
  "heartbeat" packet — it is sent constantly to keep the bus alive.
</div>

<!-- ============================================================ -->
<h2>4. Byte Analysis Tab</h2>

<p>Shows per-byte-position statistics across all received packets.</p>

<h3>Variability labels</h3>
<table>
  <tr><th>Label</th><th>Meaning</th><th>Likely function</th></tr>
  <tr><td><code>CONSTANT</code></td>
      <td>Same value in every packet</td>
      <td>Preamble, sync byte, fixed device address</td></tr>
  <tr><td><code>MOSTLY_CONSTANT</code></td>
      <td>Changes in ≤10% of packets</td>
      <td>Mode flag, command type</td></tr>
  <tr><td><code>VARIABLE</code></td>
      <td>Changes frequently</td>
      <td>Speed, direction bit, function flags, checksum</td></tr>
</table>

<!-- ============================================================ -->
<h2>5. Bit Analysis Tab</h2>

<p>Shows per-bit statistics for each byte position.</p>

<table>
  <tr><th>Row</th><th>Meaning</th></tr>
  <tr><td><b>%0</b></td><td>How often this bit is 0 (percentage)</td></tr>
  <tr><td><b>%1</b></td><td>How often this bit is 1</td></tr>
  <tr><td><b>trans%</b></td><td>How often this bit changes between consecutive packets</td></tr>
</table>

<h3>Interpretation</h3>
<ul>
  <li><b>%0 ≈ 100%</b> or <b>%1 ≈ 100%</b> → constant bit (fixed flag, sync)</li>
  <li><b>trans% ≈ 50%</b> → rapidly changing bit (speed counter, alternating flag)</li>
  <li><b>trans% low, but %0 ≠ 100%</b> → mode or direction bit (set once, stays set)</li>
</ul>

<!-- ============================================================ -->
<h2>6. Actions Tab — Recording Protocol Actions</h2>

<p>The action recorder lets you compare "idle" traffic with traffic
generated by a specific controller action.</p>

<h3>Workflow</h3>
<ol>
  <li>Enter a descriptive label, e.g. <code>speed_3</code> or <code>f0_on</code>.</li>
  <li>Click <b>1. Start Baseline</b> — keep the controller untouched for 10–20 s.</li>
  <li>Click <b>2. Action Now</b> — immediately perform the action on the controller.</li>
  <li>Click <b>3. Stop &amp; Save</b> — the diff is shown below.</li>
</ol>

<div class="tip">
  <b>Tip for correlation:</b> Record the same action at multiple intensities
  using a numeric suffix: <code>speed_0</code>, <code>speed_1</code>, <code>speed_2</code>…
  Then click <b>Run Correlation Analysis</b> to find which byte encodes the value.
</div>

<!-- ============================================================ -->
<h2>7. Checksum Tab</h2>

<p>Click <b>Run Checksum Analysis</b> after capturing enough packets (≥50 recommended).
The analyzer tries every byte position as the checksum field and tests algorithms:
<code>XOR</code>, <code>SUM8</code>, <code>SUM8_NEG</code>, <code>SUM8_COMP2</code>, <code>CRC8</code>.</p>

<p>A candidate with ≥90% match rate is almost certainly the checksum field.
Note the algorithm and byte position for use in the Sketch Generator.</p>

<!-- ============================================================ -->
<h2>8. Charts Tab</h2>

<ul>
  <li><b>Top-left:</b> most frequent packets (horizontal bar chart)</li>
  <li><b>Top-right:</b> selected byte value over the last N packets (time-series)</li>
  <li><b>Bottom-left:</b> packet length over time</li>
  <li><b>Bottom-right:</b> value distribution histogram for the selected byte</li>
</ul>

<p>Use the <b>Byte position</b> spinbox to select which byte to visualize on the right two charts.</p>

<!-- ============================================================ -->
<h2>9. Sketch Generator Tab</h2>

<p>Once you have identified the packet structure, fill in the discovered
constants and click <b>Generate Sketch</b>. You get a complete Arduino
<code>.ino</code> file with:</p>
<ul>
  <li><code>setSpeed(uint8_t speed)</code></li>
  <li><code>setDirection(bool forward)</code></li>
  <li><code>setFunction(uint8_t fn, bool on)</code></li>
  <li>Automatic checksum calculation</li>
  <li>Example <code>loop()</code></li>
</ul>

<div class="warn">
  <b>Important:</b> The generated sketch outputs packets via
  <code>Serial.write()</code> for testing. To actually drive the PIKO bus
  you must implement the physical bus driver (replace the <code>Serial.write</code>
  call in <code>buildAndSend()</code> with your bus output logic).
</div>

<!-- ============================================================ -->
<h2>10. Saving &amp; Exporting</h2>

<ul>
  <li><b>File → Save Session</b> — saves all captured data to JSON in
      <code>data/sessions/</code></li>
  <li><b>File → Export CSV…</b> — exports the packet table to a CSV file</li>
  <li><b>Log tab → Open Log File</b> — opens <code>data/piko_analyzer.log</code></li>
</ul>

<!-- ============================================================ -->
<h2>11. Troubleshooting</h2>

<table>
  <tr><th>Symptom</th><th>Likely cause</th><th>Fix</th></tr>
  <tr><td>Connect has no effect</td>
      <td>Wrong port or baud rate</td>
      <td>Check the Log tab, try other baud rates</td></tr>
  <tr><td>No packets appear</td>
      <td>Arduino not flashed / bus not connected</td>
      <td>Verify firmware, check wiring</td></tr>
  <tr><td>Parse errors in log</td>
      <td>Baud rate mismatch</td>
      <td>Match baud in app and firmware</td></tr>
  <tr><td>High "Dropped (Arduino)" count</td>
      <td>Arduino buffer overflow</td>
      <td>Increase baud rate or reduce bus activity</td></tr>
  <tr><td>All packets look the same</td>
      <td>Only idle heartbeat captured</td>
      <td>Operate the controller while capturing</td></tr>
</table>

</body></html>
"""

# ================================================================ #
# HTML content — Russian                                             #
# ================================================================ #

_RU = """\
<!DOCTYPE html>
<html>
<head>
<style>
  body  { font-family: Segoe UI, Arial, sans-serif; font-size: 13px;
          background: #1e1e2e; color: #cdd6f4; margin: 16px; }
  h1    { color: #89b4fa; border-bottom: 1px solid #45475a; padding-bottom: 6px; }
  h2    { color: #89dceb; margin-top: 22px; }
  h3    { color: #a6e3a1; margin-top: 14px; margin-bottom: 4px; }
  code  { background: #313244; padding: 1px 5px; border-radius: 3px;
          font-family: Courier New, monospace; color: #f38ba8; }
  pre   { background: #313244; padding: 10px; border-radius: 6px;
          font-family: Courier New, monospace; font-size: 12px; color: #cdd6f4; }
  .tip  { background: #2a2d3e; border-left: 4px solid #f9e2af;
          padding: 8px 12px; margin: 8px 0; border-radius: 3px; }
  .warn { background: #2a2d3e; border-left: 4px solid #f38ba8;
          padding: 8px 12px; margin: 8px 0; border-radius: 3px; }
  ul li { margin: 3px 0; }
  table { border-collapse: collapse; width: 100%; }
  th    { background: #313244; padding: 5px 10px; text-align: left; }
  td    { padding: 4px 10px; border-bottom: 1px solid #313244; }
</style>
</head>
<body>

<h1>PIKO SmartControl — Анализатор протокола: руководство пользователя</h1>

<p>Программа захватывает сырые фронты сигнала с шины PIKO SmartControl,
выявляет структуру пакетов и помогает реверс-инжинирингу протокола
<b>без каких-либо предположений</b> о значении байтов.</p>

<!-- ============================================================ -->
<h2>1. Аппаратная часть</h2>

<p>Понадобится <b>Arduino Nano</b> (или Uno/Pro Mini) и быстрый
оптопара <b>6N137</b> для гальванической развязки.</p>

<h3>Схема подключения</h3>
<pre>
Шина PIKO SmartControl ──► 6N137 (вход)
                                │
                           6N137 (выход, открытый коллектор)
                                │
                           подтяжка 4.7 кОм к +5В
                                │
                           Arduino D2 (INT0, аппаратное прерывание)
</pre>

<div class="warn">
  <b>Внимание:</b> Всегда используйте гальваническую развязку (6N137 или аналог).
  Никогда не подключайте шину напрямую к Arduino — это может уничтожить
  и плату, и командную станцию PIKO.
</div>

<h3>Прошивка Arduino</h3>
<p>Залейте прошивку <code>arduino/piko_capture/piko_capture.ino</code>
в Arduino. Она использует аппаратное прерывание INT0 на пине D2 для
захвата каждого фронта сигнала с точностью до микросекунды.</p>

<p>Скорость UART по умолчанию: <code>115200 бод</code>. При необходимости
измените <code>Serial.begin()</code> в прошивке и выберите ту же скорость в программе.</p>

<!-- ============================================================ -->
<h2>2. Подключение в программе</h2>

<ol>
  <li>Подключите Arduino по USB.</li>
  <li>Нажмите <b>↺</b> для обновления списка портов.</li>
  <li>Выберите правильный COM-порт и скорость (по умолчанию 115200).</li>
  <li>Нажмите <b>Подключить</b>. Индикатор должен стать зелёным.</li>
  <li>Нажмите <b>Начать захват</b> — Arduino начнёт передавать фронты.</li>
</ol>

<div class="tip">
  <b>Подсказка:</b> Если после нажатия «Подключить» ничего не происходит,
  откройте вкладку <b>Лог</b>. Типичные причины: неверный COM-порт,
  неверная скорость, прошивка не залита.
</div>

<!-- ============================================================ -->
<h2>3. Таблица пакетов</h2>

<p>Верхняя панель показывает все уникальные структуры пакетов,
отсортированные по частоте встречаемости.</p>

<table>
  <tr><th>Колонка</th><th>Значение</th></tr>
  <tr><td><b>Пакет (hex)</b></td><td>Содержимое в шестнадцатеричном виде</td></tr>
  <tr><td><b>Кол-во</b></td><td>Сколько раз принят именно этот пакет</td></tr>
  <tr><td><b>%</b></td><td>Доля в общем трафике</td></tr>
  <tr><td><b>Последний (мкс)</b></td><td>Метка времени Arduino последнего приёма</td></tr>
</table>

<div class="tip">
  <b>Подсказка:</b> Пакет, занимающий ≥95% трафика — это «холостой» или «heartbeat» пакет,
  который шина шлёт постоянно для поддержания соединения.
</div>

<!-- ============================================================ -->
<h2>4. Вкладка «Анализ байтов»</h2>

<p>Показывает статистику по каждой позиции байта во всех принятых пакетах.</p>

<h3>Метки постоянства</h3>
<table>
  <tr><th>Метка</th><th>Значение</th><th>Вероятная функция байта</th></tr>
  <tr><td><code>CONSTANT</code></td>
      <td>Одинаковое во всех пакетах</td>
      <td>Преамбула, байт синхронизации, фиксированный адрес</td></tr>
  <tr><td><code>MOSTLY_CONSTANT</code></td>
      <td>Меняется в ≤10% пакетов</td>
      <td>Флаг режима, тип команды</td></tr>
  <tr><td><code>VARIABLE</code></td>
      <td>Активно меняется</td>
      <td>Скорость, бит направления, флаги функций, контрольная сумма</td></tr>
</table>

<!-- ============================================================ -->
<h2>5. Вкладка «Анализ битов»</h2>

<p>Побитовая статистика для каждой позиции байта.
B7 = старший бит (MSB), B0 = младший (LSB).</p>

<table>
  <tr><th>Строка</th><th>Значение</th></tr>
  <tr><td><b>%0</b></td><td>Как часто бит равен 0 (в %)</td></tr>
  <tr><td><b>%1</b></td><td>Как часто бит равен 1</td></tr>
  <tr><td><b>перех%</b></td><td>Как часто бит меняется между соседними пакетами</td></tr>
</table>

<h3>Интерпретация</h3>
<ul>
  <li><b>%0 ≈ 100%</b> или <b>%1 ≈ 100%</b> → константный бит (фиксированный флаг)</li>
  <li><b>перех% ≈ 50%</b> → быстро меняющийся бит (счётчик, чередующийся флаг)</li>
  <li><b>перех% низкий, %0 ≠ 100%</b> → бит режима или направления</li>
</ul>

<!-- ============================================================ -->
<h2>6. Вкладка «Действия» — запись действий на контроллере</h2>

<p>Позволяет сравнить «холостой» трафик с трафиком, возникающим
при конкретном действии на контроллере.</p>

<h3>Порядок работы</h3>
<ol>
  <li>Введите метку, например <code>speed_3</code> или <code>f0_on</code>.</li>
  <li>Нажмите <b>1. Начать baseline</b> — ничего не делайте на контроллере 10–20 сек.</li>
  <li>Нажмите <b>2. Выполнить действие</b> — сразу выполните действие на контроллере.</li>
  <li>Нажмите <b>3. Стоп и сохранить</b> — программа покажет изменившиеся байты.</li>
</ol>

<div class="tip">
  <b>Для корреляционного анализа:</b> Запишите одно действие на нескольких уровнях
  с числовым суффиксом: <code>speed_0</code>, <code>speed_1</code>, <code>speed_2</code>…
  Затем нажмите <b>Запустить анализ корреляции</b> — программа найдёт байт,
  кодирующий это значение.
</div>

<!-- ============================================================ -->
<h2>7. Вкладка «Контрольная сумма»</h2>

<p>Нажмите <b>Запустить анализ КС</b> после захвата достаточного количества пакетов
(рекомендуется ≥50). Анализатор перебирает каждую позицию байта как кандидата
на роль КС и тестирует алгоритмы:
<code>XOR</code>, <code>SUM8</code>, <code>SUM8_NEG</code>, <code>SUM8_COMP2</code>, <code>CRC8</code>.</p>

<p>Кандидат с ≥90% совпадений почти наверняка является контрольной суммой.
Запишите алгоритм и позицию байта — они понадобятся в генераторе скетча.</p>

<!-- ============================================================ -->
<h2>8. Вкладка «Графики»</h2>

<ul>
  <li><b>Верхний левый:</b> самые частые пакеты (горизонтальные бары)</li>
  <li><b>Верхний правый:</b> значение выбранного байта по последним N пакетам</li>
  <li><b>Нижний левый:</b> длина пакетов во времени</li>
  <li><b>Нижний правый:</b> гистограмма распределения значений выбранного байта</li>
</ul>

<p>Спинбокс <b>Позиция байта</b> выбирает байт для правых двух графиков.</p>

<!-- ============================================================ -->
<h2>9. Вкладка «Генератор скетча»</h2>

<p>После определения структуры пакетов заполните поля с найденными константами
и нажмите <b>Сгенерировать скетч</b>. Вы получите готовый Arduino <code>.ino</code> файл с:</p>
<ul>
  <li><code>setSpeed(uint8_t speed)</code> — установка скорости</li>
  <li><code>setDirection(bool forward)</code> — выбор направления</li>
  <li><code>setFunction(uint8_t fn, bool on)</code> — управление функциями F0–F28</li>
  <li>Автоматический расчёт контрольной суммы выбранным алгоритмом</li>
  <li>Пример <code>loop()</code> с демонстрационным сценарием</li>
</ul>

<div class="warn">
  <b>Важно:</b> Сгенерированный скетч выводит пакеты через <code>Serial.write()</code>
  для тестирования. Чтобы реально управлять шиной PIKO SmartControl, необходимо
  реализовать физический драйвер шины — заменить вызов <code>Serial.write</code>
  в функции <code>buildAndSend()</code> на свою логику вывода в шину.
</div>

<!-- ============================================================ -->
<h2>10. Сохранение и экспорт</h2>

<ul>
  <li><b>Файл → Сохранить сессию</b> — сохраняет все данные в JSON в папку
      <code>data/sessions/</code></li>
  <li><b>Файл → Экспорт CSV…</b> — экспортирует таблицу пакетов в CSV</li>
  <li><b>Лог → Открыть файл лога</b> — открывает <code>data/piko_analyzer.log</code></li>
</ul>

<!-- ============================================================ -->
<h2>11. Устранение неполадок</h2>

<table>
  <tr><th>Симптом</th><th>Вероятная причина</th><th>Решение</th></tr>
  <tr><td>«Подключить» не реагирует</td>
      <td>Неверный порт или скорость</td>
      <td>Смотрите вкладку Лог, попробуйте другие скорости</td></tr>
  <tr><td>Пакеты не появляются</td>
      <td>Arduino не прошита / шина не подключена</td>
      <td>Проверьте прошивку и проводку</td></tr>
  <tr><td>Ошибки парсинга в логе</td>
      <td>Несоответствие скорости</td>
      <td>Согласуйте baud в программе и прошивке</td></tr>
  <tr><td>Много «Потеряно (Arduino)»</td>
      <td>Переполнение буфера платы</td>
      <td>Увеличьте скорость UART или уменьшите активность шины</td></tr>
  <tr><td>Все пакеты одинаковые</td>
      <td>Только холостой трафик захвачен</td>
      <td>Управляйте контроллером во время захвата</td></tr>
</table>

</body></html>
"""

_CONTENT = {"en": _EN, "ru": _RU}


class HelpViewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(True)
        layout.addWidget(self._browser)

        self._load_content()
        on_language_changed(lambda _: self._load_content())

    def _load_content(self) -> None:
        lang = get_language()
        html = _CONTENT.get(lang, _EN)
        self._browser.setHtml(html)
