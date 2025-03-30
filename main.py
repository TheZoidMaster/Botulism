import asyncio
import json
import os
import discord
from discord.ext import commands
import ollama

config = json.load(open("config.json"))

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=config["prefix"], intents=intents)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}!")


@bot.command()
@commands.is_owner()
async def ping(ctx):
    await ctx.send(f"pong but {bot.latency * 1000:.2f}ms late")


@bot.command()
@commands.is_owner()
async def get_history(ctx: discord.Message, channel_id: int = None):
    if not channel_id:
        channel_id = ctx.channel.id
    message = await ctx.reply("fetching history...")
    conversation = await get_conversation(channel_id)
    if not conversation:
        await message.edit(content="failed to fetch history")
        return
    temp_file = f"temp_{channel_id}.json"
    with open(temp_file, "w") as f:
        json.dump(conversation, f, indent=4)
    await message.edit(content=f"history fetched, saved to {temp_file}")
    with open(temp_file, "rb") as f:
        await ctx.send(file=discord.File(f, filename=f"history_{channel_id}.json"))
    os.remove(temp_file)


@bot.command()
@commands.is_owner()
async def reload_config(ctx):
    global config
    config = json.load(open("config.json"))
    await ctx.reply("config reloaded")


@bot.event
async def on_message(message: discord.Message):
    if bot.user in message.mentions:
        if message.author == bot.user or message.author.bot:
            return
        async with message.channel.typing():
            conversation = await get_conversation(message.channel.id)
            response = await get_response(conversation, message)
            response = response.replace(
                "@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")
            try:
                await message.reply(response[:2000], mention_author=True)
            except discord.HTTPException as e:
                pass
    await bot.process_commands(message)


async def get_response(conversation, message: discord.Message):
    if config["system"] != "":
        conversation.insert(0,
                            {"role": "system", "content": config["system"]})
    if config["append_system"]:
        reply_context = message.reference if message.reference else None
        if reply_context:
            reply_message = await message.channel.fetch_message(reply_context.message_id)
        conversation.insert(0,
                            {"role": "system", "content": f"you are a discord bot. your current display name is {bot.user.display_name}. you can use markdown to format your messages. only reply to the latest message in the conversation unless strictly necessary. try to keep responses short.\nyou are currently replying to {message.author.display_name} (@{message.author.name}) saying \"{message.content}\"" + (f' in reply to {reply_message.author.display_name} saying "{reply_message.content}".' if reply_context else '.') + f"\nyou are currently in \"#{message.channel.name}\", which is in the \"{message.channel.category.name}\" category, within the server \"{message.guild.name}\"."})

    response = await ollama.AsyncClient().chat(
        model=config["model"],
        messages=conversation,
        stream=False,
        options={
            "temperature": config["temperature"]
        }
    )

    return response.message.content


async def get_conversation(channel_id):
    channel = await bot.fetch_channel(channel_id)
    messages = []
    async for message in channel.history(limit=config["history_limit"]):
        messages.append(message)

    conversation = []
    current_message = {"role": "?", "content": ""}
    current_chunk = []
    for message in messages:
        if message.author == bot.user:
            if current_message["role"] == "user" or current_message["role"] == "?":
                current_chunk.reverse()
                current_message["content"] = "\n".join(current_chunk)
                current_chunk = []
                conversation.append(current_message)
                current_message = {"role": "assistant", "content": ""}
            current_chunk.append(message.content)
        else:
            if current_message["role"] == "assistant" or current_message["role"] == "?":
                current_chunk.reverse()
                current_message["content"] = "\n".join(current_chunk)
                current_chunk = []
                conversation.append(current_message)
                current_message = {"role": "user", "content": ""}
            reply_context = message.reference if message.reference else None
            if reply_context:
                try:
                    reply_message = await channel.fetch_message(reply_context.message_id)
                except:
                    reply_message = None
            current_chunk.append((f'{message.author.display_name} (@{message.author.name}) said "{message.content}"' +
                                 (f' in reply to {reply_message.author.display_name} (@{reply_message.author.name}) saying "{reply_message.content}"' if reply_context and reply_message else '')).replace(f"<@{bot.user.id}>", f"@{bot.user.name}"))
    if len(current_chunk) > 0:
        current_chunk.reverse()
        current_message["content"] = "\n".join(current_chunk)
        conversation.append(current_message)
    conversation.pop(0)
    conversation.reverse()

    return conversation

bot.run(config["token"])
