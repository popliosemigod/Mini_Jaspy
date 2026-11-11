#include <Arduino.h>
#include <WiFi.h>
#include <WiFiMulti.h>
#include "esp_wifi.h"
static WiFiMulti wifi_multi;
#include <ESPmDNS.h>
#include <list>
#include "esp_camera.h"
#include "esp_http_server.h"
#include "img_converters.h"
#include "human_face_detect_msr01.hpp"
#include "human_face_detect_mnp01.hpp"
#include "face_recognition_112_v1_s8.hpp"
#include <LittleFS.h>
#include "robo.h"
#include "link.h"

// Redes Wi-Fi conhecidas (so para a pagina da camera; o robo funciona pelo USB sem Wi-Fi).
// As senhas ficam em wifi_redes.h, que NAO vai para o GitHub (.gitignore). Para criar:
// copie wifi_redes_exemplo.h para wifi_redes.h e preencha. Sem ele, compila com o exemplo
// (sem redes) e a placa usa so a rede propria "Robo-ESP32".
struct WifiCred { const char *ssid, *pass; };
#if __has_include("wifi_redes.h")
#include "wifi_redes.h"
#else
#warning "cam/src/wifi_redes.h nao existe: usando wifi_redes_exemplo.h (sem redes conhecidas)"
#include "wifi_redes_exemplo.h"
#endif

const char *NAME_KNOWN = "Rapaz bonito e inteligente";
const char *NAME_UNKNOWN = "Creatura";
// Semelhanca minima (de -1 a 1) para considerar que e o rapaz. Maior = mais rigoroso.
const float MATCH_THRESHOLD = 0.55f;

// Pinagem ESP32-S3-EYE / Freenove ESP32-S3 WROOM CAM
#define PWDN_GPIO_NUM  -1
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM  15
#define SIOD_GPIO_NUM  4
#define SIOC_GPIO_NUM  5
#define Y9_GPIO_NUM    16
#define Y8_GPIO_NUM    17
#define Y7_GPIO_NUM    18
#define Y6_GPIO_NUM    12
#define Y5_GPIO_NUM    10
#define Y4_GPIO_NUM    8
#define Y3_GPIO_NUM    9
#define Y2_GPIO_NUM    11
#define VSYNC_GPIO_NUM 6
#define HREF_GPIO_NUM  7
#define PCLK_GPIO_NUM  13

#define IMG_W 320
#define IMG_H 240

// Cores RGB565 com bytes trocados (formato do buffer da camera)
#define C_GREEN 0xE007
#define C_RED   0x00F8
#define C_WHITE 0xFFFF
#define C_BLACK 0x0000

// ---------- fotos de cadastro embutidas no firmware ----------
#define FACE_SYM(n) extern const uint8_t _binary_data_face##n##_bin_start[];
FACE_SYM(0) FACE_SYM(1) FACE_SYM(2) FACE_SYM(3) FACE_SYM(4)
FACE_SYM(5) FACE_SYM(6) FACE_SYM(7) FACE_SYM(8)
static const uint8_t *ENROLL_PHOTOS[] = {
  _binary_data_face0_bin_start, _binary_data_face1_bin_start, _binary_data_face2_bin_start,
  _binary_data_face3_bin_start, _binary_data_face4_bin_start, _binary_data_face5_bin_start,
  _binary_data_face6_bin_start, _binary_data_face7_bin_start, _binary_data_face8_bin_start};
#define N_PHOTOS (sizeof(ENROLL_PHOTOS) / sizeof(ENROLL_PHOTOS[0]))
#define N_TEST 3  // as ultimas 3 fotos sao usadas como autoteste antes de serem cadastradas

// ---------- modelos de IA ----------
static HumanFaceDetectMSR01 *det1;
static HumanFaceDetectMNP01 *det2;
static FaceRecognition112V1S8 *recognizer;

// ---------- fonte 5x7 (somente os caracteres usados) ----------
static const char FONT_CHARS[] = " 0123456789%.CRabeglinoprtuz";
static const uint8_t FONT[][5] = {
  {0x00,0x00,0x00,0x00,0x00}, // ' '
  {0x3E,0x51,0x49,0x45,0x3E}, {0x00,0x42,0x7F,0x40,0x00}, {0x42,0x61,0x51,0x49,0x46},
  {0x21,0x41,0x45,0x4B,0x31}, {0x18,0x14,0x12,0x7F,0x10}, {0x27,0x45,0x45,0x45,0x39},
  {0x3C,0x4A,0x49,0x49,0x30}, {0x01,0x71,0x09,0x05,0x03}, {0x36,0x49,0x49,0x49,0x36},
  {0x06,0x49,0x49,0x29,0x1E}, // 0-9
  {0x23,0x13,0x08,0x64,0x62}, // %
  {0x00,0x60,0x60,0x00,0x00}, // .
  {0x3E,0x41,0x41,0x41,0x22}, // C
  {0x7F,0x09,0x19,0x29,0x46}, // R
  {0x20,0x54,0x54,0x54,0x78}, // a
  {0x7F,0x48,0x44,0x44,0x38}, // b
  {0x38,0x54,0x54,0x54,0x18}, // e
  {0x0C,0x52,0x52,0x52,0x3E}, // g
  {0x00,0x41,0x7F,0x40,0x00}, // l
  {0x00,0x44,0x7D,0x40,0x00}, // i
  {0x7C,0x08,0x04,0x04,0x78}, // n
  {0x38,0x44,0x44,0x44,0x38}, // o
  {0x7C,0x14,0x14,0x14,0x08}, // p
  {0x7C,0x08,0x04,0x04,0x08}, // r
  {0x04,0x3F,0x44,0x40,0x20}, // t
  {0x3C,0x40,0x40,0x20,0x7C}, // u
  {0x44,0x64,0x54,0x4C,0x44}, // z
};

static void fill_rect(uint16_t *img, int x1, int y1, int x2, int y2, uint16_t c) {
  x1 = max(0, x1); y1 = max(0, y1); x2 = min(IMG_W - 1, x2); y2 = min(IMG_H - 1, y2);
  for (int y = y1; y <= y2; y++)
    for (int x = x1; x <= x2; x++) img[y * IMG_W + x] = c;
}

static void draw_box(uint16_t *img, int x1, int y1, int x2, int y2, uint16_t c) {
  for (int t = 0; t < 2; t++) {
    fill_rect(img, x1 + t, y1 + t, x2 - t, y1 + t, c);
    fill_rect(img, x1 + t, y2 - t, x2 - t, y2 - t, c);
    fill_rect(img, x1 + t, y1 + t, x1 + t, y2 - t, c);
    fill_rect(img, x2 - t, y1 + t, x2 - t, y2 - t, c);
  }
}

