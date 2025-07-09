import asyncio
import threading
import json
from tkinter import Tk, Canvas, Button, Label, filedialog
from g3pylib import connect_to_glasses
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

class GazeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Tobii Gaze Viewer")

        self.canvas = Canvas(root, width=524, height=250, bg="white")
        self.canvas.pack()

        self.label_status = Label(root, text="Estado: Desconectado")
        self.label_status.pack()

        self.btn_connect = Button(root, text="Conectar", command=self.connect)
        self.btn_connect.pack()

        self.btn_start = Button(root, text="Iniciar Stream", command=self.start_stream)
        self.btn_start.pack()

        self.btn_stop = Button(root, text="Detener Stream", command=self.stop_stream)
        self.btn_stop.pack()

        self.btn_save = Button(root, text="Guardar Datos", command=self.save_data)
        self.btn_save.pack()

        self.hostname = "192.168.75.51"  
        self.glasses = None
        self.stream_task = None
        self.running = False
        self.gaze_data = []

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service)

        driver.get("https://www.google.com")

        wait = WebDriverWait(driver, 10)

        input("Pulsa ENTER para cerrar el navegador y terminar el script...")
        driver.quit()

    def connect(self):
        asyncio.run(self.async_connect())

    async def async_connect(self):

        self.glasses = await connect_to_glasses.with_zeroconf()
        self.label_status.config(text="Estado: Conectado")

    def start_stream(self):
        if not self.glasses:
            self.label_status.config(text="Estado: No conectado")
            return
        self.running = True
        threading.Thread(target=self.asyncio_thread).start()

    def stop_stream(self):
        self.running = False
        self.label_status.config(text="Estado: Stream detenido")

    def save_data(self):
        if not self.gaze_data:
            return
        file_path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON files", "*.json")])
        if file_path:
            with open(file_path, "w") as f:
                json.dump(self.gaze_data, f, indent=2)

    def asyncio_thread(self):
        asyncio.run(self.stream_gaze())

    async def stream_gaze(self):
        async with self.glasses.stream_rtsp(scene_camera=False, gaze=True) as streams:
            async with streams.gaze.decode() as gaze_stream:
                self.label_status.config(text="Estado: Streaming")
                while self.running:
                    gaze_with_timestamp = await gaze_stream.get()
                    if gaze_with_timestamp:
                        gaze_info = gaze_with_timestamp[0]
                        timestamp = gaze_with_timestamp[1]
                        if "gaze2d" in gaze_info:
                            x = gaze_info["gaze2d"][0] * 524
                            y = gaze_info["gaze2d"][1] * 250
                            self.canvas.create_oval(x-5, y-5, x+5, y+5, fill="red")
                            self.gaze_data.append({
                                "x": gaze_info["gaze2d"][0],
                                "y": gaze_info["gaze2d"][1],
                                "timestamp": timestamp
                            })
                    await asyncio.sleep(0.01)

if __name__ == "__main__":
    root = Tk()
    app = GazeApp(root)
    root.mainloop()
