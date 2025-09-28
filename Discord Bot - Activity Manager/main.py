# main.py - Main Discord bot file

import discord
from discord.ext import commands
from config import *
from sheets_manager import SheetsManager
from commands import Commands
from activity_handler import ActivityHandler
from loa_handler import LOAHandler

# Initialize components
sheets_manager = SheetsManager()
user_points = {}

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.messages = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Initialize handlers
activity_handler = ActivityHandler(sheets_manager, user_points)
commands_handler = Commands(bot, sheets_manager, user_points)
loa_handler = LOAHandler(sheets_manager)

def get_squadron_from_roles(member):
    # Extract squadron from user's Discord roles
    role_to_squadron = {
        "[-] Protection Squadron [-]": "Protection",
        "[-] Medical Squadron [-]": "Medical", 
        "[-] Assault Squadron [-]": "Assault"
    }
    
    for role in member.roles:
        print(f"  - '{role.name}'")
    
    for role in member.roles:
        if role.name in role_to_squadron:
            return role_to_squadron[role.name]
    
    # Default fallback
    print(f"DEBUG: No squadron role found for {member.display_name}, using fallback: Protection")
    return "Protection"

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    print('Bot is ready to update the Google Sheet.')
    
    # Load points from spreadsheet
    sheets_manager.load_points_from_spreadsheet(user_points)
    
    # Setup commands
    commands_handler.setup_commands()
    
    # Join forum threads
    await join_forum_threads()

@bot.event
async def on_thread_create(thread):
    # Handle new thread creation in forum channel
    if thread.parent_id == FORUM_CHANNEL_ID:
        username = thread.name
        
        # Check if user exists in spreadsheet
        if not sheets_manager.user_exists(username):
            print(f"New user detected: {username}. Creating spreadsheet entry.")
            
            # Get squadron from thread owner's roles
            squadron = get_squadron_from_roles(thread.owner)
            
            # Create new user entry in spreadsheet
            success = sheets_manager.create_new_user_entry(username, str(thread.owner.id), squadron)
            
            if success:
                print(f"Successfully created entry for {username}")
            else:
                print(f"Failed to create entry for {username}")
        
        # Send welcome message
        message_content = (
            f"**Welcome to TF-416, {thread.owner.mention}!**\n"
            "I am the activity manager for this department. Please send your logs in the following format:\n\n"
            "```\n"
            "Start time: xx:xx (timezone)\n"
            "End time: xx:xx (timezone)\n"
            "Total time: xx hours xx mins\n"
            "Proof:\n"
            "```\n"
            "Total time also allows:\n"
            "```\n"
            "Total time: xx hour(s)\n"
            "Total time: xx mins\n"
            "```\n"
            "You must have at least 1 hour in your log to earn points."
        )
        await thread.send(message_content)

@bot.event
async def on_message(message):
    # Handle incoming messages
    if message.author == bot.user:
        return
    
    # Handle LOA requests in LOA channel
    if message.channel.id == LOA_CHANNEL_ID:
        if loa_handler.is_valid_loa_format(message.content):
            # Just return, don't add any reactions - let a Officer do reactions
            return
    
    # Handle activity logs in forum channel
    if (hasattr(message.channel, 'parent_id') and 
        message.channel.parent_id == FORUM_CHANNEL_ID and 
        "Total time:" in message.content):
        await activity_handler.process_activity_log(message)
    
    await bot.process_commands(message)

@bot.event  
async def on_raw_reaction_add(payload):
    # Handle reactions to messages (works for both cached and uncached messages)
    if payload.user_id == bot.user.id:
        return
    
    # Get the channel and check if it's LOA channel
    if payload.channel_id == LOA_CHANNEL_ID and str(payload.emoji) == "✅":
        try:
            # Get the channel and message
            channel = bot.get_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            
            # Check if message contains LOA format
            if loa_handler.is_valid_loa_format(message.content):
                loa_data = loa_handler.extract_loa_data(message.content)
                
                if loa_data:
                    await loa_handler.process_loa_approval(message, loa_data)
        except Exception as e:
            print(f"Error processing LOA reaction: {e}")
    
    # Check if reaction is in forum channel for activity logs
    try:
        # Get the channel to check if it's a forum thread
        channel = bot.get_channel(payload.channel_id)
        
        if (hasattr(channel, 'parent_id') and 
            channel.parent_id == FORUM_CHANNEL_ID and 
            str(payload.emoji) == "✅"):
            
            # Fetch the message to check its content
            message = await channel.fetch_message(payload.message_id)
            
            if "Total time:" in message.content:
                # Process the approval
                await activity_handler.process_activity_approval(message)
                
    except Exception as e:
        print(f"Error processing activity reaction: {e}")


async def join_forum_threads():
    # Join all existing threads in the forum channel
    try:
        # Sync slash commands
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")

        # Find the channel
        forum_channel = bot.get_channel(FORUM_CHANNEL_ID)
        if not forum_channel:
            print(f"Could not find a channel with ID {FORUM_CHANNEL_ID}")
            return

        # Loop through all posts in the channel
        for thread in forum_channel.threads:
            if bot.user not in thread.members:
                await thread.join()
                print(f"Joined thread: {thread.name}")
    except Exception as e:
        print(f"An error occurred while joining threads: {e}")

def find_username_in_title(title, usernames):
    # Helper function to find username in thread title
    for user in usernames:
        if user.lower() in title.lower():
            return user
    return None

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)