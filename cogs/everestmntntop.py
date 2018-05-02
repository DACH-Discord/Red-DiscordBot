import os
import random
import time
from threading import Timer

from __main__ import user_allowed
from discord.ext import commands

from .utils import checks
from .utils.dataIO import dataIO


class Everestmntntop:

    def __init__(self, bot):
        self.bot = bot
        self.file_path = "data/everestmntntop/comments.json"
        self.channels_path = "data/everestmntntop/channels.json"
        self.comments = dataIO.load_json(self.file_path)
        self.channels = dataIO.load_json(self.channels_path)
        self.cooldown = False
        # self.cooldown_timer = dataIO.load_json(self.cooldown_path) 
        self.cooldown_timer = 29

    def _check_channel(self, channel):
        return channel in self.channels

    @commands.command(pass_context=True, no_pm=True)
    @checks.mod_or_permissions(administrator=True)
    async def addquote(self, ctx, user: str, *, text):
        user = user.lower()
        if user not in self.comments:
            self.comments[user] = []
        if text not in self.comments[user]:
            self.comments[user].append(text)
            dataIO.save_json(self.file_path, self.comments)
            await self.bot.say("Neuen Kommentar zu user %s hinzugefügt." % user)
        else:
            await self.bot.say("Kommentar existiert bereits!")

    @commands.command(pass_context=True, no_pm=True)
    @checks.mod_or_permissions(administrator=True)
    async def wlQuoteChannel(self, ctx, channel=None):
        if channel is None:
            channel = ctx.message.channel

        channel_id = channel.id
        if channel_id not in self.channels:
            self.channels.append(channel_id)
            dataIO.save_json(self.channels_path, self.channels)

    @commands.command(pass_context=True, no_pm=True)
    async def listquotes(self, ctx, name=None):
        if name is None:
            channel_id = ctx.message.channel.id
            counts = []
            for name in self.comments:
                counts.append("%s - %s" % (name, len(self.comments[name])))
            await self.bot.say("```python\nAnzahl Kommentare:\n\n%s```" % "\n".join(counts))
        else:
            try:
                await self.bot.say("```Anzahl Kommentare von %s : %s```" % (name, len(self.comments[name.lower()])))
            except KeyError:
                await self.bot.say("```User %s hat keine Kommentare.```" % name)
                return
            clist = []
            cout = ""
            counter = 0
            for comment in self.comments[name.lower()]:
                counter = counter + 1
                clist.append(str(counter) + " - " + comment)
                cout = "\n".join(clist)
                if (len(cout) >= 1900):
                    cout = "\n".join(clist[:-1])
                    await self.bot.whisper("```%s```" % cout)
                    time.sleep(100.0 / 1000.0)
                    clist = clist[-1:]
            await self.bot.whisper("```%s```" % cout)

    async def checkCC(self, message):
        if message.author.id == self.bot.user.id or len(message.content) < 2 or message.channel.is_private:
            return

        if not self._check_channel(message.channel.id):
            return

        if not user_allowed(message):
            return

        msg = message.content
        prefix = self.get_prefix(message)
        if prefix == "$":
            cmd = msg[len(prefix):]
            if cmd.lower() in self.comments and not self.cooldown:
                self.cooldown = True
                Timer(self.cooldown_timer, self.setCooldownFalse, [], {}).start()
                comment = random.choice(self.comments[cmd.lower()])
                await self.bot.send_message(message.channel, comment)

    def setCooldownFalse(self):
        self.cooldown = False

    def get_prefix(self, message):
        for p in self.bot.settings.get_prefixes(message.server):
            if message.content.startswith(p):
                return p
        return False


def check_folders():
    if not os.path.exists("data/everestmntntop"):
        os.makedirs("data/everestmntntop")


def check_files():
    f = "data/everestmntntop/comments.json"
    if not dataIO.is_valid_json(f):
        dataIO.save_json(f, {})
    g = "data/everestmntntop/channels.json"
    if not dataIO.is_valid_json(g):
        dataIO.save_json(g, [])
    h = "data/everestmntntop/cooldown.json"


def setup(bot):
    check_folders()
    # check_files()
    # check_files LÖSCHT alle Daten, falls ein Fehler vorliegt! NICHT BENUTZEN!
    n = Everestmntntop(bot)
    bot.add_listener(n.checkCC, "on_message")
    bot.add_cog(n)
