from config import FORCE_CHANNELS

async def check_force_join(user_id, bot):
    not_joined = []
    for channel in FORCE_CHANNELS:
        try:
            member = await bot.get_chat_member(channel, user_id)
            if member.status in ["left", "kicked"]:
                not_joined.append(channel)
        except:
            not_joined.append(channel)
    return not_joined
