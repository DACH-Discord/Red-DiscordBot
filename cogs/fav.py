import os
import random
from unicodedata import name

from discord import User, Reaction, Channel, Client
from discord.ext import commands

from cogs.favutil import entity
from cogs.favutil import fav_controller
from cogs.favutil.entity import Fav, Tag, LogEntry
from cogs.utils import checks
from cogs.utils.confirmation import reaction_confirm, delete_confirm


class GreenBook:

    def __init__(self, bot):
        self.bot = bot  # type: Client

        self.ctrl = fav_controller.FavController(self)

        self.bot.add_listener(self.on_addfav_reaction, "on_reaction_add")

    async def on_addfav_reaction(self, reaction: Reaction, user: User):
        if reaction.emoji == "\N{GREEN BOOK}":
            await self.ctrl.add_fav_action(reaction.message, user)

    @commands.command(pass_context=True)
    @delete_confirm
    async def fav(self, ctx, hint=""):
        """Quote a random one of your favorite messages. Add one by reacting with \N{GREEN BOOK} :green_book: on any user message.
        To delete a fav, react with \N{WASTEBASKET} :wastebasket: on the bot message.
        To change the tags on the fav, react with \N{LABEL} :label: on the bot message.
        To get a link to the original message, react with \N{INFORMATION SOURCE} :information_source: on the bot message.
        """
        author = ctx.message.author

        server = None
        channel = ctx.message.channel
        if not channel.is_private:
            server = channel.server

        if server:
            favs = Fav.get_by_user_and_server(author.id, server.id, hint)
        else:
            favs = Fav.get_by_user(author.id, hint)

        if not favs:
            if hint:
                await self.bot.say("You have no favs tagged with '%s'" % hint)
            else:
                await self.bot.say("You have no favs.")
            return

        favid = random.choice(favs)
        await self.ctrl.post_fav_by_id_action(favid, ctx.message.channel)

    @commands.command(pass_context=True)
    @delete_confirm
    async def myfavs(self, ctx, hint=None):
        """Get a list of your tags, or quote all favs with a specific tag."""
        await self.ctrl.myfavs_action(ctx.message.author, hint)

    @commands.command(pass_context=True)
    @delete_confirm
    async def untagged(self, ctx):
        """See all your favs that have no tags."""
        await self.ctrl.untagged_action(ctx.message.author)

    @commands.command(pass_context=True, no_pm=True)
    @reaction_confirm
    async def addfav(self, ctx, msg_id):
        """Add a fav by message id."""
        return await self.ctrl.add_fav_by_id_action(msg_id, ctx.message.server, ctx.message.author)

    @commands.command(hidden=True)
    async def pyname(self, msg: str):
        if len(msg) > 1:
            return False
        await self.bot.say(name(msg[0]))

    @commands.group(pass_context=True, hidden=True)
    @checks.is_owner()
    async def favadm(self, ctx):
        """Administrative actions"""
        if ctx.invoked_subcommand is None:
            await self.bot.send_cmd_help(ctx)

    @favadm.command(pass_context=True)
    @reaction_confirm
    async def disable_channel(self, ctx, channel: Channel):
        """Disable all messages in a channel from being faved."""
        disabled = await self.ctrl.disable_channel_action(channel)

        if disabled:
            await self.bot.add_reaction(ctx.message, "\N{LOCK}")
        else:
            await self.bot.add_reaction(ctx.message, "\N{OPEN LOCK}")
        return True

    @favadm.command(pass_context=True)
    @reaction_confirm
    async def disable_user(self, ctx, user: User):
        """Disable all messages of a user from being faved."""
        disabled = await self.ctrl.disable_user_action(user)

        if disabled:
            await self.bot.add_reaction(ctx.message, "\N{LOCK}")
        else:
            await self.bot.add_reaction(ctx.message, "\N{OPEN LOCK}")
        return True

    @favadm.command(pass_context=True)
    @reaction_confirm
    async def purge(self, ctx, msg_id: str):
        """Permanently remove a fav and all associated messages."""
        return await self.ctrl.purge_action(msg_id)


def setup(bot):
    os.makedirs("data/favs", exist_ok=True)

    entity.db.init("data/favs/favs.db", pragmas=entity.pragmas)
    entity.db.connect(reuse_if_open=True)
    entity.db.create_tables([Fav, Tag, LogEntry])

    n = GreenBook(bot)
    bot.add_cog(n)
