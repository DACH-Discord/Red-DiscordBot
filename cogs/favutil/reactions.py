import asyncio
from typing import Mapping, Callable, List, Set

from discord import Client, Message


async def create_reaction_menu(bot: Client, msg: Message, options: Mapping[str, Callable], show_options=False,
                               restrict_users: Set = {}):
    accepted_reactions = list(options.keys())

    show_options and await mass_react(bot, msg, accepted_reactions)

    got_valid_reaction = False
    while not got_valid_reaction:
        result = await bot.wait_for_reaction(message=msg, timeout=5 * 60, emoji=accepted_reactions)

        # We get null when timeout is reached
        if not result:
            return

        reaction, user = result

        # Skip false positives
        if show_options and user == bot.user:
            continue

        if reaction.emoji in accepted_reactions:
            got_valid_reaction = True

        if restrict_users and user.id not in restrict_users:
            got_valid_reaction = False

    # Find the correct action and execute it
    for emoji, fut in options.items():
        if emoji == reaction.emoji:
            result = await fut()

    return reaction.emoji, result


async def mass_react(bot: Client, msg: Message, reactions: List):
    futs = []
    for re in reactions:
        futs.append(bot.add_reaction(msg, re))

    await asyncio.gather(*futs)
