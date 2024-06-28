import argparse
import asyncio
import json
import logging
import os
import platform
import ssl
import websockets

from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate
from aiortc.contrib.media import MediaPlayer, MediaRelay
from aiortc.rtcrtpsender import RTCRtpSender

ROOT = os.path.dirname(__file__)


relay = None
webcam = None
websocket = None
audio = None
video = None


def create_local_tracks(play_from, decode):
    global relay, webcam

    if play_from:
        player = MediaPlayer(play_from, decode=decode)
        return player.audio, player.video
    else:
        options = {"framerate": "30",
                   "video_size": "640x480"}
        if relay is None:
            if platform.system() == "Darwin":
                webcam = MediaPlayer(
                    "default:none", format="avfoundation", options=options
                )
            elif platform.system() == "Windows":
                video_src = "FHD Webcam"
                # video_src = "Webcam"
                options["pixel_format"] = "yuyv422"
                webcam = MediaPlayer(
                    f"video={video_src}", format="dshow", options=options
                )
            else:
                webcam = MediaPlayer(
                    "/dev/video0", format="v4l2", options=options)
            relay = MediaRelay()
        return None, relay.subscribe(webcam.video)


def force_codec(pc, sender, forced_codec):
    kind = forced_codec.split("/")[0]
    codecs = RTCRtpSender.getCapabilities(kind).codecs
    transceiver = next(t for t in pc.getTransceivers() if t.sender == sender)
    transceiver.setCodecPreferences(
        [codec for codec in codecs if codec.mimeType == forced_codec]
    )


async def consume_signaling(pc, websocket):
    while True:
        message = await websocket.recv()
        print("Received:", message)
        sdp_type, sdp = message.split("~")[:2]
        if sdp_type == "offer":
            offer = RTCSessionDescription(sdp=sdp, type=sdp_type)
            await pc.setRemoteDescription(offer)
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            answer = answer.type + "~" + answer.sdp
            await websocket.send(answer)
        elif sdp_type == "answer":
            sdp = RTCSessionDescription(sdp=sdp, type=sdp_type)
            await pc.setRemoteDescription(sdp)
        elif sdp_type == "candidate":
            sdp_type, candidate, sdp_mid, sdp_mline_index = message.split("~")
            foundation, component, protocol, priority, ip, port, _, _type = candidate.split()[
                :8]
            candidate = RTCIceCandidate(foundation=foundation, component=component, protocol=protocol,
                                        priority=priority, ip=ip, port=port, type=_type, sdpMid=sdp_mid, sdpMLineIndex=sdp_mline_index)
            await pc.addIceCandidate(candidate)


async def index(request):
    global websocket
    uri = "ws://127.0.0.1:5011/ws?type=w&uid=1&token=1234567890"
    websocket = await websockets.connect(uri)
    content = open(os.path.join(ROOT, "webcam.html"), "r").read()
    return web.Response(content_type="text/html", text=content)


async def javascript(request):
    content = open(os.path.join(ROOT, "webcam.js"), "r").read()
    return web.Response(content_type="application/javascript", text=content)


async def offer(request):
    global audio, video
    # params = await request.json()
    # offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        print("Connection state is %s" % pc.connectionState)
        if pc.connectionState == "failed":
            await pc.close()
            pcs.discard(pc)

    @pc.on("icecandidate")
    async def on_icecandidate(candidate):
        print("icecandidate event")
        print(candidate)
        if candidate:
            candidate = candidate.to_sdp()
            candidate = "candidate~" + candidate
            await websocket.send(candidate)

    # open media source
    audio, video = create_local_tracks(
        args.play_from, decode=not args.play_without_decoding
    )

    if audio:
        audio_sender = pc.addTrack(audio)
        if args.audio_codec:
            force_codec(pc, audio_sender, args.audio_codec)
        elif args.play_without_decoding:
            raise Exception(
                "You must specify the audio codec using --audio-codec")

    if video:
        video_sender = pc.addTrack(video)
        if args.video_codec:
            force_codec(pc, video_sender, args.video_codec)
        elif args.play_without_decoding:
            raise Exception(
                "You must specify the video codec using --video-codec")

    # send offer
    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    offer = offer.type + "~" + offer.sdp
    await websocket.send(offer)

    asyncio.create_task(consume_signaling(pc, websocket))

    return web.Response(
        content_type="application/json",
        # text=json.dumps(
        #     {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        # ),
    )


pcs = set()


async def on_shutdown(app):
    # close peer connections
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WebRTC webcam demo")
    parser.add_argument("--cert-file", help="SSL certificate file (for HTTPS)")
    parser.add_argument("--key-file", help="SSL key file (for HTTPS)")
    parser.add_argument(
        "--play-from", help="Read the media from a file and sent it.")
    parser.add_argument(
        "--play-without-decoding",
        help=(
            "Read the media without decoding it (experimental). "
            "For now it only works with an MPEGTS container with only H.264 video."
        ),
        action="store_true",
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="Host for HTTP server (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="Port for HTTP server (default: 8080)"
    )
    parser.add_argument("--verbose", "-v", action="count")
    parser.add_argument(
        "--audio-codec", help="Force a specific audio codec (e.g. audio/opus)"
    )
    parser.add_argument(
        "--video-codec", help="Force a specific video codec (e.g. video/H264)"
    )

    args = parser.parse_args()
    # print(args)

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if args.cert_file:
        ssl_context = ssl.SSLContext()
        ssl_context.load_cert_chain(args.cert_file, args.key_file)
    else:
        ssl_context = None

    app = web.Application()
    app.on_shutdown.append(on_shutdown)
    app.router.add_get("/", index)
    app.router.add_get("/webcam.js", javascript)
    app.router.add_post("/offer", offer)
    web.run_app(app, host=args.host, port=args.port, ssl_context=ssl_context)
