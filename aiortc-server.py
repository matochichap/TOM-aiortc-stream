import asyncio
import logging
import platform
import websockets
import time
from aiortc import RTCPeerConnection, RTCConfiguration, RTCIceServer, RTCSessionDescription, RTCIceCandidate
from aiortc.contrib.media import MediaPlayer, MediaRelay
from aiortc.rtcrtpsender import RTCRtpSender

IP_ADDRESS = {
    "localhost": "127.0.0.1",
    "Innovation 4": "192.168.68.56",
    "NUS_STU": "10.249.218.176",
    "Galaxy S21 Ultra": "192.168.224.2", # need to update after every hotspot restart
    "SSI Windows PC": "192.168.137.147" # doesn't work, uses IP of wifi
}

WEBSOCKET_URI = f"ws://{IP_ADDRESS['Galaxy S21 Ultra']}:5011/ws?type=w&uid=1&token=1234567890"


class AiortcServer:
    def __init__(self, websocket_uri):
        self.pc = RTCPeerConnection(
            configuration=RTCConfiguration(
                iceServers=[
                    RTCIceServer(
                        urls=["stun:stun.l.google.com:19302"]
                    )
                ]
            )
        )
        self.websocket_uri = websocket_uri
        self.relay = None
        self.media_player = None

    async def connect_to_websocket(self):
        self.websocket = await websockets.connect(self.websocket_uri)
        print("Connected to websocket server")
        asyncio.create_task(self.consume_signaling())

    async def consume_signaling(self):
        message = await self.websocket.recv()
        print("Received:", message)
        sdp_type, sdp = message.split("~")[:2]
        if sdp_type == "offer":
            offer = RTCSessionDescription(sdp=sdp, type=sdp_type)
            await self.pc.setRemoteDescription(offer)
            answer = await self.pc.createAnswer()
            await self.pc.setLocalDescription(answer)
            answer = self.pc.localDescription.type + "~" + self.pc.localDescription.sdp
            await self.websocket.send(answer)
        elif sdp_type == "answer":
            sdp = RTCSessionDescription(sdp=sdp, type=sdp_type)
            await self.pc.setRemoteDescription(sdp)
        elif sdp_type == "candidate":
            sdp_type, candidate, sdp_mid, sdp_mline_index = message.split("~")
            foundation, component, protocol, priority, ip, port, _, _type = candidate.split()[
                :8]
            candidate = RTCIceCandidate(foundation=foundation, component=component, protocol=protocol,
                                        priority=priority, ip=ip, port=port, type=_type, sdpMid=sdp_mid, sdpMLineIndex=sdp_mline_index)
            await self.pc.addIceCandidate(candidate)

    def get_media(self, audio_src="Microphone (Realtek(R) Audio)", video_src="FHD Webcam", audio_codec=None, video_codec=None, play_without_decoding=False, play_from=None):
        def create_local_tracks(play_from, decode):
            if play_from:
                player = MediaPlayer(play_from, decode=decode, loop=True)
                return player.audio, player.video
            else:
                options = {"framerate": "30",
                           "video_size": "640x480"}
                if self.relay is None:
                    if platform.system() == "Darwin":
                        self.media_player = MediaPlayer(
                            "default:none", format="avfoundation", options=options
                        )
                    elif platform.system() == "Windows":
                        file = ""
                        if audio_src:
                            file += f"audio={audio_src}:"
                        if video_src:
                            file += f"video={video_src}:"
                        options["pixel_format"] = "yuyv422"
                        self.media_player = MediaPlayer(
                            file=file[:-1], format="dshow", options=options
                        )
                    else:
                        self.media_player = MediaPlayer(
                            "/dev/video0", format="v4l2", options=options)
                    self.relay = MediaRelay()
                media = [None, None]
                if audio_src:
                    media[0] = self.relay.subscribe(self.media_player.audio)
                if video_src:
                    media[1] = self.relay.subscribe(self.media_player.video)
                return media

        def force_codec(pc, sender, forced_codec):
            kind = forced_codec.split("/")[0]
            codecs = RTCRtpSender.getCapabilities(kind).codecs
            transceiver = next(t for t in pc.getTransceivers()
                               if t.sender == sender)
            transceiver.setCodecPreferences(
                [codec for codec in codecs if codec.mimeType == forced_codec]
            )

        self.pc.addTransceiver("audio")
        self.pc.addTransceiver("video")

        # open media source
        audio, video = create_local_tracks(
            play_from, decode=not play_without_decoding
        )

        if audio:
            audio_sender = self.pc.addTrack(audio)
            if audio_codec:
                force_codec(self.pc, audio_sender, audio_codec)
            elif play_without_decoding:
                raise Exception(
                    "You must specify the audio codec using audio_codec")

        if video:
            video_sender = self.pc.addTrack(video)
            if video_codec:
                force_codec(self.pc, video_sender, video_codec)
            elif play_without_decoding:
                raise Exception(
                    "You must specify the video codec using video_codec")

    # TODO: test this function
    def create_data_channel(self):
        channel = self.pc.createDataChannel("chat")
        
        time_start = None
        def current_stamp():
            global time_start

            if time_start is None:
                time_start = time.time()
                return 0
            else:
                return int((time.time() - time_start) * 1000000)

        def channel_log(channel, t, message):
            print("channel(%s) %s %s" % (channel.label, t, message))
        
        def channel_send(channel, message):
            channel_log(channel, ">", message)
            channel.send(message)
        
        async def send_pings():
            while True:
                channel_send(channel, "ping %d" % current_stamp())
                await asyncio.sleep(1)

        @channel.on("open")
        def on_open():
            asyncio.ensure_future(send_pings())

        @channel.on("message")
        def on_message(message):
            channel_log(channel, "<", message)

            if isinstance(message, str) and message.startswith("pong"):
                elapsed_ms = (current_stamp() - int(message[5:])) / 1000
                print(" RTT %.2f ms" % elapsed_ms)

    async def create_offer(self):
        self.create_data_channel()
        await self.connect_to_websocket()
        offer = await self.pc.createOffer()
        await self.pc.setLocalDescription(offer)
        offer_message = self.pc.localDescription.type + "~" + self.pc.localDescription.sdp
        await self.websocket.send(offer_message)


shutdown_event = asyncio.Event()


async def main():
    server = AiortcServer(WEBSOCKET_URI)
    # server.get_media(play_from="./big_buck_bunny_720p_1mb.mp4")
    server.get_media()
    await server.create_offer()
    logging.basicConfig(level=logging.INFO)

    try:
        await shutdown_event.wait()
    except asyncio.CancelledError:
        pass
    finally:
        # Clean up resources here
        await server.pc.close()
        await server.websocket.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down...")
        shutdown_event.set()