// Escreve texto com fundo; posiciona acima da caixa (ou abaixo se nao couber)
static void draw_label(uint16_t *img, const char *txt, int bx, int by_top, int by_bot, uint16_t bg) {
  int len = strlen(txt);
  int scale = (len * 6 * 2 + 4 <= IMG_W) ? 2 : 1;
  int w = len * 6 * scale + 4, h = 7 * scale + 4;
  int x = constrain(bx, 0, IMG_W - w);
  int y = by_top - h;
  if (y < 0) y = min(by_bot + 1, IMG_H - h);
  fill_rect(img, x, y, x + w - 1, y + h - 1, bg);
  for (int i = 0; i < len; i++) {
    const char *p = strchr(FONT_CHARS, txt[i]);
    if (!p) continue;
    const uint8_t *g = FONT[p - FONT_CHARS];
    for (int col = 0; col < 5; col++)
      for (int row = 0; row < 7; row++)
        if (g[col] & (1 << row))
          fill_rect(img, x + 2 + (i * 6 + col) * scale, y + 2 + row * scale,
                    x + 2 + (i * 6 + col) * scale + scale - 1, y + 2 + row * scale + scale - 1, C_WHITE);
  }
}

// ---------- cadastro a partir das fotos ----------
static bool detect_largest(uint16_t *img, std::vector<int> &kp) {
  std::vector<int> shape = {IMG_H, IMG_W, 3};
  auto &cand = det1->infer(img, shape);
  auto &res = det2->infer(img, shape, cand);
  int best = -1;
  for (auto &r : res) {
    int area = (r.box[2] - r.box[0]) * (r.box[3] - r.box[1]);
    if (area > best) { best = area; kp = r.keypoint; }
  }
  return best > 0;
}

static void mirror(uint16_t *dst, const uint16_t *src) {
  for (int y = 0; y < IMG_H; y++)
    for (int x = 0; x < IMG_W; x++) dst[y * IMG_W + x] = src[y * IMG_W + (IMG_W - 1 - x)];
}

static int enroll_image(uint16_t *img) {
  std::vector<int> kp;
  if (!detect_largest(img, kp)) return 0;
  recognizer->enroll_id(img, {IMG_H, IMG_W, 3}, kp, NAME_KNOWN, false);
  return 1;
}

static void enroll_from_photos() {
  size_t sz = IMG_W * IMG_H * 2;
  uint16_t *img = (uint16_t *)ps_malloc(sz);
  uint16_t *flip = (uint16_t *)ps_malloc(sz);
  int ok = 0;
  LOGF("Cadastrando o rosto a partir das fotos...");
  for (int i = 0; i < (int)N_PHOTOS - N_TEST; i++) {
    memcpy(img, ENROLL_PHOTOS[i], sz);
    mirror(flip, img);
    int a = enroll_image(img), b = enroll_image(flip);
    LOGF("  foto %d: %s / espelhada: %s\n", i, a ? "OK" : "sem rosto", b ? "OK" : "sem rosto");
    ok += a + b;
  }
  LOGF("Autoteste (fotos que o modelo ainda nao viu):");
  for (int i = N_PHOTOS - N_TEST; i < (int)N_PHOTOS; i++) {
    memcpy(img, ENROLL_PHOTOS[i], sz);
    std::vector<int> kp;
    if (!detect_largest(img, kp)) { LOGF("  foto %d: sem rosto\n", i); continue; }
    face_info_t r = recognizer->recognize(img, {IMG_H, IMG_W, 3}, kp);
    LOGF("  foto %d: semelhanca %.2f -> %s\n", i, r.similarity,
                  r.similarity >= MATCH_THRESHOLD ? NAME_KNOWN : NAME_UNKNOWN);
  }
  for (int i = N_PHOTOS - N_TEST; i < (int)N_PHOTOS; i++) {
    memcpy(img, ENROLL_PHOTOS[i], sz);
    mirror(flip, img);
    ok += enroll_image(img) + enroll_image(flip);
  }
  LOGF("Cadastro concluido: %d imagens de rosto (%d ids)\n", ok, recognizer->get_enrolled_id_num());
  free(img); free(flip);
}

// ---------- rostos aprendidos pela camera ----------
// Quem aparece como "Creatura" diz o nome; o robo guarda amostras do rosto (o vetor que o modelo
// tira de cada rosto) e passa a reconhecer a pessoa pelo nome. Depois, sempre que reconhece alguem
// com certeza media, junta mais uma amostra: aprende aos poucos, pela propria camera.
// As amostras ficam na PSRAM (a RAM interna e o recurso critico, ver relatorio 6.3) e no arquivo
// /rostos.bin da particao spiffs, que sobrevive a desligar e a regravar o firmware.
#define APR_MAX 80                 // amostras no total (80 x 2 KB na PSRAM)
#define APR_POR_PESSOA 15          // teto por pessoa: a mais antiga da lugar a nova
#define APR_INICIAIS 5             // amostras tiradas ao aprender um nome
#define APR_INTERVALO_MS 600       // entre uma amostra e outra ao aprender
#define APR_PRAZO_MS 30000         // tempo para conseguir as amostras iniciais
#define APR_AUTO_MIN 0.60f         // reconhecido com certeza media: vale mais uma amostra
#define APR_AUTO_MAX 0.80f         // acima disso a amostra nao ensina nada novo
#define APR_AUTO_INTERVALO_MS 30000
#define APR_ROSTO_MIN_PX 50        // rosto menor que isso (largura) nao serve de amostra
#define APR_NOME_MAX 32
#define APR_DIM_MAX 512
#define APR_ARQUIVO "/rostos.bin"

struct Amostra { char nome[APR_NOME_MAX]; float emb[APR_DIM_MAX]; };
static Amostra *apr = NULL;
static int apr_n = 0, apr_dim = 0;
static SemaphoreHandle_t apr_mutex;
static char apr_aprendendo[APR_NOME_MAX] = "";  // "" = nao esta aprendendo ninguem
static int apr_faltam = 0, apr_tiradas = 0;
static uint32_t apr_ultima = 0, apr_inicio = 0, apr_auto_ultima = 0, apr_mudou_em = 0;
static volatile bool apr_sujo = false;          // precisa gravar o arquivo
static bool fs_ok = false;

