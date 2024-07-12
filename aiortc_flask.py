import logging
from aiortc_connection import AiortcConnection
from constants import IP_ADDRESS
from flask import Flask, request, jsonify, render_template

HOST = IP_ADDRESS["localhost"]
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

connection = AiortcConnection(HOST)
connection.create_peer_connection()
connection.create_data_channel()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/call", methods=["POST"])
async def call():
    global connection
    try:
        await connection.connect_to_websocket()
        connection.start_signaling()
        # NOTE: media should ideally be created with pc and dc,
        # but due to frame drop error from ffmpeg spamming logs,
        # media is created when call is made
        # TODO: can find a way to silence ffmpeg logs
        connection.get_media()
        await connection.send_offer()
    except Exception as e:
        logging.error(e)
        return jsonify({"status": "error"}), 400
    return jsonify({"status": "ok"}), 200


@app.route("/hangup", methods=["POST"])
async def hangup():
    global connection
    try:
        connection.stop_signaling()
        await connection.disconnect_from_websocket()
        # clear pc, dc, media, restart pc, dc
        await connection.clear()
        connection.create_peer_connection()
        connection.create_data_channel()
    except Exception as e:
        logging.error(e)
        return jsonify({"status": "error"}), 400
    return jsonify({"status": "ok"}), 200


@app.route("/send_message", methods=["POST"])
def send_message():
    global connection
    data = request.json
    try:
        connection.send_message(data["message"])
    except Exception as e:
        logging.error(e)
        return jsonify({"status": "error"}), 400
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    try:
        app.run(host=HOST, port=5000)
    except KeyboardInterrupt:
        logging.info("Server stopped")
