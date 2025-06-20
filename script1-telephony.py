from dotenv import load_dotenv

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions
from livekit.plugins import (
    openai,
    cartesia,
    deepgram,
    noise_cancellation,
    silero,
)
# from livekit.plugins.turn_detector.multilingual import MultilingualModel
from livekit.plugins import aws
import os
from livekit.agents import metrics, MetricsCollectedEvent



# Configuration
room_name = "my-room"
agent_name = "test-agent"
outbound_trunk_id = os.getenv("SIP_OUTBOUND_TRUNK_ID")


load_dotenv(dotenv_path=".env.local")
class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(instructions="You are a helpful voice AI assistant.")

        


async def entrypoint(ctx: agents.JobContext):
    session = AgentSession(
        stt=deepgram.STT(model="nova-3", language="multi"),
        llm=openai.llm.LLM.with_cerebras(
            model="llama3.1-8b",
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
            activation_threshold=0.2,  # 0.5,
            sample_rate=16000,
        ),
        # turn_detection=MultilingualModel(),
        min_endpointing_delay=0.1

        )

    await session.start(
        room=ctx.room,
        agent=Assistant(),
        room_input_options=RoomInputOptions(
            # LiveKit Cloud enhanced noise cancellation
            # - If self-hosting, omit this parameter
            # - For telephony applications, use `BVCTelephony` for best results
            noise_cancellation=noise_cancellation.BVC(), 
        ),
    )

    await ctx.connect()

    await session.generate_reply(
        instructions="Greet the user and offer your assistance."
    )

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint,agent_name="test-agent"))