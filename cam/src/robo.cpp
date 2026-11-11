#include "robo.h"
#include "link.h"
#include <WiFi.h>
#include "driver/i2s.h"
#include "driver/gpio.h"
#include "soc/gpio_periph.h"
#include "soc/io_mux_reg.h"
#include "freertos/stream_buffer.h"
#include "lwip/sockets.h"
#include <fcntl.h>

// DMA do I2S ocupa RAM INTERNA (so ~300 KB no chip, disputada com Wi-Fi/lwIP).
// Com DMA grande a rede ficava sem memoria e parava de aceitar conexoes.
#define MIC_DMA_COUNT 6
#define MIC_DMA_LEN 256          // 6 x 256 quadros x 8 B = 12 KB (~96 ms)
#define MIC_READ_FRAMES 256
#define SPK_DMA_COUNT 6
#define SPK_DMA_LEN 256          // 6 x 256 x 4 B = 6 KB

// ================= servos =================
#define PAN_MIN 20
#define PAN_MAX 160
#define TILT_MIN 50
#define TILT_MAX 130
#define SERVO_CH_PAN 4    // canais 4/5 usam o timer 2 (camera usa canal/timer 0)
#define SERVO_CH_TILT 5

static volatile float pan_target = 90, tilt_target = 90;
static float pan_now = 90, tilt_now = 90;
static volatile bool tracking = true;
static volatile uint32_t gesture_until = 0;

// Velocidade maxima (graus/s) e freio suave. Historico (11/11/2026): 125 graus/s seguindo o rosto e
// 300 nos gestos ("agressivo") -> 20 e 45 ("ainda muito rapido") -> 10 e 20. Ajustavel sem regravar:
// comando "servovel <rastreio> <gesto>" (o robo.py manda a do --servo-vel ao conectar).
static volatile float vel_rastreio = 10.0f;  // seguindo o rosto
static volatile float vel_gesto = 20.0f;     // sim / nao / curioso / olhar
#define SERVO_FREIO 0.24f                    // fracao do erro por passo de 20 ms: desacelera ao chegar

// Cada passo do gesto dura o bastante para o servo chegar na velocidade de cima (12 graus a 20 graus/s
// = 0,6 s, e o freio no fim).
struct Key { int8_t dpan, dtilt; uint16_t ms; };
static const Key G_SIM[] = {{0, 12, 1500}, {0, -8, 1500}, {0, 12, 1500}, {0, -8, 1500}, {0, 0, 1500}};
static const Key G_NAO[] = {{-15, 0, 1500}, {15, 0, 1500}, {-15, 0, 1500}, {15, 0, 1500}, {0, 0, 1500}};
static const Key G_CURIOSO[] = {{0, 0, 100}, {12, -8, 2000}, {0, 0, 1800}};

void robo_set_servo_vel(float rastreio, float gesto) {
  vel_rastreio = constrain(rastreio, 1.0f, 200.0f);
  vel_gesto = constrain(gesto, 1.0f, 300.0f);
  LOGF("[servo] velocidade: seguir rosto %.0f graus/s, gestos %.0f graus/s", vel_rastreio, vel_gesto);
}
static const Key *g_keys = NULL;
static int g_len = 0;
static float g_base_pan, g_base_tilt;
static volatile bool g_restart = false;

static void servo_write(int ch, float deg) {
  uint32_t us = 500 + (uint32_t)(deg * 2000.0f / 180.0f);
  ledcWrite(ch, us * 16384 / 20000);
}

static void servo_task(void *) {
  int g_i = 0; uint32_t g_next = 0;
  while (true) {
    if (g_restart) { g_i = 0; g_next = 0; g_restart = false; }
    if (g_keys) {
      if (millis() >= g_next) {
        if (g_i >= g_len) { g_keys = NULL; pan_target = g_base_pan; tilt_target = g_base_tilt; }
        else {
          pan_target = constrain(g_base_pan + g_keys[g_i].dpan, PAN_MIN, PAN_MAX);
          tilt_target = constrain(g_base_tilt + g_keys[g_i].dtilt, TILT_MIN, TILT_MAX);
          g_next = millis() + g_keys[g_i].ms; g_i++;
        }
      }
    } else g_i = 0, g_next = 0;
    // Passo de 20 ms: uma fracao do que falta (freia ao chegar), nunca acima
    // da velocidade maxima.
    const float step = (g_keys ? vel_gesto : vel_rastreio) * 0.020f;
    pan_now += constrain((pan_target - pan_now) * SERVO_FREIO, -step, step);
    tilt_now += constrain((tilt_target - tilt_now) * SERVO_FREIO, -step, step);
    servo_write(SERVO_CH_PAN, pan_now);
    servo_write(SERVO_CH_TILT, tilt_now);
    delay(20);
  }
}

