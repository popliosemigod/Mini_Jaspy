// MODELO das redes Wi-Fi da placa. Copie este arquivo para "wifi_redes.h" (mesma pasta) e preencha.
// O wifi_redes.h fica fora do GitHub (.gitignore), entao as senhas reais nunca sao publicadas.
//
// O Wi-Fi so serve para a pagina da camera no navegador: o robo conversa com o PC pelo cabo USB.
// Se a placa nao achar nenhuma rede daqui, depois de 30 s ela cria a rede propria
// "Robo-ESP32", ABERTA (sem senha) -> pagina em http://192.168.4.1/
#pragma once
static const WifiCred WIFI_REDES[] = {
  {"NOME_DA_REDE", "SENHA_DA_REDE"},
  // {"Hotspot_do_celular", "senha"},
};
