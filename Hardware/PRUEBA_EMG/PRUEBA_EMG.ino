// Proyecto Final PSB - EMG + Voz
// Lectura de MyoWare Muscle Sensor con ESP32
// Señal usada: ENV del MyoWare
// Pin ESP32: GPIO34
// Salida serial: valor promedio de EMG cada 200 ms

const int pinMyoWare = 34;

// 40 muestras x 5 ms = 200 ms
const int N = 40;

void setup() {
  Serial.begin(115200);
  delay(1000);
}

void loop() {
  long suma = 0;

  for (int i = 0; i < N; i++) {
    int valor = analogRead(pinMyoWare);
    suma += valor;
    delay(5);
  }

  float emg_promedio = suma / float(N);

  Serial.println(emg_promedio);
}