import serial
import time

PUERTO = "COM4"
BAUDIOS = 115200

print("Conectando con ESP32...")
print(f"Puerto: {PUERTO}")
print(f"Baudios: {BAUDIOS}")

try:
    esp32 = serial.Serial(PUERTO, BAUDIOS, timeout=1)
    time.sleep(2)

    print("Conexión establecida.")
    print("Leyendo datos del ESP32...")
    print("Presiona Ctrl + C para detener.\n")

    while True:
        linea = esp32.readline().decode("utf-8", errors="ignore").strip()

        if linea:
            try:
                mav = float(linea)
                print(f"MAV EMG: {mav:.2f}")
            except ValueError:
                print(f"Dato no numérico recibido: {linea}")

except serial.SerialException as e:
    print("No se pudo abrir el puerto serial.")
    print("Revisa que el ESP32 esté conectado y que el Monitor Serial/Plotter esté cerrado.")
    print(e)

except KeyboardInterrupt:
    print("\nLectura finalizada.")

finally:
    try:
        esp32.close()
        print("Puerto serial cerrado.")
    except:
        pass