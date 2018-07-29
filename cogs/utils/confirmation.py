from functools import wraps

from discord.ext.commands import Context


def reaction_confirm(func):
    """A decorator to wrap a command function. The original message from the user will
    receive a positive reaction when the command result evaluates to True, and a negative
    reaction otherwise. Use it like this::

        @commands.command(pass_context=True)
        @reaction_confirm
        async def my_command(self, ctx):
            return True
    """

    @wraps(func)
    async def decorator(*args, **kwargs):
        success = await func(*args, **kwargs)

        if len(args) >= 2 and isinstance(args[1], Context):
            ctx = args[1]  # type: Context
        else:
            raise TypeError("Use pass_context=True for your command!")

        if success:
            await ctx.bot.add_reaction(ctx.message, "\N{WHITE HEAVY CHECK MARK}")
        else:
            await ctx.bot.add_reaction(ctx.message, "\N{NEGATIVE SQUARED CROSS MARK}")

    return decorator


def delete_confirm(func):
    """A decorator to wrap a command function. The original message from the user will
    be deleted immediately. Use it like this::

        @commands.command(pass_context=True)
        @delete_confirm
        async def my_command(self, ctx):
            return True
    """

    @wraps(func)
    async def decorator(*args, **kwargs):
        if len(args) >= 2 and isinstance(args[1], Context):
            ctx = args[1]  # type: Context
        else:
            raise TypeError("Use pass_context=True for your command!")

        # Cannot delete messages in private channels
        if not ctx.message.channel.is_private:
            await ctx.bot.delete_message(ctx.message)

        await func(*args, **kwargs)

    return decorator