// Nome seguro para JSON e arquivo: sem aspas/barras/controle, ate 31 bytes sem partir UTF-8.
static void apr_limpa_nome(char *dst, const char *src) {
  int k = 0;
  while (*src == ' ') src++;
  for (; *src && k < APR_NOME_MAX - 1; src++) {
    unsigned char ch = *src;
    if (ch < 32 || ch == '"' || ch == '\\' || ch == ';') continue;
    dst[k++] = ch;
  }
  // nao corta caractere acentuado ao meio: se o ultimo ficou incompleto, sai inteiro
  int j = k - 1;
  while (j > 0 && ((unsigned char)dst[j] & 0xC0) == 0x80) j--;
  if (j >= 0) {
    unsigned char lead = dst[j];
    int len = lead < 0x80 ? 1 : (lead >> 5) == 6 ? 2 : (lead >> 4) == 14 ? 3 : 4;
    if (j + len > k) k = j;
  }
  while (k > 0 && dst[k - 1] == ' ') k--;
  dst[k] = 0;
}

static int apr_conta(const char *nome) {
  int c = 0;
  for (int i = 0; i < apr_n; i++) if (!strcasecmp(apr[i].nome, nome)) c++;
  return c;
}

static float apr_cosseno(const float *a, const float *b, int dim) {
  float ab = 0, aa = 0, bb = 0;
  for (int i = 0; i < dim; i++) { ab += a[i] * b[i]; aa += a[i] * a[i]; bb += b[i] * b[i]; }
  return (aa > 0 && bb > 0) ? ab / sqrtf(aa * bb) : -1.0f;
}

// Amostra mais parecida com o rosto (-1 se nao ha amostras). Chamar com apr_mutex.
static int apr_melhor(const float *e, int dim, float *sim) {
  int bi = -1; *sim = -1.0f;
  if (dim != apr_dim) return -1;
  for (int i = 0; i < apr_n; i++) {
    float s = apr_cosseno(e, apr[i].emb, dim);
    if (s > *sim) { *sim = s; bi = i; }
  }
  return bi;
}

// Junta uma amostra. Com a pessoa no teto, a amostra mais antiga dela da lugar. Chamar com apr_mutex.
static bool apr_adiciona(const char *nome, const float *e, int dim) {
  if (!apr || dim > APR_DIM_MAX || (apr_dim && dim != apr_dim)) return false;
  int alvo = -1;
  if (apr_conta(nome) >= APR_POR_PESSOA) {
    for (int i = 0; i < apr_n; i++) if (!strcasecmp(apr[i].nome, nome)) { alvo = i; break; }
    memmove(&apr[alvo], &apr[alvo + 1], (apr_n - alvo - 1) * sizeof(Amostra));
    alvo = apr_n - 1;
  } else if (apr_n < APR_MAX) {
    alvo = apr_n++;
  } else {
    LOGF("[rosto] memoria de rostos cheia (%d amostras): use 'esquecer <nome>'", APR_MAX);
    return false;
  }
  apr_dim = dim;
  strncpy(apr[alvo].nome, nome, APR_NOME_MAX - 1);
  apr[alvo].nome[APR_NOME_MAX - 1] = 0;
  memcpy(apr[alvo].emb, e, dim * sizeof(float));
  apr_sujo = true; apr_mudou_em = millis();
  return true;
}

static int apr_esquece(const char *nome) {
  xSemaphoreTake(apr_mutex, portMAX_DELAY);
  int k = 0, tirou = 0;
  for (int i = 0; i < apr_n; i++) {
    if (!strcasecmp(apr[i].nome, nome)) { tirou++; continue; }
    if (k != i) apr[k] = apr[i];
    k++;
  }
  apr_n = k;
  if (tirou) { apr_sujo = true; apr_mudou_em = millis(); }
  xSemaphoreGive(apr_mutex);
  return tirou;
}

static void apr_grava() {
  if (!fs_ok) return;
  // copia e solta o mutex: a escrita na flash leva segundos e a camera nao pode esperar
  xSemaphoreTake(apr_mutex, portMAX_DELAY);
  int n = apr_n, dim = apr_dim;
  Amostra *copia = n ? (Amostra *)ps_malloc(n * sizeof(Amostra)) : NULL;
  if (copia) memcpy(copia, apr, n * sizeof(Amostra));
  apr_sujo = false;
  xSemaphoreGive(apr_mutex);
  if (n && !copia) { apr_sujo = true; return; }
  File f = LittleFS.open(APR_ARQUIVO, "w");
  if (!f) { apr_sujo = true; free(copia); return; }
  f.write((const uint8_t *)"ROS1", 4);
  f.write((const uint8_t *)&dim, 4);
  f.write((const uint8_t *)&n, 4);
  for (int i = 0; i < n; i++) {
    f.write((const uint8_t *)copia[i].nome, APR_NOME_MAX);
    f.write((const uint8_t *)copia[i].emb, dim * sizeof(float));
  }
  f.close();
  free(copia);
  LOGF("[rosto] %d amostras gravadas na flash", n);
}

static void apr_carrega() {
  apr = (Amostra *)ps_malloc(APR_MAX * sizeof(Amostra));
  fs_ok = LittleFS.begin(true);  // particao spiffs; formata na primeira vez
  if (!apr || !fs_ok) { LOGF("[rosto] sem memoria para rostos aprendidos (psram=%d fs=%d)", apr != NULL, fs_ok); return; }
  File f = LittleFS.open(APR_ARQUIVO, "r");
  if (!f) { LOGF("[rosto] nenhum rosto aprendido ainda"); return; }
  char mag[4]; int dim = 0, n = 0;
  if (f.read((uint8_t *)mag, 4) == 4 && !memcmp(mag, "ROS1", 4) && f.read((uint8_t *)&dim, 4) == 4 &&
      f.read((uint8_t *)&n, 4) == 4 && dim > 0 && dim <= APR_DIM_MAX && n >= 0 && n <= APR_MAX) {
    int lidas = 0;
    for (; lidas < n; lidas++) {
      if (f.read((uint8_t *)apr[lidas].nome, APR_NOME_MAX) != APR_NOME_MAX) break;
      if (f.read((uint8_t *)apr[lidas].emb, dim * sizeof(float)) != dim * sizeof(float)) break;
      apr[lidas].nome[APR_NOME_MAX - 1] = 0;
    }
    apr_n = lidas; apr_dim = dim;
  }
  f.close();
  String quem = "";
  for (int i = 0; i < apr_n; i++)
    if (quem.indexOf(String(apr[i].nome) + " (") < 0) quem += String(apr[i].nome) + " (" + apr_conta(apr[i].nome) + ") ";
  LOGF("[rosto] %d amostras aprendidas carregadas: %s", apr_n, apr_n ? quem.c_str() : "-");
}