void robo_set_angles(int pan, int tilt) {
  pan_target = constrain(pan, PAN_MIN, PAN_MAX);
  tilt_target = constrain(tilt, TILT_MIN, TILT_MAX);
  LOGF("[servo] olhar: pan %d tilt %d (agora %d/%d)", (int)pan_target, (int)tilt_target, (int)pan_now, (int)tilt_now);
}
void robo_set_tracking(bool on) { tracking = on; }
bool robo_tracking() { return tracking; }
int robo_pan() { return (int)pan_now; }
int robo_tilt() { return (int)tilt_now; }

void robo_gesture(const char *name) {
  if (!strcmp(name, "centro")) { g_keys = NULL; robo_set_angles(90, 90); return; }
  const Key *k = NULL; int n = 0;
  if (!strcmp(name, "sim")) { k = G_SIM; n = sizeof(G_SIM) / sizeof(Key); }
  else if (!strcmp(name, "nao")) { k = G_NAO; n = sizeof(G_NAO) / sizeof(Key); }
  else if (!strcmp(name, "curioso")) { k = G_CURIOSO; n = sizeof(G_CURIOSO) / sizeof(Key); }
  if (!k) return;
  g_base_pan = pan_target; g_base_tilt = tilt_target;
  g_len = n; g_restart = true; g_keys = k;
  LOGF("[servo] gesto '%s' a %.0f graus/s (de pan %d tilt %d)", name, vel_gesto, (int)pan_now, (int)tilt_now);
}

void robo_track_face(int cx, int cy, int img_w, int img_h) {
  if (!tracking || g_keys) return;
  int ex = cx - img_w / 2, ey = cy - img_h / 2;
  if (abs(ex) > 25) pan_target = constrain(pan_target - PAN_DIR * ex * 0.04f, PAN_MIN, PAN_MAX);
  if (abs(ey) > 20) tilt_target = constrain(tilt_target + TILT_DIR * ey * 0.04f, TILT_MIN, TILT_MAX);
  // log no maximo a cada 2 s, e so se o alvo andou: seguir rosto chama isto a cada quadro
  static uint32_t ultimo_log = 0;
  static int log_pan = -1, log_tilt = -1;
  if (millis() - ultimo_log > 2000 && (abs((int)pan_target - log_pan) >= 3 || abs((int)tilt_target - log_tilt) >= 3)) {
    ultimo_log = millis(); log_pan = (int)pan_target; log_tilt = (int)tilt_target;
    LOGF("[servo] seguindo rosto: alvo pan %d tilt %d (agora %d/%d)", log_pan, log_tilt, (int)pan_now, (int)tilt_now);
  }
}

// ================= audio =================
static volatile bool speaking = false;
static volatile uint32_t mic_mute_until = 0;
bool robo_speaking() { return speaking; }

