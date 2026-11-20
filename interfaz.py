
"""Interfaz gráfica principal de EcoSuelo."""

import tkinter as tk
from tkinter import ttk, messagebox, font
import queue
import math
from pathlib import Path

from comunicacion import ComunicacionESP32


VERDE_OSCURO = "#075B2A"
VERDE_INTENSO = "#078A32"
VERDE_CLARO = "#EAF5EC"
VERDE_BORDE = "#C9E3CE"
BLANCO = "#FFFFFF"


def dibujar_redondeado(canvas, x1, y1, x2, y2, radio, **opciones):
    puntos = []
    esquinas = (
        (x2 - radio, y1 + radio, -90, 0),
        (x2 - radio, y2 - radio, 0, 90),
        (x1 + radio, y2 - radio, 90, 180),
        (x1 + radio, y1 + radio, 180, 270),
    )
    for centro_x, centro_y, inicio, fin in esquinas:
        for paso in range(7):
            angulo = math.radians(inicio + (fin - inicio) * paso / 6)
            puntos.extend((
                centro_x + radio * math.cos(angulo),
                centro_y + radio * math.sin(angulo)
            ))
    return canvas.create_polygon(
        puntos, smooth=True, splinesteps=12, **opciones
    )


class BotonRedondeado(tk.Canvas):
    def __init__(self, parent, text, command, primary=False, width=150):
        super().__init__(
            parent,
            width=width,
            height=40,
            bg=BLANCO,
            highlightthickness=0,
            bd=0
        )
        self.text = text
        self.command = command
        self.primary = primary
        self.state = "normal"
        self.bind("<Configure>", self._dibujar)
        self.bind("<Button-1>", self._activar)
        self.bind("<Enter>", self._dibujar)
        self.bind("<Leave>", self._dibujar)
        self.configure(cursor="hand2")
        self._dibujar()

    def config(self, **opciones):
        if "text" in opciones:
            self.text = opciones.pop("text")
        if "state" in opciones:
            self.state = opciones.pop("state")
        if opciones:
            super().configure(**opciones)
        self._dibujar()

    configure = config

    def _dibujar(self, _evento=None):
        self.delete("boton")
        ancho = max(self.winfo_width(), int(self.cget("width")))
        alto = max(self.winfo_height(), int(self.cget("height")))
        deshabilitado = self.state == "disabled"
        hover = self.winfo_containing(
            self.winfo_pointerx(), self.winfo_pointery()
        ) is self

        if deshabilitado:
            fondo, texto, borde = VERDE_CLARO, VERDE_OSCURO, VERDE_CLARO
        elif self.primary:
            fondo = VERDE_OSCURO if hover else VERDE_INTENSO
            texto, borde = BLANCO, fondo
        else:
            fondo = BLANCO if hover else VERDE_CLARO
            texto, borde = VERDE_OSCURO, VERDE_BORDE

        dibujar_redondeado(
            self, 1, 1, ancho - 2, alto - 2, 12,
            fill=fondo, outline=borde, width=2, tags="boton"
        )
        self.create_text(
            ancho / 2, alto / 2, text=self.text,
            fill=texto, font=("Arial", 11, "bold"), tags="boton"
        )

    def _activar(self, _evento):
        if self.state != "disabled":
            self.command()


