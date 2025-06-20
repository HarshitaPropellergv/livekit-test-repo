#script containing tool definition
from livekit.agents.job import get_current_job_context
from livekit import api


async def conversation_finished(self):
        """1)(when the user intends to end the conversation ) call this function.
           2)when the conversation comes to end call this function example: bye, goodbye,thats it, I don't want to talk anymore, """
        # interrupt any existing generation
        self.session.interrupt()
        # generate a goodbye message and hang up
        # awaiting it will ensure the message is played out before returning
        print("Ending conversation...-------------")
        await self.session.generate_reply(
            instructions=f"say goodbye", allow_interruptions=False
        )
        job_ctx = get_current_job_context()
        # await self.test_aggregation()
        #adding sleep()
        await job_ctx.api.room.delete_room(
            api.DeleteRoomRequest(room=job_ctx.room.name)
        )