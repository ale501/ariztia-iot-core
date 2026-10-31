import cv2
import os
import time

CAMARA = 0
CARPETA = "dataset_pollitos"

INTERVALO = 0.5

os.makedirs(CARPETA, exist_ok=True)

cap = cv2.VideoCapture(CAMARA, cv2.CAP_DSHOW)

cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

if not cap.isOpened():
    print("ERROR: No se pudo abrir la cámara 0")
    exit()

contador = 0
ultimo_guardado = 0

print("=" * 60)
print("CAPTURA DATASET POLLITOS")
print("=" * 60)
print("Cámara: 0")
print("Q = salir")
print("S = guardar imagen manualmente")
print("=" * 60)

while True:

    ret, frame = cap.read()

    if not ret:
        print("ERROR leyendo cámara")
        break

    ahora = time.time()

    # Captura automática
    if ahora - ultimo_guardado >= INTERVALO:

        nombre = os.path.join(
            CARPETA,
            f"pollito_{contador:05d}.jpg"
        )

        cv2.imwrite(nombre, frame)

        contador += 1
        ultimo_guardado = ahora

        print(f"Guardada: {nombre}")

    texto = f"IMAGENES: {contador}"

    cv2.putText(
        frame,
        texto,
        (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 255, 0),
        2
    )

    cv2.putText(
        frame,
        "Q = SALIR | S = GUARDAR",
        (20, 80),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 255),
        2
    )

    cv2.imshow("Captura Dataset Pollitos", frame)

    tecla = cv2.waitKey(1) & 0xFF

    if tecla == ord("q"):
        break

    elif tecla == ord("s"):

        nombre = os.path.join(
            CARPETA,
            f"manual_{contador:05d}.jpg"
        )

        cv2.imwrite(nombre, frame)

        contador += 1

        print(f"Guardada manualmente: {nombre}")

cap.release()
cv2.destroyAllWindows()

print()
print("CAPTURA TERMINADA")
print(f"Total aproximado: {contador}")
