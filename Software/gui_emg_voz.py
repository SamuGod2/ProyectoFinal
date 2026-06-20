import serial
import sounddevice as sd
import numpy as np
import time
import threading
import queue
import tkinter as tk
from collections import deque
import csv
import os
import re
from datetime import datetime

# =========================
# CONFIGURACIÓN GENERAL
# =========================

PUERTO_EMG = "COM4"
BAUDIOS = 115200

DISPOSITIVO_MIC = 0

FS_AUDIO = 48000
DURACION_AUDIO = 0.2
N_AUDIO = int(FS_AUDIO * DURACION_AUDIO)

LECTURAS_EMG_CONSECUTIVAS = 2

ZCR_MIN = 0.02
ZCR_MAX = 0.30

TIEMPO_REPOSO = 5
TIEMPO_CONTRACCION = 5
TIEMPO_SILENCIO = 5
TIEMPO_COMANDO = 5
TIEMPO_RECUPERACION = 10

FACTOR_UMBRAL_EMG = 0.40

ESCALA_BARRA_EMG = 2500.0
ESCALA_BARRA_VOZ = 0.0015

CARPETA_RESULTADOS = "Resultados"

datos_queue = queue.Queue()
ejecutando = True
iniciar_calibracion = threading.Event()

sujeto_actual = "Sujeto"


# =========================
# FUNCIONES DE PROCESAMIENTO
# =========================

def calcular_energia(x):
    return np.mean(x ** 2)


def calcular_zcr(x):
    signos = np.sign(x)
    cruces = np.sum(np.abs(np.diff(signos))) / 2
    return cruces / len(x)


def tomar_decision(emg_activo, voz_activa):
    if not emg_activo and not voz_activa:
        return "REPOSO"

    if emg_activo and not voz_activa:
        return "FALTA VOZ"

    if not emg_activo and voz_activa:
        return "FALTA MOVIMIENTO MUSCULAR"

    return "ACTIVADO"


def leer_emg(esp32):
    linea = esp32.readline().decode("utf-8", errors="ignore").strip()

    if not linea:
        return None

    try:
        return float(linea)
    except ValueError:
        return None


def limpiar_buffer_serial(esp32):
    try:
        esp32.reset_input_buffer()
        time.sleep(0.2)
    except:
        pass


def clasificar_intensidad_emg(emg_actual, reposo_ref, contraccion_ref, umbral_emg):
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
# FUNCIONES PARA CSV
# =========================

def limpiar_nombre_archivo(texto):
    texto = texto.strip()

    if texto == "":
        texto = "Sujeto"

    texto = re.sub(r"[^a-zA-Z0-9_-]", "_", texto)
    return texto


def crear_archivo_csv(sujeto):
    os.makedirs(CARPETA_RESULTADOS, exist_ok=True)

    sujeto_limpio = limpiar_nombre_archivo(sujeto)
    fecha = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    nombre_archivo = f"prueba_{sujeto_limpio}_{fecha}.csv"
    ruta = os.path.join(CARPETA_RESULTADOS, nombre_archivo)

    archivo = open(ruta, mode="w", newline="", encoding="utf-8")
    escritor = csv.writer(archivo)

    escritor.writerow([
        "fecha_hora",
        "sujeto",
        "tipo_registro",
        "tiempo_s",
        "reposo_prom",
        "reposo_min",
        "reposo_max",
        "contraccion_prom",
        "contraccion_min",
        "contraccion_max",
        "umbral_emg",
        "energia_silencio_prom",
        "energia_silencio_min",
        "energia_silencio_max",
        "energia_comando_prom",
        "energia_comando_min",
        "energia_comando_max",
        "umbral_voz",
        "emg_actual",
        "emg_promedio_2s",
        "emg_activo",
        "intensidad_emg",
        "energia_voz",
        "energia_promedio_2s",
        "zcr",
        "zcr_promedio_2s",
        "voz_activa",
        "estado"
    ])

    archivo.flush()
    return archivo, escritor, ruta


