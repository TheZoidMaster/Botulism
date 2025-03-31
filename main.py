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
    if bot.user in message.mentions or config["name"].lower() in message.content.lower():
        if message.author == bot.user:
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
    if config["append_system"]:
        reply_context = message.reference if message.reference else None
        if reply_context:
            reply_message = await message.channel.fetch_message(reply_context.message_id)
        conversation.insert(len(conversation) - 1,
                            {"role": "system", "content": f"you are a discord bot. your current display name is {bot.user.display_name}, and your username is @{bot.user.name}. you can use markdown to format your messages. only reply to the latest message in the conversation unless strictly necessary. try to keep responses short.\nyou are currently replying to {message.author.display_name} (@{message.author.name}) saying \"{message.content}\"" + (f' in response to {reply_message.author.display_name} saying "{reply_message.content}".' if reply_context else '.') + f"\nyou are currently in \"#{message.channel.name}\", which is in the \"{message.channel.category.name}\" category, within the server \"{message.guild.name}\". NEVER copy the user's message, always give a unique response."})
    if config["system"] != "":
        conversation.insert(len(conversation) - 1,
                            {"role": "system", "content": config["system"]})

    for _ in range(10):
        response = await ollama.AsyncClient().chat(
            model=config["model"],
            messages=conversation,
            stream=False,
            options={
                "temperature": config["temperature"]
            }
        )
        if await check_parroting(conversation, response.message.content):
            break
    else:
        response.message.content = "I'm sorry, I couldn't generate a suitable response after multiple attempts."

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
                                 (f' replying to {reply_message.author.display_name} (@{reply_message.author.name}) saying "{reply_message.content}"' if reply_context and reply_message else '')).replace(f"<@{bot.user.id}>", f"@{bot.user.name}"))
    if len(current_chunk) > 0:
        current_chunk.reverse()
        current_message["content"] = "\n".join(current_chunk)
        conversation.append(current_message)
    conversation.pop(0)
    conversation.reverse()

    return conversation


async def check_parroting(proposed_conversation, proposed_response):
    conversation_string = "\n".join(
        [f'{message["role"]}: {message["content"]}' for message in proposed_conversation]
    )
    conversation = [
        {"role": "system", "content": f"The user is going to give you a conversation and a proposed response. Use your \"allow_message\" tool to allow or deny the message. Deny the message if it is a copy of another message in the conversation, otherwise allow it. Do not be too strict. Never respond in text, always use the \"allow_message\" tool."},
        {"role": "user", "content": f"Conversation: {conversation_string}\n\nProposed Response: {proposed_response}"},
    ]

    print("checking response: ", proposed_response)

    response = await ollama.AsyncClient().chat(
        model=config["model"],
        messages=conversation,
        stream=False,
        tools=[{
            "type": "function",
            "function": {
                "name": "allow_response",
                "description": "allow or disallow the response",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "response": {
                            "type": "boolean",
                            "description": "whether to allow the response or not",
                        }
                    },
                    "required": ["response"]
                }
            }
        }]
    )

    print("parroting check response: ", response.message.content)

    if response.message.tool_calls:
        for tool in response.message.tool_calls:
            if tool.function.name == "allow_response":
                try:
                    print("tool call found, returning ",
                          tool.function.arguments["response"])
                    return bool(tool.function.arguments["response"])
                except:
                    print(
                        "tool call found, but error parsing response, returning False")
                    return False

    print("no tool call found, returning False")

    return False


bot.run(config["token"])
