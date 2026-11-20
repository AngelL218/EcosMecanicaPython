"""Comunicacion Bluetooth/USB Serial para EcoSuelo."""
import json
import queue
import threading

import serial
from serial.tools import list_ports


def analizar_linea(linea):
    """Convierte una linea JSON en diccionario; ignora texto no JSON."""
    linea = linea.strip()
    if not linea.startswith("{") or not linea.endswith("}"):
        return None
    try:
        mensaje = json.loads(linea)
    except json.JSONDecodeError:
        return None
    if not isinstance(mensaje, dict) or not isinstance(mensaje.get("type"), str):
        return None
    return mensaje


class ComunicacionESP32:
    """Gestiona la conexion serie con el ESP32 sin bloquear la interfaz."""

    def __init__(self):
        self.eventos = queue.Queue()
        self._serial = None
        self._lock = threading.RLock()
        self._detener_lector = None
        self._lector = None

    @staticmethod
    def listar_puertos():
        """Devuelve los puertos COM disponibles."""
        try:
            return [p.device for p in list_ports.comports()]
        except (serial.SerialException, OSError) as error:
            raise RuntimeError(f"No se pudieron listar los puertos: {error}") from error

    @property
    def conectado(self):
        with self._lock:
            return self._serial is not None and self._serial.is_open

    @property
    def puerto_actual(self):
        with self._lock:
            if self._serial is not None and self._serial.is_open:
                return self._serial.port
            return None

    def conectar(self, puerto):
        """Abre el puerto Bluetooth y solicita el estado al ESP32."""
        if not puerto:
            raise RuntimeError("Selecciona un puerto COM.")

        self.desconectar()
        try:
            conexion = serial.Serial(
                port=puerto,
                baudrate=115200,
                timeout=0.25,
                write_timeout=3,
            )
        except (serial.SerialException, OSError) as error:
            raise RuntimeError(
                f"No se pudo abrir {puerto}. Comprueba que esté emparejado "
                f"y que ningún otro programa esté usando el puerto. Detalle: {error}"
            ) from error

        detener = threading.Event()
        lector = threading.Thread(
            target=self._leer,
            args=(conexion, detener),
            daemon=True,
            name=f"EcoSuelo-{puerto}",
        )

        with self._lock:
            self._serial = conexion
            self._detener_lector = detener
            self._lector = lector

        self.eventos.put({
            "type": "connection",
            "connected": True,
            "port": puerto,
        })

        lector.start()
        try:
            self.enviar({"command": "status"})
        except RuntimeError:
            self.desconectar()

    def desconectar(self):
        """Cierra la conexión con el ESP32."""

        with self._lock:
            conexion = self._serial
            detener = self._detener_lector

            self._serial = None
            self._detener_lector = None
            self._lector = None

        if detener is not None:
            detener.set()

        if conexion is not None:
            try:
                if conexion.is_open:
                    conexion.close()
            except (serial.SerialException, OSError):
                pass

        self.eventos.put({
            "type": "connection",
            "connected": False
        })


    def enviar(self, comando):
        """Envía un comando JSON al ESP32."""
        if not isinstance(comando, dict):
            raise ValueError("El comando debe ser un diccionario.")

        error = None

        with self._lock:
            conexion = self._serial

            if conexion is None or not conexion.is_open:
                raise RuntimeError("No hay un ESP32 conectado.")

            try:
                mensaje = json.dumps(
                    comando,
                    ensure_ascii=False,
                    separators=(",", ":")
                ) + "\n"

                conexion.write(mensaje.encode("utf-8"))
                conexion.flush()

            except (serial.SerialException, OSError) as problema:
                error = problema

        if error is not None:
            self._cerrar_por_error(conexion, error)
            raise RuntimeError(
                f"Error al enviar datos al ESP32: {error}"
            ) from error



    def _leer(self, conexion, detener):
        """Lee los mensajes enviados por el ESP32."""
        while not detener.is_set():
            try:
                linea = conexion.readline()
            except (serial.SerialException, OSError) as error:
                if not detener.is_set():
                    self._cerrar_por_error(conexion, error)
                return

            if not linea:
                continue

            texto = linea.decode("utf-8", errors="replace").strip()

            try:
                mensaje = analizar_linea(texto)
            except (ValueError, TypeError):
                continue

            if mensaje is not None:
                self.eventos.put(mensaje)

    def _cerrar_por_error(self, conexion, error):
        """Cierra la conexión cuando ocurre un error de comunicación."""

        with self._lock:
            if self._serial is not conexion:
                return

            detener = self._detener_lector

            self._serial = None
            self._detener_lector = None
            self._lector = None

        if detener is not None:
            detener.set()

        try:
            if conexion.is_open:
                conexion.close()
        except (serial.SerialException, OSError):
            pass

        self.eventos.put({
            "type": "error",
            "message": f"Se perdió la comunicación con el ESP32: {error}"
        })

        self.eventos.put({
            "type": "connection",
            "connected": False
        })