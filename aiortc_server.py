import asyncio
import logging
import platform
import re
import subprocess
import websockets
from aiortc import RTCPeerConnection, RTCConfiguration, RTCIceServer, RTCSessionDescription, RTCIceCandidate
from aiortc.contrib.media import MediaPlayer, MediaRelay
from aiortc.rtcrtpsender import RTCRtpSender
from constants import IP_ADDRESS


class AiortcServer:
    def __init__(self, ip):
        self._pc = None
        self._dc = None
        self._relay = None
        self._media_player = None
        self._signaling = None
        self._websocket = None
        self._websocket_uri = f"ws://{ip}:5011/ws?type=w&uid=1&token=1234567890"

    async def _consume_signaling(self):
        message = await self._websocket.recv()
        logging.info("Received:", message)
        sdp_type, sdp = message.split("~")[:2]
        if sdp_type == "pcnull":
            await self.hangup()
            logging.info("Remote PC is null. Hanging up...")
            return
        if sdp_type == "offer":
            offer = RTCSessionDescription(sdp=sdp, type=sdp_type)
            await self._pc.setRemoteDescription(offer)
            answer = await self._pc.createAnswer()
            await self._pc.setLocalDescription(answer)
            answer = self._pc.localDescription.type + "~" + self._pc.localDescription.sdp
            await self._websocket.send(answer)
        elif sdp_type == "answer":
            sdp = RTCSessionDescription(sdp=sdp, type=sdp_type)
            await self._pc.setRemoteDescription(sdp)
        elif sdp_type == "candidate":
            sdp_type, candidate, sdp_mid, sdp_mline_index = message.split("~")
            foundation, component, protocol, priority, ip, port, _, _type = candidate.split()[
                :8]
            candidate = RTCIceCandidate(foundation=foundation, component=component, protocol=protocol,
                                        priority=priority, ip=ip, port=port, type=_type, sdpMid=sdp_mid, sdpMLineIndex=sdp_mline_index)
            await self._pc.addIceCandidate(candidate)

    async def connect_to_websocket(self):
        if self._websocket:
            await self.disconnect_from_websocket()
        self._websocket = await websockets.connect(self._websocket_uri)
        logging.info("Connected to websocket server")

    async def disconnect_from_websocket(self):
        if self._websocket:
            await self._websocket.close()
        self._websocket = None
        logging.info("Disconnected from websocket server")

    def start_signaling(self):
        if self._signaling:
            self._signaling.cancel()
        self._signaling = asyncio.create_task(self._consume_signaling())
        logging.info("Signaling started")

    def stop_signaling(self):
        if self._signaling:
            self._signaling.cancel()
            self._signaling = None
        logging.info("Signaling stopped")

    def create_peer_connection(self):
        if self._pc:
            raise Exception("Peer connection already created")
        self._pc = RTCPeerConnection(
            configuration=RTCConfiguration(
                iceServers=[
                    RTCIceServer(
                        urls=["stun:stun.l.google.com:19302"]
                    )
                ]
            )
        )
        logging.info("Peer connection created")

    def create_data_channel(self):
        if not self._pc:
            raise Exception("Peer connection not created")
        self._dc = self._pc.createDataChannel("chat")

        @self._dc.on("message")
        def on_message(message):
            # convert bytes to string
            message = message.decode("utf-8")
            logging.info("<<< " + message)
        logging.info("Data channel created")

    def clear_media(self):
        if self._media_player:
            if self._media_player.video:
                self._media_player.video.stop()
            if self._media_player.audio:
                self._media_player.audio.stop()
            self._media_player = None
        if self._relay:
            # NOTE: Dereferencing relay does not stop the relay from running
            #      Unable to find a way to clear tracks in the relay
            self._relay = None
        logging.info("Media cleared")

    def get_media(self, audio_src=None, video_src=None, audio_codec=None, video_codec=None, play_without_decoding=False, play_from=None):
        """
        Get media from the specified sources.

        audio_src: name of the audio device on the system
        video_src: name of the video device on the system
        audio_codec: audio codec to use
        video_codec: video codec to use
        play_without_decoding: play media without decoding
        play_from: path to the media file to play
        """
        def get_devices():
            """
            Get the list of audio and video devices available on the system.
            """
            def list_video_devices():
                result = subprocess.run(
                    "ffmpeg -list_devices true -f dshow -i dummy".split(),
                    capture_output=True,
                    text=True)
                output = result.stderr
                return output

            def extract_device_names(output):
                pattern = r'"([^"]+)"\s+\((video|audio)\)'
                matches = re.findall(pattern, output)
                return matches

            devices = {"video": [], "audio": []}
            try:
                names = extract_device_names(list_video_devices())
            except FileNotFoundError:
                logging.info("ffmpeg not found. Please install ffmpeg.")
                return devices
            for name, media in names:
                devices[media].append(name)
            return devices

        def create_local_tracks(play_from, decode):
            if play_from:
                player = MediaPlayer(play_from, decode=decode, loop=True)
                return player.audio, player.video
            else:
                options = {"framerate": "30",
                           "video_size": "640x480"}
                if self._relay is None:
                    if platform.system() == "Darwin":
                        self._media_player = MediaPlayer(
                            "default:none", format="avfoundation", options=options
                        )
                    elif platform.system() == "Windows":
                        # devices = get_devices()
                        file = ""
                        # for video in devices["video"]:
                        #     file += f"video={video}"
                        #     for audio in devices["audio"]:
                        #         file += f":audio={audio}"
                        if audio_src:
                            file += f"audio={audio_src}:"
                        if video_src:
                            file += f"video={video_src}:"
                        options["pixel_format"] = "yuyv422"
                        self._media_player = MediaPlayer(
                            file=file[:-1], format="dshow", options=options
                        )
                    else:
                        self._media_player = MediaPlayer(
                            "/dev/video0", format="v4l2", options=options)
                    self._relay = MediaRelay()
                media = [None, None]
                if audio_src:
                    media[0] = self._relay.subscribe(
                        self._media_player.audio, buffered=False)
                if video_src:
                    media[1] = self._relay.subscribe(
                        self._media_player.video, buffered=False)
                return media

        def force_codec(pc, sender, forced_codec):
            kind = forced_codec.split("/")[0]
            codecs = RTCRtpSender.getCapabilities(kind).codecs
            transceiver = next(t for t in pc.getTransceivers()
                               if t.sender == sender)
            transceiver.setCodecPreferences(
                [codec for codec in codecs if codec.mimeType == forced_codec]
            )

        if not self._pc:
            raise Exception("Peer connection not created")

        self._pc.addTransceiver("audio")
        self._pc.addTransceiver("video")

        # clear media if already present
        self.clear_media()

        # open media source
        audio, video = create_local_tracks(
            play_from, decode=not play_without_decoding
        )

        if audio:
            audio_sender = self._pc.addTrack(audio)
            if audio_codec:
                force_codec(self._pc, audio_sender, audio_codec)
            elif play_without_decoding:
                raise Exception(
                    "You must specify the audio codec using audio_codec")

        if video:
            video_sender = self._pc.addTrack(video)
            if video_codec:
                force_codec(self._pc, video_sender, video_codec)
            elif play_without_decoding:
                raise Exception(
                    "You must specify the video codec using video_codec")
        logging.info("Media added")

    async def create_offer(self):
        # NOTE: Call this after creating pc, dc and adding media
        if not self._pc:
            raise Exception("Peer connection not created")
        if not self._websocket:
            raise Exception("Websocket connection not created")
        offer = await self._pc.createOffer()
        await self._pc.setLocalDescription(offer)
        offer_message = self._pc.localDescription.type + \
            "~" + self._pc.localDescription.sdp
        await self._websocket.send(offer_message)
        logging.info("Offer sent")

    def send_message(self, message):
        if not self._dc:
            raise Exception("Data channel not created")
        self._dc.send(message)
        logging.info(">>> " + message)

    async def hangup(self):
        self.clear_media()
        if self._pc:
            await self._pc.close()
        if self._dc:
            self._dc.close()
        self._pc = None
        self._dc = None
        # self.stop_signaling()
        logging.info("Resources cleaned up")


shutdown_event = asyncio.Event()


async def main():
    server = AiortcServer(IP_ADDRESS["localhost"])
    await server.connect_to_websocket()
    server.create_peer_connection()
    server.create_data_channel()
    # server.get_media(play_from="./big_buck_bunny_720p_1mb.mp4")
    server.get_media(audio_src="Microphone (Realtek(R) Audio)",
                     video_src="FHD Webcam")
    # server.get_media(audio_src="Microphone Array (Realtek(R) Audio)",
    #                  video_src="Webcam")
    await server.create_offer()
    logging.basicConfig(level=logging.info)

    try:
        await shutdown_event.wait()
    except asyncio.CancelledError:
        pass
    finally:
        await server.hangup()
        await server.disconnect_from_websocket()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Shutting down...")
        shutdown_event.set()