static void i2s_init() {
  i2s_config_t mic = {};
  mic.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX);
  mic.sample_rate = AUDIO_RATE;
  mic.bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT;
  mic.channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT;  // le os 2 canais e escolhe o que tem sinal
  mic.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  mic.dma_buf_count = MIC_DMA_COUNT;  // DMA fica na RAM interna: manter pequeno (folga vem do buffer na PSRAM)
  mic.dma_buf_len = MIC_DMA_LEN;
  i2s_driver_install(I2S_NUM_0, &mic, 0, NULL);
  i2s_pin_config_t mp = {};
  mp.mck_io_num = I2S_PIN_NO_CHANGE;
  mp.bck_io_num = MIC_SCK; mp.ws_io_num = MIC_WS;
  mp.data_out_num = I2S_PIN_NO_CHANGE; mp.data_in_num = MIC_SD;
  i2s_set_pin(I2S_NUM_0, &mp);

  i2s_config_t spk = {};
  spk.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX);
  spk.sample_rate = AUDIO_RATE;
  spk.bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT;
  spk.channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT;
  spk.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  spk.dma_buf_count = SPK_DMA_COUNT;
  spk.dma_buf_len = SPK_DMA_LEN;
  spk.tx_desc_auto_clear = true;
  i2s_driver_install(I2S_NUM_1, &spk, 0, NULL);
  i2s_pin_config_t sp = {};
  sp.mck_io_num = I2S_PIN_NO_CHANGE;
  sp.bck_io_num = SPK_BCLK; sp.ws_io_num = SPK_LRC;
  sp.data_out_num = SPK_DIN; sp.data_in_num = I2S_PIN_NO_CHANGE;
  i2s_set_pin(I2S_NUM_1, &sp);
  i2s_zero_dma_buffer(I2S_NUM_1);
  i2s_stop(I2S_NUM_1);      // amplificador comeca dormindo
}

// ---------- Microfone -> PC (porta 82) ----------
// Leitura do I2S e envio pela rede ficam em tarefas separadas, ligadas por um buffer de ~2 s na PSRAM.
// Assim o DMA (que ocupa RAM INTERNA, escassa) pode ser pequeno sem perder audio quando o Wi-Fi engasga.
#define MIC_RB_BYTES (AUDIO_RATE * 2 * 2)   // 2 s de PCM 16 bits
static StreamBufferHandle_t mic_rb = NULL;
static volatile bool mic_client_on = false;
static volatile uint32_t mic_read_samples = 0, mic_sent_bytes = 0, mic_dropped = 0, mic_send_fail = 0;
// acumulados desde o boot (para /stats)
static volatile uint32_t tot_read = 0, tot_sent_pkts = 0, tot_send_fail = 0, tot_dropped = 0, tot_spk_pkts = 0;
static volatile bool echo_test = false;
void robo_set_echo_test(bool on) { echo_test = on; }
bool robo_echo_test() { return echo_test; }
void robo_stats_json(char *b, size_t n) {
  snprintf(b, n, "\"mic_lidas\":%u,\"mic_pacotes\":%u,\"mic_falhas_envio\":%u,\"mic_estouros\":%u,"
                 "\"mic_ouvinte\":%d,\"spk_pacotes\":%u,\"falando\":%d,\"eco\":%d",
           tot_read, tot_sent_pkts, tot_send_fail, tot_dropped, mic_client_on, tot_spk_pkts, speaking, echo_test);
}

void robo_mic_stats(uint32_t *read_samples, uint32_t *sent_bytes, uint32_t *dropped) {
  *read_samples = mic_read_samples; *sent_bytes = mic_sent_bytes; *dropped = mic_dropped;
  if (mic_send_fail) LOGF("[mic] %u tentativas de envio falharam (fila do Wi-Fi cheia)\n", mic_send_fail);
  mic_read_samples = 0; mic_sent_bytes = 0; mic_dropped = 0; mic_send_fail = 0;
}

// ---------- filtro passa-altas (biquad, forma direta I) ----------
static float bq_b0, bq_b1, bq_b2, bq_a1, bq_a2;
static float bq_x1[2], bq_x2[2], bq_y1[2], bq_y2[2];
static void hp_design(float fc, float fs) {
  float w0 = 2.0f * PI * fc / fs, c = cosf(w0), al = sinf(w0) / (2.0f * 0.7071f), a0 = 1.0f + al;
  bq_b0 = (1.0f + c) / 2.0f / a0; bq_b1 = -(1.0f + c) / a0; bq_b2 = bq_b0;
  bq_a1 = -2.0f * c / a0; bq_a2 = (1.0f - al) / a0;
}
static inline float hp_biquad(int k, float x) {
  float y = bq_b0 * x + bq_b1 * bq_x1[k] + bq_b2 * bq_x2[k] - bq_a1 * bq_y1[k] - bq_a2 * bq_y2[k];
  bq_x2[k] = bq_x1[k]; bq_x1[k] = x; bq_y2[k] = bq_y1[k]; bq_y1[k] = y;
  return y;
}

