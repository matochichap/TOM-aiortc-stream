import asyncio
import logging
from aiortc_server import AiortcServer
from aiohttp import web
from constants import IP_ADDRESS

HOST = IP_ADDRESS["Galaxy S21 Ultra"]
server = AiortcServer(HOST)


async def index(request):
    content = open("index.html", "r").read()
    return web.Response(content_type="text/html", text=content)


async def javascript(request):
    content = open("script.js", "r").read()
    return web.Response(content_type="application/javascript", text=content)


async def call(request):
    global server
    await server.connect_to_websocket()
    server.start_signaling()
    server.create_peer_connection()
    server.create_data_channel()
    server.get_media(audio_src="Microphone (Realtek(R) Audio)",
                    video_src="FHD Webcam")
    # server.get_media(audio_src="Microphone Array (Realtek(R) Audio)",
    #                  video_src="Webcam")
    await server.create_offer()
    return web.Response(text="ok")


async def hangup(request):
    global server
    server.stop_signaling()
    await server.hangup()
    await server.disconnect_from_websocket()
    return web.Response(text="ok")


async def send_message(request):
    global server
    data = await request.json()
    server.send_message(data["message"])
    return web.Response(text="ok")


if __name__ == "__main__":
    try:
        logging.basicConfig(level=logging.INFO)
        app = web.Application()
        app.router.add_get("/", index)
        app.router.add_get("/script.js", javascript)
        app.router.add_post("/send_message", send_message)
        app.router.add_post("/call", call)
        app.router.add_post("/hangup", hangup)
        web.run_app(app, host=HOST, port=5000)
    except KeyboardInterrupt:
        asyncio.run(server.hangup())
