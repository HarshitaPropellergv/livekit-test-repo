from dotenv import load_dotenv
 
from livekit import agents, api, rtc
from livekit.agents import AgentSession, Agent, RoomInputOptions, AutoSubscribe
from livekit.plugins import (
    openai,
    deepgram,
    silero,
    aws,
    sarvam
)
from livekit.plugins.turn_detector.multilingual import MultilingualModel # Re-enable for robust turn detection
import os
import asyncio
import logging
from livekit.agents import metrics, MetricsCollectedEvent
from time import perf_counter
import datetime
from livekit.plugins import noise_cancellation
 
# --- Import LiveKit's BackgroundAudioPlayer as per your example ---
from livekit.agents import BackgroundAudioPlayer,BuiltinAudioClip,AudioConfig
 
logger = logging.getLogger("outbound-caller")
logger.setLevel(logging.INFO)
 
room_name = "my-room"
agent_name = "test-agent"
outbound_trunk_id = os.getenv("SIP_OUTBOUND_TRUNK_ID")
 
load_dotenv(dotenv_path=".env.local")
 
class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(instructions="You are a helpful voice AI assistant for a call center. Respond concisely and professionally.")
        self.participant: rtc.RemoteParticipant | None = None
 
    def set_participant(self, participant: rtc.RemoteParticipant):
        self.participant = participant
 
async def entrypoint(ctx: agents.JobContext):
    # --- As per LiveKit example: Initialize BackgroundAudioPlayer first ---
    # background_audio = BackgroundAudioPlayer(
    #     ambient_sound_source="cafe_noise.wav" # Use your actual path for ambient sound
    # )
 
    session = AgentSession(
        stt=deepgram.stt.STT(
            model="nova-3",
            interim_results=True,
            smart_format=True,
            punctuate=True,
            filler_words=True,
            profanity_filter=False,
            language="en-IN",
        ),
        llm=openai.LLM.with_azure(
            azure_deployment="gpt-4.1-mini",
            azure_endpoint="https://azurellm-livekit.openai.azure.com/openai/deployments/gpt-4.1-mini/chat/completions?api-version=2025-01-01-preview",
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version=os.getenv("OPENAI_API_VERSION"),
            # api_key=openai_api_key
        ),
        tts=sarvam.TTS(
            target_language_code="en-IN",
            speaker="anushka",
            api_key=os.getenv("SARVAM_API_KEY")
            ),
        vad=silero.VAD.load(
            min_speech_duration=0.05,
            min_silence_duration=0.2,
            prefix_padding_duration=0.2,
            max_buffered_speech=60.0,
            activation_threshold=0.5,
            sample_rate=16000,
        ),
        turn_detection=MultilingualModel(), # Re-enable for robust turn detection
 
        min_endpointing_delay=0.1,
 
        # --- As per LiveKit example: Pass the BackgroundAudioPlayer to AgentSession ---
    )
    background_audio = BackgroundAudioPlayer(
      # play office ambience sound looping in the background
      ambient_sound=AudioConfig(BuiltinAudioClip.OFFICE_AMBIENCE, volume=0.8),
      # play keyboard typing sound when the agent is thinking
      thinking_sound=[
               AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING, volume=0.8),
               AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING2, volume=0.7),
         ],
      )
 
    agent = Assistant()
 
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
 
    user_identity = "phone_user"
    phone_number = ctx.job.metadata
 
    # --- NO CUSTOM AUDIO HANDLER OR TRACK PUBLISHING HERE ---
    # LiveKit's BackgroundAudioPlayer handles its own track publication internally via session.start.
 
    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(), # Uncomment if needed
        ),
    )
    await background_audio.start(room=ctx.room,agent_session=session)
 
    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
 
    participant = await ctx.wait_for_participant(identity=user_identity)
    agent.set_participant(participant)
 
    start_time_check_call_status = perf_counter()
    while perf_counter() - start_time_check_call_status < 30:
        call_status = participant.attributes.get("sip.callStatus")
        if call_status == "active":
            logger.info(f"Call is active for {phone_number}, agent starting initial greeting...")
 
            # Background audio automatically starts if set as ambient_sound_source
            # in BackgroundAudioPlayer initialization.
            # If you want to play a *different* clip dynamically, use:
            # await background_audio.play("your_dynamic_clip.wav")
 
            start_time_call = datetime.datetime.now()
            await session.say("Hello, this is Maanvi, calling from propeller group..", allow_interruptions=True)
 
            logger.info("User has picked up, agent has delivered initial greeting.")
 
            try:
                log_counter = 0
                while not participant.disconnect_reason:
                    if log_counter % 50 == 0:
                        logger.info(f"Call {phone_number} active, agent running...")
                    log_counter += 1
                    await asyncio.sleep(0.1)
                logger.info(f"Call ended naturally for {phone_number}. Reason: {participant.disconnect_reason}")
            except asyncio.CancelledError:
                logger.info(f"Conversation loop for {phone_number} was cancelled.")
            except Exception as e:
                logger.error(f"Error during conversation for {phone_number}: {e}")
            break
 
        elif call_status == "automation":
            logger.info(f"Call status for {phone_number} is 'automation'. Waiting...")
            pass
        elif participant.disconnect_reason:
            logger.info(f"Call ended for {phone_number} before active, reason: {participant.disconnect_reason}")
            break
 
        await asyncio.sleep(0.1)
 
    logger.info(f"Agent session is ending for {phone_number}. Shutting down.")
 
    # --- CRITICAL: Ensure graceful shutdown of the entire agent task ---
    # This ensures the entrypoint waits until the LiveKit room is disconnected,
    # allowing all internal components (including BackgroundAudioPlayer) to clean up gracefully.
    ctx.shutdown()

 
 
if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint, agent_name="test-agent"))