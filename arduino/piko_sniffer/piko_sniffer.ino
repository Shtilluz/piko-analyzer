/*
 * PIKO SmartControl Protocol Sniffer
 *
 * Hardware: Arduino Nano + 6N137 optocoupler
 * Signal input: D2 (INT0 — hardware interrupt)
 *
 * OPERATING MODE:
 *   RAW mode — transmit every edge with timestamp and duration.
 *   This is the correct first step when the protocol is unknown.
 *   Do NOT decode bytes or packets until timing patterns are understood.
 *
 * SERIAL OUTPUT FORMAT (115200 baud, one line per event):
 *   RAW:<timestamp_us>:<duration_us>:<level>
 *     timestamp_us — micros() at the moment the edge was detected
 *     duration_us  — duration of the previous half-period (before this edge)
 *     level        — current pin state after the edge (0 or 1)
 *
 *   STAT:<rx_count>:<dropped>   — sent every ~1 s from loop()
 *
 *   Commands received on Serial (newline-terminated):
 *     "RAW\n"   — switch to RAW mode (default)
 *     "STOP\n"  — pause output (ISR still runs, ring buffer fills)
 *     "RST\n"   — reset counters and clear buffer
 *     "BAUD:<n>\n" — not supported at runtime; change at compile time
 */

#define SIGNAL_PIN   2          // INT0 — must be 2 or 3 on Nano
#define SERIAL_BAUD  115200
#define RING_SIZE    512        // must be power of 2
#define RING_MASK    (RING_SIZE - 1)

// Minimum pulse width to store; shorter pulses are likely noise.
// Start conservative; lower if useful pulses are being dropped.
#define MIN_PULSE_US 10

// Gap that marks a frame boundary (no signal for this long).
// Set to 0 to disable frame boundary markers — we don't know the protocol yet.
#define FRAME_GAP_US 5000

// ---- Ring buffer --------------------------------------------------------

struct Edge {
    uint32_t timestamp_us;
    uint32_t duration_us;
    uint8_t  level;           // pin state AFTER this edge
};

volatile Edge    ring[RING_SIZE];
volatile uint16_t ring_head = 0;  // ISR writes here
volatile uint16_t ring_tail = 0;  // loop() reads here
volatile uint32_t dropped   = 0;  // edges dropped due to full buffer
volatile uint32_t rx_count  = 0;

// ---- ISR ----------------------------------------------------------------

volatile uint32_t prev_time = 0;
volatile bool     first_edge = true;

void IRAM_ATTR on_edge()
{
    uint32_t now   = micros();
    uint8_t  level = digitalRead(SIGNAL_PIN);

    uint32_t duration = 0;
    if (!first_edge) {
        duration = now - prev_time;
    }
    prev_time  = now;
    first_edge = false;

    if (!first_edge && duration < MIN_PULSE_US) {
        // Ignore noise pulses shorter than threshold.
        return;
    }

    uint16_t next_head = (ring_head + 1) & RING_MASK;
    if (next_head == ring_tail) {
        // Buffer full — drop and count.
        dropped++;
        return;
    }

    ring[ring_head].timestamp_us = now;
    ring[ring_head].duration_us  = duration;
    ring[ring_head].level        = level;
    ring_head = next_head;
    rx_count++;
}

// ---- State machine -------------------------------------------------------

enum Mode { MODE_RAW, MODE_STOP };
volatile Mode mode = MODE_RAW;

// ---- Setup ---------------------------------------------------------------

void setup()
{
    Serial.begin(SERIAL_BAUD);
    while (!Serial) { /* wait for USB CDC on Leonardo/Micro; Nano is instant */ }

    pinMode(SIGNAL_PIN, INPUT);  // 6N137 output is open-collector; add pull-up if needed
    // If the optocoupler output is open-drain, enable internal pull-up:
    // pinMode(SIGNAL_PIN, INPUT_PULLUP);

    attachInterrupt(digitalPinToInterrupt(SIGNAL_PIN), on_edge, CHANGE);

    Serial.println(F("PIKO:READY:RAW"));
}

// ---- Main loop -----------------------------------------------------------

static uint32_t last_stat_ms  = 0;
static uint32_t last_rx_logged = 0;

void loop()
{
    // ---- Process incoming commands ----
    if (Serial.available()) {
        String cmd = Serial.readStringUntil('\n');
        cmd.trim();
        if (cmd == "RAW") {
            mode = MODE_RAW;
            Serial.println(F("OK:RAW"));
        } else if (cmd == "STOP") {
            mode = MODE_STOP;
            Serial.println(F("OK:STOP"));
        } else if (cmd == "RST") {
            noInterrupts();
            ring_head  = 0;
            ring_tail  = 0;
            dropped    = 0;
            rx_count   = 0;
            first_edge = true;
            interrupts();
            Serial.println(F("OK:RST"));
        } else {
            Serial.print(F("ERR:UNKNOWN:"));
            Serial.println(cmd);
        }
    }

    // ---- Drain ring buffer ----
    while (ring_tail != ring_head) {
        // Snapshot one entry with interrupts briefly disabled.
        noInterrupts();
        Edge e = ring[ring_tail];
        ring_tail = (ring_tail + 1) & RING_MASK;
        interrupts();

        if (mode == MODE_RAW) {
            // Format: RAW:<timestamp>:<duration>:<level>
            Serial.print(F("RAW:"));
            Serial.print(e.timestamp_us);
            Serial.print(':');
            Serial.print(e.duration_us);
            Serial.print(':');
            Serial.println(e.level);
        }
        // In MODE_STOP we still drain the buffer to prevent overflow,
        // but we do not transmit.
    }

    // ---- Periodic statistics ----
    uint32_t now_ms = millis();
    if (now_ms - last_stat_ms >= 1000) {
        last_stat_ms = now_ms;

        noInterrupts();
        uint32_t snap_rx      = rx_count;
        uint32_t snap_dropped = dropped;
        interrupts();

        // Only send STAT if something happened since last report.
        if (snap_rx != last_rx_logged) {
            Serial.print(F("STAT:"));
            Serial.print(snap_rx);
            Serial.print(':');
            Serial.println(snap_dropped);
            last_rx_logged = snap_rx;
        }
    }
}