static void mic_reader_task(void *) {
  hp_design(250.0f, AUDIO_RATE);
  int32_t *raw = (int32_t *)ps_malloc(MIC_READ_FRAMES * 2 * sizeof(int32_t));
  int16_t *out = (int16_t *)ps_malloc(MIC_READ_FRAMES * sizeof(int16_t));
  while (true) {
    size_t got = 0;
    i2s_read(I2S_NUM_0, raw, MIC_READ_FRAMES * 8, &got, portMAX_DELAY);
    int n = got / 8;
    mic_read_samples += n; tot_read += n;
    if (!mic_client_on && !link_mic_on()) continue;   // ninguem ouvindo: descarta
    int64_t el = 0, er = 0;
    for (int i = 0; i < n; i++) { el += abs(raw[2 * i] >> 16); er += abs(raw[2 * i + 1] >> 16); }
    int ch = (el >= er) ? 0 : 1;    // usa o canal que tem sinal (L/R do INMP441)
    bool mute = !echo_test && (speaking || millis() < mic_mute_until);
    // Passa-altas de 4a ordem (2 biquads Butterworth, 250 Hz): remove a deriva DC do INMP441 e o
    // zumbido da rede eletrica (120 Hz / 30 Hz medidos). Voz fica com qualidade "telefone" (otima p/ Whisper).
    for (int i = 0; i < n; i++) {
      float y = hp_biquad(1, hp_biquad(0, (float)(raw[2 * i + ch] >> 14)));
      int32_t s = mute ? 0 : (int32_t)y;
      out[i] = (int16_t)constrain(s, -32768, 32767);
    }
    if (xStreamBufferSend(mic_rb, out, n * 2, 0) < (size_t)(n * 2)) { xStreamBufferReset(mic_rb); mic_dropped++; tot_dropped++; }
  }
}

// Envio por UDP: o PC manda qualquer pacote ("HELLO") para a porta 82 a cada ~1 s; a placa responde
// para esse endereco com pacotes [seq uint32 LE][320 amostras PCM16 = 20 ms]. Sem esperar ACK (TCP
// desabava na rede corporativa com latencia de 100 ms a 1 s); pacote perdido = 20 ms de silencio.
#define MIC_PKT_SAMPLES 320
static void mic_sender_task(void *) {
  int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
  sockaddr_in me = {};
  me.sin_family = AF_INET; me.sin_port = htons(MIC_PORT); me.sin_addr.s_addr = htonl(INADDR_ANY);
  bind(sock, (sockaddr *)&me, sizeof(me));
  fcntl(sock, F_SETFL, O_NONBLOCK);
  sockaddr_in peer = {};
  uint32_t last_hello = 0, seq = 0;
  uint8_t *pkt = (uint8_t *)ps_malloc(4 + MIC_PKT_SAMPLES * 2);
  char hello[32];
  while (true) {
    sockaddr_in from; socklen_t fl = sizeof(from);
    while (recvfrom(sock, hello, sizeof(hello), 0, (sockaddr *)&from, &fl) > 0) {
      bool novo = !mic_client_on || from.sin_addr.s_addr != peer.sin_addr.s_addr || from.sin_port != peer.sin_port;
      peer = from; last_hello = millis();
      if (novo) {
        xStreamBufferReset(mic_rb); seq = 0; mic_client_on = true;
        LOGF("[mic] PC %s:%u ouvindo (UDP)\n", inet_ntoa(peer.sin_addr), ntohs(peer.sin_port));
      }
      fl = sizeof(from);
    }
    if (mic_client_on && millis() - last_hello > 3000) { mic_client_on = false; LOGF("[mic] PC parou de ouvir"); }
    bool usb_on = link_mic_on();
    if (!mic_client_on && !usb_on) { delay(20); continue; }
    size_t n = xStreamBufferReceive(mic_rb, pkt + 4, MIC_PKT_SAMPLES * 2, pdMS_TO_TICKS(50));
    if (!n) continue;
    if (usb_on) { link_send('M', pkt + 4, n); tot_sent_pkts++; }
    if (!mic_client_on) continue;
    memcpy(pkt, &seq, 4); seq++;
    // Se a fila do Wi-Fi estiver cheia (rede engasgou), espera e tenta de novo em vez de descartar
    for (int tent = 0; tent < 10; tent++) {
      if (sendto(sock, pkt, 4 + n, 0, (sockaddr *)&peer, sizeof(peer)) > 0) { mic_sent_bytes += n; tot_sent_pkts++; break; }
      mic_send_fail++; tot_send_fail++;
      delay(5);
    }
  }
}

