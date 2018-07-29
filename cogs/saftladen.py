from discord import Channel, Role
from discord.ext import commands
from discord.utils import find

from cogs.utils.confirmation import reaction_confirm
from cogs.utils import checks


class Saftladen:
    lockdown_overwrites = {
        "send_messages": False,
        "add_reactions": False,
        "speak": False
    }

    exception_overwrites = {
        "send_messages": True,
        "add_reactions": True,
        "speak": True
    }

    exception_roles = [
        "Mods",
        "Bots"
    ]

    def __init__(self, bot):
        self.bot = bot
        self.old_perms = dict()

    async def overwrite(self, channel: Channel, role: Role, **overwrites):
        if channel not in self.old_perms:
            self.old_perms[channel] = dict()

        if role not in self.old_perms[channel]:
            self.old_perms[channel][role] = channel.overwrites_for(role)

        new_ow = channel.overwrites_for(role)
        new_ow.update(**overwrites)

        await self.bot.edit_channel_permissions(channel, role, new_ow)

    async def restore(self, channel: Channel) -> bool:
        if channel in self.old_perms:
            for role, old_ow in self.old_perms[channel].items():
                if not old_ow.is_empty():
                    await self.bot.edit_channel_permissions(channel, role, old_ow)
                else:
                    await self.bot.delete_channel_permissions(channel, role)

            del self.old_perms[channel]
            return True
        else:
            return False

    @commands.command(pass_context=True, no_pm=True)
    @checks.mod()
    @reaction_confirm
    async def lockdown(self, ctx, channel: Channel = None):
        if not channel:
            channel = ctx.message.channel
        server = channel.server

        # Lock out @everyone
        await self.overwrite(channel, server.default_role, **self.lockdown_overwrites)

        # Create exceptions
        for role_name in self.exception_roles:
            role = find(lambda r: r.name == role_name, server.roles)
            await self.overwrite(channel, role, **self.exception_overwrites)

        return True

    @commands.command(pass_context=True, no_pm=True)
    @checks.mod()
    @reaction_confirm
    async def unlock(self, ctx, channel: Channel = None):
        if not channel:
            channel = ctx.message.channel

        return await self.restore(channel)

    @commands.command(pass_context=True, no_pm=True, hidden=True)
    @checks.mod()
    async def showperms(self, ctx, channel: Channel = None):
        if not channel:
            channel = ctx.message.channel

        msg = "```\n"
        for target, overwrites in channel.overwrites:
            msg += "%s: %s\n" % (target, overwrites._values)
        msg += "```"

        await self.bot.say(msg)

    @commands.command(pass_context=True, no_pm=True, hidden=True)
    @checks.admin()
    async def clearperms(self, ctx, channel: Channel = None):
        if not channel:
            channel = ctx.message.channel

        for target, overwrites in channel.overwrites:
            await self.bot.delete_channel_permissions(channel, target)

        if channel in self.old_perms:
            del self.old_perms[channel]

        await self.bot.say("Ok")


def setup(bot):
    n = Saftladen(bot)
    bot.add_cog(n)
