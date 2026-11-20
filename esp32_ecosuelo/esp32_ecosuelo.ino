
#include <ESP32Servo.h>
#include <BluetoothSerial.h>
#include <esp_system.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// =====================================
// CONFIGURACION
// =====================================

#define SENSOR_PIN 34
#define SERVO_PIN 18

#define NUM_LECTURAS 20

#define ADC_SECO 4095
#define ADC_HUMEDO 0

#define POSICION_MEDICION 15
#define POSICION_REPOSO 90

BluetoothSerial SerialBT;
Servo servoSensor;

// =====================================
// VARIABLES
// =====================================

char bufferUSB[128];
char bufferBT[128];

size_t indiceUSB = 0;
size_t indiceBT = 0;

bool bluetoothIniciado = false;
bool monitoreoActivo = false;

uint32_t intervaloMs = 10000;
uint32_t ultimaMedicion = 0;
uint32_t secuencia = 0;
uint32_t identificadorArranque = 0;

Print *canalMonitoreo = nullptr;

// =====================================
// COMUNICACION
// =====================================

bool canalDisponible(Print &salida) {
  if (&salida == static_cast<Print *>(&SerialBT)) {
    return bluetoothIniciado && SerialBT.connected();
  }

  return true;
}

void enviarEstado(Print &salida) {
  if (!canalDisponible(salida)) return;

  char mensaje[160];

  snprintf(
    mensaje,
    sizeof(mensaje),
    "{\"type\":\"status\",\"connected\":true,\"monitoring\":%s,\"interval_ms\":%lu}",
    monitoreoActivo ? "true" : "false",
    (unsigned long)intervaloMs
  );

  salida.println(mensaje);
}

void enviarError(Print &salida, const char *mensaje) {
  if (!canalDisponible(salida)) return;

  char respuesta[180];

  snprintf(
    respuesta,
    sizeof(respuesta),
    "{\"type\":\"error\",\"message\":\"%s\"}",
    mensaje
  );

  salida.println(respuesta);
}

// =====================================
// LEER CAMPOS JSON
// =====================================

bool leerCampoCadena(
  const char *json,
  const char *campo,
  char *destino,
  size_t capacidad
) {
  char busqueda[40];

  snprintf(busqueda, sizeof(busqueda), "\"%s\"", campo);

  const char *pos = strstr(json, busqueda);
  if (!pos) return false;

  pos = strchr(pos, ':');
  if (!pos) return false;

  pos++;

  while (*pos == ' ' || *pos == '\t') pos++;

  if (*pos != '"') return false;

  pos++;

  size_t i = 0;

  while (*pos && *pos != '"') {
    if (i >= capacidad - 1) return false;
    destino[i++] = *pos++;
  }

  if (*pos != '"') return false;

  destino[i] = '\0';

  return true;
}

bool leerCampoEntero(
  const char *json,
  const char *campo,
  uint32_t &valor
) {
  char busqueda[40];

  snprintf(busqueda, sizeof(busqueda), "\"%s\"", campo);

  const char *pos = strstr(json, busqueda);
  if (!pos) return false;

  pos = strchr(pos, ':');
  if (!pos) return false;

  pos++;

  while (*pos == ' ' || *pos == '\t') pos++;

  if (*pos < '0' || *pos > '9') return false;

  char *final;
  unsigned long numero = strtoul(pos, &final, 10);

  if (final == pos) return false;

  valor = (uint32_t)numero;

  return true;
}

// =====================================
// CONTROL DEL SERVO
// =====================================

void posicionarServoMedicion() {
  servoSensor.write(POSICION_MEDICION);
}

void posicionarServoReposo() {
  servoSensor.write(POSICION_REPOSO);
}

void moverServoManual(Print &salida) {
  if (monitoreoActivo) {
    enviarError(
      salida,
      "Deten el monitoreo antes de mover el servo."
    );
    return;
  }

  posicionarServoMedicion();
  delay(500);

  enviarEstado(salida);
}

// =====================================
// PROCESAR COMANDOS
// =====================================

