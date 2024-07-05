from aiortc_server import AiortcServer
from aiohttp import web
from constants import IP_ADDRESS

HOST = IP_ADDRESS["localhost"]
server = None


async def index(request):
    content = open("index.html", "r").read()
    return web.Response(content_type="text/html", text=content)


async def javascript(request):
    content = open("script.js", "r").read()
    return web.Response(content_type="application/javascript", text=content)


async def start(request):
    global server
    server = AiortcServer(HOST)
    server.get_media(
        audio_src="Microphone Array (Realtek(R) Audio)", video_src="Webcam")
    await server.create_offer()
    return web.Response(text="ok")


async def send_message(request):
    global server
    if not server:
        print("Server not started")
        return web.Response(text="Server not started")
    data = await request.json()
    server.dc.send(data["message"])
    return web.Response(text="ok")


if __name__ == "__main__":
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/script.js", javascript)
    app.router.add_post("/send_message", send_message)
    app.router.add_post("/start", start)
    web.run_app(app, host=HOST, port=5000)
