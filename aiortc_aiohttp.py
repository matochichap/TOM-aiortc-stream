import asyncio
import logging
from aiortc_connection import AiortcConnection
from aiohttp import web
from constants import IP_ADDRESS

logging.basicConfig(level=logging.INFO)

HOST = IP_ADDRESS["localhost"]
connection = AiortcConnection(HOST)
is_calling = False


async def index(request):
    return web.FileResponse("./static/index.html")


async def call(request):
    global connection, is_calling
    if is_calling:
        logging.info("Already calling")
        return web.Response(text="Already calling")
    await connection.connect_to_websocket()
    connection.start_signaling()
    connection.create_peer_connection()
    connection.create_data_channel()
    connection.get_media()
    await connection.send_offer()
    is_calling = True
    return web.Response(text="ok")


async def hangup(request):
    global connection, is_calling
    connection.stop_signaling()
    await connection.disconnect_from_websocket()
    await connection.clear()
    is_calling = False
    return web.Response(text="ok")


async def send_message(request):
    global connection
    data = await request.json()
    try:
        connection.send_message(data["message"])
    except Exception as e:
        logging.error(f"Send message via data channel error: {e}")
    return web.Response(text="ok")


if __name__ == "__main__":
    try:
        app = web.Application()
        app.router.add_static("/static", "./static")
        app.router.add_get("/", index)
        app.router.add_post("/send_message", send_message)
        app.router.add_post("/call", call)
        app.router.add_post("/hangup", hangup)
        web.run_app(app, host=HOST, port=5000)
    except KeyboardInterrupt:
        asyncio.run(connection.clear())