def guardar_fila_csv(
    escritor,
    archivo,
    sujeto,
    tipo_registro,
    tiempo_s="",
    reposo_prom="",
    reposo_min="",
    reposo_max="",
    contraccion_prom="",
    contraccion_min="",
    contraccion_max="",
    umbral_emg="",
    energia_silencio_prom="",
    energia_silencio_min="",
    energia_silencio_max="",
    energia_comando_prom="",
    energia_comando_min="",
    energia_comando_max="",
    umbral_voz="",
    emg_actual="",
    emg_promedio_2s="",
    emg_activo="",
    intensidad_emg="",
    energia_voz="",
    energia_promedio_2s="",
    zcr="",
    zcr_promedio_2s="",
    voz_activa="",
    estado=""
):
    fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    escritor.writerow([
        fecha_hora,
        sujeto,
        tipo_registro,
        tiempo_s,
        reposo_prom,
        reposo_min,
        reposo_max,
        contraccion_prom,
        contraccion_min,
        contraccion_max,
        umbral_emg,
        energia_silencio_prom,
        energia_silencio_min,
        energia_silencio_max,
        energia_comando_prom,
        energia_comando_min,
        energia_comando_max,
        umbral_voz,
        emg_actual,
        emg_promedio_2s,
        emg_activo,
        intensidad_emg,
        energia_voz,
        energia_promedio_2s,
        zcr,
        zcr_promedio_2s,
        voz_activa,
        estado
    ])

    archivo.flush()


# =========================
# FUNCIONES DE CALIBRACIÓN GUI
# =========================

def enviar_estado_gui(fase, mensaje, tiempo=None):
    datos_queue.put({
        "fase": fase,
        "mensaje": mensaje,
        "tiempo": tiempo
    })


def cuenta_regresiva_gui(segundos, fase, mensaje):
    for t in range(segundos, 0, -1):
        if not ejecutando:
            return

        enviar_estado_gui(fase, mensaje, t)
        time.sleep(1)


# =========================
# CALIBRACIÓN EMG
# =========================

def capturar_emg_durante(esp32, duracion_segundos, etiqueta):
    valores = []
    tiempo_inicio = time.time()

    while time.time() - tiempo_inicio < duracion_segundos and ejecutando:
        valor = leer_emg(esp32)

        if valor is not None:
            valores.append(valor)
            datos_queue.put({
                "calibracion_valor": True,
                "etiqueta": etiqueta,
                "valor": valor
            })

    if len(valores) == 0:
        return None, None, None

    promedio = np.mean(valores)
    minimo = np.min(valores)
    maximo = np.max(valores)

    return promedio, minimo, maximo


def calibrar_umbral_emg(esp32):
    enviar_estado_gui(
        "CALIBRACIÓN EMG",
        "Calibración automática del EMG. No muevas los cables.",
        None
    )

    time.sleep(2)

    cuenta_regresiva_gui(
        TIEMPO_REPOSO,
        "REPOSO EMG",
        "Mantén el brazo completamente relajado."
    )

    limpiar_buffer_serial(esp32)

    enviar_estado_gui(
        "REPOSO EMG",
        "Capturando reposo EMG...",
        None
    )

    reposo_prom, reposo_min, reposo_max = capturar_emg_durante(
        esp32,
        TIEMPO_REPOSO,
        "REPOSO EMG"
    )

    if reposo_prom is None:
        return None

    datos_queue.put({
        "resultado_reposo": True,
        "reposo_prom": reposo_prom,
        "reposo_min": reposo_min,
        "reposo_max": reposo_max
    })

    time.sleep(2)

    cuenta_regresiva_gui(
        TIEMPO_CONTRACCION,
        "CONTRACCIÓN EMG",
        "Cierra el puño y flexiona ligeramente la muñeca."
    )

    limpiar_buffer_serial(esp32)

    enviar_estado_gui(
        "CONTRACCIÓN EMG",
        "Capturando contracción EMG...",
        None
    )

    contraccion_prom, contraccion_min, contraccion_max = capturar_emg_durante(
        esp32,
        TIEMPO_CONTRACCION,
        "CONTRACCIÓN EMG"
    )

    if contraccion_prom is None:
        return None

    datos_queue.put({
        "resultado_contraccion": True,
        "contraccion_prom": contraccion_prom,
        "contraccion_min": contraccion_min,
        "contraccion_max": contraccion_max
    })

    diferencia = contraccion_prom - reposo_prom

    if diferencia <= 0:
        datos_queue.put({
            "error": "La contracción EMG promedio no fue mayor que el reposo. Repite la calibración."
        })
        return None

    # Umbral EMG al 40 %
    umbral_emg = reposo_prom + FACTOR_UMBRAL_EMG * (contraccion_prom - reposo_prom)

    datos_queue.put({
        "umbral_emg_calculado": True,
        "reposo_prom": reposo_prom,
        "contraccion_prom": contraccion_prom,
        "umbral_emg": umbral_emg
    })

    time.sleep(2)

    return {
        "umbral_emg": umbral_emg,
        "reposo_prom": reposo_prom,
        "reposo_min": reposo_min,
        "reposo_max": reposo_max,
        "contraccion_prom": contraccion_prom,
        "contraccion_min": contraccion_min,
        "contraccion_max": contraccion_max
    }