// Comecar a aprender um nome (comando "aprender <nome>"). A camera fica acordada ate terminar.
void vision_wake(uint32_t ms);
static void apr_comeca(const char *bruto) {
  char nome[APR_NOME_MAX];
  apr_limpa_nome(nome, bruto);
  if (!nome[0] || !strcasecmp(nome, NAME_UNKNOWN)) { LOGF("[rosto] nome invalido para aprender"); return; }
  xSemaphoreTake(apr_mutex, portMAX_DELAY);
  strcpy(apr_aprendendo, nome);
  apr_faltam = APR_INICIAIS; apr_tiradas = 0; apr_inicio = millis(); apr_ultima = 0;
  xSemaphoreGive(apr_mutex);
  vision_wake(APR_PRAZO_MS + 2000);
  LOGF("[rosto] aprendendo '%s': olhe para a camera (%d amostras)", nome, APR_INICIAIS);
}

// ---------- ultimo quadro processado (compartilhado entre tarefas) ----------
static SemaphoreHandle_t frame_mutex;
static uint8_t *last_jpg = NULL;
static size_t last_jpg_len = 0;
static volatile uint32_t frame_id = 0;
static volatile float fps = 0;
static char faces_json[1024] = "{\"faces\":0,\"fps\":0,\"list\":[]}";

// ---------- energia da camera ----------
// A camera + IA de rosto (7,5 quadros/s, JPEG, PSRAM, clock de 20 MHz) atrapalhava o Wi-Fi.
// Por padrao ela DORME (desligada de verdade) e acorda sob demanda: /wake, /capture ou stream aberto.
static volatile int vision_always_on = 0;        // /config?vision=1 deixa sempre ligada
static volatile uint32_t vision_wake_until = 0;  // millis() ate quando deve ficar acordada
static volatile int stream_clients = 0;
static volatile bool camera_on = false;
static volatile int cam_xclk_mhz = 20;           // /config?xclk=10 reduz interferencia
static volatile bool cam_reinit = false;
static volatile uint32_t cam_wakeups = 0;
#define VISION_IDLE_MS 20000
static bool init_camera();

void vision_wake(uint32_t ms) {
  uint32_t until = millis() + ms;
  if ((int32_t)(until - vision_wake_until) > 0) vision_wake_until = until;
}
static bool vision_needed() {
  return vision_always_on || stream_clients > 0 || (int32_t)(vision_wake_until - millis()) > 0;
}

static void vision_task(void *) {
  uint32_t t_last = millis();
  String last_report = "";

  while (true) {
    if (cam_reinit && camera_on) { esp_camera_deinit(); camera_on = false; cam_reinit = false; }
    if (!vision_needed()) {
      if (camera_on) { esp_camera_deinit(); camera_on = false; LOGF("[camera] dormindo"); }
      fps = 0;
      delay(50);
      continue;
    }
    if (!camera_on) {
      uint32_t t0 = millis();
      if (!init_camera()) { delay(500); continue; }
      camera_on = true; cam_wakeups++;
      LOGF("[camera] acordou em %lu ms\n", millis() - t0);
    }
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) { delay(10); continue; }
    uint16_t *img = (uint16_t *)fb->buf;
    std::vector<int> shape = {(int)fb->height, (int)fb->width, 3};

    auto &cand = det1->infer(img, shape);
    auto &res = det2->infer(img, shape, cand);

    String list = "", report = "", names_now = "";
    int n = 0, best_area = 0, best_cx = 0, best_cy = 0;
    // do maior rosto: o vetor (para aprender), quem e e com que certeza
    static float *emb_maior = (float *)ps_malloc(APR_DIM_MAX * sizeof(float));  // PSRAM: a interna e curta
    int dim_maior = 0, larg_maior = 0;
    char nome_maior[APR_NOME_MAX] = "";
    float sim_maior = -1.0f;
    bool maior_aprendido = false;
    for (auto &r : res) {
      int area = (r.box[2] - r.box[0]) * (r.box[3] - r.box[1]);
      face_info_t id;
      id.id = -1; id.similarity = -1.0f;  // sem rostos cadastrados (fotos ausentes): todo mundo e "Creatura"
      int dim = 0;
      float sim_apr = -1.0f;
      char name[APR_NOME_MAX];
      strcpy(name, NAME_UNKNOWN);
      bool learned = false;
      if (recognizer->get_enrolled_id_num() > 0) {
        id = recognizer->recognize(img, shape, r.keypoint);
        // o vetor deste rosto (o modelo guarda o da ultima imagem reconhecida)
        Tensor<float> &e = recognizer->get_face_emb(-1);
        dim = e.get_size();
        if (dim > 0 && dim <= APR_DIM_MAX) {
          xSemaphoreTake(apr_mutex, portMAX_DELAY);
          int bi = apr_melhor(e.element, dim, &sim_apr);
          if (bi >= 0 && sim_apr >= MATCH_THRESHOLD && sim_apr >= id.similarity) {
            strcpy(name, apr[bi].nome);
            learned = true;
          }
          xSemaphoreGive(apr_mutex);
          if (area > best_area) memcpy(emb_maior, e.element, dim * sizeof(float));
        } else dim = 0;
      }
      float sim = learned ? sim_apr : id.similarity;
      bool known = learned || id.similarity >= MATCH_THRESHOLD;
      if (!learned && known) strcpy(name, NAME_KNOWN);
      if (!known) sim = max(id.similarity, sim_apr);
      if (area > best_area) {
        best_area = area; best_cx = (r.box[0] + r.box[2]) / 2; best_cy = (r.box[1] + r.box[3]) / 2;
        dim_maior = dim; larg_maior = r.box[2] - r.box[0];
        strcpy(nome_maior, name); sim_maior = sim; maior_aprendido = learned;
      }
      uint16_t color = known ? C_GREEN : C_RED;
      int x1 = r.box[0], y1 = r.box[1], x2 = r.box[2], y2 = r.box[3];
      draw_box(img, x1, y1, x2, y2, color);
      // a fonte da imagem so tem as letras dos dois nomes fixos; nomes aprendidos vao no JSON
      if (!learned) draw_label(img, name, x1, y1, y2, color);
      if (n) { list += ","; report += ", "; }
      list += "{\"name\":\"" + String(name) + "\",\"sim\":" + String(sim, 2) + "}";
      report += String(name) + " (" + String(sim, 2) + ")";
      names_now += String(name) + ";";
      n++;
    }

    // Aprender: so com UM rosto no quadro (para nao guardar a pessoa errada) e grande o bastante.
    uint32_t agora = millis();
    xSemaphoreTake(apr_mutex, portMAX_DELAY);
    if (apr_aprendendo[0]) {
      if (n == 1 && dim_maior > 0 && larg_maior >= APR_ROSTO_MIN_PX && agora - apr_ultima >= APR_INTERVALO_MS) {
        if (apr_adiciona(apr_aprendendo, emb_maior, dim_maior)) {
          apr_ultima = agora; apr_tiradas++; apr_faltam--;
          LOGF("[rosto] amostra %d de %d de '%s'", apr_tiradas, APR_INICIAIS, apr_aprendendo);
        }
      }
      if (apr_faltam <= 0 || agora - apr_inicio > APR_PRAZO_MS) {
        if (apr_tiradas) LOGF("[rosto] aprendi '%s' (%d amostras)", apr_aprendendo, apr_conta(apr_aprendendo));
        else LOGF("[rosto] nao consegui aprender '%s': nenhum rosto sozinho e de frente em %d s",
                  apr_aprendendo, APR_PRAZO_MS / 1000);
        apr_aprendendo[0] = 0; apr_faltam = 0;
      }
    } else if (n == 1 && maior_aprendido && dim_maior > 0 && larg_maior >= APR_ROSTO_MIN_PX &&
               sim_maior >= APR_AUTO_MIN && sim_maior < APR_AUTO_MAX &&
               agora - apr_auto_ultima >= APR_AUTO_INTERVALO_MS) {
      // reconhecido, mas com certeza media: este rosto ensina algo novo (outro angulo, outra luz)
      if (apr_adiciona(nome_maior, emb_maior, dim_maior)) {
        apr_auto_ultima = agora;
        LOGF("[rosto] mais uma amostra de '%s' (certeza %.2f, agora %d)", nome_maior, sim_maior, apr_conta(nome_maior));
      }
    }
    xSemaphoreGive(apr_mutex);

    if (best_area > 0) robo_track_face(best_cx, best_cy, fb->width, fb->height);

    uint8_t *jpg = NULL; size_t jlen = 0;
    bool ok = fmt2jpg(fb->buf, fb->len, fb->width, fb->height, fb->format, 75, &jpg, &jlen);
    esp_camera_fb_return(fb);

    uint32_t now = millis();
    fps = fps * 0.8f + 0.2f * (1000.0f / max<uint32_t>(1, now - t_last));
    t_last = now;

    xSemaphoreTake(frame_mutex, portMAX_DELAY);
    if (ok) { free(last_jpg); last_jpg = jpg; last_jpg_len = jlen; frame_id++; }
    snprintf(faces_json, sizeof(faces_json),
             "{\"faces\":%d,\"fps\":%.1f,\"list\":[%s],\"pan\":%d,\"tilt\":%d,\"track\":%d,\"speaking\":%d,"
             "\"aprendendo\":\"%s\",\"faltam\":%d}",
             n, fps, list.c_str(), robo_pan(), robo_tilt(), robo_tracking(), robo_speaking(),
             apr_aprendendo, apr_faltam);
    xSemaphoreGive(frame_mutex);

    // so loga quando muda quem esta na frente da camera
    String names = n ? names_now : String("nenhum rosto");
    if (names != last_report) {
      LOGF("Rostos: %s\n", n ? report.c_str() : "nenhum rosto");
      last_report = names;
    }
  }
}

