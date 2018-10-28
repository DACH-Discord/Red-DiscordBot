import asyncio
import os
import random
from functools import partial
from unicodedata import name

from discord import User, Reaction, Embed, Member, NotFound, Message, Channel, Client, ChannelType, Server
from discord.ext import commands
from discord.utils import get
from peewee import fn, JOIN

from cogs.favutil import entity, delete_message_by_id
from cogs.favutil.entity import Fav, Tag, LogEntry
from cogs.favutil.exception import ChannelNotFoundError
from cogs.favutil.reactions import create_reaction_menu
from cogs.utils import checks
from cogs.utils.confirmation import reaction_confirm, delete_confirm


class GreenBook:

    def __init__(self, bot):
        self.bot = bot  # type: Client

        self.disabled_channels = []
        self.disabled_users = []

        self.bot.add_listener(self.on_addfav_reaction, "on_reaction_add")

    async def on_addfav_reaction(self, reaction: Reaction, user: User):
        if reaction.emoji == "\N{GREEN BOOK}":
            await self.add_fav_action(reaction.message, user)

    @commands.command(pass_context=True)
    @delete_confirm
    async def fav(self, ctx, hint=""):
        """Quote a random from your favorite messages. Add one by reacting with \N{GREEN BOOK}."""
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
        await self.post_fav_by_id_action(favid, ctx.message.channel)

    @commands.command(pass_context=True)
    @delete_confirm
    async def myfavs(self, ctx, hint=None):
        """Get a list of your tags, or quote all favs with a specific tag."""
        await self.myfavs_action(ctx.message.author, hint)

    @commands.command(pass_context=True)
    @delete_confirm
    async def untagged(self, ctx):
        """See all your favs that have no tags."""
        await self.untagged_action(ctx.message.author)

    @commands.command(pass_context=True)
    @reaction_confirm
    async def addfav(self, ctx, msg_id):
        """Add a fav by message id."""
        await self.add_fav_by_id_action(msg_id, ctx.message.server, ctx.message.author)

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
        disabled = await self.disable_channel_action(channel)

        if disabled:
            await self.bot.add_reaction(ctx.message, "\N{LOCK}")
        else:
            await self.bot.add_reaction(ctx.message, "\N{OPEN LOCK}")
        return True

    @favadm.command(pass_context=True)
    @reaction_confirm
    async def disable_user(self, ctx, user: User):
        """Disable all messages of a user from being faved."""
        disabled = await self.disable_user_action(user)

        if disabled:
            await self.bot.add_reaction(ctx.message, "\N{LOCK}")
        else:
            await self.bot.add_reaction(ctx.message, "\N{OPEN LOCK}")
        return True

    @favadm.command(pass_context=True)
    @reaction_confirm
    async def purge(self, ctx, msg_id: str):
        """Permanently remove a fav and all associated messages"""
        return await self.purge_action(msg_id)

    async def embed_fav(self, fav: Fav) -> Embed:
        channel = self.bot.get_channel(fav.channel_id)
        if not channel:
            raise ChannelNotFoundError()

        favowner = get(channel.server.members, id=fav.user_id)
        msg = await self.bot.get_message(channel, fav.msg_id)

        embed = Embed()
        embed.description = msg.clean_content
        embed.set_author(name=msg.author.display_name, icon_url=msg.author.avatar_url)
        # TODO Fix timezone
        embed.set_footer(text="#%s - %s | Fav by %s" %
                              (msg.channel.name,
                               msg.timestamp.strftime("%d.%m.%Y %H:%M"),
                               favowner.display_name))
        if isinstance(msg.author, Member):
            embed.colour = msg.author.colour

        # Handle image embeds from source message
        for attachment in msg.attachments:
            if "width" in attachment:
                embed.set_image(url=attachment["url"])
                break

        return embed

    async def post_fav_by_id_action(self, favid, channel: Channel):
        try:
            fav = Fav.get_by_id(favid)
            embed = await self.embed_fav(fav)
            favmsg = await self.bot.send_message(channel, embed=embed)

            # Write log
            LogEntry.create(favmsg.id,
                            favmsg.channel.id,
                            favmsg.server.id if favmsg.server else None,
                            fav.fav_id)

            # Create reaction menu
            should_show_controls = favmsg.channel.is_private
            opts = {"\N{WASTEBASKET}": partial(self.delete_fav_action, favid, favmsg),
                    "\N{LABEL}": partial(self.retag_fav_action, favid)}

            # Wait for control reactions without blocking
            asyncio.ensure_future(
                create_reaction_menu(self.bot, favmsg, opts, show_options=should_show_controls))

        except ChannelNotFoundError:
            await self.bot.send_message(channel, "Could not find source channel, deleting from db.")
            Fav.delete_by_id(favid)

        except NotFound:
            await self.bot.send_message(channel, "Could not find source message, deleting from db.")
            Fav.delete_by_id(favid)

    async def add_fav_action(self, msg: Message, user: User):
        # Ignore private messages
        if msg.channel.is_private:
            return

        # Ignore disabled channels
        if msg.channel.id in self.disabled_channels:
            return

        # Ignore disabled users
        if msg.author.id in self.disabled_users:
            return

        # Ignore bots
        if msg.author.bot:
            return

        new_fav = Fav.create(user_id=user.id,
                             msg_id=msg.id,
                             channel_id=msg.channel.id,
                             server_id=msg.server.id,
                             author_id=msg.author.id)

        favembed = await self.embed_fav(new_fav)
        await self.retag_fav_action(new_fav.fav_id, embed=favembed)

    async def add_fav_by_id_action(self, msg_id, server: Server, user: User):
        # Create a get_message Future for every textchannel on the server
        searches = []
        for channel in server.channels:
            if channel.type is not ChannelType.text:
                continue
            fut = asyncio.ensure_future(self.bot.get_message(channel, msg_id))
            searches.append(fut)

        for res in asyncio.as_completed(searches):
            try:
                msg = await res
                await self.add_fav_action(msg, user)
            except NotFound:
                continue

    async def delete_fav_action(self, favid, msg: Message):
        Fav.delete_by_id(favid)
        await self.bot.delete_message(msg)

    async def retag_fav_action(self, favid, embed=None):
        thefav = Fav.get_by_id(favid)
        user = await self.bot.get_user_info(thefav.user_id)

        tagquestion = await self.bot.send_message(content="Add tags to your fav (space-separated)?",
                                                  destination=user,
                                                  embed=embed)

        # Cancel action
        opts = {"\N{NEGATIVE SQUARED CROSS MARK}": partial(asyncio.sleep, 0)}
        react_fut = asyncio.ensure_future(
            create_reaction_menu(self.bot, tagquestion, opts, show_options=True))

        # Tag receiver
        msg_fut = asyncio.ensure_future(
            self.bot.wait_for_message(author=user,
                                      channel=tagquestion.channel))

        done, pending = await asyncio.wait([react_fut, msg_fut],
                                           return_when=asyncio.FIRST_COMPLETED,
                                           timeout=30)

        if msg_fut in done:  # Got answer from user
            tagmsg = await msg_fut
            new_tags = set(tagmsg.content.split(" "))

            # Many spaces result in empty splits, we don't want them
            if "" in new_tags:
                new_tags.remove("")

            thefav.set_tags(new_tags)

            await asyncio.wait([
                self.bot.remove_reaction(tagquestion, "\N{NEGATIVE SQUARED CROSS MARK}", self.bot.user),
                self.bot.add_reaction(tagmsg, "\N{WHITE HEAVY CHECK MARK}")])

        else:  # Timeout reached or cancel pressed
            thefav.clear_tags()
            await self.bot.delete_message(tagquestion)

    async def myfavs_action(self, author, hint):
        if not hint:
            # Print all existing tags
            tags = Tag.select(Tag, fn.COUNT(Tag.tag_id).alias("fav_count")) \
                .join(Fav) \
                .where(Fav.user_id == author.id) \
                .group_by(Tag.tagname)

            msg = "```\n" \
                  "[all favs] (%i)\n" \
                  "[untagged favs] (%i)\n" % (Fav.count_by_user(author.id), Fav.count_untagged_by_user(author.id))
            for tag in tags:
                msg += "%s (%i)\n" % (tag.tagname, tag.fav_count)
            msg += "```"

            await self.bot.send_message(author, msg)
        else:
            # Print the favs from the given tag
            favs = Fav.select().join(Tag) \
                .where((Fav.user_id == author.id) & (Tag.tagname == hint))

            for favid in favs:
                await self.post_fav_by_id_action(favid, author)

    async def untagged_action(self, author):
        user_id = author.id
        favs = Fav.select() \
            .join(Tag, join_type=JOIN.LEFT_OUTER) \
            .where((Fav.user_id == user_id)) \
            .group_by(Fav) \
            .having(fn.COUNT(Tag.tag_id) == 0)
        for favid in favs:
            await self.post_fav_by_id_action(favid, author)

    async def purge_action(self, msg_id):
        entry = LogEntry.get_by_msg_id(msg_id)
        # If that message is not known to the log, there's nothing we can do
        if not entry:
            return False
        # Get all the messages that quote this fav
        history = LogEntry.get_by_fav_id(entry.fav_id)
        # Delete all quotes by log
        tasks = []
        for entry in history:
            coro = delete_message_by_id(self.bot, entry.channel_id, entry.msg_id)
            tasks.append(coro)
        # Also delete the original message and Fav table entry
        fav = Fav.get_by_id(entry.fav_id)
        if fav:
            coro = delete_message_by_id(self.bot, fav.channel_id, fav.msg_id)
            tasks.append(coro)
            fav.delete()
        await asyncio.gather(*tasks, return_exceptions=True)
        # TODO maybe send the command-issuer a log of what was actually done
        return True

    async def disable_channel_action(self, channel):
        if channel.id not in self.disabled_channels:
            self.disabled_channels.append(channel.id)
            return True
        else:
            self.disabled_channels.remove(channel.id)
            return False

    async def disable_user_action(self, user):
        if user.id not in self.disabled_channels:
            self.disabled_users.append(user.id)
            return True
        else:
            self.disabled_users.remove(user.id)
            return False


def setup(bot):
    os.makedirs("data/favs", exist_ok=True)

    entity.db.init("data/favs/favs.db", pragmas=entity.pragmas)
    entity.db.connect(reuse_if_open=True)
    entity.db.create_tables([Fav, Tag, LogEntry])

    n = GreenBook(bot)
    bot.add_cog(n)