# =========================
# CALIBRACIÓN VOZ
# =========================

def capturar_energia_voz_durante(duracion_segundos, etiqueta):
    energias = []
    zcrs = []
    tiempo_inicio = time.time()

    while time.time() - tiempo_inicio < duracion_segundos and ejecutando:
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

        energias.append(energia)
        zcrs.append(zcr)

        datos_queue.put({
            "calibracion_voz_valor": True,
            "etiqueta": etiqueta,
            "energia": energia,
            "zcr": zcr
        })

    if len(energias) == 0:
        return None

    return {
        "energia_prom": np.mean(energias),
        "energia_min": np.min(energias),
        "energia_max": np.max(energias),
        "zcr_prom": np.mean(zcrs)
    }


def calibrar_umbral_voz():
    enviar_estado_gui(
        "CALIBRACIÓN VOZ",
        "Ahora se calibrará el umbral de energía de voz.",
        None
    )

    time.sleep(2)

    cuenta_regresiva_gui(
        TIEMPO_SILENCIO,
        "SILENCIO",
        "Guarda silencio. No hables durante esta etapa."
    )

    enviar_estado_gui(
        "SILENCIO",
        "Capturando energía de silencio ambiental...",
        None
    )

    silencio = capturar_energia_voz_durante(
        TIEMPO_SILENCIO,
        "SILENCIO"
    )

    if silencio is None:
        return None

    datos_queue.put({
        "resultado_silencio": True,
        "energia_silencio_prom": silencio["energia_prom"],
        "energia_silencio_min": silencio["energia_min"],
        "energia_silencio_max": silencio["energia_max"]
    })

    time.sleep(2)

    cuenta_regresiva_gui(
        TIEMPO_COMANDO,
        "COMANDO DE VOZ",
        "Di varias veces el comando: YA, ABRE o ALTO."
    )

    enviar_estado_gui(
        "COMANDO DE VOZ",
        "Capturando energía del comando vocal...",
        None
    )

    comando = capturar_energia_voz_durante(
        TIEMPO_COMANDO,
        "COMANDO"
    )

    if comando is None:
        return None

    datos_queue.put({
        "resultado_comando": True,
        "energia_comando_prom": comando["energia_prom"],
        "energia_comando_min": comando["energia_min"],
        "energia_comando_max": comando["energia_max"]
    })

    diferencia = comando["energia_prom"] - silencio["energia_prom"]

    if diferencia <= 0:
        datos_queue.put({
            "error": "La energía del comando no fue mayor que la del silencio. Repite la calibración de voz."
        })
        return None

    umbral_voz = (silencio["energia_prom"] + comando["energia_prom"]) / 2

    datos_queue.put({
        "umbral_voz_calculado": True,
        "energia_silencio_prom": silencio["energia_prom"],
        "energia_comando_prom": comando["energia_prom"],
        "umbral_voz": umbral_voz
    })

    time.sleep(2)

    return {
        "umbral_voz": umbral_voz,
        "energia_silencio_prom": silencio["energia_prom"],
        "energia_silencio_min": silencio["energia_min"],
        "energia_silencio_max": silencio["energia_max"],
        "energia_comando_prom": comando["energia_prom"],
        "energia_comando_min": comando["energia_min"],
        "energia_comando_max": comando["energia_max"]
    }


# =========================
# HILO DE ADQUISICIÓN
# =========================