// ---------- PC -> alto-falante (UDP, porta 83) ----------
// Pacotes [seq uint32 LE][PCM16 mono 16 kHz]. seq 0 = nova fala; seq 0xFFFFFFFF = fim da fala.
// Um "colchao" de 300 ms na PSRAM absorve os atrasos da rede antes de comecar a tocar.
#define SPK_RB_BYTES (AUDIO_RATE * 2 * 20)   // ate 20 s de fala
#define SPK_PREBUFFER (AUDIO_RATE * 2 * 3 / 10)
static StreamBufferHandle_t spk_rb = NULL;
static volatile bool spk_end = false;
static volatile uint32_t spk_last_rx = 0;

void robo_spk_begin() { xStreamBufferReset(spk_rb); spk_end = false; spk_last_rx = millis(); }
void robo_spk_push(const uint8_t *d, size_t len) {
  spk_last_rx = millis(); tot_spk_pkts++;
  xStreamBufferSend(spk_rb, d, len & ~1, pdMS_TO_TICKS(200));
}
void robo_spk_end() { spk_end = true; }

static void spk_rx_task(void *) {
  int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
  sockaddr_in me = {};
  me.sin_family = AF_INET; me.sin_port = htons(SPK_PORT); me.sin_addr.s_addr = htonl(INADDR_ANY);
  bind(sock, (sockaddr *)&me, sizeof(me));
  uint8_t *pkt = (uint8_t *)ps_malloc(1500);
  static const uint8_t zeros[640] = {0};
  uint32_t expected = 0;
  while (true) {
    int r = recv(sock, pkt, 1500, 0);
    if (r < 4) continue;
    uint32_t seq; memcpy(&seq, pkt, 4);
    spk_last_rx = millis(); tot_spk_pkts++;
    if (seq == 0xFFFFFFFF) { spk_end = true; continue; }
    if (seq == 0) { xStreamBufferReset(spk_rb); spk_end = false; expected = 0; }
    if (seq < expected) continue;  // duplicado/atrasado
    for (uint32_t gap = seq - expected; gap > 0 && gap <= 10; gap--)  // perdidos: preenche com silencio
      xStreamBufferSend(spk_rb, zeros, min(r - 4, (int)sizeof(zeros)), pdMS_TO_TICKS(100));
    expected = seq + 1;
    int len = (r - 4) & ~1;
    xStreamBufferSend(spk_rb, pkt + 4, len, pdMS_TO_TICKS(200));
  }
}

static void spk_play_task(void *) {
  int16_t *in = (int16_t *)ps_malloc(512 * sizeof(int16_t));
  int16_t *st = (int16_t *)ps_malloc(1024 * sizeof(int16_t));
  while (true) {
    size_t avail = xStreamBufferBytesAvailable(spk_rb);
    if (avail < SPK_PREBUFFER && !(spk_end && avail > 0)) { delay(10); continue; }
    i2s_start(I2S_NUM_1);   // acorda o amplificador (MAX98357A sai do repouso quando o clock volta)
    {                        // 80 ms de silencio: o amplificador estabiliza sem cortar a 1a silaba
      memset(st, 0, 1024 * sizeof(int16_t));
      size_t w;
      for (int k = 0; k < 5; k++) i2s_write(I2S_NUM_1, st, 256 * 4, &w, portMAX_DELAY);
    }
    LOGF("[spk] tocando audio");
    speaking = true;
    while (true) {
      size_t got = xStreamBufferReceive(spk_rb, in, 512 * sizeof(int16_t), pdMS_TO_TICKS(30));
      if (got < 2) {
        if (spk_end || millis() - spk_last_rx > 1500) break;   // fim da fala (ou PC sumiu)
        continue;
      }
      int n = got / 2;
      for (int i = 0; i < n; i++) {
        int16_t v = (int16_t)(in[i] * SPK_VOLUME);
        st[2 * i] = v; st[2 * i + 1] = v;
      }
      size_t w;
      i2s_write(I2S_NUM_1, st, n * 4, &w, portMAX_DELAY);
    }
    delay(SPK_DMA_COUNT * SPK_DMA_LEN * 1000 / AUDIO_RATE + 20);  // espera o DMA esvaziar
    i2s_zero_dma_buffer(I2S_NUM_1);
    i2s_stop(I2S_NUM_1);    // amplificador dorme (sem clock = repouso automatico, sem chiado)
    spk_end = false;
    speaking = false;
    mic_mute_until = millis() + 300;
    LOGF("[spk] fim");
  }
}

