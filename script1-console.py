#console code
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
from livekit.plugins.turn_detector.multilingual import MultilingualModel
from livekit.plugins import aws
import os



load_dotenv(dotenv_path=".env.local")
class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(instructions="You are a helpful voice AI assistant.")


async def entrypoint(ctx: agents.JobContext):
    session = AgentSession(
        stt=deepgram.STT(model="nova-3", language="multi"),
        llm=openai.LLM.with_azure(
            azure_deployment="gpt-4o",
            azure_endpoint="https://azurellm-livekit.openai.azure.com/openai/deployments/gpt-4.1-mini/chat/completions?api-version=2025-01-01-preview",
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version=os.getenv("OPENAI_API_VERSION"),
        ),
        tts=aws.TTS(
            voice="Amy",
            language="en-IN",
            speech_engine="neural",
            sample_rate= 16000,#env
            region="us-east-1" ,#env
            api_key=os.getenv("AWS_ACCESS_KEY_ID"),
            api_secret=os.getenv("AWS_SECRET_ACCESS_KEY"),
        ),
        vad=silero.VAD.load(),
        turn_detection=MultilingualModel(),
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


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))