def hilo_adquisicion():
    global ejecutando
    global sujeto_actual

    contador_emg = 0
    esp32 = None
    archivo_csv = None
    escritor_csv = None

    historial_emg = deque(maxlen=10)
    historial_energia = deque(maxlen=10)
    historial_zcr = deque(maxlen=10)

    try:
        esp32 = serial.Serial(PUERTO_EMG, BAUDIOS, timeout=1)
        time.sleep(2)

        limpiar_buffer_serial(esp32)

        datos_queue.put({
            "conexion": f"ESP32 conectado en {PUERTO_EMG}"
        })

        datos_queue.put({
            "fase": "ESPERA",
            "mensaje": "Coloca sensor, escribe ID del sujeto y presiona INICIAR CALIBRACIÓN.",
            "tiempo": None
        })

        while ejecutando and not iniciar_calibracion.is_set():
            time.sleep(0.1)

        if not ejecutando:
            return

        archivo_csv, escritor_csv, ruta_csv = crear_archivo_csv(sujeto_actual)

        datos_queue.put({
            "archivo_resultados": ruta_csv
        })

        resultado_emg = calibrar_umbral_emg(esp32)

        if resultado_emg is None:
            datos_queue.put({
                "error": "No se pudo calibrar EMG. Revisa el sensor y reinicia la GUI."
            })
            return

        resultado_voz = calibrar_umbral_voz()

        if resultado_voz is None:
            datos_queue.put({
                "error": "No se pudo calibrar voz. Revisa micrófono, silencio y volumen de voz."
            })
            return

        UMBRAL_EMG = resultado_emg["umbral_emg"]
        UMBRAL_VOZ = resultado_voz["umbral_voz"]

        reposo_ref = resultado_emg["reposo_prom"]
        contraccion_ref = resultado_emg["contraccion_prom"]

        guardar_fila_csv(
            escritor_csv,
            archivo_csv,
            sujeto_actual,
            tipo_registro="CALIBRACION",
            tiempo_s=0,
            reposo_prom=f"{resultado_emg['reposo_prom']:.2f}",
            reposo_min=f"{resultado_emg['reposo_min']:.2f}",
            reposo_max=f"{resultado_emg['reposo_max']:.2f}",
            contraccion_prom=f"{resultado_emg['contraccion_prom']:.2f}",
            contraccion_min=f"{resultado_emg['contraccion_min']:.2f}",
            contraccion_max=f"{resultado_emg['contraccion_max']:.2f}",
            umbral_emg=f"{UMBRAL_EMG:.2f}",
            energia_silencio_prom=f"{resultado_voz['energia_silencio_prom']:.6f}",
            energia_silencio_min=f"{resultado_voz['energia_silencio_min']:.6f}",
            energia_silencio_max=f"{resultado_voz['energia_silencio_max']:.6f}",
            energia_comando_prom=f"{resultado_voz['energia_comando_prom']:.6f}",
            energia_comando_min=f"{resultado_voz['energia_comando_min']:.6f}",
            energia_comando_max=f"{resultado_voz['energia_comando_max']:.6f}",
            umbral_voz=f"{UMBRAL_VOZ:.6f}",
            estado="UMBRALES CALCULADOS"
        )

        cuenta_regresiva_gui(
            TIEMPO_RECUPERACION,
            "DESCANSO",
            "Relaja el brazo antes de iniciar la prueba EMG + voz."
        )

        limpiar_buffer_serial(esp32)

        datos_queue.put({
            "sistema_listo": True,
            "umbral_emg": UMBRAL_EMG,
            "umbral_voz": UMBRAL_VOZ
        })

        tiempo_inicio_prueba = time.time()

        while ejecutando:
            emg_actual = leer_emg(esp32)

            if emg_actual is None:
                continue

            if emg_actual > UMBRAL_EMG:
                contador_emg += 1
            else:
                contador_emg = 0

            emg_activo = contador_emg >= LECTURAS_EMG_CONSECUTIVAS

            intensidad_emg = clasificar_intensidad_emg(
                emg_actual,
                reposo_ref,
                contraccion_ref,
                UMBRAL_EMG
            )

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

            historial_emg.append(emg_actual)
            historial_energia.append(energia)
            historial_zcr.append(zcr)

            emg_promedio_2s = np.mean(historial_emg)
            energia_promedio_2s = np.mean(historial_energia)
            zcr_promedio_2s = np.mean(historial_zcr)

            estado = tomar_decision(emg_activo, voz_activa)

            tiempo_s = time.time() - tiempo_inicio_prueba

            guardar_fila_csv(
                escritor_csv,
                archivo_csv,
                sujeto_actual,
                tipo_registro="PRUEBA",
                tiempo_s=f"{tiempo_s:.2f}",
                umbral_emg=f"{UMBRAL_EMG:.2f}",
                umbral_voz=f"{UMBRAL_VOZ:.6f}",
                emg_actual=f"{emg_actual:.2f}",
                emg_promedio_2s=f"{emg_promedio_2s:.2f}",
                emg_activo="SI" if emg_activo else "NO",
                intensidad_emg=intensidad_emg,
                energia_voz=f"{energia:.6f}",
                energia_promedio_2s=f"{energia_promedio_2s:.6f}",
                zcr=f"{zcr:.4f}",
                zcr_promedio_2s=f"{zcr_promedio_2s:.4f}",
                voz_activa="SI" if voz_activa else "NO",
                estado=estado
            )

            datos_queue.put({
                "emg_actual": emg_actual,
                "emg_promedio_2s": emg_promedio_2s,
                "umbral_emg": UMBRAL_EMG,
                "emg_activo": emg_activo,
                "intensidad_emg": intensidad_emg,
                "energia": energia,
                "energia_promedio_2s": energia_promedio_2s,
                "umbral_voz": UMBRAL_VOZ,
                "zcr": zcr,
                "zcr_promedio_2s": zcr_promedio_2s,
                "voz_activa": voz_activa,
                "estado": estado
            })

    except Exception as e:
        datos_queue.put({
            "error": str(e)
        })

    finally:
        if archivo_csv is not None:
            archivo_csv.close()

        if esp32 is not None and esp32.is_open:
            esp32.close()


