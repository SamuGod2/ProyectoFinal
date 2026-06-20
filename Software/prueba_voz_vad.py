import sounddevice as sd
import numpy as np
import time

FS = 48000
DURACION = 0.2
N = int(FS * DURACION)

# Dispositivo de micrófono que ya respondió
DISPOSITIVO_MIC = 0

# Umbral bajo para iniciar prueba
UMBRAL_ENERGIA = 0.000050

def calcular_energia(x):
    return np.mean(x ** 2)

def calcular_zcr(x):
    signos = np.sign(x)
    cruces = np.sum(np.abs(np.diff(signos))) / 2
    return cruces / len(x)

print("Probando micrófono solo con energia...")
print(f"Usando dispositivo de audio: {DISPOSITIVO_MIC}")
print("Haz silencio y luego di fuerte: YA, ALTO o ABRE.")
print("Presiona Ctrl + C para detener.\n")

try:
    while True:
        audio = sd.rec(
            N,
            samplerate=FS,
            channels=1,
            dtype='float32',
            device=DISPOSITIVO_MIC
        )
        sd.wait()

        x = audio[:, 0]

        energia = calcular_energia(x)
        zcr = calcular_zcr(x)

        voz_detectada = energia > UMBRAL_ENERGIA

        estado = "VOZ DETECTADA" if voz_detectada else "silencio"

        print(f"Energia: {energia:.6f} | ZCR: {zcr:.4f} | Estado: {estado}")

        time.sleep(0.05)

except KeyboardInterrupt:
    print("\nPrueba finalizada.")