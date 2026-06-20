# **Proyecto Final PSB - EMG + Voz**

## Descripción general



Este proyecto implementa una interfaz humano-máquina por gestos con doble seguridad, utilizando una señal EMG del antebrazo y una señal de voz capturada mediante el micrófono de la computadora.



El sistema permite simular la activación de un actuador virtual solamente cuando se detectan dos condiciones al mismo tiempo:



1. Activación muscular del antebrazo mediante EMG.
2. Comando de voz detectado mediante energía de la señal y ZCR.



Si una de las dos condiciones no se cumple, la GUI bloquea la activación e indica el motivo.



#### Hardware utilizado

* ESP32 WROOM
* MyoWare Muscle Sensor
* Electrodos adhesivos
* Protoboard
* Cable USB
* Micrófono de la computadora
* Computadora con Python



#### Conexión del MyoWare al ESP32

* MyoWare VIN -> ESP32 3V3
* MyoWare GND -> ESP32 GND
* MyoWare ENV -> ESP32 GPIO34



#### Colores de cables utilizados

* Cable amarillo -> VIN
* Cable naranja -> GND
* Cable rojo -> ENV



#### Comunicación

El ESP32 se comunica con Python mediante el puerto serial COM4 a 115200 baudios.



#### Software utilizado

* Python 3
* pyserial
* sounddevice
* numpy
* tkinter
* csv
* Arduino IDE



#### Archivo principal



El archivo principal del sistema es:



##### gui\_emg\_voz.py



Este archivo contiene la GUI principal, la calibración automática de EMG, la calibración automática de voz, el procesamiento en tiempo real, la lógica de decisión y el guardado de resultados en CSV.



#### Archivos de apoyo



##### leer\_emg\_serial.py



Archivo utilizado para comprobar la lectura serial del ESP32.



##### integracion\_emg\_voz.py



Archivo de prueba para integrar EMG y voz antes de la GUI final.



##### listar\_microfonos.py



Archivo usado para identificar los dispositivos de entrada de audio disponibles.



##### probar\_microfonos\_todos.py



Archivo utilizado para probar diferentes micrófonos.



##### prueba\_voz\_vad.py



Archivo utilizado para probar la detección básica de voz mediante energía y ZCR.



## Ejecución del sistema



1. Conectar el ESP32 a la computadora.
2. Verificar que el puerto serial sea COM4.
3. Colocar el MyoWare Muscle Sensor sobre el antebrazo.
4. Abrir una terminal en la carpeta Software.
5. Ejecutar: 
	     **py gui\_emg\_voz.py**

6. Escribir el ID o nombre del sujeto.
7. Presionar el botón INICIAR CALIBRACIÓN.
8. Seguir las instrucciones de la GUI:
     Reposo EMG.
     Contracción EMG.
     Silencio ambiental.
     Comando de voz.
     Descanso.

9. Realizar las pruebas de activación.



### Calibración EMG



El sistema registra una etapa de reposo y una etapa de contracción voluntaria. A partir de estos valores se calcula un umbral individual para cada sujeto.



La fórmula utilizada es:



&#x09;**Umbral EMG = reposo + 0.40 x (contracción - reposo)**



El factor 0.40 permite aumentar la sensibilidad del prototipo. Este valor puede modificarse en el código mediante la variable:



&#x09;FACTOR\_UMBRAL\_EMG



Por ejemplo:



&#x09;FACTOR\_UMBRAL\_EMG = 0.40



Si se desea un criterio más estricto, puede cambiarse a:



FACTOR\_UMBRAL\_EMG = 0.50



### Calibración de voz



El sistema registra una etapa de silencio ambiental y una etapa de comando vocal. A partir de ambas etapas calcula un umbral de energía de voz.



La fórmula utilizada es:



&#x09;**Umbral voz = (energía silencio + energía comando) / 2**



Además, se utiliza la tasa de cruces por cero, ZCR, para validar que la señal detectada corresponda a un evento vocal.



Rango ZCR utilizado:



&#x09;ZCR\_MIN = 0.02

&#x09;ZCR\_MAX = 0.30



### Estados de la GUI



La interfaz muestra cuatro estados principales:



&#x09;**REPOSO / INACTIVO**



No hay activación muscular ni comando de voz suficientes.



&#x09;**FALTA VOZ**



Existe activación muscular, pero no se detecta comando de voz.



&#x09;**FALTA MOVIMIENTO MUSCULAR**



Existe voz detectada, pero no hay activación muscular suficiente.



&#x09;**ACTIVADO**



Se detecta activación muscular y voz al mismo tiempo. En este caso se permite la activación del actuador virtual.



### Resultados



Los resultados se guardan automáticamente en archivos CSV dentro de la carpeta:



Resultados



Cada archivo contiene:



* Fecha y hora.
* ID del sujeto.
* Datos de calibración EMG.
* Datos de calibración de voz.
* Umbral EMG.
* Umbral de voz.
* EMG actual.
* Promedio EMG de 2 segundos.
* Energía de voz.
* ZCR.
* Estado del sistema.



### Estructura de carpetas



**Proyecto\_Final\_PSB\_EMG\_Voz**/

│

├── **Hardware**/

│   ├── conexion\_hardware.txt

│   ├── diagrama\_conexion\_esp32\_myoware.png

│   ├── fotos del hardware

│   └── codigo ESP32

│

├── **Software**/

│   ├── gui\_emg\_voz.py

│   ├── leer\_emg\_serial.py

│   ├── integracion\_emg\_voz.py

│   ├── listar\_microfonos.py

│   ├── probar\_microfonos\_todos.py

│   └── prueba\_voz\_vad.py

│

├── **Capturas\_GUI**/

│   └── capturas de estados de la GUI

│

├── **Resultados**/

│   └── archivos CSV generados

│

├── **Reporte**/

│   └── reporte final en DOCX y PDF

│

└── **README.md**



###### Nota



Este prototipo fue desarrollado como proyecto final de Procesamiento de Señales Biomédicas. Su objetivo es demostrar la adquisición, procesamiento y fusión de dos señales: EMG y voz, para generar una acción de control con doble seguridad.