class AplicacionEcoSuelo:

    def __init__(self, ventana):
        self.ventana = ventana
        self.ventana.title("EcoSuelo - Monitoreo de humedad")
        self.ventana.geometry("1050x790")
        self.ventana.minsize(850, 700)

        self.comunicacion = ComunicacionESP32()
        self.conectado = False
        self.monitoreando = False
        self.mediciones = []

        self.crear_interfaz()
        self.actualizar_puertos()

        self.ventana.after(200, self.procesar_eventos)
        self.ventana.protocol("WM_DELETE_WINDOW", self.cerrar)

    def crear_interfaz(self):
        self.ventana.configure(bg=BLANCO)
        estilo = ttk.Style(self.ventana)
        estilo.theme_use("clam")
        estilo.configure(
            "Eco.TLabel", background=BLANCO, foreground=VERDE_OSCURO,
            font=("Arial", 10)
        )
        estilo.configure(
            "Eco.TEntry", fieldbackground=BLANCO, foreground=VERDE_OSCURO,
            bordercolor=VERDE_BORDE, lightcolor=VERDE_INTENSO,
            darkcolor=VERDE_BORDE, padding=5
        )
        estilo.configure(
            "Eco.TCombobox", fieldbackground=BLANCO, foreground=VERDE_OSCURO,
            background=BLANCO, bordercolor=VERDE_BORDE,
            lightcolor=VERDE_INTENSO, darkcolor=VERDE_BORDE, padding=4
        )
        estilo.map(
            "Eco.TCombobox",
            fieldbackground=[("readonly", BLANCO)],
            foreground=[("readonly", VERDE_OSCURO)]
        )
        estilo.configure(
            "Eco.Treeview", background=BLANCO, fieldbackground=BLANCO,
            foreground=VERDE_OSCURO, rowheight=30,
            bordercolor=VERDE_BORDE, borderwidth=1, relief="solid",
            font=("Arial", 10)
        )
        estilo.configure(
            "Eco.Treeview.Heading", background=VERDE_OSCURO,
            foreground=BLANCO, font=("Arial", 10, "bold"), padding=(8, 6),
            bordercolor=VERDE_BORDE, borderwidth=1, relief="solid"
        )
        estilo.map(
            "Eco.Treeview.Heading",
            background=[("active", VERDE_INTENSO)]
        )
        estilo.map(
            "Eco.Treeview",
            background=[("selected", VERDE_CLARO)],
            foreground=[("selected", VERDE_OSCURO)]
        )
        estilo.configure("Eco.TFrame", background=BLANCO)
        estilo.configure(
            "Eco.Vertical.TScrollbar",
            troughcolor=BLANCO,
            background=VERDE_OSCURO,
            darkcolor=VERDE_OSCURO,
            lightcolor=VERDE_INTENSO,
            bordercolor=VERDE_OSCURO,
            arrowcolor=BLANCO
        )

        contenedor = ttk.Frame(self.ventana, style="Eco.TFrame")
        contenedor.pack(fill="both", expand=True)
        self.canvas_contenido = tk.Canvas(
            contenedor, bg=BLANCO, highlightthickness=0, bd=0
        )
        self.canvas_contenido.pack(side="left", fill="both", expand=True)
        self.barra_desplazamiento = ttk.Scrollbar(
            contenedor,
            orient="vertical",
            command=self.canvas_contenido.yview,
            style="Eco.Vertical.TScrollbar"
        )
        self.barra_desplazamiento.pack(side="right", fill="y")
        self.canvas_contenido.configure(
            yscrollcommand=self.barra_desplazamiento.set
        )
        self.contenido_principal = ttk.Frame(
            self.canvas_contenido, style="Eco.TFrame"
        )
        self.ventana_contenido = self.canvas_contenido.create_window(
            (0, 0), window=self.contenido_principal, anchor="nw"
        )
        self.contenido_principal.bind(
            "<Configure>", self._actualizar_region_desplazamiento
        )
        self.canvas_contenido.bind(
            "<Configure>", self._ajustar_ancho_contenido
        )
        self.ventana.bind_all("<MouseWheel>", self._desplazar_rueda)
        self.ventana.bind_all("<Button-4>", self._desplazar_rueda_linux)
        self.ventana.bind_all("<Button-5>", self._desplazar_rueda_linux)

        encabezado = tk.Frame(
            self.contenido_principal, bg=VERDE_OSCURO, height=104
        )
        encabezado.pack(fill="x")
        encabezado.pack_propagate(False)
        logo_original = tk.PhotoImage(
            file=str(Path(__file__).with_name("logo_ecosuelo.png"))
        )
        self.logo_ecosuelo = logo_original.subsample(8, 8)
        for y in range(self.logo_ecosuelo.height()):
            for x in range(self.logo_ecosuelo.width()):
                if all(color >= 245 for color in self.logo_ecosuelo.get(x, y)):
                    self.logo_ecosuelo.transparency_set(x, y, True)
        tk.Label(
            encabezado, image=self.logo_ecosuelo, bg=VERDE_OSCURO, bd=0
        ).place(relx=1.0, rely=0.5, x=-12, anchor="e")
        tk.Label(
            encabezado, text="EcoSuelo", bg=VERDE_OSCURO, fg=BLANCO,
            font=("Arial", 30, "bold")
        ).pack(pady=(12, 0))
        tk.Label(
            encabezado, text="Sistema de monitoreo de humedad del suelo",
            bg=VERDE_OSCURO, fg=BLANCO, font=("Arial", 12)
        ).pack(pady=(0, 8))

        self.contenedor_columnas = ttk.Frame(
            self.contenido_principal, style="Eco.TFrame"
        )
        self.contenedor_columnas.pack(fill="x", expand=True)
        self.contenedor_columnas.columnconfigure(
            0, weight=1, uniform="columnas"
        )
        self.contenedor_columnas.columnconfigure(
            1, weight=2, uniform="columnas"
        )
        self.columna_izquierda = ttk.Frame(
            self.contenedor_columnas, style="Eco.TFrame"
        )
        self.columna_izquierda.grid(
            row=0, column=0, sticky="nsew", padx=(12, 6)
        )
        self.columna_derecha = ttk.Frame(
            self.contenedor_columnas, style="Eco.TFrame"
        )
        self.columna_derecha.grid(
            row=0, column=1, sticky="nsew", padx=(6, 12)
        )

        conexion = self._crear_seccion(
            "Conexión USB / Bluetooth", 176,
            parent=self.columna_izquierda
        )
        conexion.columnconfigure(1, weight=1)
        ttk.Label(
            conexion, text="Puerto:", style="Eco.TLabel",
            font=("Arial", 10, "bold")
        ).grid(row=0, column=0, padx=(6, 8), pady=(6, 3), sticky="e")
        self.puerto = ttk.Combobox(
            conexion, state="readonly", width=16, style="Eco.TCombobox"
        )
        self.puerto.grid(row=0, column=1, padx=(0, 6), pady=(6, 3), sticky="ew")
        BotonRedondeado(
            conexion, "Actualizar", self.actualizar_puertos, width=110
        ).grid(row=1, column=0, padx=(6, 4), pady=3, sticky="ew")
        self.boton_conectar = BotonRedondeado(
            conexion, "Conectar", self.alternar_conexion,
            primary=True, width=110
        )
        self.boton_conectar.grid(
            row=1, column=1, padx=(4, 6), pady=3, sticky="ew"
        )
        self.estado = tk.Label(
            conexion, text="Desconectado", bg=VERDE_CLARO,
            fg=VERDE_OSCURO, font=("Arial", 10, "bold"),
            padx=8, pady=5
        )
        self.estado.grid(
            row=2, column=0, columnspan=2, padx=6, pady=(4, 6), sticky="ew"
        )

        configuracion = self._crear_seccion(
            "Configuración del monitoreo", 112,
            parent=self.columna_izquierda
        )
        configuracion.columnconfigure(1, weight=1)
        ttk.Label(
            configuracion,
            text="Intervalo entre mediciones (segundos):",
            style="Eco.TLabel", wraplength=150
        ).grid(row=0, column=0, padx=(8, 6), pady=6, sticky="w")
        self.intervalo = tk.StringVar(value="10")
        ttk.Entry(
            configuracion, textvariable=self.intervalo, width=7,
            style="Eco.TEntry"
        ).grid(row=0, column=1, padx=(0, 8), pady=6, sticky="ew")

        botones = self._crear_seccion(
            "Control del sistema", 190,
            parent=self.columna_izquierda
        )
        botones.columnconfigure(0, weight=1)
        self.boton_iniciar = BotonRedondeado(
            botones, "Iniciar mediciones", self.iniciar_monitoreo,
            primary=True, width=210
        )
        self.boton_iniciar.grid(
            row=0, column=0, padx=8, pady=3, sticky="ew"
        )
        self.boton_detener = BotonRedondeado(
            botones, "Detener mediciones", self.detener_monitoreo, width=210
        )
        self.boton_detener.grid(
            row=1, column=0, padx=8, pady=3, sticky="ew"
        )
        self.boton_servo = BotonRedondeado(
            botones, "Mover servomotor", self.mover_servo, width=210
        )
        self.boton_servo.grid(
            row=2, column=0, padx=8, pady=3, sticky="ew"
        )
        self.boton_iniciar.config(state="disabled")
        self.boton_detener.config(state="disabled")
        self.boton_servo.config(state="disabled")

        resultados = self._crear_seccion(
            "Última medición", 175, parent=self.columna_derecha
        )
        resultados.columnconfigure(0, weight=1)
        resultados.columnconfigure(1, weight=1)
        for columna, (titulo, atributo, inicial, tamano) in enumerate((
            ("ADC", "valor_adc", "ADC: --", 25),
            ("Humedad", "valor_humedad", "Humedad: -- %", 23)
        )):
            tarjeta = tk.Canvas(
                resultados, bg=BLANCO, height=104,
                highlightthickness=0, bd=0
            )
            tarjeta.grid(
                row=0, column=columna, padx=8, pady=(6, 4),
                sticky="nsew"
            )
            etiqueta_titulo = tk.Label(
                tarjeta, text=titulo, bg=VERDE_CLARO, fg=VERDE_OSCURO,
                font=("Arial", 11, "bold"), anchor="center"
            )
            etiqueta = tk.Label(
                tarjeta, text=inicial, bg=VERDE_CLARO,
                fg=VERDE_OSCURO, font=("Arial", tamano, "bold"),
                anchor="center"
            )
            ventana_titulo = tarjeta.create_window(
                0, 0, window=etiqueta_titulo, anchor="center"
            )
            ventana_valor = tarjeta.create_window(
                0, 0, window=etiqueta, anchor="center"
            )

            def ajustar_tarjeta(
                evento, lienzo=tarjeta, titulo_id=ventana_titulo,
                valor_id=ventana_valor, titulo_widget=etiqueta_titulo,
                valor_widget=etiqueta
            ):
                lienzo.delete("fondo_tarjeta")
                dibujar_redondeado(
                    lienzo, 1, 1, evento.width - 1, evento.height - 1, 12,
                    fill=VERDE_CLARO, outline=VERDE_BORDE, width=1,
                    tags="fondo_tarjeta"
                )
                lienzo.tag_lower("fondo_tarjeta")
                ancho_etiqueta = max(1, evento.width - 16)
                lienzo.itemconfigure(
                    titulo_id, width=ancho_etiqueta
                )
                lienzo.itemconfigure(
                    valor_id, width=ancho_etiqueta
                )
                titulo_widget.configure(wraplength=ancho_etiqueta)
                valor_widget.configure(wraplength=ancho_etiqueta)
                lienzo.coords(titulo_id, evento.width / 2, 27)
                lienzo.coords(valor_id, evento.width / 2, 68)

            tarjeta.bind("<Configure>", ajustar_tarjeta)
            setattr(self, atributo, etiqueta)

        self.valor_estado = tk.Label(
            resultados, text="Esperando medición...", bg=VERDE_CLARO,
            fg=VERDE_OSCURO, font=("Arial", 9, "bold"), pady=4,
            anchor="center"
        )
        self.valor_estado.grid(
            row=1, column=0, columnspan=2, padx=8, pady=(2, 4), sticky="ew"
        )

        historial = self._crear_seccion(
            "Historial de mediciones", 240, expand=True,
            parent=self.columna_derecha
        )

        columnas = ("numero", "adc", "humedad")

        self.tabla = ttk.Treeview(
            historial,
            columns=columnas,
            show="headings",
            height=5,
            style="Eco.Treeview"
        )
        self.scroll_historial = ttk.Scrollbar(
            historial,
            orient="vertical",
            command=self.tabla.yview,
            style="Eco.Vertical.TScrollbar"
        )
        self.tabla.configure(yscrollcommand=self.scroll_historial.set)
        self.tabla.tag_configure(
            "fila_blanca", background=BLANCO, foreground=VERDE_OSCURO
        )
        self.tabla.tag_configure(
            "fila_verde", background=VERDE_CLARO, foreground=VERDE_OSCURO
        )

        self.tabla.heading("numero", text="N.º", anchor="center")
        self.tabla.heading("adc", text="Lectura ADC", anchor="center")
        self.tabla.heading("humedad", text="Humedad (%)", anchor="center")

        self.tabla.column("numero", width=60, anchor="center", stretch=False)
        self.tabla.column("adc", width=130, anchor="center", stretch=True)
        self.tabla.column("humedad", width=130, anchor="center", stretch=True)
        self.tabla.pack(
            side="left", fill="both", expand=True, padx=(8, 0), pady=6
        )
        self.scroll_historial.pack(
            side="right", fill="y", padx=(0, 8), pady=6
        )

    def _crear_seccion(self, titulo, altura, expand=False, parent=None):
        canvas = tk.Canvas(
            parent or self.contenido_principal, height=altura, bg=BLANCO,
            highlightthickness=0, bd=0
        )
        canvas.pack(
            fill="both", expand=expand, padx=0, pady=6
        )
        contenido = tk.Frame(canvas, bg=BLANCO)
        ventana_contenido = canvas.create_window(
            12, 28, anchor="nw", window=contenido
        )

        def redibujar(evento):
            canvas.delete("decoracion")
            dibujar_redondeado(
                canvas, 1, 10, evento.width - 2, evento.height - 2, 14,
                fill=BLANCO, outline=VERDE_BORDE, width=1.2,
                tags="decoracion"
            )
            medida = font.Font(family="Arial", size=11, weight="bold")
            ancho_titulo = medida.measure(titulo) + 32
            dibujar_redondeado(
                canvas, 18, 0, 18 + ancho_titulo, 30, 12,
                fill=VERDE_OSCURO, outline=VERDE_OSCURO,
                tags="decoracion"
            )
            canvas.create_text(
                18 + ancho_titulo / 2, 14, text=titulo,
                fill=BLANCO, font=("Arial", 11, "bold"),
                tags="decoracion"
            )
            canvas.coords(ventana_contenido, 12, 29)
            canvas.itemconfigure(
                ventana_contenido,
                width=max(1, evento.width - 24),
                height=max(1, evento.height - 40)
            )
            canvas.tag_raise(ventana_contenido)

        canvas.bind("<Configure>", redibujar)
        return contenido

    def _actualizar_region_desplazamiento(self, _evento=None):
        self.canvas_contenido.configure(
            scrollregion=self.canvas_contenido.bbox("all")
        )

    def _ajustar_ancho_contenido(self, evento):
        self.canvas_contenido.itemconfigure(
            self.ventana_contenido, width=evento.width
        )

    def _desplazar_rueda(self, evento):
        if evento.delta:
            unidades = int(-evento.delta / 120)
            if unidades == 0:
                unidades = -1 if evento.delta > 0 else 1
            self.canvas_contenido.yview_scroll(unidades, "units")
        return "break"

    def _desplazar_rueda_linux(self, evento):
        if evento.num == 4:
            self.canvas_contenido.yview_scroll(-1, "units")
        elif evento.num == 5:
            self.canvas_contenido.yview_scroll(1, "units")
        return "break"

    # ACTUALIZAR PUERTOS
    def actualizar_puertos(self):
        try:
            puertos = self.comunicacion.listar_puertos()
            self.puerto["values"] = puertos

            if "COM6" in puertos:
                self.puerto.set("COM6")
            elif puertos:
                self.puerto.current(0)
            else:
                self.puerto.set("")

        except Exception as error:
            messagebox.showerror(
                "Error",
                f"No se pudieron consultar los puertos:\n{error}"
            )

    # CONECTAR Y DESCONECTAR
    def alternar_conexion(self):

        if not self.conectado:
            puerto = self.puerto.get()

            if not puerto:
                messagebox.showwarning(
                    "Puerto",
                    "Selecciona un puerto COM."
                )
                return

            try:
                self.comunicacion.conectar(puerto)

            except Exception as error:
                messagebox.showerror(
                    "Error de conexión",
                    str(error)
                )
                return

            self.estado.config(
                text="Conectando...",
                foreground=VERDE_INTENSO
            )
            self.boton_conectar.config(state="disabled")

        else:
            self.comunicacion.desconectar()

            self.conectado = False
            self.monitoreando = False

            self.estado.config(
                text="Desconectado",
                foreground=VERDE_OSCURO
            )

            self.boton_conectar.config(
                text="Conectar",
                state="normal"
            )

            self.boton_iniciar.config(state="disabled")
            self.boton_detener.config(state="disabled")
            self.boton_servo.config(state="disabled")

    # INICIAR MEDICIONES
    def iniciar_monitoreo(self):

        if not self.conectado:
            return

        try:
            segundos = float(self.intervalo.get())

            if segundos < 1 or segundos > 86400:
                raise ValueError

        except ValueError:
            messagebox.showwarning(
                "Intervalo inválido",
                "Introduce un intervalo entre 1 y 86400 segundos."
            )
            return

        try:
            self.comunicacion.enviar({
                "command": "start",
                "interval_ms": round(segundos * 1000)
            })

            self.monitoreando = True

            self.boton_iniciar.config(state="disabled")
            self.boton_detener.config(state="normal")
            self.boton_servo.config(state="disabled")

            self.valor_estado.config(
                text="Monitoreo iniciado..."
            )

        except Exception as error:
            messagebox.showerror("Error", str(error))

    # DETENER MEDICIONES
    def detener_monitoreo(self):

        try:
            self.comunicacion.enviar({
                "command": "stop"
            })

        except Exception as error:
            messagebox.showerror("Error", str(error))
            return

        self.monitoreando = False

        self.boton_iniciar.config(
            state="normal" if self.conectado else "disabled"
        )
        self.boton_detener.config(state="disabled")
        self.boton_servo.config(
            state="normal" if self.conectado else "disabled"
        )

        self.valor_estado.config(
            text="Monitoreo detenido"
        )

    # MOVER SERVOMOTOR MANUALMENTE
    
    def mover_servo(self):
        if not self.conectado:
            return

        if self.monitoreando:
            messagebox.showwarning(
                "Monitoreo activo",
                "Detén las mediciones antes de mover el servo."
            )
            return

        try:
            self.comunicacion.enviar({"command": "servo"})
            self.valor_estado.config(
                text="Servo moviéndose a 30 grados..."
            )
        except Exception as error:
            messagebox.showerror(
                "Error del servomotor",
                str(error)
            )
    def procesar_eventos(self):
        while True:
            try:
                mensaje = self.comunicacion.eventos.get_nowait()
    
            except queue.Empty:
                break

            tipo = mensaje.get("type")

            if tipo == "connection":

                if mensaje.get("connected"):
                    self.conectado = True

                    self.estado.config(
                        text="Conectado",
                        foreground=VERDE_INTENSO
                    )

                    self.boton_conectar.config(
                        text="Desconectar",
                        state="normal"
                    )

                    self.boton_iniciar.config(state="normal")
                    self.boton_servo.config(state="normal")

                else:
                    self.conectado = False
                    self.monitoreando = False

                    self.estado.config(
                        text="Desconectado",
                        foreground=VERDE_OSCURO
                    )

                    self.boton_conectar.config(
                        text="Conectar",
                        state="normal"
                    )

                    self.boton_iniciar.config(state="disabled")
                    self.boton_detener.config(state="disabled")
                    self.boton_servo.config(state="disabled")

            elif tipo == "status":

                self.conectado = mensaje.get("connected", False)
                self.monitoreando = mensaje.get("monitoring", False)

                if self.conectado:

                    self.estado.config(
                        text="Conectado",
                        foreground=VERDE_INTENSO
                    )

                    self.boton_conectar.config(
                        text="Desconectar",
                        state="normal"
                    )

                    self.boton_iniciar.config(
                        state="disabled" if self.monitoreando else "normal"
                    )

                    self.boton_detener.config(
                        state="normal" if self.monitoreando else "disabled"
                    )

                    self.boton_servo.config(
                        state="disabled" if self.monitoreando else "normal"
                    )

            elif tipo == "measurement":
                self.registrar_medicion(mensaje)

            elif tipo == "error":
                messagebox.showerror(
                    "Error del ESP32",
                    mensaje.get("message", "Error desconocido")
                )

                if not self.monitoreando and self.conectado:
                    self.boton_servo.config(state="normal")

        self.ventana.after(200, self.procesar_eventos)

    # REGISTRAR MEDICIONES
    def registrar_medicion(self, mensaje):

        adc = mensaje.get("adc")
        humedad = mensaje.get("humidity")

        if adc is None or humedad is None:
            return

        numero = len(self.mediciones) + 1

        self.mediciones.append({
            "numero": numero,
            "adc": adc,
            "humedad": humedad
        })

        self.valor_adc.config(
            text=f"ADC: {adc}"
        )

        self.valor_humedad.config(
            text=f"Humedad: {humedad} %"
        )

        self.valor_estado.config(
            text="Medición recibida correctamente"
        )

        self.tabla.insert(
            "",
            "end",
            values=(numero, adc, humedad),
            tags=("fila_verde" if numero % 2 == 0 else "fila_blanca",)
        )

    # CERRAR APLICACIÓN
    def cerrar(self):

        try:
            self.comunicacion.desconectar()

        except Exception:
            pass

        self.ventana.destroy()


def iniciar_aplicacion():

    ventana = tk.Tk()
    AplicacionEcoSuelo(ventana)
    ventana.mainloop()


if __name__ == "__main__":
    iniciar_aplicacion()