// ---------- servidor web ----------
static const char INDEX_HTML[] PROGMEM = R"HTML(<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Camera - Reconhecimento</title>
<style>html,body{margin:0;height:100%;background:#000;font-family:sans-serif}
img{width:100%;height:100%;object-fit:contain;display:block}
#b{position:fixed;top:10px;left:10px;padding:6px 12px;border-radius:8px;
background:rgba(0,0,0,.65);color:#fff;font-size:17px;line-height:1.5}
.k{color:#4ade80;font-weight:bold}.u{color:#f87171;font-weight:bold}</style></head>
<body><img id="v"><div id="b">...</div><script>
const v=document.getElementById('v'),b=document.getElementById('b');
const S='http://'+location.hostname+':81/stream';
v.src=S;v.onerror=()=>setTimeout(()=>{v.src=S+'?'+Date.now()},1000);
setInterval(()=>fetch('/faces').then(r=>r.json()).then(j=>{
 let h=j.list.length?j.list.map(f=>'<span class="'+(f.name=='Creatura'?'u':'k')+'">'+f.name+'</span> '
  +Math.round(f.sim*100)+'%').join('<br>'):'Nenhum rosto';
 b.innerHTML=h+'<br><small>'+j.fps.toFixed(1)+' fps</small>';}).catch(()=>{}),400);
</script></body></html>)HTML";

#define BOUNDARY "frame"
static const char *STREAM_TYPE = "multipart/x-mixed-replace;boundary=" BOUNDARY;
static const char *STREAM_SEP = "\r\n--" BOUNDARY "\r\n";
static const char *STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

static esp_err_t index_handler(httpd_req_t *req) {
  httpd_resp_set_type(req, "text/html");
  return httpd_resp_send(req, INDEX_HTML, HTTPD_RESP_USE_STRLEN);
}

static esp_err_t faces_handler(httpd_req_t *req) {
  char buf[sizeof(faces_json)];
  xSemaphoreTake(frame_mutex, portMAX_DELAY);
  strcpy(buf, faces_json);
  xSemaphoreGive(frame_mutex);
  httpd_resp_set_type(req, "application/json");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  return httpd_resp_send(req, buf, HTTPD_RESP_USE_STRLEN);
}

// Foto atual (com as caixas e nomes desenhados) para o "cerebro" no PC
// Acorda a camera (se precisar), espera um quadro novo e devolve uma copia do JPEG (liberar com free)
static size_t grab_fresh_jpeg(uint8_t **out) {
  bool was_on = camera_on;
  uint32_t id0 = frame_id;
  vision_wake(VISION_IDLE_MS);
  // camera estava dormindo: espera ligar e 3 quadros (exposicao automatica se ajustar)
  uint32_t need = was_on ? 1 : 3, t0 = millis();
  while (frame_id - id0 < need && millis() - t0 < 5000) delay(20);
  xSemaphoreTake(frame_mutex, portMAX_DELAY);
  size_t len = last_jpg_len;
  uint8_t *copy = len ? (uint8_t *)ps_malloc(len) : NULL;
  if (copy) memcpy(copy, last_jpg, len);
  xSemaphoreGive(frame_mutex);
  *out = copy;
  return copy ? len : 0;
}

static esp_err_t capture_handler(httpd_req_t *req) {
  uint8_t *copy = NULL;
  size_t len = grab_fresh_jpeg(&copy);
  if (!copy) { httpd_resp_send_500(req); return ESP_FAIL; }
  httpd_resp_set_type(req, "image/jpeg");
  esp_err_t r = httpd_resp_send(req, (const char *)copy, len);
  free(copy);
  return r;
}

static int query_int(httpd_req_t *req, const char *key, int def) {
  char q[96], v[16];
  if (httpd_req_get_url_query_str(req, q, sizeof(q)) != ESP_OK) return def;
  if (httpd_query_key_value(q, key, v, sizeof(v)) != ESP_OK) return def;
  return atoi(v);
}

// /servo?pan=90&tilt=90&track=1  (parametros opcionais)
static esp_err_t servo_handler(httpd_req_t *req) {
  int pan = query_int(req, "pan", -1), tilt = query_int(req, "tilt", -1), tr = query_int(req, "track", -1);
  if (tr >= 0) robo_set_tracking(tr);
  if (pan >= 0 || tilt >= 0) robo_set_angles(pan >= 0 ? pan : robo_pan(), tilt >= 0 ? tilt : robo_tilt());
  return httpd_resp_send(req, "ok", 2);
}

// /gesture?g=sim|nao|curioso|centro
static esp_err_t gesture_handler(httpd_req_t *req) {
  char q[64], g[16] = "";
  if (httpd_req_get_url_query_str(req, q, sizeof(q)) == ESP_OK) httpd_query_key_value(q, "g", g, sizeof(g));
  robo_gesture(g);
  return httpd_resp_send(req, "ok", 2);
}

// /wake?ms=15000 : acorda a camera (o PC chama assim que detecta voz)
static esp_err_t wake_handler(httpd_req_t *req) {
  vision_wake(query_int(req, "ms", VISION_IDLE_MS));
  return httpd_resp_send(req, "ok", 2);
}

// /config?vision=0|1&xclk=10|20&echo=0|1  (echo=1: mic NAO fica mudo enquanto o alto-falante toca; so p/ autoteste)
static esp_err_t config_handler(httpd_req_t *req) {
  int v = query_int(req, "vision", -1), x = query_int(req, "xclk", -1), e = query_int(req, "echo", -1);
  if (v >= 0) vision_always_on = v;
  if (x > 0 && x != cam_xclk_mhz) { cam_xclk_mhz = x; cam_reinit = true; }
  if (e >= 0) robo_set_echo_test(e);
  char b[96];
  snprintf(b, sizeof(b), "{\"vision\":%d,\"xclk\":%d,\"echo\":%d}", vision_always_on, cam_xclk_mhz, robo_echo_test());
  httpd_resp_set_type(req, "application/json");
  return httpd_resp_send(req, b, HTTPD_RESP_USE_STRLEN);
}

// /stats : telemetria para diagnostico
static esp_err_t stats_handler(httpd_req_t *req) {
  char b[400], m[200];
  robo_stats_json(m, sizeof(m));
  snprintf(b, sizeof(b),
           "{\"uptime_s\":%lu,\"rssi\":%d,\"canal\":%d,\"ram_interna\":%u,\"ram_interna_min\":%u,"
           "\"psram\":%u,\"camera\":%d,\"camera_despertares\":%u,\"fps\":%.1f,\"xclk\":%d,%s}",
           millis() / 1000, WiFi.RSSI(), WiFi.channel(), heap_caps_get_free_size(MALLOC_CAP_INTERNAL),
           heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL), heap_caps_get_free_size(MALLOC_CAP_SPIRAM),
           camera_on, cam_wakeups, fps, cam_xclk_mhz, m);
  httpd_resp_set_type(req, "application/json");
  return httpd_resp_send(req, b, HTTPD_RESP_USE_STRLEN);
}

