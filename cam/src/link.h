#pragma once
// Link binario com o PC pelo cabo USB (UART0 / CH343), independente do Wi-Fi.
//
// Quadro: [0xA5][0x5A][tipo:1][tamanho:2 LE][dados][xor dos dados:1]
// Placa -> PC:  'M' microfone (PCM16 mono 16 kHz)   'L' log (texto)
//               'J' foto JPEG                       'F' JSON de rostos/estado
// PC -> placa:  'B' inicio de fala   'A' PCM16 mono 16 kHz para o alto-falante   'E' fim de fala
//               'C' comando em texto (ver main.cpp: link_command)
#include <Arduino.h>

#define LINK_BAUD 2000000

void link_begin();                                   // chamar no inicio do setup (substitui Serial.begin)
void link_send(char type, const void *data, size_t len);
void link_log(const char *fmt, ...);                 // printf -> quadro 'L'
void link_start_rx(void (*on_cmd)(const char *cmd)); // tarefa que recebe quadros do PC
bool link_mic_on();                                  // o PC pediu o microfone pelo USB (renovado a cada 2 s)

#define LOGF(...) link_log(__VA_ARGS__)
