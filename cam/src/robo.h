#pragma once
#include <Arduino.h>

// ---------- mapa de pinos (livres na Freenove ESP32-S3 CAM) ----------
// Microfone INMP441 (I2S0)
#define MIC_SCK  41
#define MIC_WS   42
#define MIC_SD   1
// Amplificador MAX98357A (I2S1)
#define SPK_BCLK 47
#define SPK_LRC  21
#define SPK_DIN  14
// Servos do pescoco
#define SERVO_PAN_PIN  38   // horizontal (esquerda/direita)
#define SERVO_TILT_PIN 39   // vertical (cima/baixo)

// Se o pescoco seguir o rosto para o lado errado, troque o sinal (1 / -1)
#define PAN_DIR  1
#define TILT_DIR 1

#define AUDIO_RATE 16000
#define MIC_PORT 82   // UDP: PC manda HELLO, placa envia [seq][PCM 16 kHz 16 bits mono]
#define SPK_PORT 83   // UDP: PC envia [seq][PCM 16 kHz 16 bits mono]; seq 0xFFFFFFFF = fim

// Volume do alto-falante aplicado na placa (0.0 a 1.0). 0.25 = baixo, mas audivel.
#define SPK_VOLUME 0.25f

void robo_begin();            // servos + I2S (antes do Wi-Fi)
void robo_start_servers();    // servidores de audio (depois do Wi-Fi)
void robo_track_face(int cx, int cy, int img_w, int img_h);  // chamado a cada quadro com rosto
void robo_set_angles(int pan, int tilt);
void robo_set_tracking(bool on);
void robo_gesture(const char *name);  // "sim", "nao", "centro", "curioso"
void robo_set_servo_vel(float rastreio, float gesto);  // graus/s (comando "servovel r g")
int robo_pan();
int robo_tilt();
bool robo_tracking();
bool robo_speaking();
void robo_set_echo_test(bool on);   // autoteste: mic nao fica mudo durante a fala
bool robo_echo_test();
void robo_spk_begin();                         // fala vinda pelo USB
void robo_spk_push(const uint8_t *d, size_t len);
void robo_spk_end();
void robo_stats_json(char *buf, size_t n);  // trecho JSON (sem chaves) com contadores de audio
void robo_mic_stats(uint32_t *read_samples, uint32_t *sent_bytes, uint32_t *dropped);  // zera ao ler
