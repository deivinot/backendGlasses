from flask import Flask, jsonify, request
import threading
import asyncio
import json
import websockets
from g3pylib import connect_to_glasses
from g3pylib.calibrate import Calibrate
from g3pylib.g3typing import URI


app = Flask(__name__)

LIVE_FRAME_RATE = 25
WEBSOCKET_PORT = 8765
connected_clients = set()

# Variables de control
glasses_instance = None
stream_running = True
stream_task = None
loop = None
websocket_server = None

# WebSocket broadcast
async def broadcast_to_clients(message: str):
    disconnected = set()
    for client in connected_clients:
        try:
            await client.send(message)
        except websockets.exceptions.ConnectionClosed:
            disconnected.add(client)
    connected_clients.difference_update(disconnected)

# WebSocket handler
async def websocket_handler(websocket):  #path
    print("Cliente conectado")
    connected_clients.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        print("Cliente desconectado")
        connected_clients.remove(websocket)

# Streaming async loop
async def start_live_stream_async():
    global websocket_server, glasses_instance
    if glasses_instance is None:
        print("Error: Las gafas no están conectadas.")
        return
    websocket_server = await websockets.serve(websocket_handler, "localhost", WEBSOCKET_PORT)
    print(f"WebSocket server escuchando en ws://localhost:{WEBSOCKET_PORT}")
    async with glasses_instance.stream_rtsp(scene_camera=True, gaze=True) as streams:
        async with streams.scene_camera.decode() as scene_stream, streams.gaze.decode() as gaze_stream:
            print("Modo live iniciado.")
            while stream_running:
                latest_frame = await scene_stream.get()
                if latest_frame[1] is None:
                    continue

                latest_gaze = await gaze_stream.get()
                if latest_gaze[1] is None:
                    continue

                while latest_gaze[1] < latest_frame[1]:
                    latest_gaze = await gaze_stream.get()

                gaze_data = latest_gaze[0]

                if "gaze2d" in gaze_data:
                    gaze_point = gaze_data["gaze2d"]
                    await broadcast_to_clients(json.dumps({
                        "x": gaze_point[0],
                        "y": gaze_point[1],
                        "timestamp": latest_gaze[1]
                    }))
                else:
                    await broadcast_to_clients(json.dumps({
                        "x": -1,
                        "y": -1,
                        "timestamp": latest_gaze[1]
                    }))

# Stream Thread
def stream_thread():
    global loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(start_live_stream_async())
    except RuntimeError as e:

        print(f"Loop detenido: {e}")
        loop.close()

    finally:
        loop.close()

# Endpoint para conectar gafas
@app.route("/connect", methods=["POST"])
def connect_glasses():
    global glasses_instance
    try:
        glasses_instance = asyncio.run(connect_to_glasses.with_hostname("192.168.75.51").__aenter__())
        return jsonify({"status": f"Conectado a 192.168.75.51"}), 200
    except Exception as e:
        return jsonify({"status": f"Error conectando: {str(e)}"}), 500

# Endpoint para desconectar gafas
@app.route("/disconnect", methods=["POST"])
def disconnect_glasses():
    global glasses_instance
    try:
        if glasses_instance:
            if hasattr(glasses_instance, "_connection"):
                try:
                    glasses_instance._connection.close()
                except Exception as e:
                    print(f"Error al cerrar conexión forzadamente: {e}")
            glasses_instance = None
            return jsonify({"status": "Gafas desconectadas"}), 200
        else:
            return jsonify({"status": "No había conexión activa con las gafas"}), 400
    except Exception as e:
        print(f"Error al desconectar las gafas: {e}")
        return jsonify({"status": "Error al desconectar las gafas"}), 500

# Iniciar stream
@app.route("/start", methods=["POST"])
def start_stream():
    global stream_running, stream_task

    if glasses_instance is None:
        return jsonify({"status": "Las gafas no están conectadas"}), 400

    stream_running = True
    stream_task = threading.Thread(target=stream_thread)
    stream_task.start()

    return jsonify({"status": "Stream iniciado"}), 200

# Detener stream
@app.route("/stop", methods=["POST"])
def stop_stream():
    global stream_running, stream_task, loop, websocket_server

    if not stream_running or stream_task is None:
        return jsonify({"status": "No estaba en marcha"}), 400

    stream_running = False

    if websocket_server and loop and loop.is_running():
        async def close_ws():
            websocket_server.close()
            await websocket_server.wait_closed()
            print("WebSocket cerrado correctamente")

        future = asyncio.run_coroutine_threadsafe(close_ws(), loop)
        try:
            future.result(timeout=5)
        except Exception as e:
            print(f"Error al cerrar WebSocket: {e}")

    loop.call_soon_threadsafe(loop.stop)
    stream_task.join()

    websocket_server = None
    stream_task = None
    loop = None

    return jsonify({"status": "Stream detenido"}), 200

# Calibrar
@app.route("/calibrate", methods=["POST"])
async def calibrate():
    resultado=None
    async with connect_to_glasses.with_hostname("192.168.75.51") as glasses:
        calibrator = Calibrate(glasses._connection, URI("/calibrate"))
        result = await calibrator.run()
        if result:
            resultado= "Calibración exitosa"
        else:
            resultado= "Fallo en la calibración"
    
    return jsonify({"status": resultado})



if __name__ == "__main__":
    app.run()
