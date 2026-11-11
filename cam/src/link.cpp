#include "link.h"
#include "robo.h"

static SemaphoreHandle_t tx_mutex;
static void (*cmd_cb)(const char *) = NULL;
static volatile uint32_t mic_req_until = 0;

void link_begin() {
  Serial.setRxBufferSize(32768);
  Serial.setTxBufferSize(16384);
  Serial.begin(LINK_BAUD);
  tx_mutex = xSemaphoreCreateMutex();
}

void link_send(char type, const void *data, size_t len) {
  if (len > 65535) len = 65535;
  uint8_t h[5] = {0xA5, 0x5A, (uint8_t)type, (uint8_t)(len & 0xFF), (uint8_t)(len >> 8)};
  uint8_t x = 0;
  const uint8_t *p = (const uint8_t *)data;
  for (size_t i = 0; i < len; i++) x ^= p[i];
  xSemaphoreTake(tx_mutex, portMAX_DELAY);
  Serial.write(h, 5);
  if (len) Serial.write(p, len);
  Serial.write(&x, 1);
  xSemaphoreGive(tx_mutex);
}

void link_log(const char *fmt, ...) {
  char b[256];
  va_list ap; va_start(ap, fmt);
  int n = vsnprintf(b, sizeof(b), fmt, ap);
  va_end(ap);
  if (n < 0) return;
  if (n >= (int)sizeof(b)) n = sizeof(b) - 1;
  while (n > 0 && (b[n - 1] == '\n' || b[n - 1] == '\r')) n--;
  link_send('L', b, n);
}

bool link_mic_on() { return (int32_t)(mic_req_until - millis()) > 0; }

static void handle(char type, uint8_t *d, size_t len) {
  switch (type) {
    case 'B': robo_spk_begin(); break;
    case 'A': robo_spk_push(d, len); break;
    case 'E': robo_spk_end(); break;
    case 'C': {
      d[len] = 0;
      const char *c = (const char *)d;
      if (!strncmp(c, "mic ", 4)) { mic_req_until = atoi(c + 4) ? millis() + 4000 : 0; break; }
      if (cmd_cb) cmd_cb(c);
      break;
    }
  }
}

static void rx_task(void *) {
  static uint8_t buf[4096 + 8];
  int st = 0; uint8_t type = 0; size_t len = 0, got = 0; uint8_t x = 0;
  static uint8_t tmp[512];
  while (true) {
    int a = Serial.available();
    if (a <= 0) { delay(1); continue; }
    int n = Serial.read(tmp, min(a, (int)sizeof(tmp)));
    for (int k = 0; k < n; k++) {
    uint8_t c = tmp[k];
    switch (st) {
      case 0: st = (c == 0xA5) ? 1 : 0; break;
      case 1: st = (c == 0x5A) ? 2 : (c == 0xA5 ? 1 : 0); break;
      case 2: type = c; st = 3; break;
      case 3: len = c; st = 4; break;
      case 4:
        len |= (size_t)c << 8; got = 0; x = 0;
        st = (len > 4096) ? 0 : (len ? 5 : 6);
        break;
      case 5:
        buf[got++] = c; x ^= c;
        if (got == len) st = 6;
        break;
      case 6:
        if ((uint8_t)c == x) handle(type, buf, len);
        st = 0;
        break;
    }
    }
  }
}

void link_start_rx(void (*on_cmd)(const char *cmd)) {
  cmd_cb = on_cmd;
  xTaskCreatePinnedToCore(rx_task, "link_rx", 4096, NULL, 8, NULL, 0);
}
