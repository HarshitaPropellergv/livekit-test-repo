from dotenv import load_dotenv

from livekit import agents,api,rtc
from livekit.agents import AgentSession, Agent, RoomInputOptions,AutoSubscribe
from livekit.plugins import (
    openai,
    cartesia,
    deepgram,
    # noise_cancellation,
    silero,
)
# from livekit.plugins.turn_detector.multilingual import MultilingualModel
from livekit.plugins import aws
import os
import asyncio
import uuid
from pathlib import Path
import wave
import numpy as np
import logging
from livekit.agents import metrics, MetricsCollectedEvent
from time import perf_counter
import datetime

logger = logging.getLogger("outbound-caller")
logger.setLevel(logging.INFO)

# Configuration
room_name = "my-room"
agent_name = "test-agent"
outbound_trunk_id = os.getenv("SIP_OUTBOUND_TRUNK_ID")


load_dotenv(dotenv_path=".env.local")
class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(instructions="You are a helpful voice AI assistant.")
        self.participant: rtc.RemoteParticipant | None = None

    
    def set_participant(self, participant: rtc.RemoteParticipant):
        self.participant = participant


        

class AudioHandler:
    def __init__(self, sample_rate=48000, channels=1, track_id=None):
        self.audio_source = rtc.AudioSource(sample_rate, channels)
        self.track_id = track_id or f"audio_{str(uuid.uuid4())}"#updating
        self.audio_track = rtc.LocalAudioTrack.create_audio_track(self.track_id, self.audio_source)
        self.audio_task = None
        self.audio_running = asyncio.Event()
 
    async def start_audio(self, wav_path: Path | str, volume: float = 0.2):
        self.audio_running.set()
        self.audio_task = asyncio.create_task(self._play_audio(wav_path, volume))
 
    async def stop_audio(self):
        """Stop audio playback immediately"""
        self.audio_running.clear()
        if self.audio_task:
            await self.audio_task
            self.audio_task = None
 
    async def _play_audio(self, wav_path: Path | str, volume: float):
        samples_per_channel = 9600
        wav_path = Path(wav_path)
 
        while self.audio_running.is_set():
            with wave.open(str(wav_path), 'rb') as wav_file:
                sample_rate = wav_file.getframerate()
                num_channels = wav_file.getnchannels()
 
                audio_data = wav_file.readframes(wav_file.getnframes())
                audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
 
                if num_channels == 2:
                    audio_array = audio_array.reshape(-1, 2).mean(axis=1)
 
                for i in range(0, len(audio_array), samples_per_channel):
                    if not self.audio_running.is_set():
                        break
 
                    chunk = audio_array[i:i + samples_per_channel]
 
                    if len(chunk) < samples_per_channel:
                        chunk = np.pad(chunk, (0, samples_per_channel - len(chunk)))
 
                    chunk = np.tanh(chunk / 32768.0) * 32768.0
                    chunk = np.round(chunk * volume).astype(np.int16)
 
                    await self.audio_source.capture_frame(rtc.AudioFrame(
                        data=chunk.tobytes(),
                        sample_rate=48000,
                        samples_per_channel=samples_per_channel,
                        num_channels=1
                    ))
 
                    await asyncio.sleep((samples_per_channel / 48000) * 0.98)
 
    async def publish_track(self, room):
        await room.local_participant.publish_track(
            self.audio_track,
            rtc.TrackPublishOptions(
                source=rtc.TrackSource.SOURCE_MICROPHONE,
                stream=self.track_id
            )
        )

async def entrypoint(ctx: agents.JobContext):
    #defining agent session
    session = AgentSession(
        stt=deepgram.stt.STT(
            model= "nova-3",#env
            interim_results=True,
            smart_format=True,
            punctuate=True,
            filler_words=True,
            profanity_filter=False,
            language="en-IN",
            # language="hi",
        ),
        llm=openai.llm.LLM.with_cerebras(
            model="llama-4-scout-17b-16e-instruct",
            temperature=0.8,
            api_key=os.getenv("CEREBRAS_API_KEY")
         ),
        tts=aws.TTS(
            
            voice="Kajal",
            language="en-IN",
            speech_engine="neural",
            sample_rate= 16000,#env
            region="ap-south-1" ,#env
            api_key=os.getenv("AWS_ACCESS_KEY_ID"),
            api_secret=os.getenv("AWS_SECRET_ACCESS_KEY"),
        ),
        vad=silero.VAD.load(
            min_speech_duration=0.05,  # 0.05,
            min_silence_duration=0.2,  # 0.55,
            prefix_padding_duration=0.2,  # 0.5,
            max_buffered_speech=60.0,  # 60.0,
            activation_threshold=0.5,  # 0.5,
            sample_rate=16000,
        ),
        # turn_detection=MultilingualModel(),
        min_endpointing_delay=0.1

    )

    #agent instance 
    agent = Assistant()
    #job context connect 
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    user_identity = "phone_user"
    phone_number = ctx.job.metadata

    audio_handler = AudioHandler()
    try:
        await audio_handler.publish_track(ctx.room)
        logger.info(f"\n success  during publish track \n")
    except Exception as e:
        logger.info(f"\n exception  during publish track error: {e}\n")
   



    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            # LiveKit Cloud enhanced noise cancellation
            # - If self-hosting, omit this parameter
            # - For telephony applications, use `BVCTelephony` for best results
            # noise_cancellation=noise_cancellation.BVC(), 
        ),
    )
    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)

    participant = await ctx.wait_for_participant(identity=user_identity)
    agent.set_participant(participant)
    
    start_time = perf_counter()
    while perf_counter() - start_time < 30:
        call_status = participant.attributes.get("sip.callStatus")
        if call_status == "active":
            logger.info(f"Call is active for {phone_number} , starting agent and background audio...")
 
            await audio_handler.start_audio("cafe_noise.wav")
            await asyncio.sleep(1)
 
            #for call time metrics
            start_time = datetime.datetime.now()
            await session.say("Hello, this is Maanvi, calling from propeller group..", allow_interruptions=True)
 
            logger.info("User has picked up, agent and audio started")
 
            # Stay in conversation until call ends
            try:
                log_counter = 0
                while not participant.disconnect_reason:
                    if log_counter % 50 == 0:  # Log every 5 seconds (50 * 0.1s sleep)
                        logger.info(f"Call {phone_number} active, agent running...")
                    log_counter += 1
                    await asyncio.sleep(0.1)
                logger.info("Call ended naturally")
            except Exception as e:
                logger.error(f"Error during conversation: {e}")
            break
 
        elif call_status == "automation":
            pass
        elif participant.disconnect_reason:
            logger.info(f"----------Call ended for {phone_number}, stopping background audio..., reason:: {participant.disconnect_reason}")
            await audio_handler.stop_audio()
            break
        await asyncio.sleep(0.1)

    logger.info(f"Session ended, cleaning up for {phone_number}")

    # await session.generate_reply(
    #     instructions="Greet the user and offer your assistance."
    # )
    await audio_handler.stop_audio()
    ctx.shutdown()




if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint,agent_name="test-agent"))