static esp_err_t stream_handler(httpd_req_t *req) {
  char part[64];
  esp_err_t res = httpd_resp_set_type(req, STREAM_TYPE);
  if (res != ESP_OK) return res;
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  uint32_t sent_id = 0;
  uint8_t *copy = NULL; size_t cap = 0;
  stream_clients++;
  while (true) {
    if (frame_id == sent_id) { delay(5); continue; }
    xSemaphoreTake(frame_mutex, portMAX_DELAY);
    size_t len = last_jpg_len;
    if (len > cap) { free(copy); copy = (uint8_t *)ps_malloc(len); cap = copy ? len : 0; }
    if (copy) memcpy(copy, last_jpg, len);
    sent_id = frame_id;
    xSemaphoreGive(frame_mutex);
    if (!copy) { res = ESP_FAIL; break; }

    size_t hlen = snprintf(part, sizeof(part), STREAM_PART, len);
    res = httpd_resp_send_chunk(req, STREAM_SEP, strlen(STREAM_SEP));
    if (res == ESP_OK) res = httpd_resp_send_chunk(req, part, hlen);
    if (res == ESP_OK) res = httpd_resp_send_chunk(req, (const char *)copy, len);
    if (res != ESP_OK) break;
  }
  stream_clients--;
  free(copy);
  return res;
}

static void start_servers() {
  httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
  cfg.server_port = 80;
  cfg.ctrl_port = 32768;
  cfg.max_uri_handlers = 12;
  httpd_handle_t web = NULL;
  if (httpd_start(&web, &cfg) == ESP_OK) {
    httpd_uri_t idx = {"/", HTTP_GET, index_handler, NULL};
    httpd_uri_t fc = {"/faces", HTTP_GET, faces_handler, NULL};
    httpd_register_uri_handler(web, &idx);
    httpd_register_uri_handler(web, &fc);
    httpd_uri_t cap = {"/capture", HTTP_GET, capture_handler, NULL};
    httpd_uri_t sv = {"/servo", HTTP_GET, servo_handler, NULL};
    httpd_uri_t ge = {"/gesture", HTTP_GET, gesture_handler, NULL};
    httpd_register_uri_handler(web, &cap);
    httpd_register_uri_handler(web, &sv);
    httpd_register_uri_handler(web, &ge);
    httpd_uri_t wk = {"/wake", HTTP_GET, wake_handler, NULL};
    httpd_uri_t cf = {"/config", HTTP_GET, config_handler, NULL};
    httpd_uri_t sx = {"/stats", HTTP_GET, stats_handler, NULL};
    httpd_register_uri_handler(web, &wk);
    httpd_register_uri_handler(web, &cf);
    httpd_register_uri_handler(web, &sx);
  }
  cfg.server_port = 81;
  cfg.ctrl_port = 32769;
  httpd_handle_t st = NULL;
  if (httpd_start(&st, &cfg) == ESP_OK) {
    httpd_uri_t s = {"/stream", HTTP_GET, stream_handler, NULL};
    httpd_register_uri_handler(st, &s);
  }
}