# =========================
# ACTUALIZACIÓN DE GUI
# =========================

def actualizar_gui():
    while not datos_queue.empty():
        data = datos_queue.get()

        if "conexion" in data:
            lbl_conexion.config(text=data["conexion"])

        elif "archivo_resultados" in data:
            lbl_archivo.config(text=f"Archivo CSV: {data['archivo_resultados']}")

        elif "fase" in data:
            fase = data["fase"]
            mensaje = data["mensaje"]
            tiempo = data["tiempo"]

            lbl_fase.config(text=f"Fase: {fase}")

            if tiempo is None:
                lbl_cronometro.config(text=mensaje)
            else:
                lbl_cronometro.config(text=f"{mensaje} Tiempo restante: {tiempo} s")

            lbl_estado_general.config(
                text=f"ESTADO: {fase}",
                bg="#1565C0",
                fg="white"
            )

            lbl_indicacion_general.config(
                text="Indicación: sigue las instrucciones de calibración.",
                bg="#E3F2FD",
                fg="#0D47A1"
            )

        elif "calibracion_valor" in data:
            lbl_valor_calibracion.config(
                text=f"{data['etiqueta']} | EMG actual: {data['valor']:.2f}"
            )

        elif "calibracion_voz_valor" in data:
            lbl_valor_voz_calibracion.config(
                text=f"{data['etiqueta']} | Energía: {data['energia']:.6f} | ZCR: {data['zcr']:.4f}"
            )

        elif "resultado_reposo" in data:
            lbl_reposo.config(
                text=f"Reposo prom: {data['reposo_prom']:.2f} | Min: {data['reposo_min']:.2f} | Max: {data['reposo_max']:.2f}"
            )

        elif "resultado_contraccion" in data:
            lbl_contraccion.config(
                text=f"Contracción prom: {data['contraccion_prom']:.2f} | Min: {data['contraccion_min']:.2f} | Max: {data['contraccion_max']:.2f}"
            )

        elif "umbral_emg_calculado" in data:
            lbl_umbral_emg.config(
                text=f"Umbral EMG: {data['umbral_emg']:.2f}"
            )
            lbl_formula_emg.config(
                text="Criterio EMG: Umbral EMG = reposo + 0.40 x (contracción - reposo)"
            )

        elif "resultado_silencio" in data:
            lbl_silencio.config(
                text=f"Silencio prom: {data['energia_silencio_prom']:.6f} | Min: {data['energia_silencio_min']:.6f} | Max: {data['energia_silencio_max']:.6f}"
            )

        elif "resultado_comando" in data:
            lbl_comando.config(
                text=f"Comando prom: {data['energia_comando_prom']:.6f} | Min: {data['energia_comando_min']:.6f} | Max: {data['energia_comando_max']:.6f}"
            )

        elif "umbral_voz_calculado" in data:
            lbl_umbral_voz.config(
                text=f"Umbral voz: {data['umbral_voz']:.6f}"
            )
            lbl_formula_voz.config(
                text="Criterio voz: Umbral voz = (energía silencio + energía comando) / 2"
            )

        elif "sistema_listo" in data:
            lbl_fase.config(text="Fase: PRUEBA EMG + VOZ")
            lbl_cronometro.config(text="Sistema listo. Realiza las pruebas.")
            lbl_umbral_emg.config(text=f"Umbral EMG: {data['umbral_emg']:.2f}")
            lbl_umbral_voz.config(text=f"Umbral voz: {data['umbral_voz']:.6f}")

            lbl_estado_general.config(
                text="ESTADO: SISTEMA LISTO",
                bg="#616161",
                fg="white"
            )
            lbl_indicacion_general.config(
                text="Indicación: prueba reposo, solo EMG, solo voz y EMG + voz.",
                bg="#EEEEEE",
                fg="black"
            )

        elif "error" in data:
            lbl_conexion.config(text=f"ERROR: {data['error']}")
            lbl_estado_general.config(
                text="ESTADO: ERROR",
                bg="#B71C1C",
                fg="white"
            )
            lbl_indicacion_general.config(
                text="Error: revisa sensor, micrófono, puerto COM o calibración.",
                bg="#FFCDD2",
                fg="#B71C1C"
            )

        else:
            emg_actual = data["emg_actual"]
            emg_promedio_2s = data["emg_promedio_2s"]
            umbral_emg = data["umbral_emg"]
            energia = data["energia"]
            energia_promedio_2s = data["energia_promedio_2s"]
            umbral_voz = data["umbral_voz"]
            zcr = data["zcr"]
            zcr_promedio_2s = data["zcr_promedio_2s"]
            emg_activo = data["emg_activo"]
            voz_activa = data["voz_activa"]
            intensidad_emg = data["intensidad_emg"]
            estado = data["estado"]

            lbl_emg_actual.config(text=f"EMG actual: {emg_actual:.2f}")
            lbl_emg_2s.config(text=f"EMG promedio 2 s: {emg_promedio_2s:.2f}")
            lbl_emg.config(text=f"EMG: {'ACTIVO' if emg_activo else 'INACTIVO'}")
            lbl_intensidad.config(text=f"Intensidad: {intensidad_emg}")
            lbl_umbral_emg.config(text=f"Umbral EMG: {umbral_emg:.2f}")

            lbl_energia.config(text=f"Energía voz: {energia:.6f}")
            lbl_energia_2s.config(text=f"Energía promedio 2 s: {energia_promedio_2s:.6f}")
            lbl_zcr.config(text=f"ZCR: {zcr:.4f}")
            lbl_zcr_2s.config(text=f"ZCR promedio 2 s: {zcr_promedio_2s:.4f}")
            lbl_voz.config(text=f"Voz: {'DETECTADA' if voz_activa else 'NO DETECTADA'}")
            lbl_umbral_voz.config(text=f"Umbral voz: {umbral_voz:.6f}")

            ancho_emg = min(int((emg_actual / ESCALA_BARRA_EMG) * 300), 300)
            canvas_emg.coords(barra_emg, 10, 10, 10 + ancho_emg, 40)

            ancho_voz = min(int((energia / ESCALA_BARRA_VOZ) * 300), 300)
            canvas_voz.coords(barra_voz, 10, 10, 10 + ancho_voz, 40)

            if estado == "ACTIVADO":
                lbl_estado_general.config(
                    text="ESTADO: ACTIVADO",
                    bg="#2E7D32",
                    fg="white"
                )
                lbl_indicacion_general.config(
                    text="Acción permitida: EMG y voz detectados al mismo tiempo.",
                    bg="#C8E6C9",
                    fg="#1B5E20"
                )

            elif estado == "REPOSO":
                lbl_estado_general.config(
                    text="ESTADO: REPOSO / INACTIVO",
                    bg="#616161",
                    fg="white"
                )
                lbl_indicacion_general.config(
                    text="Sistema en reposo: no hay activación muscular ni comando de voz suficientes.",
                    bg="#EEEEEE",
                    fg="black"
                )

            elif estado == "FALTA VOZ":
                lbl_estado_general.config(
                    text="ESTADO: FALTA VOZ",
                    bg="#C62828",
                    fg="white"
                )
                lbl_indicacion_general.config(
                    text="Bloqueado: hay movimiento muscular, pero falta comando de voz.",
                    bg="#FFCDD2",
                    fg="#B71C1C"
                )

            elif estado == "FALTA MOVIMIENTO MUSCULAR":
                lbl_estado_general.config(
                    text="ESTADO: FALTA MOVIMIENTO MUSCULAR",
                    bg="#C62828",
                    fg="white"
                )
                lbl_indicacion_general.config(
                    text="Bloqueado: hay voz, pero falta activación muscular del antebrazo.",
                    bg="#FFCDD2",
                    fg="#B71C1C"
                )

    ventana.after(100, actualizar_gui)


