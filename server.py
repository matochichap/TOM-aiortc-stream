import argparse
import asyncio
import json
import logging
import os
import ssl
import uuid
import websockets
import platform

import cv2
from aiohttp import web
from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription, RTCIceCandidate, RTCRtpSender
from aiortc.contrib.media import MediaBlackhole, MediaPlayer, MediaRecorder, MediaRelay
from av import VideoFrame

ROOT = os.path.dirname(__file__)

logger = logging.getLogger("pc")
pcs = set()
websocket = None
relay = None
webcam = None


def add_media_tracks(pc):
    def create_local_tracks(play_from, decode):
        global relay, webcam

        if play_from:
            player = MediaPlayer(play_from, decode=decode)
            return player.audio, player.video
        else:
            options = {"framerate": "30", "video_size": "640x480"}
            if relay is None:
                if platform.system() == "Darwin":
                    webcam = MediaPlayer(
                        "default:none", format="avfoundation", options=options
                    )
                elif platform.system() == "Windows":
                    options["pixel_format"] = "yuyv422"
                    webcam = MediaPlayer(
                        "video=Webcam", format="dshow", options=options
                    )
                # "C:\Users\ruiji\Downloads\big_buck_bunny_720p_1mb.mp4", format="dshow", options=options
                # "C:/Users/ruiji/Downloads/big_buck_bunny_720p_1mb.mp4", options=options
                else:
                    webcam = MediaPlayer(
                        "/dev/video0", format="v4l2", options=options)
                relay = MediaRelay()
            return None, relay.subscribe(webcam.video)

    def force_codec(pc, sender, forced_codec):
        kind = forced_codec.split("/")[0]
        codecs = RTCRtpSender.getCapabilities(kind).codecs
        transceiver = next(t for t in pc.getTransceivers()
                           if t.sender == sender)
        transceiver.setCodecPreferences(
            [codec for codec in codecs if codec.mimeType == forced_codec]
        )

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
    return pc


class VideoTransformTrack(MediaStreamTrack):
    """
    A video stream track that transforms frames from an another track.
    """

    kind = "video"

    def __init__(self, track, transform):
        super().__init__()  # don't forget this!
        self.track = track
        self.transform = transform

    async def recv(self):
        frame = await self.track.recv()

        if self.transform == "cartoon":
            img = frame.to_ndarray(format="bgr24")

            # prepare color
            img_color = cv2.pyrDown(cv2.pyrDown(img))
            for _ in range(6):
                img_color = cv2.bilateralFilter(img_color, 9, 9, 7)
            img_color = cv2.pyrUp(cv2.pyrUp(img_color))

            # prepare edges
            img_edges = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            img_edges = cv2.adaptiveThreshold(
                cv2.medianBlur(img_edges, 7),
                255,
                cv2.ADAPTIVE_THRESH_MEAN_C,
                cv2.THRESH_BINARY,
                9,
                2,
            )
            img_edges = cv2.cvtColor(img_edges, cv2.COLOR_GRAY2RGB)

            # combine color and edges
            img = cv2.bitwise_and(img_color, img_edges)

            # rebuild a VideoFrame, preserving timing information
            new_frame = VideoFrame.from_ndarray(img, format="bgr24")
            new_frame.pts = frame.pts
            new_frame.time_base = frame.time_base
            return new_frame
        elif self.transform == "edges":
            # perform edge detection
            img = frame.to_ndarray(format="bgr24")
            img = cv2.cvtColor(cv2.Canny(img, 100, 200), cv2.COLOR_GRAY2BGR)

            # rebuild a VideoFrame, preserving timing information
            new_frame = VideoFrame.from_ndarray(img, format="bgr24")
            new_frame.pts = frame.pts
            new_frame.time_base = frame.time_base
            return new_frame
        elif self.transform == "rotate":
            # rotate image
            img = frame.to_ndarray(format="bgr24")
            rows, cols, _ = img.shape
            M = cv2.getRotationMatrix2D(
                (cols / 2, rows / 2), frame.time * 45, 1)
            img = cv2.warpAffine(img, M, (cols, rows))

            # rebuild a VideoFrame, preserving timing information
            new_frame = VideoFrame.from_ndarray(img, format="bgr24")
            new_frame.pts = frame.pts
            new_frame.time_base = frame.time_base
            return new_frame
        else:
            return frame


