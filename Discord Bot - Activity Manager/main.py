# main.py - Main Discord bot file

import re
import discord
from discord.ext import tasks, commands
from config import *
from sheets_manager import SheetsManager
from commands import Commands
from activity_handler import ActivityHandler
from loa_handler import LOAHandler
from auto_nickrole import RoleManager

# Initialize components
sheets_manager = SheetsManager()
user_points = {}
active_log = {}
pending_proof = {}

last_row_count = 0 # This is for MR form notifier

# Load timezones from file
timezone_offsets = sheets_manager.load_timezones_from_txt()

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.messages = True
bot = commands.Bot(command_prefix='!', intents=intents)
role_manager = RoleManager(bot, sheets_manager)

# Initialize handlers
activity_handler = ActivityHandler(sheets_manager, user_points, role_manager)
commands_handler = Commands(bot, sheets_manager, user_points, active_log, pending_proof, timezone_offsets, role_manager)
loa_handler = LOAHandler(sheets_manager, role_manager=role_manager)

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

@tasks.loop(minutes=1.0) # This needs to be up here because it needs to be before def on_ready
async def check_for_new_entries():
    global last_row_count
    try:
        spreadsheet = sheets_manager.client.open_by_url(MR_ASCENSION_URL)
        worksheet = spreadsheet.worksheet("Odpovede z formulára 1")
        
        all_values = worksheet.col_values(1)
        current_rows = len(all_values)

        if last_row_count == 0:
            last_row_count = current_rows
            return

        if current_rows > int(last_row_count):
            channel = bot.get_channel(MR_SHEETS_NOTIFIER_ID)
            if channel:
                await channel.send(
                    f"🔔 **New Ascension Form Entry!**\n"
                    f"🔗 (<{MR_ASCENSION_SHEETS_URL}>)",
                )
            last_row_count = current_rows
    except Exception as e:
        print(f"Error checking for new entries: {e}")

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    print('Bot is ready to update the Google Sheet.')
    
    # Load points from spreadsheet
    sheets_manager.load_points_from_spreadsheet(user_points)
    
    # Setup commands
    commands_handler.setup_commands()

    if not check_for_new_entries.is_running():
        check_for_new_entries.start()
    
    # Join forum threads
    await join_forum_threads()

@bot.event
async def on_thread_create(thread):
    # Handle new thread creation in forum channel
    if thread.guild.id != SERVER_ID:
        return
    
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
            f"**Welcome to TF-416, {thread.owner.mention}!**\n\n"
            "I am the **Activity Manager** for this department. Please log your activity using the following slash commands:\n\n"
            
            "1. **Start Session:** Use `/clockin timezone:`\n"
            "   * Example: `/clockin timezone:BST`\n\n"
            
            "2. **End Session:** Use `/clockout` (Optional: add a `note:`)\n"
            "   * Example: `/clockout note:I was with so and so for an hour`\n\n"
            
            "3. **Post Proof:** After clocking out, submit your **proof image** here in this thread. The bot will automatically post your formatted log.\n\n"
            
            "**⚠️ Important Log Rules:**\n"
            "• You can use **/time** to check how long you have played before clocking out (Helpful if trying to play exactly for 1 hour ect.\n)"
            "• You must have at least **1 hour** in your log to earn points.\n"
            "• Don't try log in any other way, it will NOT be accepted otherwise"
        )
        await thread.send(message_content)

