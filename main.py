import json
import os
import re
import discord
from discord.ext import commands
import ollama
import asyncio

config = json.load(open("config.json"))

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=config["prefix"], intents=intents)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}!")
    await bot.change_presence(activity=discord.CustomActivity(name=config["status"]))


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
    await bot.change_presence(activity=discord.CustomActivity(name=config["status"]))
    await ctx.reply("config reloaded")


@bot.event
async def on_message(message: discord.Message):
    override = False
    try:
        always_respond_channel_id = int(config["always_respond_channel_id"])
    except KeyError:
        always_respond_channel_id = None
    if always_respond_channel_id:
        if message.channel.id == always_respond_channel_id:
            override = True
    if (bot.user in message.mentions or re.search(r'\b' + re.escape(config["name"].lower()) + r'\b', message.content.lower()) or override) and not message.content.startswith(config["prefix"]) and not message.content.startswith("-#") and not message.content == "---" and not message.author == bot.user and not message.author.bot:
        async with message.channel.typing():
            conversation = await get_conversation(message.channel.id)
            response = await get_response(conversation, message)
            try:
                await message.reply(response[:2000], mention_author=True)
            except discord.HTTPException as e:
                pass
    await bot.process_commands(message)


async def clean_message(message: str):
    for ping_match in list(re.finditer(r"<@!?(\d+)>", message)):
        user_id = int(ping_match.group(1))
        try:
            user = await bot.fetch_user(user_id)
            message = message.replace(
                ping_match.group(0), f"\"{user.display_name}\" (@{user.name})")
        except:
            pass

    for emoji_match in list(re.finditer(r"<a?:(\w+):(\d+)>", message)):
        emoji_name = emoji_match.group(1)
        try:
            message = message.replace(
                emoji_match.group(0), f":{emoji_name}:")
        except:
            pass

    return message


async def get_response(conversation, message: discord.Message):
    try:
        if config["append_default_system"]:
            reply_context = message.reference if message.reference else None
            if reply_context:
                reply_message = await message.channel.fetch_message(reply_context.message_id)
            emois = await get_emojis()
            conversation.insert(len(conversation) - 1,
                                {"role": "system", "content": f"you are a discord bot. your current display name is {bot.user.display_name}, and your username is @{bot.user.name}. you can use markdown to format your messages. only reply to the latest message in the conversation unless strictly necessary. try to keep responses short.\nyou are currently replying to \"{message.author.display_name}\" (@{message.author.name}) saying \"{await clean_message(message.content)}\"" + (
                                    f' in the context of "{reply_message.author.display_name}" (@{reply_message.author.name}) saying "{await clean_message(reply_message.content)}".' if reply_context else '.') + f"\nyou are currently in \"#{message.channel.name}\", within the server \"{message.guild.name}\". to ping somebody, just do it like this: @username (just the person's username with an @ in front), not like this: <@userid>. NEVER copy the user's message, always give a unique response, or you will be BRUTALLY MURDERED.\ncurrently available emojis (to use these, just type :emoji_name_here: (the emoji name wrapped in colons) NOT <:emoji_name_here:id>): {', '.join(emois)}"})
        if config["system"] != "":
            conversation.insert(len(conversation) - 1,
                                {"role": "system", "content": config["system"]})

        if 'response_lock' not in globals():
            response_lock = asyncio.Lock()

        async with response_lock:
            print(
                f"replying to @{message.author.name} in #{message.channel.name} in {message.guild.name} saying \"{await clean_message(message.content)}\"")

            final_message = ""
            async for chunk in await ollama.AsyncClient().chat(
                model=config["model"],
                messages=conversation,
                stream=True,
                options={
                    "temperature": config["temperature"]
                }
            ):
                content = chunk.message.content
                print(content, end="", flush=True)
                final_message += content

            response = final_message
            print("\n")
    except Exception as e:
        return f"yell at <@854819626969333771> for being stupid and while you're at it, give them this error\n`{e}`"

    response
    matches = re.finditer(r":(.*?):", response)
    for match in matches:
        emoji_code = await get_emoji_code(match.group(1))
        if emoji_code:
            response = response.replace(f":{match.group(1)}:", emoji_code)

    angle_matches = re.finditer(r"<@([a-zA-Z0-9_]+)>", response)
    for match in angle_matches:
        ping_code = await get_ping_code(match.group(1), message.guild.id)
        if ping_code:
            response = response.replace(f"<@{match.group(1)}>", ping_code)

    matches = re.finditer(r"@([a-zA-Z0-9_]+)", response)
    for match in matches:
        ping_code = await get_ping_code(match.group(1), message.guild.id)
        if ping_code:
            response = response.replace(f"@{match.group(1)}", ping_code)

    response = re.sub(r'<(?!@)(\d+)>', r'<@\1>', response)

    response = re.sub(r'[^\x00-\x7F]+', '', response)

    return response