async def index(request):
    global websocket
    uri = "ws://127.0.0.1:5011/ws?type=w&uid=1&token=1234567890"
    websocket = await websockets.connect(uri)
    content = open(os.path.join(ROOT, "index.html"), "r").read()
    return web.Response(content_type="text/html", text=content)


async def javascript(request):
    content = open(os.path.join(ROOT, "client.js"), "r").read()
    return web.Response(content_type="application/javascript", text=content)


async def offer(request):
    global websocket
    # params = await request.json()
    # # create offer
    # offer = "offer~" + params["sdp"]
    # await websocket.send(offer)

    pc = RTCPeerConnection()
    print("Created peer connection")
    pc = add_media_tracks(pc)
    print("Added media tracks")
    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    await websocket.send("offer~" + pc.localDescription.sdp)
    pc_id = "PeerConnection(%s)" % uuid.uuid4()
    pcs.add(pc)

    def log_info(msg, *args):
        logger.info(pc_id + " " + msg, *args)

    # log_info("Created for %s", request.remote)

    # prepare local media
    player = MediaPlayer(os.path.join(ROOT, "demo-instruct.wav"))
    if args.record_to:
        recorder = MediaRecorder(args.record_to)
    else:
        recorder = MediaBlackhole()

    @pc.on("datachannel")
    def on_datachannel(channel):
        @channel.on("message")
        def on_message(message):
            if isinstance(message, str) and message.startswith("ping"):
                channel.send("pong" + message[4:])

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        log_info("Connection state is %s", pc.connectionState)
        if pc.connectionState == "failed":
            await pc.close()
            pcs.discard(pc)

    @pc.on("track")
    def on_track(track):
        log_info("Track %s received", track.kind)

        if track.kind == "audio":
            pc.addTrack(player.audio)
            recorder.addTrack(track)
        elif track.kind == "video":
            pc.addTrack(
                VideoTransformTrack(
                    relay.subscribe(track)
                    # relay.subscribe(track), transform=params["video_transform"]
                )
            )
            if args.record_to:
                recorder.addTrack(relay.subscribe(track))

        @track.on("ended")
        async def on_ended():
            log_info("Track %s ended", track.kind)
            await recorder.stop()

    @pc.on("icecandidate")
    async def on_icecandidate(candidate):
        print("on_icecandidate")
        if candidate:
            candidate = candidate.to_sdp()
            candidate = "candidate~" + candidate
            await websocket.send(candidate)

    # offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
    # await pc.setRemoteDescription(offer)

    print("Waiting for answer")
    answer = await websocket.recv()
    print(answer)

    # handle answer
    sdp_type, sdp = answer.split("~")
    answer = RTCSessionDescription(sdp=sdp, type=sdp_type)
    await pc.setRemoteDescription(answer)
    await recorder.start()

    # handle candidate
    candidate = await websocket.recv()
    print("received candidate")
    print(candidate)
    sdp_type, candidate, sdp_mid, sdp_mline_index = candidate.split("~")
    foundation, component, protocol, priority, ip, port, _, _type = candidate.split()[
        :8]
    candidate = RTCIceCandidate(foundation=foundation, component=component, protocol=protocol,
                                priority=priority, ip=ip, port=port, type=_type, sdpMid=sdp_mid, sdpMLineIndex=sdp_mline_index)
    await pc.addIceCandidate(candidate)

    return web.Response(
        content_type="application/json",
        text=json.dumps(
            {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        ),
    )


async def send(request):
    global websocket
    params = await request.json()
    message = params["message"]
    await websocket.send(message)
    print("Sent message: " + message)


async def on_shutdown(app):
    # close peer connections
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="WebRTC audio / video / data-channels demo"
    )
    parser.add_argument("--cert-file", help="SSL certificate file (for HTTPS)")
    parser.add_argument("--key-file", help="SSL key file (for HTTPS)")
    parser.add_argument(
        "--host", default="127.0.0.1", help="Host for HTTP server (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Port for HTTP server (default: 8080)"
    )
    parser.add_argument("--record-to", help="Write received media to a file.")
    parser.add_argument("--verbose", "-v", action="count")
    args = parser.parse_args()
    args.play_from = None
    args.play_without_decoding = False
    args.audio_codec = None
    args.video_codec = None

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
    app.router.add_get("/client.js", javascript)
    app.router.add_get("/offer", offer)
    app.router.add_post("/send", send)
    web.run_app(
        app, access_log=None, host=args.host, port=args.port, ssl_context=ssl_context
    )
