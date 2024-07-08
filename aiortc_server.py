import asyncio
import logging
import platform
import websockets
from aiortc import RTCPeerConnection, RTCConfiguration, RTCIceServer, RTCSessionDescription, RTCIceCandidate
from aiortc.contrib.media import MediaPlayer, MediaRelay
from aiortc.rtcrtpsender import RTCRtpSender
from constants import IP_ADDRESS


class AiortcServer:
    def __init__(self, ip):
        self.pc = RTCPeerConnection(
            configuration=RTCConfiguration(
                iceServers=[
                    RTCIceServer(
                        urls=["stun:stun.l.google.com:19302"]
                    )
                ]
            )
        )
        self.dc = None
        self.websocket_uri = f"ws://{ip}:5011/ws?type=w&uid=1&token=1234567890"
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

    def get_media(self, audio_src=None, video_src=None, audio_codec=None, video_codec=None, play_without_decoding=False, play_from=None):
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

    def create_data_channel(self):
        dc = self.pc.createDataChannel("chat")

        # async def send_pings():
        #     while True:
        #         dc.send("ping")
        #         print(">>> ping")
        #         await asyncio.sleep(5)

        # @dc.on("open")
        # def on_open():
        #     asyncio.ensure_future(send_pings())

        @dc.on("message")
        def on_message(message):
            # convert bytes to string
            message = message.decode("utf-8")
            print("<<< " + message)
        return dc

    async def create_offer(self):
        self.dc = self.create_data_channel()
        await self.connect_to_websocket()
        offer = await self.pc.createOffer()
        await self.pc.setLocalDescription(offer)
        offer_message = self.pc.localDescription.type + "~" + self.pc.localDescription.sdp
        await self.websocket.send(offer_message)


shutdown_event = asyncio.Event()


async def main():
    server = AiortcServer(IP_ADDRESS["localhost"])
    # server.get_media(play_from="./big_buck_bunny_720p_1mb.mp4")
    # server.get_media(audio_src="Microphone (Realtek(R) Audio)",
    #                  video_src="FHD Webcam")
    server.get_media(audio_src="Microphone Array (Realtek(R) Audio)",
                     video_src="Webcam")
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