void procesarComando(const char *json, Print &salida) {
  char comando[20];

  if (!leerCampoCadena(
    json,
    "command",
    comando,
    sizeof(comando)
  )) {
    enviarError(salida, "Comando no valido.");
    return;
  }

  if (strcmp(comando, "status") == 0) {
    enviarEstado(salida);
  }

  else if (strcmp(comando, "start") == 0) {
    uint32_t nuevoIntervalo = 0;

    if (
      !leerCampoEntero(json, "interval_ms", nuevoIntervalo) ||
      nuevoIntervalo < 1000 ||
      nuevoIntervalo > 86400000UL
    ) {
      enviarError(salida, "Intervalo no valido.");
      return;
    }

    intervaloMs = nuevoIntervalo;

    posicionarServoMedicion();
    delay(300);

    canalMonitoreo = &salida;
    monitoreoActivo = true;

    // Primera medicion inmediata
    ultimaMedicion = millis() - intervaloMs;

    enviarEstado(salida);
  }

  else if (strcmp(comando, "stop") == 0) {
    monitoreoActivo = false;
    canalMonitoreo = nullptr;

    posicionarServoReposo();

    enviarEstado(salida);
  }

  else if (strcmp(comando, "servo") == 0) {
    moverServoManual(salida);
  }

  else {
    enviarError(salida, "Comando desconocido.");
  }
}

// =====================================
// LEER USB Y BLUETOOTH
// =====================================

void leerCanal(
  Stream &entrada,
  Print &salida,
  char *buffer,
  size_t &indice
) {
  while (entrada.available()) {
    char caracter = entrada.read();

    if (caracter == '\r') continue;

    if (caracter == '\n') {
      buffer[indice] = '\0';

      if (indice > 0) {
        procesarComando(buffer, salida);
      }

      indice = 0;
    }

    else if (indice < 127) {
      buffer[indice++] = caracter;
    }

    else {
      indice = 0;
      enviarError(salida, "Comando demasiado largo.");
    }
  }
}

// =====================================
// DESCONEXION BLUETOOTH
// =====================================

void revisarBluetooth() {
  if (
    canalMonitoreo == static_cast<Print *>(&SerialBT) &&
    (!bluetoothIniciado || !SerialBT.connected())
  ) {
    monitoreoActivo = false;
    canalMonitoreo = nullptr;

    posicionarServoReposo();
  }
}

// =====================================
// REALIZAR MEDICION
// =====================================

void realizarMedicion(Print &salida) {
  if (!canalDisponible(salida)) {
    revisarBluetooth();
    return;
  }

  uint32_t suma = 0;

  for (int i = 0; i < NUM_LECTURAS; i++) {
    suma += analogRead(SENSOR_PIN);
    delay(10);
  }

  int adc = suma / NUM_LECTURAS;

  float humedad =
    ((float)(ADC_SECO - adc) * 100.0f) /
    (ADC_SECO - ADC_HUMEDO);

  humedad = constrain(humedad, 0.0f, 100.0f);

  secuencia++;

  char mensaje[180];

  snprintf(
    mensaje,
    sizeof(mensaje),
    "{\"type\":\"measurement\",\"id\":\"%08lX\",\"seq\":%lu,\"adc\":%d,\"humidity\":%.1f}",
    (unsigned long)identificadorArranque,
    (unsigned long)secuencia,
    adc,
    humedad
  );

  salida.println(mensaje);
}

// =====================================
// INICIO
// =====================================

void setup() {
  Serial.begin(115200);

  bluetoothIniciado = SerialBT.begin("EcoSuelo");

  analogReadResolution(12);
  analogSetPinAttenuation(SENSOR_PIN, ADC_11db);

  pinMode(SENSOR_PIN, INPUT);

  servoSensor.setPeriodHertz(50);
  servoSensor.attach(SERVO_PIN, 500, 2500);

  posicionarServoReposo();

  identificadorArranque = esp_random();

  delay(500);

  enviarEstado(Serial);
}

// =====================================
// BUCLE PRINCIPAL
// =====================================

void loop() {
  revisarBluetooth();

  leerCanal(
    Serial,
    Serial,
    bufferUSB,
    indiceUSB
  );

  if (bluetoothIniciado && SerialBT.connected()) {
    leerCanal(
      SerialBT,
      SerialBT,
      bufferBT,
      indiceBT
    );
  }

  revisarBluetooth();

  if (
    monitoreoActivo &&
    canalMonitoreo != nullptr &&
    millis() - ultimaMedicion >= intervaloMs
  ) {
    ultimaMedicion = millis();

    realizarMedicion(*canalMonitoreo);
  }
}
