#pragma once
#include <Arduino.h>

#if defined(PLACA_XIAO_SENSE)
// ---------- XIAO ESP32-S3 Sense ----------
// Microfone PDM embutido na placa de expansao Sense (MSM261D3526H1CPM): CLK GPIO42, DATA GPIO41.
#define MIC_PDM  1
#define MIC_PDM_CLK  42
#define MIC_PDM_DATA 41
#define MIC_GAIN     4.0f      // ganho digital do PDM (o sinal dele sai baixo); ajuste com robo.py --nivel
// Amplificador MAX98357A (I2S1) nos pinos D3/D4/D5 da XIAO
#define SPK_DIN  4    // D3
#define SPK_BCLK 5    // D4
#define SPK_LRC  6    // D5
// Servos do pescoco (opcionais)
#define SERVO_PAN_PIN  1    // D0
#define SERVO_TILT_PIN 2    // D1
#else
// ---------- Freenove ESP32-S3 WROOM CAM (montagem antiga) ----------
// Microfone INMP441 (I2S0)
#define MIC_PDM  0
#define MIC_SCK  41
#define MIC_WS   42
#define MIC_SD   1
#define MIC_GAIN 1.0f
// Amplificador MAX98357A (I2S1)
#define SPK_BCLK 47
#define SPK_LRC  21
#define SPK_DIN  14
// Servos do pescoco
#define SERVO_PAN_PIN  38   // horizontal (esquerda/direita)
#define SERVO_TILT_PIN 39   // vertical (cima/baixo)
#endif

// Se o pescoco seguir o rosto para o lado errado, troque o sinal (1 / -1)
#define PAN_DIR  1
#define TILT_DIR 1

#define AUDIO_RATE 16000   // microfone (o Whisper trabalha em 16 kHz)
#define SPK_RATE   22050   // alto-falante: 22 kHz deixa a voz mais nitida que 16 kHz
#define MIC_PORT 82   // UDP: PC manda HELLO, placa envia [seq][PCM 16 kHz 16 bits mono]
#define SPK_PORT 83   // UDP: PC envia [seq][PCM SPK_RATE 16 bits mono]; seq 0xFFFFFFFF = fim

// Volume do alto-falante aplicado na placa (0.0 a 1.0).
// Com o GAIN do MAX98357A em 3 dB (resistor de 100k do GAIN para o VIN), 0.5 da o mesmo volume
// "baixo, mas audivel" de antes (que era 9 dB x 0.25), usando o dobro da faixa digital -> menos chiado.
// Sem o resistor (GAIN solto = 9 dB), use 0.25.
#define SPK_VOLUME 0.5f

void robo_begin();            // servos + I2S (antes do Wi-Fi)
void robo_start_servers();    // servidores de audio (depois do Wi-Fi)
void robo_track_face(int cx, int cy, int img_w, int img_h);  // chamado a cada quadro com rosto
void robo_set_angles(int pan, int tilt);
void robo_set_tracking(bool on);
void robo_gesture(const char *name);  // "sim", "nao", "centro", "curioso"
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