// Diagnostico dos servos (comando "servodiag"): le o PROPRIO pino do servo por 40 ms e mede a fracao
// do tempo em nivel alto. 90 graus = 1,5 ms a cada 20 ms = ~7,5%. Ligar so o buffer de ENTRADA do pino
// (PIN_INPUT_ENABLE) nao mexe na rota de saida: o PWM continua indo para o servo enquanto se mede.
// 0% = o sinal nao sai (software); ~7,5% = o sinal sai e o problema e ligacao/alimentacao (11/11/2026).
static void diag_pino(int pino, int canal, float graus) {
  PIN_INPUT_ENABLE(GPIO_PIN_MUX_REG[pino]);
  uint32_t alto = 0, total = 0, t0 = micros();
  while (micros() - t0 < 40000) { total++; if (gpio_get_level((gpio_num_t)pino)) alto++; }
  float esperado = (500.0f + graus * 2000.0f / 180.0f) / 20000.0f * 100.0f;
  LOGF("[servo] diag GPIO%d: nivel alto %.1f%% (esperado %.1f%% para %.0f graus) | ledc canal %d duty %u freq %u Hz",
       pino, total ? 100.0f * alto / total : 0.0f, esperado, graus, canal, ledcRead(canal), ledcReadFreq(canal));
}

void robo_servo_diag() {
  diag_pino(SERVO_PAN_PIN, SERVO_CH_PAN, pan_now);
  diag_pino(SERVO_TILT_PIN, SERVO_CH_TILT, tilt_now);
}

void robo_begin() {
  ledcSetup(SERVO_CH_PAN, 50, 14);
  ledcSetup(SERVO_CH_TILT, 50, 14);
  ledcAttachPin(SERVO_PAN_PIN, SERVO_CH_PAN);
  ledcAttachPin(SERVO_TILT_PIN, SERVO_CH_TILT);
  servo_write(SERVO_CH_PAN, 90);
  servo_write(SERVO_CH_TILT, 90);
  xTaskCreatePinnedToCore(servo_task, "servo", 4096, NULL, 3, NULL, 0);
  i2s_init();
}

void robo_start_servers() {
  static StaticStreamBuffer_t rb_struct, spk_struct;
  uint8_t *rb_storage = (uint8_t *)ps_malloc(MIC_RB_BYTES + 1);
  mic_rb = xStreamBufferCreateStatic(MIC_RB_BYTES, MIC_PKT_SAMPLES * 2, rb_storage, &rb_struct);
  uint8_t *spk_storage = (uint8_t *)ps_malloc(SPK_RB_BYTES + 1);
  spk_rb = xStreamBufferCreateStatic(SPK_RB_BYTES, 1, spk_storage, &spk_struct);
  xTaskCreatePinnedToCore(mic_reader_task, "mic_rd", 3072, NULL, 7, NULL, 0);
  xTaskCreatePinnedToCore(mic_sender_task, "mic_tx", 4096, NULL, 5, NULL, 0);
  xTaskCreatePinnedToCore(spk_rx_task, "spk_rx", 4096, NULL, 7, NULL, 0);
  xTaskCreatePinnedToCore(spk_play_task, "spk", 4096, NULL, 6, NULL, 0);
}
