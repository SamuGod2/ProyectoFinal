import serial
import sounddevice as sd
import numpy as np
import time
from collections import deque

# =========================
# CONFIGURACIÓN GENERAL
# =========================

PUERTO_EMG = "COM4"
BAUDIOS = 115200

# Micrófono que respondió correctamente
DISPOSITIVO_MIC = 0

# Audio
FS_AUDIO = 48000
DURACION_AUDIO = 0.2          # 200 ms
N_AUDIO = int(FS_AUDIO * DURACION_AUDIO)

# Voz
UMBRAL_VOZ = 0.000050
ZCR_MIN = 0.02
ZCR_MAX = 0.30

# Confirmación para evitar activación por un solo pico aislado
LECTURAS_EMG_CONSECUTIVAS = 2
contador_emg_activo = 0

# Calibración EMG
TIEMPO_REPOSO = 5             # segundos
TIEMPO_CONTRACCION = 5        # segundos
TIEMPO_RECUPERACION = 10      # segundos de descanso antes de iniciar EMG + voz

# Buffer temporal de 2 segundos
# Cada ciclo trabaja con ventanas aproximadas de 200 ms
# 10 ventanas x 200 ms = 2 segundos
historial_emg = deque(maxlen=10)
historial_energia = deque(maxlen=10)
historial_zcr = deque(maxlen=10)


# =========================
# FUNCIONES DE VOZ
# =========================

def calcular_energia(x):
    return np.mean(x ** 2)


def calcular_zcr(x):
    signos = np.sign(x)
    cruces = np.sum(np.abs(np.diff(signos))) / 2
    return cruces / len(x)


def detectar_voz():
    audio = sd.rec(
        N_AUDIO,
        samplerate=FS_AUDIO,
        channels=1,
        dtype="float32",
        device=DISPOSITIVO_MIC
    )
    sd.wait()

    x = audio[:, 0]

    energia = calcular_energia(x)
    zcr = calcular_zcr(x)

    voz_activa = (
        energia > UMBRAL_VOZ and
        ZCR_MIN <= zcr <= ZCR_MAX
    )

    return voz_activa, energia, zcr


# =========================
# FUNCIONES DE EMG
# =========================

def leer_emg(esp32):
    linea = esp32.readline().decode("utf-8", errors="ignore").strip()

    if not linea:
        return None

    try:
        return float(linea)
    except ValueError:
        return None


def cuenta_regresiva(segundos, mensaje):
    print("\n" + mensaje)

    for t in range(segundos, 0, -1):
        print(f"Tiempo restante: {t} s")
        time.sleep(1)


def limpiar_buffer_serial(esp32):
    """
    Limpia datos atrasados del puerto serial.
    Esto es importante porque el ESP32 sigue enviando datos
    durante las cuentas regresivas.
    """
    try:
        esp32.reset_input_buffer()
        time.sleep(0.2)
    except:
        pass


def capturar_emg_durante(esp32, duracion_segundos, etiqueta):
    """
    Captura valores EMG durante cierto tiempo.
    El ESP32 manda un valor cada 200 ms aproximadamente.
    """
    valores = []
    tiempo_inicio = time.time()

    print(f"\nCapturando EMG: {etiqueta}")

    while time.time() - tiempo_inicio < duracion_segundos:
        valor = leer_emg(esp32)

        if valor is not None:
            valores.append(valor)
            print(f"{etiqueta} | EMG: {valor:.2f}")

    if len(valores) == 0:
        return None, None, None

    promedio = np.mean(valores)
    minimo = np.min(valores)
    maximo = np.max(valores)

    return promedio, minimo, maximo


