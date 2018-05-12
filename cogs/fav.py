import asyncio
import os
import random
import sqlite3
from sqlite3 import Connection

from discord import User, Reaction, Embed, Member, NotFound
from discord.ext import commands


class ChannelNotFoundError(Exception):
    pass


class GreenBook:

    def __init__(self, bot, conn: Connection):
        self.bot = bot
        self.db = conn

        self.bot.add_listener(self.on_addfav_reaction, "on_reaction_add")

    async def on_addfav_reaction(self, reaction: Reaction, user: User):
        if reaction.emoji == "\N{GREEN BOOK}":
            # Save the fav and later offer to add tags to it
            self.db.execute("INSERT INTO favs (user_id, msg_id, channel_id) VALUES (?, ?, ?)",
                            (user.id, reaction.message.id, reaction.message.channel.id))

            # Get the id of this fav
            cur = self.db.cursor()
            cur.execute("SELECT fav_id FROM favs WHERE user_id=? AND msg_id=?", (user.id, reaction.message.id))
            favid = cur.fetchone()[0]
            cur.close()

            favembed = await self.embed_fav(favid, user.display_name)
            tagquestion = await self.bot.send_message(content="Add tags to fav (space-separated)?",
                                                      destination=user,
                                                      embed=favembed)
            tagmsg = await self.bot.wait_for_message(timeout=30, author=user, channel=tagquestion.channel)

            if tagmsg:
                tags = [(favid, tag) for tag in tagmsg.content.split(" ")]
                self.db.executemany("INSERT INTO tags (fav_id, tagname) VALUES (?, ?)", tags)
                await self.bot.add_reaction(tagmsg, "\N{WHITE HEAVY CHECK MARK}")
            else:
                await self.bot.delete_message(tagquestion)

    async def embed_fav(self, favid, requester_name) -> Embed:
        cur = self.db.cursor()
        cur.execute("SELECT msg_id, channel_id, user_id FROM favs WHERE fav_id=?", (favid,))
        msg_id, channel_id, user_id = cur.fetchone()
        cur.close()

        # Get the channel the fav message was posted in
        channel = self.bot.get_channel(channel_id)
        if not channel:
            raise ChannelNotFoundError()

        # Retrieve the message, this may raise a variety of exceptions, handle in calling method
        msg = await self.bot.get_message(channel, msg_id)

        embed = Embed()
        embed.description = msg.clean_content
        embed.set_author(name=msg.author.display_name, icon_url=msg.author.avatar_url)
        embed.set_footer(text="%s - #%s - %s" %
                              (requester_name, msg.channel.name, msg.timestamp.strftime("%d.%m.%Y %H:%M")))
        if isinstance(msg.author, Member):
            embed.colour = msg.author.colour

        # Handle image embeds from source message
        for attachment in msg.attachments:
            if "width" in attachment:
                embed.set_image(url=attachment["url"])
                break

        return embed

    async def post_fav(self, favid, requester: User):
        try:
            embed = await self.embed_fav(favid, requester.display_name)
            favmsg = await self.bot.say(embed=embed)

            # Wait for control reactions without blocking
            should_show_controls = favmsg.channel.is_private
            fut = self.handle_fav_controls(favmsg, favid, requester, show_controls=should_show_controls)
            asyncio.ensure_future(fut)

        except ChannelNotFoundError:
            await self.bot.say("Could not find source channel, deleting from db.")
            self.delete_fav(favid)

        except NotFound:
            await self.bot.say("Could not find source message, deleting from db.")
            self.delete_fav(favid)

    async def handle_fav_controls(self, favmsg, favid, owner: User, show_controls=False):
        if show_controls:
            await self.bot.add_reaction(favmsg, "\N{WASTEBASKET}")

        wait_for_reaction = True
        while wait_for_reaction:
            wait_for_reaction = False
            reaction, user = await self.bot.wait_for_reaction(message=favmsg, user=owner, timeout=30 * 60)

            # User did not react
            if not reaction:
                return

            if reaction.emoji == "\N{WASTEBASKET}":
                self.delete_fav(favid)
                await self.bot.delete_message(favmsg)
            else:
                wait_for_reaction = True

    def delete_fav(self, favid):
        self.db.execute("delete from favs where fav_id=?", (favid,))
        self.db.execute("delete from tags where fav_id=?", (favid,))

    def favcount(self, user_id):
        cur = self.db.execute("select count(*) from favs where user_id=?", (user_id,))
        result = cur.fetchone()[0]
        cur.close()
        return result

    def untagged_count(self, user_id):
        cur = self.db.execute("select count(*) from favs natural left join tags where user_id=? and tagname is null",
                              (user_id,))
        result = cur.fetchone()[0]
        cur.close()
        return result

    @commands.command(pass_context=True, hidden=True)
    async def addfav(self, ctx, msg_id, hints=None):
        """Add a fav by message id. Also react with \N{GREEN BOOK} to add a fav."""
        raise NotImplementedError()

    @commands.command(pass_context=True)
    async def fav(self, ctx, hint=None):
        """Quote a random from your favorite messages."""
        author = ctx.message.author
        user_id = author.id
        cur = self.db.cursor()

        if hint:
            cur.execute("SELECT fav_id FROM favs NATURAL JOIN tags WHERE user_id=? AND tagname=?",
                        (user_id, hint))
        else:
            cur.execute("SELECT fav_id FROM favs WHERE user_id=?", (user_id,))
        favs = cur.fetchall()

        cur.close()

        if not favs:
            if hint:
                await self.bot.say("You have no favs tagged with '%s'" % hint)
            else:
                await self.bot.say("You have no favs.")
            return

        favid = random.choice(favs)[0]
        await self.post_fav(favid, author)

        if not ctx.message.channel.is_private:
            await self.bot.delete_message(ctx.message)

    @commands.command(pass_context=True)
    async def myfavs(self, ctx, hint=None):
        """Get a list of your fav tags, or quote all with a specific tag."""
        author = ctx.message.author
        user_id = author.id

        cur = self.db.cursor()
        if not hint:
            # Print all existing tags
            cur.execute("""select tagname, count(tagname) n
                               from favs natural join tags
                               where user_id=?
                               group by tagname
                               order by tagname""",
                        (user_id,))
            tags = cur.fetchall()

            msg = "```\n" \
                  "[all favs] (%i)\n" \
                  "[untagged favs] (%i)\n" % (self.favcount(user_id), self.untagged_count(user_id))
            for tag, count in tags:
                msg += "%s (%i)\n" % (tag, count)
            msg += "```"

            await self.bot.send_message(author, msg)
        else:
            # Print the favs from the given tag
            cur.execute("select fav_id from favs natural join tags where user_id=? and tagname=?",
                        (user_id, hint))
            favs = cur.fetchall()

            for favid, in favs:
                await self.post_fav(favid, author)
        cur.close()


def init_db(conn: Connection):
    conn.execute("PRAGMA foreign_keys  = ON")

    conn.execute("""CREATE TABLE favs (
                        fav_id integer primary key,
                        user_id text not null,
                        msg_id text not null,
                        channel_id text not null)""")

    conn.execute("""create table tags (
                        fav_id  int,
                        tagname text collate nocase not null,
                        foreign key (fav_id) references favs(fav_id));""")


def update_db(conn: Connection):
    exists = conn.execute("select * from sqlite_master where type='table' and name='lists'").fetchone()
    if exists:
        conn.execute("""create table tags (
                          fav_id  int,
                          tagname text collate nocase not null,
                          foreign key (fav_id) references favs(fav_id))""")

        conn.execute("""insert into tags(fav_id, tagname)
                                  select fav_id, listname from lists;""")

        conn.execute("""drop table lists""")


def setup(bot):
    os.makedirs("data/favs", exist_ok=True)

    needs_init = not os.path.exists("data/favs/favs.db")
    conn = sqlite3.connect("data/favs/favs.db")
    conn.isolation_level = None  # autocommit

    needs_init and init_db(conn)
    update_db(conn)

    n = GreenBook(bot, conn)
    bot.add_cog(n)
