#pragma once
// =====================================================================
//  placa.h - os pinos de cada placa. Um lugar so.
//
//  PLACA_XIAO  : Seeed XIAO ESP32-S3 Sense (camera e microfone PDM na propria
//                placa; USB nativo). Pinos da camera, do microfone e do
//                amplificador conferidos no firmware da cabeca do Jaspy do
//                laboratorio (firmware/cabeca/include/config_cerebro.h).
//  (padrao)    : Freenove ESP32-S3 WROOM CAM com INMP441 e CH343 (o que roda
//                hoje; valores IGUAIS aos de antes da troca).
//
//  Os numeros sao GPIO. Na XIAO, D0=1 D1=2 D2=3 D3=4 D4=5 D5=6 D6=43 D7=44
//  D8=7 D9=8 D10=9 (os nomes impressos na placa).
// =====================================================================

#if defined(PLACA_XIAO)

#define PLACA_NOME "XIAO ESP32-S3 Sense"

// Camera (OV2640 na Sense; a mesma interface DVP)
#define PWDN_GPIO_NUM  -1
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM  10
#define SIOD_GPIO_NUM  40
#define SIOC_GPIO_NUM  39
#define Y9_GPIO_NUM    48
#define Y8_GPIO_NUM    11
#define Y7_GPIO_NUM    12
#define Y6_GPIO_NUM    14
#define Y5_GPIO_NUM    16
#define Y4_GPIO_NUM    18
#define Y3_GPIO_NUM    17
#define Y2_GPIO_NUM    15
#define VSYNC_GPIO_NUM 38
#define HREF_GPIO_NUM  47
#define PCLK_GPIO_NUM  13

// Microfone: PDM embutido na Sense (nada a ligar)
#define MIC_PDM
#define MIC_CLK_PDM 42
#define MIC_DATA_PDM 41

// Amplificador MAX98357A (I2S1): D0, D1, D2 - os mesmos da cabeca do Jaspy
#define SPK_BCLK 1   // D0
#define SPK_LRC  2   // D1
#define SPK_DIN  3   // D2

// Servos do pescoco: D3 e D4 (livres; 38/39, onde ficavam na Freenove, sao da camera aqui).
// Evitar D6/D7 (43/44: UART0, o log de boot sai por ali) e D8/D9/D10 (7/8/9: SD da expansao).
#define SERVO_PAN_PIN  4    // D3
#define SERVO_TILT_PIN 5    // D4

#else  // ---------------- Freenove ESP32-S3 WROOM CAM ----------------

#define PLACA_NOME "Freenove ESP32-S3 CAM"

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

#endif