// ---------- camera ----------
static bool init_camera() {
  camera_config_t c = {};
  c.ledc_channel = LEDC_CHANNEL_0;
  c.ledc_timer = LEDC_TIMER_0;
  c.pin_d0 = Y2_GPIO_NUM; c.pin_d1 = Y3_GPIO_NUM; c.pin_d2 = Y4_GPIO_NUM; c.pin_d3 = Y5_GPIO_NUM;
  c.pin_d4 = Y6_GPIO_NUM; c.pin_d5 = Y7_GPIO_NUM; c.pin_d6 = Y8_GPIO_NUM; c.pin_d7 = Y9_GPIO_NUM;
  c.pin_xclk = XCLK_GPIO_NUM; c.pin_pclk = PCLK_GPIO_NUM;
  c.pin_vsync = VSYNC_GPIO_NUM; c.pin_href = HREF_GPIO_NUM;
  c.pin_sccb_sda = SIOD_GPIO_NUM; c.pin_sccb_scl = SIOC_GPIO_NUM;
  c.pin_pwdn = PWDN_GPIO_NUM; c.pin_reset = RESET_GPIO_NUM;
  c.xclk_freq_hz = cam_xclk_mhz * 1000000;
  c.pixel_format = PIXFORMAT_RGB565;
  c.frame_size = FRAMESIZE_QVGA;  // 320x240
  c.fb_count = 2;
  c.fb_location = CAMERA_FB_IN_PSRAM;
  c.grab_mode = CAMERA_GRAB_LATEST;
  esp_err_t err = esp_camera_init(&c);
  if (err != ESP_OK) { LOGF("Falha na camera: 0x%x\n", err); return false; }
  sensor_t *s = esp_camera_sensor_get();
  LOGF("Sensor PID: 0x%x\n", s->id.PID);
  if (s->id.PID == OV3660_PID) { s->set_vflip(s, 1); s->set_brightness(s, 1); s->set_saturation(s, -2); }
  return true;
}

// Sem economia de energia (o roteador nao segura pacotes esperando a placa "acordar") e potencia maxima
static void wifi_tune() {
  esp_wifi_set_ps(WIFI_PS_NONE);
  WiFi.setTxPower(WIFI_POWER_19_5dBm);
}

// ---------- comandos vindos do PC pelo USB (quadros 'C') ----------
// Executados numa tarefa propria para nao travar a recepcao do audio do alto-falante.
static QueueHandle_t cmd_queue;
static volatile bool wifi_enabled = true;

// ---------- rede Wi-Fi propria da placa (modo reserva) ----------
// Se a placa nao achar nenhuma rede conhecida (ex.: em outro lugar), ela cria a propria rede para a
// pagina da camera continuar acessivel pelo celular. O robo em si nao precisa disso (funciona pelo USB).
#define AP_SSID "Robo-ESP32"
#define AP_PASS ""                     // rede ABERTA (sem senha), a pedido do usuario: facil de entrar e ver
#define AP_AFTER_MS 30000              // sem rede conhecida por 30 s -> cria a rede propria
#define AP_STA_RETRY_MS 120000         // com a rede propria ativa, procura as conhecidas a cada 2 min
static volatile bool ap_on = false;
static void on_link_cmd(const char *c) {
  char b[64] = {0};
  strncpy(b, c, sizeof(b) - 1);
  xQueueSend(cmd_queue, b, 0);
}

static void send_faces() {
  char buf[sizeof(faces_json)];
  xSemaphoreTake(frame_mutex, portMAX_DELAY);
  strcpy(buf, faces_json);
  xSemaphoreGive(frame_mutex);
  // "speaking" do faces_json so e atualizado quando a camera roda: corrige com o valor atual
  char *sp = strstr(buf, "\"speaking\":");
  if (sp) sp[11] = robo_speaking() ? '1' : '0';
  link_send('F', buf, strlen(buf));
}

static void cmd_task(void *) {
  char c[64];
  while (true) {
    if (xQueueReceive(cmd_queue, c, portMAX_DELAY) != pdTRUE) continue;
    char a[32] = "";
    int x = 0, y = 0;
    if (!strcmp(c, "capture")) {
      uint8_t *jpg = NULL;
      size_t len = grab_fresh_jpeg(&jpg);
      if (jpg) { link_send('J', jpg, len); free(jpg); } else link_send('J', "", 0);
      send_faces();
    } else if (!strcmp(c, "faces")) {
      send_faces();
    } else if (!strncmp(c, "aprender ", 9)) {
      apr_comeca(c + 9);
    } else if (!strncmp(c, "esquecer ", 9)) {
      char nome[APR_NOME_MAX];
      apr_limpa_nome(nome, c + 9);
      int t = apr_esquece(nome);
      LOGF("[rosto] esqueci '%s' (%d amostras apagadas)", nome, t);
    } else if (!strcmp(c, "pessoas")) {
      String quem = "";
      xSemaphoreTake(apr_mutex, portMAX_DELAY);
      for (int i = 0; i < apr_n; i++)
        if (quem.indexOf(String(apr[i].nome) + " (") < 0) quem += String(apr[i].nome) + " (" + apr_conta(apr[i].nome) + ") ";
      xSemaphoreGive(apr_mutex);
      LOGF("[rosto] conhecidos: %s (fotos) %s", NAME_KNOWN, quem.c_str());
    } else if (sscanf(c, "wake %d", &x) == 1) {
      vision_wake(x);
    } else if (sscanf(c, "gesture %31s", a) == 1) {
      robo_gesture(a);
    } else if (sscanf(c, "servo %d %d", &x, &y) == 2) {
      robo_set_angles(x, y);
    } else if (sscanf(c, "track %d", &x) == 1) {
      robo_set_tracking(x);
    } else if (sscanf(c, "echo %d", &x) == 1) {
      robo_set_echo_test(x);
    } else if (sscanf(c, "vision %d", &x) == 1) {
      vision_always_on = x;
    } else if (sscanf(c, "wifi %d", &x) == 1) {
      // Wi-Fi so serve para a pagina da camera; o robo funciona pelo USB sem ele
      wifi_enabled = x;
      if (!x) { if (ap_on) WiFi.softAPdisconnect(true); ap_on = false; WiFi.disconnect(true); WiFi.mode(WIFI_OFF); LOGF("[wifi] desligado"); }
      else { WiFi.mode(WIFI_STA); WiFi.setSleep(false); LOGF("[wifi] ligado"); }
    } else if (!strcmp(c, "stats")) {
      char m[200], b[640];
      robo_stats_json(m, sizeof(m));
      bool sta = WiFi.status() == WL_CONNECTED;
      snprintf(b, sizeof(b),
               "{\"uptime_s\":%lu,\"wifi\":%d,\"rede\":\"%s\",\"ip\":\"%s\",\"ap\":%d,\"ap_rede\":\"%s\",\"ap_senha\":\"%s\","
               "\"ap_ip\":\"%s\",\"rssi\":%d,\"ram_interna\":%u,\"camera\":%d,%s}",
               millis() / 1000, sta, sta ? WiFi.SSID().c_str() : "", WiFi.localIP().toString().c_str(), ap_on,
               AP_SSID, AP_PASS, WiFi.softAPIP().toString().c_str(), WiFi.RSSI(),
               heap_caps_get_free_size(MALLOC_CAP_INTERNAL), camera_on, m);
      link_send('S', b, strlen(b));
    }
  }
}

