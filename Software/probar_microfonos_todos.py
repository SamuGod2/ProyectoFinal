import sounddevice as sd
import numpy as np

FS = 44100
DURACION = 1.0
N = int(FS * DURACION)

dispositivos = sd.query_devices()

print("Probando dispositivos de entrada...\n")
print("Cuando diga 'Habla ahora', di fuerte: YA\n")

for i, d in enumerate(dispositivos):
    canales_entrada = d["max_input_channels"]

    if canales_entrada > 0:
        print(f"\nDispositivo {i}: {d['name']}")
        print(f"Canales de entrada: {canales_entrada}")

        try:
            input("Presiona ENTER y luego di: YA...")

            audio = sd.rec(
                N,
                samplerate=FS,
                channels=1,
                dtype="float32",
                device=i
            )
            sd.wait()

            x = audio[:, 0]

            energia = np.mean(x ** 2)
            pico = np.max(np.abs(x))
            rms = np.sqrt(energia)

            print(f"Energia: {energia:.12f}")
            print(f"RMS:     {rms:.12f}")
            print(f"Pico:    {pico:.12f}")

        except Exception as e:
            print(f"No se pudo probar este dispositivo: {e}")