def iniciar_prueba():
    global sujeto_actual

    sujeto = entrada_sujeto.get().strip()

    if sujeto == "":
        sujeto = "Sujeto"

    sujeto_actual = sujeto

    iniciar_calibracion.set()

    btn_iniciar.config(state="disabled")
    entrada_sujeto.config(state="disabled")

    lbl_cronometro.config(text="Iniciando calibración...")
    lbl_sujeto_activo.config(text=f"Sujeto activo: {sujeto_actual}")

    lbl_estado_general.config(
        text="ESTADO: INICIANDO CALIBRACIÓN",
        bg="#1565C0",
        fg="white"
    )
    lbl_indicacion_general.config(
        text="Indicación: iniciando calibración automática de EMG y voz.",
        bg="#E3F2FD",
        fg="#0D47A1"
    )


def cerrar_ventana():
    global ejecutando
    ejecutando = False
    iniciar_calibracion.set()
    ventana.destroy()


# =========================
# CREACIÓN DE LA VENTANA
# =========================

ventana = tk.Tk()
ventana.title("Interfaz humano-máquina EMG + Voz")
ventana.geometry("1040x850")
ventana.protocol("WM_DELETE_WINDOW", cerrar_ventana)

titulo = tk.Label(
    ventana,
    text="Interfaz humano-máquina por gestos con doble seguridad",
    font=("Arial", 18, "bold")
)
titulo.pack(pady=5)

