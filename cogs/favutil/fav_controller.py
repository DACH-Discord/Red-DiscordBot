import asyncio
from functools import partial

from discord import Channel, User, NotFound, Message, Server, ChannelType, Embed, Member, Colour
from discord.utils import get
from peewee import fn, JOIN

from cogs import fav
from cogs.favutil.entity import Fav, LogEntry, Tag
from cogs.favutil.exception import ChannelNotFoundError
from cogs.favutil.reactions import create_reaction_menu


class FavController:

    def __init__(self, gb: 'fav.GreenBook'):
        self._gb = gb
        self._bot = gb.bot

        self.disabled_channels = []
        self.disabled_users = []

    @property
    def green_book(self):
        return self._gb

    @property
    def bot(self):
        return self.green_book.bot

    async def _embed_fav(self, fav: Fav) -> Embed:
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

            # Prevent default black colour
            if embed.colour == Colour.default():
                embed.colour = Colour(0xffffff)

        # Handle image embeds from source message
        for attachment in msg.attachments:
            if "width" in attachment:
                embed.set_image(url=attachment["url"])
                break

        return embed

    async def post_fav_by_id_action(self, favid, channel: Channel):
        try:
            fav = Fav.get_by_id(favid)
            embed = await self._embed_fav(fav)
            favmsg = await self.bot.send_message(channel, embed=embed)

        except ChannelNotFoundError:
            await self._bot.send_message(channel, "Could not find source channel, deleting from db.")
            Fav.delete_by_id(favid)
            return

        except NotFound:
            await self._bot.send_message(channel, "Could not find source message, deleting from db.")
            Fav.delete_by_id(favid)
            return

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
            create_reaction_menu(self._bot, favmsg, opts, show_options=should_show_controls))

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

        favembed = await self._embed_fav(new_fav)
        await self.retag_fav_action(new_fav.fav_id, embed=favembed)

    async def add_fav_by_id_action(self, msg_id, server: Server, user: User):
        # Create a get_message Future for every textchannel on the server
        searches = []
        for channel in server.channels:
            if channel.type is not ChannelType.text:
                continue
            fut = asyncio.ensure_future(self._bot.get_message(channel, msg_id))
            searches.append(fut)

        for res in asyncio.as_completed(searches):
            try:
                msg = await res
                await self.add_fav_action(msg, user)
            except NotFound:
                continue

    async def delete_fav_action(self, favid, msg: Message):
        Fav.delete_by_id(favid)
        await self._bot.delete_message(msg)

    async def retag_fav_action(self, favid, embed=None):
        thefav = Fav.get_by_id(favid)
        user = await self._bot.get_user_info(thefav.user_id)

        tagquestion = await self._bot.send_message(content="Add tags to your fav (space-separated)?",
                                                   destination=user,
                                                   embed=embed)

        # Cancel action
        opts = {"\N{NEGATIVE SQUARED CROSS MARK}": partial(asyncio.sleep, 0)}
        react_fut = asyncio.ensure_future(
            create_reaction_menu(self._bot, tagquestion, opts, show_options=True))

        # Tag receiver
        msg_fut = asyncio.ensure_future(
            self._bot.wait_for_message(author=user,
                                       channel=tagquestion.channel))

        abort_fut = asyncio.ensure_future(
            self._bot.wait_for_message(author=self._bot.user,
                                       channel=tagquestion.channel))

        done, pending = await asyncio.wait([react_fut, msg_fut, abort_fut],
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
                self._bot.remove_reaction(tagquestion, "\N{NEGATIVE SQUARED CROSS MARK}", self._bot.user),
                self._bot.add_reaction(tagmsg, "\N{WHITE HEAVY CHECK MARK}")])

        elif react_fut in done or abort_fut in done:  # Timeout reached, cancel pressed, or new botmessage triggered
            thefav.clear_tags()
            await self._bot.delete_message(tagquestion)

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

            await self._bot.send_message(author, msg)
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
            coro = self._delete_message_by_id(entry.channel_id, entry.msg_id)
            tasks.append(coro)
        # Also delete the original message and Fav table entry
        fav = Fav.get_by_id(entry.fav_id)
        if fav:
            coro = self._delete_message_by_id(fav.channel_id, fav.msg_id)
            tasks.append(coro)
            fav.delete()
        await asyncio.gather(*tasks, return_exceptions=True)
        # TODO maybe send the command-issuer a log of what was actually done
        return True

    async def disable_channel_action(self, channel: Channel) -> bool:
        if channel.id not in self.disabled_channels:
            self.disabled_channels.append(channel.id)
            return True
        else:
            self.disabled_channels.remove(channel.id)
            return False

    async def disable_user_action(self, user: User) -> bool:
        if user.id not in self.disabled_channels:
            self.disabled_users.append(user.id)
            return True
        else:
            self.disabled_users.remove(user.id)
            return False

    async def _delete_message_by_id(self, channel_id, message_id):
        chan = self.bot.get_channel(channel_id)
        msg = await self.bot.get_message(chan, message_id)
        await self.bot.delete_message(msg)