@bot.event
async def on_message(message):
    # Handle incoming messages
    if message.author == bot.user:
        return
    
    if message.guild and message.guild.id != SERVER_ID:
        return
        
    # Handles image proofs for activity logs
    if  (hasattr(message.channel, 'parent_id') and 
        message.channel.parent_id == FORUM_CHANNEL_ID and
        message.attachments):
        
        # Debug logging
        print(f"[DEBUG] Image received from {message.author.name}")
        print(f"[DEBUG] Pending proof users: {list(pending_proof.keys())}")
        
        if message.author.id not in pending_proof:
            print(f"[DEBUG] User {message.author.id} not in pending_proof - ignoring image")
            return
        
        try:
            session_data = pending_proof.pop(message.author.id)
            print(f"[DEBUG] Processing proof for {message.author.name}")
        except KeyError:
            print(f"[DEBUG ERROR] User {message.author.id} was in pending_proof but pop()")
            await message.reply(
                "⚠️ **Error:** Could not find your clock-out session.\n",
                mention_author=False
            )
            return
        except Exception as e:
            print(f"[PROOF ERROR] Unexpected error getting session data: {e}")
            await message.reply(
                "❌ **Error:** Something went wrong retrieving your session data.\n",
                mention_author=False
            )
            return
            
        try:
            # Format the times with timezone
            tz_str = session_data.get("timezone", "UTC")
            start_time = session_data["start_time"]
            end_time = session_data["end_time"]

            # Makes sure it appears as the correct timezone    
            user_tz_str = session_data.get("timezone")
            offset_hours = commands_handler.parse_timezone(user_tz_str)

            if offset_hours is not None:
                from datetime import timedelta, timezone as tz
                user_offset = tz(timedelta(hours=offset_hours))
                
                # Convert times to user's timezone
                start_local = start_time.replace(tzinfo=tz.utc).astimezone(user_offset)
                end_local = end_time.replace(tzinfo=tz.utc).astimezone(user_offset)
                
                # Format with timezone
                start_time_str = start_local.strftime("%H:%M")
                end_time_str = end_local.strftime("%H:%M")
            else:
                print(f"[PROOF ERROR] Could not parse timezone: {user_tz_str}")
                await message.reply(
                    "❌ **Error:** Invalid timezone in your session.\n"
                    "Please tell foxhole",
                    mention_author=False
                )
                return
                
            # Calculate hours and minutes
            total_seconds = int(session_data["total_time"].total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
                
            log_message = (
                f"**New Activity Log Detected!**\n\n"
                f"**Start time:** {start_time_str} ({tz_str})\n"
                f"**End time:** {end_time_str} ({tz_str})\n"
                f"**Total time:** {hours} hours {minutes} mins\n"
            )

            if "note" in session_data and session_data["note"]:
                log_message += f"**Note:** {session_data['note']}\n\n"

            log_message += f"**Proof of Activity:**"


            files_to_send = []
            for attachment in message.attachments:
                try:
                    file = await attachment.to_file()
                    files_to_send.append(file)
                except Exception as e:
                    # Log error but continue
                    print(f"[PROOF ERROR] Error downloading attachment: {e}") 
                
            if not files_to_send:
                print(f"[PROOF ERROR] No files could be downloaded from attachments")
                await message.reply(
                    "❌ **Error:** Could not process your image attachments.\n"
                    "Please try sending them again.",
                    mention_author=False
                )
                return
                
            image_urls = [attachment.url for attachment in message.attachments]

            # Delete the original message
            try:
                await message.delete()
            except Exception as e:
                print(f"[PROOF WARNING] Could not delete original message: {e}")
                # Continue anyway - not critical
                
            # Post the formatted log with the image
            posted_message = await message.channel.send(
                content=log_message,
                files=files_to_send
            )
            
            print(f"[PROOF SUCCESS] Posted formatted log for {message.author.name}")
            
            files_to_send.clear()

        except Exception as e:
            print(f"[PROOF ERROR] Failed to process proof image: {e}")
            import traceback
            traceback.print_exc()
            await message.reply(
                "❌ **Error:** Something went wrong processing your activity proof.\n"
                "Your session data has been lost. Please:\n"
                "1. Use `/clockout` again\n"
                "2. Immediately send your proof image\n\n"
                "If this keeps happening, contact paiboy/foxhole.",
                mention_author=False
            )

        return  
    
    # Handle activity logs in forum channel
    if (hasattr(message.channel, 'parent_id') and 
        message.channel.parent_id == FORUM_CHANNEL_ID and 
        "Total time:" in message.content):
        
        # Skip the first message to avoid this sending if someone puts format in description
        messages = [msg async for msg in message.channel.history(limit=2, oldest_first=True)]
        if len(messages) > 0 and messages[0].id == message.id:
            # This is the first message, ignore it
            return
        
        await activity_handler.process_activity_log(message)
    
    await bot.process_commands(message)

@bot.event  
async def on_raw_reaction_add(payload):
    # Handle reactions to messages (works for both cached and uncached messages)
    if payload.user_id == bot.user.id:
        return
    
    if payload.guild_id != SERVER_ID:
        return
    
    # Handle deployment reactions
    if payload.channel_id == DEPLOYMENT_ID and str(payload.emoji) == "✅":
        try:
            channel = bot.get_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            
            # Check if this is a deployment message (contains "Commander" and "Operatives")
            if "**Commander**" in message.content and "**Operatives**" in message.content:
                await update_deployment_board(message, payload.user_id)
        except Exception as e:
            print(f"Error processing deployment reaction: {e}")

    # Get the channel and check if it's LOA channel
    if payload.channel_id == LOA_CHANNEL_ID and str(payload.emoji) == "✅":
        try:
            # Get the channel and message
            channel = bot.get_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            
            # Process LOA approval (no format checking, just use Discord ID)
            await loa_handler.process_loa_approval(message)
        
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

async def find_username_in_title(title, usernames):
    # Helper function to find username in thread title
    for user in usernames:
        if user.lower() in title.lower():
            return user
    return None

async def update_deployment_board(message, user_id):
    # Deployment board when users react
    try:
        user = bot.get_user(user_id)
        if not user:
            return
        
        if user.mention in message.content:
            return 
        
        lines = message.content.split('\n')
        
        operatives_idx = None
        react_line_idx = None
        
        for i, line in enumerate(lines):
            if line.strip() == "**Operatives**":
                operatives_idx = i
            if "React to join" in line or "React with" in line:
                react_line_idx = i
                break
        
        if operatives_idx is None or react_line_idx is None:
            return
        
        if operatives_idx + 1 < len(lines) and lines[operatives_idx + 1].strip() == "None":
            lines[operatives_idx + 1] = user.mention
        else:
            insert_idx = react_line_idx
            
            if react_line_idx > 0 and lines[react_line_idx - 1].strip() == "":
                insert_idx = react_line_idx - 1
            
            lines.insert(insert_idx, user.mention)
        
        new_content = '\n'.join(lines)
        
        # Update the message
        await message.edit(
            content=new_content, 
            allowed_mentions=discord.AllowedMentions(roles=True, users=False)
        )
        
    except Exception as e:
        print(f"Error updating deployment board: {e}")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)