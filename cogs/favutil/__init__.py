async def delete_message_by_id(bot, channel_id, message_id):
    chan = bot.get_channel(channel_id)
    msg = await bot.get_message(chan, message_id)
    await bot.delete_message(msg)