@bot.command()
@commands.is_owner()
async def dump_system(ctx):
    try:
        message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
    except Exception as e:
        await ctx.reply(f"failed to fetch message, did you run the command in reply to a message?\n`{e}`")
        return
    reply_context = message.reference if message.reference else None
    if reply_context:
        reply_message = await message.channel.fetch_message(reply_context.message_id)
    emois = await get_emojis()
    system_message = f"you are a discord bot. your current display name is {bot.user.display_name}, and your username is @{bot.user.name}. you can use markdown to format your messages. only reply to the latest message in the conversation unless strictly necessary. try to keep responses short.\nyou are currently replying to \"{message.author.display_name}\" (@{message.author.name}) saying \"{await clean_message(message.content)}\"" + (
        f' in the context of "{reply_message.author.display_name}" (@{reply_message.author.name}) saying "{await clean_message(reply_message.content)}".' if reply_context else '.') + f"\nyou are currently in \"#{message.channel.name}\", within the server \"{message.guild.name}\". to ping somebody, just do it like this: @username (just the person's username with an @ in front), not like this: <@userid>. NEVER copy the user's message, always give a unique response, or you will be BRUTALLY MURDERED.\ncurrently available emojis (to use these, just type :emoji_name_here: (the emoji name wrapped in colons) NOT <:emoji_name_here:id>): {', '.join(emois)}"
    await ctx.reply(f"```{system_message}```")


async def get_emojis():
    emojis = []
    emoji_strings = []
    for guild in bot.guilds:
        for emoji in guild.emojis:
            emojis.append(emoji)
    for emoji in emojis:
        emoji_strings.append(f"{emoji.name}")
    return emoji_strings


async def get_emoji_code(emoji_name):
    for guild in bot.guilds:
        for emoji in guild.emojis:
            if emoji.name == emoji_name:
                if emoji.animated:
                    emoji_code = f"<a:{emoji.name}:{emoji.id}>"
                else:
                    emoji_code = f"<:{emoji.name}:{emoji.id}>"
                return emoji_code
    return None


async def get_ping_code(username, guild_id):
    guild = bot.get_guild(guild_id)
    if guild:
        for member in guild.members:
            if member.name.lower() == username.lower():
                return f"<@{member.id}>"
    return username


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
                print(current_chunk)
                current_chunk.reverse()
                current_message["content"] = "\n".join(current_chunk)
                current_chunk = []
                conversation.append(current_message)
                current_message = {"role": "assistant", "content": ""}
            current_chunk.append(await clean_message(message.content))
        else:
            if message.content == "---":
                break
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
            if not message.content.startswith(config["prefix"]) and not message.content.startswith("-#"):
                message_content = await clean_message(message.content)

                current_chunk.append((f'"{message.author.display_name}" (@{message.author.name}) said "{message_content}"' +
                                     (f' in the context of "{reply_message.author.display_name}" (@{reply_message.author.name}) saying "{await clean_message(reply_message.content)}"' if reply_context and reply_message else '')))
    if len(current_chunk) > 0:
        current_chunk.reverse()
        current_message["content"] = "\n".join(current_chunk)
        conversation.append(current_message)
    conversation.pop(0)
    conversation.reverse()

    return conversation

bot.run(config["token"])