void setup() {
  link_begin();
  delay(200);
  LOGF("Iniciando camera com reconhecimento facial...");
  while (!init_camera()) delay(2000);
  camera_on = true;
  vision_wake(VISION_IDLE_MS);  // fica acordada 20 s apos o boot e depois dorme
  robo_begin();

  det1 = new HumanFaceDetectMSR01(0.1F, 0.5F, 10, 0.2F);
  det2 = new HumanFaceDetectMNP01(0.5F, 0.3F, 5);
  recognizer = new FaceRecognition112V1S8();
  recognizer->set_thresh(MATCH_THRESHOLD);
  enroll_from_photos();
  apr_mutex = xSemaphoreCreateMutex();
  apr_carrega();

  frame_mutex = xSemaphoreCreateMutex();
  xTaskCreatePinnedToCore(vision_task, "vision", 16 * 1024, NULL, 5, NULL, 1);

  // Wi-Fi e opcional (pagina da camera / audio por UDP). O robo funciona pelo USB mesmo sem rede,
  // entao nada aqui espera a conexao: ela acontece em segundo plano no loop().
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.setHostname("esp32cam");
  for (auto &r : WIFI_REDES) wifi_multi.addAP(r.ssid, r.pass);
  start_servers();
  robo_start_servers();
  cmd_queue = xQueueCreate(8, 64);
  xTaskCreatePinnedToCore(cmd_task, "cmd", 6144, NULL, 4, NULL, 0);
  link_start_rx(on_link_cmd);
  LOGF("Pronto! Link USB ativo (%d baud). Wi-Fi conectando em segundo plano.", LINK_BAUD);
}

static void start_own_ap() {
  WiFi.mode(WIFI_AP_STA);  // AP para o celular + STA continua procurando as redes conhecidas
  WiFi.softAP(AP_SSID, strlen(AP_PASS) ? AP_PASS : NULL);  // NULL = rede aberta
  ap_on = true;
  LOGF("[wifi] Nenhuma rede conhecida. Rede propria '%s' (%s) ativa. Pagina: http://%s/",
       AP_SSID, strlen(AP_PASS) ? "com senha" : "aberta, sem senha", WiFi.softAPIP().toString().c_str());
}

static void stop_own_ap() {
  WiFi.softAPdisconnect(true);
  WiFi.mode(WIFI_STA);
  ap_on = false;
}

void loop() {
  // Rostos aprendidos vao para a flash aqui, fora da tarefa da camera, sem ninguem aprendendo e
  // com o alto-falante quieto: gravar flash pausa o cache e picotaria o audio.
  if (apr_sujo && !apr_aprendendo[0] && !robo_speaking() && millis() - apr_mudou_em > 2000) apr_grava();
  static uint32_t t = 0;
  static bool was_connected = false;
  static uint32_t lost_since = 0, last_sta_try = 0;
  if (wifi_enabled) {
    if (WiFi.status() == WL_CONNECTED) {
      if (!was_connected) {
        was_connected = true;
        wifi_tune();
        MDNS.begin("esp32cam");
        LOGF("Wi-Fi conectado! Rede '%s'. Pagina: http://%s/", WiFi.SSID().c_str(), WiFi.localIP().toString().c_str());
      }
      if (ap_on) { stop_own_ap(); LOGF("[wifi] rede propria desligada (placa entrou em '%s')", WiFi.SSID().c_str()); }
    } else {
      if (was_connected) { LOGF("Wi-Fi caiu, reconectando..."); was_connected = false; lost_since = millis(); }
      if (!ap_on) {
        wifi_multi.run(5000);  // tenta todas as redes conhecidas
        // lugar novo / rede desconhecida: depois de 30 s sem rede, cria a rede propria da placa
        if (WiFi.status() != WL_CONNECTED && millis() - lost_since > AP_AFTER_MS) {
          start_own_ap();
          last_sta_try = millis();
        }
      } else if (millis() - last_sta_try > AP_STA_RETRY_MS) {
        // com a rede propria ativa, ainda procura as redes conhecidas de vez em quando (scan rapido)
        last_sta_try = millis();
        wifi_multi.run(5000);
      }
    }
  }
  if (millis() - t > 30000) {
    float secs = (millis() - t) / 1000.0f;
    t = millis();
    uint32_t rd, tx, dr;
    robo_mic_stats(&rd, &tx, &dr);
    LOGF("[mic] lidas %.0f amostras/s, enviadas %.0f amostras/s, estouros do buffer %u\n",
                  rd / secs, tx / 2 / secs, dr);
    LOGF("IP: http://%s/  (WiFi %s, rede '%s', sinal %d dBm canal %d) fps=%.1f  RAM interna livre=%u (maior bloco %u, minimo %u)\n",
                  WiFi.localIP().toString().c_str(), WiFi.status() == WL_CONNECTED ? "OK" : "desconectado",
                  WiFi.SSID().c_str(), WiFi.RSSI(), WiFi.channel(), fps, heap_caps_get_free_size(MALLOC_CAP_INTERNAL),
                  heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL),
                  heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL));
  }
  delay(100);
}