def calibrar_umbral_emg(esp32):
    print("\n===================================")
    print("CALIBRACIÓN AUTOMÁTICA DEL EMG")
    print("===================================")
    print("Esta calibración calcula un umbral individual para el sujeto.")
    print("Primero se medirá reposo y después contracción voluntaria.")
    print("No muevas los cables durante la calibración.")

    input("\nPresiona ENTER para iniciar calibración de REPOSO...")

    cuenta_regresiva(
        TIEMPO_REPOSO,
        "CALIBRACIÓN DE REPOSO: mantén el brazo relajado."
    )

    limpiar_buffer_serial(esp32)

    reposo_prom, reposo_min, reposo_max = capturar_emg_durante(
        esp32,
        TIEMPO_REPOSO,
        "REPOSO"
    )

    if reposo_prom is None:
        print("No se pudieron capturar datos de reposo.")
        return None

    print("\nResultado reposo:")
    print(f"Promedio reposo: {reposo_prom:.2f}")
    print(f"Mínimo reposo:   {reposo_min:.2f}")
    print(f"Máximo reposo:   {reposo_max:.2f}")

    input("\nPresiona ENTER para iniciar calibración de CONTRACCIÓN...")

    cuenta_regresiva(
        TIEMPO_CONTRACCION,
        "CALIBRACIÓN DE CONTRACCIÓN: cierra el puño y flexiona ligeramente la muñeca."
    )

    limpiar_buffer_serial(esp32)

    contraccion_prom, contraccion_min, contraccion_max = capturar_emg_durante(
        esp32,
        TIEMPO_CONTRACCION,
        "CONTRACCIÓN"
    )

    if contraccion_prom is None:
        print("No se pudieron capturar datos de contracción.")
        return None

    print("\nResultado contracción:")
    print(f"Promedio contracción: {contraccion_prom:.2f}")
    print(f"Mínimo contracción:   {contraccion_min:.2f}")
    print(f"Máximo contracción:   {contraccion_max:.2f}")

    diferencia = contraccion_prom - reposo_prom

    if diferencia <= 0:
        print("\nADVERTENCIA: la contracción promedio no fue mayor que el reposo promedio.")
        print("Revisa colocación del sensor o repite calibración.")
        return None

    # =========================
    # FÓRMULA CORREGIDA
    # Punto medio entre reposo y contracción
    # =========================

    umbral_calculado = (reposo_prom + contraccion_prom) / 2

    print("\n===================================")
    print("UMBRAL EMG CALCULADO")
    print("===================================")
    print(f"Reposo promedio:       {reposo_prom:.2f}")
    print(f"Contracción promedio:  {contraccion_prom:.2f}")
    print("Criterio usado:        Punto medio entre reposo y contracción")
    print(f"Umbral EMG calculado:  {umbral_calculado:.2f}")
    print("===================================\n")

    # =========================
    # RECUPERACIÓN MUSCULAR
    # =========================

    cuenta_regresiva(
        TIEMPO_RECUPERACION,
        "DESCANSO / RECUPERACIÓN: relaja el brazo antes de iniciar EMG + voz."
    )

    limpiar_buffer_serial(esp32)

    return umbral_calculado, reposo_prom, contraccion_prom


# =========================
# CLASIFICACIÓN DE INTENSIDAD
# =========================

def clasificar_intensidad_emg(emg_actual, reposo_ref, contraccion_ref, umbral_emg):
    """
    Clasificación simple de intensidad para mostrar en consola.
    No afecta la lógica de seguridad principal.
    """
    rango = contraccion_ref - reposo_ref

    if rango <= 0:
        return "SIN CALIBRAR"

    if emg_actual < umbral_emg:
        return "INACTIVO"

    if emg_actual < umbral_emg + 0.25 * rango:
        return "DÉBIL"

    if emg_actual < umbral_emg + 0.60 * rango:
        return "PROMEDIO"

    return "FUERTE"


# =========================
# FUNCIÓN DE DECISIÓN BIMODAL
# =========================

def tomar_decision(emg_activo, voz_activa):
    if not emg_activo and not voz_activa:
        return "REPOSO"

    if emg_activo and not voz_activa:
        return "BLOQUEADO: falta comando de voz"

    if not emg_activo and voz_activa:
        return "BLOQUEADO: falta gesto muscular"

    return "ACTUADOR ACTIVADO"


# =========================
# PROGRAMA PRINCIPAL
# =========================

