import os
import random
import sqlite3
from sqlite3 import Connection

from discord import User, Reaction, Embed, NotFound
from discord.ext import commands


class GreenBook:

    def __init__(self, bot, conn: Connection):
        self.bot = bot
        self.db = conn

        self.bot.add_listener(self.react, "on_reaction_add")

    async def react(self, reaction: Reaction, user: User):
        if reaction.emoji == "\N{GREEN BOOK}":
            self.db.execute("INSERT INTO favs (user_id, msg_id, channel_id) VALUES (?, ?, ?)",
                            (user.id, reaction.message.id, reaction.message.channel.id))

            # Get the id of this fav
            cur = self.db.cursor()
            cur.execute("SELECT fav_id FROM favs WHERE user_id=? AND msg_id=?", (user.id, reaction.message.id))
            favid = cur.fetchone()[0]
            cur.close()

            favembed = await self.embed_fav(favid)

            tagquestion = await self.bot.send_message(destination=user,
                                                      content="Add tags to fav (space-separated)?",
                                                      embed=favembed)
            tagmsg = await self.bot.wait_for_message(timeout=30, author=user, channel=tagquestion.channel)

            if tagmsg:
                tags = [(favid, tag) for tag in tagmsg.content.split(" ")]
                self.db.executemany("INSERT INTO lists (fav_id, listname) VALUES (?, ?)", tags)
                await self.bot.add_reaction(tagmsg, "\N{WHITE HEAVY CHECK MARK}")
            else:
                await self.bot.delete_message(tagquestion)

    async def embed_fav(self, favid):
        cur = self.db.cursor()
        cur.execute("SELECT msg_id, channel_id FROM favs WHERE fav_id=?", (favid,))
        msg_id, channel_id = cur.fetchone()
        cur.close()

        channel = self.bot.get_channel(channel_id)
        try:
            msg = await self.bot.get_message(channel, msg_id)
        except NotFound:
            # delete the fav
            return None

        embed = Embed()
        embed.description = msg.clean_content
        embed.set_author(name=msg.author.display_name, icon_url=msg.author.avatar_url)
        embed.set_footer(text="#%s - %s" % (msg.channel.name, msg.timestamp.strftime("%d.%m.%Y %H:%M")))
        embed.colour = msg.author.colour

        for attachment in msg.attachments:
            if "width" in attachment:
                embed.set_image(url=attachment["url"])
                break

        return embed

    @commands.command(pass_context=True)
    async def fav(self, ctx, hint=None):
        user_id = ctx.message.author.id
        cur = self.db.cursor()

        if hint:
            cur.execute("SELECT fav_id FROM favs NATURAL JOIN lists WHERE user_id=? AND listname=?",
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

        thefav = random.choice(favs)
        embed = await self.embed_fav(thefav[0])

        if embed:
            await self.bot.send_message(destination=ctx.message.channel, embed=embed)
            # await self.bot.delete_message(ctx.message)
        else:
            await self.bot.say("Could not find fav with id %s" % thefav[0])

    @commands.command(pass_context=True)
    async def myfavs(self, ctx, hint=None):
        user_id = ctx.message.author.id

        cur = self.db.cursor()
        if not hint:
            cur.execute("""select
              listname tag,
              count(listname) n
            from favs
              natural join lists
            where user_id = ?
            group by listname
            order by listname""", (user_id,))
            tags = cur.fetchall()

            msg = "```\n"
            for tag, count in tags:
                msg += "%s (%i)\n" % (tag, count)
            msg += "```"

            await self.bot.send_message(ctx.message.author, msg)
        else:
            cur.execute("""select fav_id
            from favs
              natural join lists
            where user_id = ? and listname = ?""", (user_id, hint))
            favs = cur.fetchall()

            for favnum, in favs:
                embed = await self.embed_fav(favnum)
                if embed:
                    await self.bot.send_message(ctx.message.author, embed=embed)
        cur.close()


def init_db(conn: Connection):
    conn.execute("PRAGMA foreign_keys  = ON")

    conn.execute("""CREATE TABLE favs (
                        fav_id integer primary key,
                        user_id text not null,
                        msg_id text not null,
                        channel_id text not null)""")

    conn.execute("""CREATE TABLE lists (
                        fav_id int,
                        listname text not null,
                        foreign key(fav_id) references favs(fav_id))""")


def setup(bot):
    os.makedirs("data/favs", exist_ok=True)

    do_init = not os.path.exists("data/favs/favs.db")
    conn = sqlite3.connect("data/favs/favs.db")
    conn.isolation_level = None  # autocommit

    do_init and init_db(conn)

    n = GreenBook(bot, conn)
    bot.add_cog(n)