subtitulo = tk.Label(
    ventana,
    text="Sistema bimodal: EMG del antebrazo + VAD básico por energía y ZCR",
    font=("Arial", 12)
)
subtitulo.pack(pady=1)

lbl_conexion = tk.Label(
    ventana,
    text="Conectando con ESP32...",
    font=("Arial", 11)
)
lbl_conexion.pack(pady=2)


# =========================
# PANEL DE CONTROL
# =========================

frame_control = tk.LabelFrame(
    ventana,
    text="Control de prueba",
    font=("Arial", 12, "bold"),
    padx=12,
    pady=5
)
frame_control.pack(pady=4, fill="x", padx=20)

lbl_id = tk.Label(
    frame_control,
    text="ID / Nombre del sujeto:",
    font=("Arial", 11)
)
lbl_id.grid(row=0, column=0, padx=5, pady=4, sticky="w")

entrada_sujeto = tk.Entry(
    frame_control,
    font=("Arial", 11),
    width=25
)
entrada_sujeto.insert(0, "Sujeto_01")
entrada_sujeto.grid(row=0, column=1, padx=5, pady=4)

btn_iniciar = tk.Button(
    frame_control,
    text="INICIAR CALIBRACIÓN",
    font=("Arial", 11, "bold"),
    width=22,
    bg="#1565C0",
    fg="white",
    command=iniciar_prueba
)
btn_iniciar.grid(row=0, column=2, padx=10, pady=4)

btn_salir = tk.Button(
    frame_control,
    text="DETENER / SALIR",
    font=("Arial", 11, "bold"),
    width=18,
    bg="#B71C1C",
    fg="white",
    command=cerrar_ventana
)
btn_salir.grid(row=0, column=3, padx=10, pady=4)

lbl_sujeto_activo = tk.Label(
    frame_control,
    text="Sujeto activo: ---",
    font=("Arial", 10),
    anchor="w"
)
lbl_sujeto_activo.grid(row=1, column=0, columnspan=2, padx=5, pady=3, sticky="w")

lbl_archivo = tk.Label(
    frame_control,
    text="Archivo CSV: todavía no creado",
    font=("Arial", 10),
    anchor="w"
)
lbl_archivo.grid(row=1, column=2, columnspan=2, padx=5, pady=3, sticky="w")


# =========================
# PANEL DE CALIBRACIÓN
# =========================

frame_calibracion = tk.LabelFrame(
    ventana,
    text="Calibración automática por sujeto",
    font=("Arial", 12, "bold"),
    padx=12,
    pady=5
)
frame_calibracion.pack(pady=4, fill="x", padx=20)

lbl_fase = tk.Label(
    frame_calibracion,
    text="Fase: iniciando",
    font=("Arial", 12, "bold"),
    anchor="w"
)
lbl_fase.pack(fill="x")

lbl_cronometro = tk.Label(
    frame_calibracion,
    text="Esperando conexión...",
    font=("Arial", 12),
    anchor="w"
)
lbl_cronometro.pack(fill="x", pady=1)

lbl_valor_calibracion = tk.Label(
    frame_calibracion,
    text="EMG calibración: ---",
    font=("Arial", 9),
    anchor="w"
)
lbl_valor_calibracion.pack(fill="x", pady=1)

lbl_reposo = tk.Label(
    frame_calibracion,
    text="Reposo prom: ---",
    font=("Arial", 9),
    anchor="w"
)
lbl_reposo.pack(fill="x", pady=1)

lbl_contraccion = tk.Label(
    frame_calibracion,
    text="Contracción prom: ---",
    font=("Arial", 9),
    anchor="w"
)
lbl_contraccion.pack(fill="x", pady=1)

lbl_formula_emg = tk.Label(
    frame_calibracion,
    text="Criterio EMG: pendiente de calibración",
    font=("Arial", 9),
    anchor="w"
)
lbl_formula_emg.pack(fill="x", pady=1)

lbl_valor_voz_calibracion = tk.Label(
    frame_calibracion,
    text="Voz calibración: ---",
    font=("Arial", 9),
    anchor="w"
)
lbl_valor_voz_calibracion.pack(fill="x", pady=1)

lbl_silencio = tk.Label(
    frame_calibracion,
    text="Silencio prom: ---",
    font=("Arial", 9),
    anchor="w"
)
lbl_silencio.pack(fill="x", pady=1)