print("Iniciando integración EMG + Voz con MyoWare...")
print(f"Puerto EMG: {PUERTO_EMG}")
print(f"Baudios: {BAUDIOS}")
print(f"Micrófono: dispositivo {DISPOSITIVO_MIC}")
print(f"Umbral voz: {UMBRAL_VOZ}")
print(f"Rango ZCR válido: {ZCR_MIN} a {ZCR_MAX}")
print(f"Lecturas EMG consecutivas requeridas: {LECTURAS_EMG_CONSECUTIVAS}")
print("Buffer temporal: 10 ventanas de 200 ms = 2 segundos")
print("Presiona Ctrl + C para detener.\n")

try:
    esp32 = serial.Serial(PUERTO_EMG, BAUDIOS, timeout=1)
    time.sleep(2)

    print("Conexión con ESP32 establecida.\n")

    # Limpiar datos iniciales acumulados
    limpiar_buffer_serial(esp32)

    # =========================
    # CALIBRACIÓN DEL SUJETO
    # =========================

    resultado_calibracion = calibrar_umbral_emg(esp32)

    if resultado_calibracion is None:
        print("No se pudo calibrar automáticamente.")
        print("Se usará umbral de respaldo para MyoWare: 1500.0")
        UMBRAL_EMG = 1500.0
        reposo_ref = 1250.0
        contraccion_ref = 2200.0
    else:
        UMBRAL_EMG, reposo_ref, contraccion_ref = resultado_calibracion

    print("\nSistema listo para prueba EMG + Voz.")
    print(f"UMBRAL EMG ACTIVO: {UMBRAL_EMG:.2f}")
    print("Prueba los estados:")
    print("1. Reposo + silencio")
    print("2. Solo contracción")
    print("3. Solo voz")
    print("4. Contracción + voz")
    print("\nPresiona Ctrl + C para detener.\n")

    while True:
        emg_actual = leer_emg(esp32)

        if emg_actual is None:
            continue

        # =========================
        # DETECCIÓN DE EMG
        # =========================

        if emg_actual > UMBRAL_EMG:
            contador_emg_activo += 1
        else:
            contador_emg_activo = 0

        emg_activo = contador_emg_activo >= LECTURAS_EMG_CONSECUTIVAS

        intensidad_emg = clasificar_intensidad_emg(
            emg_actual,
            reposo_ref,
            contraccion_ref,
            UMBRAL_EMG
        )

        # =========================
        # DETECCIÓN DE VOZ
        # =========================

        voz_activa, energia_voz, zcr = detectar_voz()

        # =========================
        # BUFFER DE 2 SEGUNDOS
        # =========================

        historial_emg.append(emg_actual)
        historial_energia.append(energia_voz)
        historial_zcr.append(zcr)

        emg_promedio_2s = np.mean(historial_emg)
        energia_promedio_2s = np.mean(historial_energia)
        zcr_promedio_2s = np.mean(historial_zcr)

        # =========================
        # DECISIÓN FINAL
        # =========================

        estado = tomar_decision(emg_activo, voz_activa)

        print(
            f"EMG: {emg_actual:8.2f} | "
            f"EMG 2s: {emg_promedio_2s:8.2f} | "
            f"Umbral: {UMBRAL_EMG:8.2f} | "
            f"EMG: {'SI' if emg_activo else 'NO'} | "
            f"Intensidad: {intensidad_emg:8s} | "
            f"Energia voz: {energia_voz:.6f} | "
            f"Energia 2s: {energia_promedio_2s:.6f} | "
            f"ZCR: {zcr:.4f} | "
            f"ZCR 2s: {zcr_promedio_2s:.4f} | "
            f"Voz: {'SI' if voz_activa else 'NO'} | "
            f"Estado: {estado}"
        )

except serial.SerialException as e:
    print("No se pudo abrir el puerto serial.")
    print("Revisa que el ESP32 esté conectado y que Arduino IDE no esté usando COM4.")
    print(e)

except KeyboardInterrupt:
    print("\nPrograma detenido por el usuario.")

finally:
    try:
        esp32.close()
        print("Puerto serial cerrado.")
    except:
        pass