import asyncio
import logging
from aiortc_connection import AiortcConnection
from aiohttp import web
from constants import IP_ADDRESS

logging.basicConfig(level=logging.INFO)

HOST = IP_ADDRESS["localhost"]
connection = AiortcConnection(HOST)
connection.create_peer_connection()
connection.create_data_channel()


async def index(request):
    logging.info("index.html requested")
    content = open("index.html", "r").read()
    return web.Response(content_type="text/html", text=content)


async def javascript(request):
    content = open("script.js", "r").read()
    return web.Response(content_type="application/javascript", text=content)


async def call(request):
    global connection
    await connection.connect_to_websocket()
    connection.start_signaling()
    # NOTE: media should ideally be created with pc and dc,
    # but due to frame drop error from ffmpeg spamming logs,
    # media is created when call is made
    # TODO: can find a way to silence ffmpeg logs
    connection.get_media()
    await connection.send_offer()
    return web.Response(text="ok")


async def hangup(request):
    global connection
    connection.stop_signaling()
    await connection.disconnect_from_websocket()
    # clear pc, dc, media, restart pc, dc
    await connection.clear()
    connection.create_peer_connection()
    connection.create_data_channel()
    return web.Response(text="ok")


async def send_message(request):
    global connection
    data = await request.json()
    connection.send_message(data["message"])
    return web.Response(text="ok")


if __name__ == "__main__":
    try:
        app = web.Application()
        app.router.add_get("/", index)
        app.router.add_get("/script.js", javascript)
        app.router.add_post("/send_message", send_message)
        app.router.add_post("/call", call)
        app.router.add_post("/hangup", hangup)
        web.run_app(app, host=HOST, port=5000)
    except KeyboardInterrupt:
        asyncio.run(connection.clear())