lbl_comando = tk.Label(
    frame_calibracion,
    text="Comando prom: ---",
    font=("Arial", 9),
    anchor="w"
)
lbl_comando.pack(fill="x", pady=1)

lbl_formula_voz = tk.Label(
    frame_calibracion,
    text="Criterio voz: pendiente de calibración",
    font=("Arial", 9),
    anchor="w"
)
lbl_formula_voz.pack(fill="x", pady=1)


# =========================
# INDICADOR PRINCIPAL VISIBLE
# =========================

lbl_estado_general = tk.Label(
    frame_calibracion,
    text="ESTADO: ESPERA",
    font=("Arial", 20, "bold"),
    width=60,
    height=2,
    bg="#616161",
    fg="white"
)
lbl_estado_general.pack(pady=5)

lbl_indicacion_general = tk.Label(
    frame_calibracion,
    text="Indicación: esperando inicio del sistema.",
    font=("Arial", 12, "bold"),
    width=100,
    height=2,
    bg="#EEEEEE",
    fg="black"
)
lbl_indicacion_general.pack(pady=3)


# =========================
# PANEL DE DATOS
# =========================

frame_datos = tk.Frame(ventana)
frame_datos.pack(pady=4)

frame_emg = tk.LabelFrame(
    frame_datos,
    text="Señal EMG",
    font=("Arial", 12, "bold"),
    padx=15,
    pady=6
)
frame_emg.grid(row=0, column=0, padx=15)

lbl_emg_actual = tk.Label(frame_emg, text="EMG actual: ---", font=("Arial", 11), width=32, anchor="w")
lbl_emg_actual.pack(pady=1)

lbl_emg_2s = tk.Label(frame_emg, text="EMG promedio 2 s: ---", font=("Arial", 11), width=32, anchor="w")
lbl_emg_2s.pack(pady=1)

lbl_emg = tk.Label(frame_emg, text="EMG: ---", font=("Arial", 11), width=32, anchor="w")
lbl_emg.pack(pady=1)

lbl_intensidad = tk.Label(frame_emg, text="Intensidad: ---", font=("Arial", 11), width=32, anchor="w")
lbl_intensidad.pack(pady=1)

lbl_umbral_emg = tk.Label(frame_emg, text="Umbral EMG: ---", font=("Arial", 9), width=32, anchor="w")
lbl_umbral_emg.pack(pady=1)

canvas_emg = tk.Canvas(frame_emg, width=320, height=45, bg="white")
canvas_emg.pack(pady=3)
canvas_emg.create_rectangle(10, 10, 310, 35, outline="black")
barra_emg = canvas_emg.create_rectangle(10, 10, 10, 35, fill="#1565C0")


frame_voz = tk.LabelFrame(
    frame_datos,
    text="Señal de voz",
    font=("Arial", 12, "bold"),
    padx=15,
    pady=6
)
frame_voz.grid(row=0, column=1, padx=15)

lbl_energia = tk.Label(frame_voz, text="Energía voz: ---", font=("Arial", 11), width=32, anchor="w")
lbl_energia.pack(pady=1)

lbl_energia_2s = tk.Label(frame_voz, text="Energía promedio 2 s: ---", font=("Arial", 11), width=32, anchor="w")
lbl_energia_2s.pack(pady=1)

lbl_zcr = tk.Label(frame_voz, text="ZCR: ---", font=("Arial", 11), width=32, anchor="w")
lbl_zcr.pack(pady=1)

lbl_zcr_2s = tk.Label(frame_voz, text="ZCR promedio 2 s: ---", font=("Arial", 11), width=32, anchor="w")
lbl_zcr_2s.pack(pady=1)

lbl_voz = tk.Label(frame_voz, text="Voz: ---", font=("Arial", 11), width=32, anchor="w")
lbl_voz.pack(pady=1)

lbl_umbral_voz = tk.Label(frame_voz, text="Umbral voz: ---", font=("Arial", 9), width=32, anchor="w")
lbl_umbral_voz.pack(pady=1)

canvas_voz = tk.Canvas(frame_voz, width=320, height=45, bg="white")
canvas_voz.pack(pady=3)
canvas_voz.create_rectangle(10, 10, 310, 35, outline="black")
barra_voz = canvas_voz.create_rectangle(10, 10, 10, 35, fill="#6A1B9A")


nota = tk.Label(
    ventana,
    text="La activación ocurre solo si EMG y voz coinciden en la misma ventana temporal.",
    font=("Arial", 9)
)
nota.pack(pady=2)


# =========================
# INICIAR HILO Y GUI
# =========================

hilo = threading.Thread(target=hilo_adquisicion, daemon=True)
hilo.start()

actualizar_gui()
ventana.mainloop()