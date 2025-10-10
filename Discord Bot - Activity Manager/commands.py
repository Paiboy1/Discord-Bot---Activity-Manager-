# commands.py - Slash commands for Discord bot

import discord
from discord import app_commands
from datetime import datetime, timezone as tz, timedelta
from config import *
import re

class LeaderboardView(discord.ui.View):
    def __init__(self, leaderboard_data, interaction):
        super().__init__(timeout=None) 
        self.leaderboard_data = leaderboard_data
        self.interaction = interaction
        self.current_page = 0
        self.users_per_page = 10
        self.total_pages = (len(leaderboard_data) - 1) // self.users_per_page + 1
        
        # Update button states
        self.update_buttons()
    
    def update_buttons(self):
        # Update button states based on current page
        self.previous_button.disabled = (self.current_page == 0)
        self.next_button.disabled = (self.current_page >= self.total_pages - 1)
    
    def get_embed(self):
        # Create embed for current page
        start_idx = self.current_page * self.users_per_page
        end_idx = min(start_idx + self.users_per_page, len(self.leaderboard_data))
        page_users = self.leaderboard_data[start_idx:end_idx]
        
        embed = discord.Embed(
            title="Leaderboard",
            color=0x3498db,
            timestamp=datetime.now(tz.utc)
        )
        
        leaderboard_text = ""
        for i, (display_name, points) in enumerate(page_users, start=start_idx + 1):
            leaderboard_text += f"{i}) {display_name} - **{points} points**\n"
        
        embed.description = leaderboard_text
        embed.set_footer(text=f"Page {self.current_page + 1}/{self.total_pages} • Showing {len(self.leaderboard_data)} users")
        
        return embed
    
    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary, custom_id="previous")
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, custom_id="next")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)
        else:
            await interaction.response.defer()

class Commands:
    def __init__(self, bot, sheets_manager, user_points, active_log, pending_proof):
        self.bot = bot
        self.sheets_manager = sheets_manager
        self.user_points = user_points
        self.active_log = active_log
        self.pending_proof = pending_proof
        self.status_board_message_id = None

    async def _check_server(self, interaction: discord.Interaction) -> bool:
        if interaction.guild_id != SERVER_ID:
            await interaction.response.send_message(
                "⚠️ Paiboy1 has taken the Bot down for maintenance, Will be back up soon!", 
                ephemeral=True
            )
            return False
        return True
    
    def setup_commands(self):
        # Register all slash commands with the bot
        self.bot.tree.add_command(app_commands.Command(
            name="leaderboard", 
            description="Display the activity points leaderboard",
            callback=self.leaderboard
        ))
        
        self.bot.tree.add_command(app_commands.Command(
            name="points", 
            description="Check the balance for the given user",
            callback=self.points
        ))
        
        self.bot.tree.add_command(app_commands.Command(
            name="add", 
            description="Add to member's balance",
            callback=self.add_points
        ))
        
        self.bot.tree.add_command(app_commands.Command(
            name="remove", 
            description="Remove points from member's balance",
            callback=self.remove_points
        ))
        
        self.bot.tree.add_command(app_commands.Command(
            name="reset", 
            description="Weekly reset function",
            callback=self.reset_weekly
        ))

        self.bot.tree.add_command(app_commands.Command(
            name="loa", 
            description="Remove member from LOA status",
            callback=self.loa_remove
        ))

        self.bot.tree.add_command(app_commands.Command(
            name="clockin",
            description="Clock in to start log timer",
            callback=self.clockin
        ))

        self.bot.tree.add_command(app_commands.Command(
            name="clockout",
            description="Clock out to stop log timer",
            callback=self.clockout
        ))

    def parse_timezone(self, timezone_str):
        # Handle every timezone
        if not timezone_str:
            return None
        
        timezone_str = timezone_str.upper().strip()
        
        # Named timezones
        named_timezones = {
            "EST": -5, "EDT": -4,
            "PST": -8, "PDT": -7,
            "GMT": 0, "UTC": 0,
            "BST": 1,
            "CST": -6, "CDT": -5,
            "MST": -7, "MDT": -6,
            "IST": 5.5,  
            "JST": 9,    
            "AEST": 10, 
            "CET": 2,  
        }
        
        if timezone_str in named_timezones:
            return named_timezones[timezone_str]
        
        # Handle GMT+X or UTC+X format
        match = re.match(r'(GMT|UTC)([+-])(\d+(?:\.\d+)?)', timezone_str)
        if match:
            sign = 1 if match.group(2) == '+' else -1
            offset = float(match.group(3))
            return sign * offset
        
        return None
    
    async def update_status_board(self):
        # Update the session status board
        channel = self.bot.get_channel(SESSION_STATUS_CHANNEL_ID)
        if not channel:
            print("Session status channel not found")
            return
        
        # Determine commander and online users
        commander = None
        online_users = []
        
        for user_id, session in self.active_log.items():
            user = self.bot.get_user(user_id)
            if not user:
                continue
            
            # Get their rank from spreadsheet
            username = session.get("username")
            rank = self.sheets_manager.get_user_rank(username)
            
            # Check if E5 or higher for commander role
            if rank and rank in ["E5", "E6", "E7", "E8", "E9"]:
                if not commander:
                    commander = user.mention
                else:
                    online_users.append(user.mention)
            else:
                online_users.append(user.mention)
        
        # Build message content
        content = "**Commander**\n"
        content += commander if commander else "None"
        content += "\n\n**Operatives**\n"
        content += "\n".join(online_users) if online_users else "None"
        
        # Create or update message
        try:
            # Fetch the most recent message in the channel
            messages = [msg async for msg in channel.history(limit=10)]
            bot_messages = [msg for msg in messages if msg.author.id == self.bot.user.id]
            
            if bot_messages:
                # Edit the most recent bot message
                await bot_messages[0].edit(content=content)
            else:
                # No existing message, create a new one
                await channel.send(content, silent=True)
        except Exception as e:
            print(f"Error updating status board: {e}")
            return


    async def leaderboard(self, interaction: discord.Interaction):
        # Display the activity points leaderboard with pages
        if not await self._check_server(interaction):
            return
        try:
            # Get all data directly from spreadsheet
            all_values = self.sheets_manager.worksheet.get_all_values()
            
            leaderboard_data = []
            
            # Find the actual end of usernames by looking for empty usernames
            last_user_row = 0
            for i, row in enumerate(all_values[3:], start=4): 
                if len(row) > 1:
                    username = row[1].strip() if row[1] else ""  
                    if username:  # If there's a username, this is a valid user row
                        last_user_row = i
                    else:
                        break  # Stop at first empty username
            
            # Extract usernames and points from spreadsheet 
            for i, row in enumerate(all_values[3:last_user_row], start=4):
                if len(row) > max(POINTS_COLUMN, STATUS_COLUMN, 1):
                    username = row[1].strip() if len(row) > 1 and row[1] else ""  
                    points = row[POINTS_COLUMN] if len(row) > POINTS_COLUMN else "0"
                    discord_id = row[DISCORD_ID_COLUMN] if len(row) > DISCORD_ID_COLUMN and row[DISCORD_ID_COLUMN] else ""
                    status = row[STATUS_COLUMN] if len(row) > STATUS_COLUMN else ""
                    
                    # Skip users who don't have an active status (likely hidden/former members)
                    # Only include users with "Active", "Inactive", or "LOA" status (exclude empty status)
                    valid_statuses = ["Active", "Inactive", "LOA"]
                    
                    # Include users with usernames AND valid status
                    if username and any(status_val in str(status) for status_val in valid_statuses):
                        point_value = int(points) if points.isdigit() else 0
                        
                        # Try to find Discord member to get their nickname (fallback to username if not found)
                        display_name = username 
                        
                        if discord_id:
                            # If we have Discord ID, try to get their server nickname
                            try:
                                member = interaction.guild.get_member(int(discord_id))
                                if member:
                                    display_name = member.nick if member.nick else member.display_name
                            except:
                                pass
                        else:
                            # If no Discord ID, try to find member by username extraction
                            for member in interaction.guild.members:
                                # Extract username from Discord display name
                                import re
                                extracted = re.sub(r'^(\[.*?\]|\(.*?\)|[A-Z]+\d*\s*-\s*)', '', member.display_name).strip()
                                if extracted.lower() == username.lower():
                                    display_name = member.nick if member.nick else member.display_name
                                    break
                        
                        leaderboard_data.append((display_name, point_value))
            
            if not leaderboard_data:
                embed = discord.Embed(
                    title="Leaderboard",
                    description="No users found in the spreadsheet.",
                    color=0x3498db,
                    timestamp=datetime.now(tz.utc)
                )
                embed.set_footer(text="Page 1/1")
                await interaction.response.send_message(embed=embed)
                return
            
            # Sort by points descending, then by name ascending for ties
            sorted_users = sorted(leaderboard_data, key=lambda x: (-x[1], x[0].lower()))
            
            # Create paged leaderboard view
            view = LeaderboardView(sorted_users, interaction)
            embed = view.get_embed()
            
            await interaction.response.send_message(embed=embed, view=view)
            
        except Exception as e:
            await interaction.response.send_message(f"⚠ **Error:** Could not generate leaderboard. {e}")

    
    @app_commands.describe(user="Username to check points for (optional)")
    async def points(self, interaction: discord.Interaction, user: str = None):
        if not await self._check_server(interaction):
            return
        # Check points for a specific user
        try:
            if user:
                # Check if this is a Discord mention format <@123456789>
                import re
                mention_match = re.match(r'<@(\d+)>', user)
                
                if mention_match:
                    # This is a Discord mention, extract the Discord ID
                    discord_id = mention_match.group(1)
                    username = self.sheets_manager.get_username_by_discord_id(discord_id)
                    
                    if not username:
                        await interaction.response.send_message(f"❌ **Error:** Could not find Discord ID '{discord_id}' in the roster spreadsheet.")
                        return
                else:
                    # This is a regular username string, clean it
                    # First remove @ symbol if present
                    user_clean = user.lstrip('@')
                    # Then remove rank prefixes like [SGT], (RANK), etc.
                    username = re.sub(r'^(\[.*?\]|\(.*?\)|[A-Z]+\d*\s*-\s*)', '', user_clean).strip()
                
                # Now look up the points for the username
                try:
                    cell = self.sheets_manager.worksheet.find(username)
                    row_index = cell.row
                    
                    # Get current points from spreadsheet
                    current_points_cell = self.sheets_manager.worksheet.cell(row_index, POINTS_COLUMN + 1)
                    points = int(current_points_cell.value) if current_points_cell.value and str(current_points_cell.value).isdigit() else 0
                    
                    await interaction.response.send_message(f"**{username}** has **{points} points**")
                    
                except Exception as find_error:
                    await interaction.response.send_message(f"❌ **Error:** Could not find username '{username}' in the roster spreadsheet.")
            else:
                # Show current user's points by Discord ID lookup
                user_id = str(interaction.user.id)
                username = self.sheets_manager.get_username_by_discord_id(user_id)
                
                if username:
                    try:
                        cell = self.sheets_manager.worksheet.find(username)
                        row_index = cell.row
                        
                        # Get current points from spreadsheet
                        current_points_cell = self.sheets_manager.worksheet.cell(row_index, POINTS_COLUMN + 1)
                        points = int(current_points_cell.value) if current_points_cell.value and str(current_points_cell.value).isdigit() else 0
                        
                        await interaction.response.send_message(f"You have **{points} points**")
                        
                    except Exception as find_error:
                        await interaction.response.send_message(f"❌ **Error:** Could not find your username '{username}' in the roster spreadsheet.")
                else:
                    await interaction.response.send_message("❌ **Error:** Could not find your Discord ID in the roster spreadsheet.")
                    
        except Exception as e:
            await interaction.response.send_message(f"❌ **Error:** Could not check points. {e}")
    
    @app_commands.describe(amount="Number of points to add", member="Member to add points to")
    async def add_points(self, interaction: discord.Interaction, amount: int, member: discord.Member):
        if not await self._check_server(interaction):
            return
        # Manually add points to a user
        try:
            # Extract username from Discord member's display name
            import re
            cleaned_name = re.sub(r'^(\[.*?\]|\(.*?\)|[A-Z]+\d*\s*-\s*)', '', member.display_name).strip()
            username = cleaned_name
            
            # Get current points from spreadsheet
            try:
                cell = self.sheets_manager.worksheet.find(username)
                row_index = cell.row
                
                # Get current points
                current_points_cell = self.sheets_manager.worksheet.cell(row_index, POINTS_COLUMN + 1)
                current_points = int(current_points_cell.value) if current_points_cell.value and str(current_points_cell.value).isdigit() else 0
                
                # Add new points to current total
                new_total = current_points + amount
                
                # Save new total to spreadsheet
                self.sheets_manager.worksheet.update_cell(row_index, POINTS_COLUMN + 1, new_total)
                
                await interaction.response.send_message(
                    f"✅ **Points Added!**\n"
                    f"• Added **{amount} points** to **{member.display_name}** ({username})\n"
                    f"• Previous total: **{current_points} points**\n"
                    f"• New total: **{new_total} points**"
                )
                
            except Exception as find_error:
                await interaction.response.send_message(
                    f"❌ **Error:** Could not find username '{username}' in the roster spreadsheet. "
                    f"Make sure {member.display_name}'s Roblox username is in the roster."
                )

        except Exception as e:
            await interaction.response.send_message(f"❌ **Error:** Could not add points. {e}")
    
    @app_commands.describe(amount="Number of points to remove", member="Member to remove points from")
    async def remove_points(self, interaction: discord.Interaction, amount: int, member: discord.Member):
        if not await self._check_server(interaction):
            return
        # Manually remove points from a user
        try:
            # Extract username from Discord member's display name
            import re
            cleaned_name = re.sub(r'^(\[.*?\]|\(.*?\)|[A-Z]+\d*\s*-\s*)', '', member.display_name).strip()
            username = cleaned_name
            
            # Get current points from spreadsheet
            try:
                cell = self.sheets_manager.worksheet.find(username)
                row_index = cell.row
                
                # Get current points
                current_points_cell = self.sheets_manager.worksheet.cell(row_index, POINTS_COLUMN + 1)
                current_points = int(current_points_cell.value) if current_points_cell.value and str(current_points_cell.value).isdigit() else 0
                
                # Subtract points from current total
                new_total = current_points - amount
                
                # Prevent negative points
                if new_total < 0:
                    new_total = 0
                
                # Save new total to spreadsheet
                self.sheets_manager.worksheet.update_cell(row_index, POINTS_COLUMN + 1, new_total)
                
                await interaction.response.send_message(
                    f"✅ **Points Removed!**\n"
                    f"• Removed **{amount} points** from **{member.display_name}** ({username})\n"
                    f"• Previous total: **{current_points} points**\n"
                    f"• New total: **{new_total} points**"
                )
                
            except Exception as find_error:
                await interaction.response.send_message(
                    f"❌ **Error:** Could not find username '{username}' in the roster spreadsheet. "
                    f"Make sure {member.display_name}'s Roblox username is in the roster."
                )
            
        except Exception as e:
            await interaction.response.send_message(f"❌ **Error:** Could not remove points. {e}")
    
    @app_commands.describe(user="Member to remove from LOA status")
    async def loa_remove(self, interaction: discord.Interaction, user: discord.Member):
        if not await self._check_server(interaction):
            return
        # Remove member from LOA status
        try:
            # Defer immediately to prevent timeout
            await interaction.response.defer()
            
            # First try to get username by Discord ID from spreadsheet
            username = self.sheets_manager.get_username_by_discord_id(str(user.id))
            
            if not username:
                # If not found by Discord ID, try to extract from display name
                display_name = user.display_name
                
                import re
                cleaned_name = re.sub(r'^(\[.*?\]|\(.*?\)|[A-Z]+\d*\s*-\s*)', '', display_name).strip()
                username = cleaned_name
            
            if not username:
                await interaction.followup.send(
                    f"❌ **Error:** Could not determine Roblox username for {user.mention}. "
                    f"Make sure their Discord ID is in the spreadsheet or their display name contains their Roblox username."
                )
                return
            
            # Try to remove LOA status directly
            success = self.sheets_manager.remove_loa_status(username)
            
            if success:
                await interaction.followup.send(
                    f"✅ **LOA Status Removed**\n"
                )
            else:
                await interaction.followup.send(
                    f"❌ **Error:** Could not find Roblox username '{username}' in the roster spreadsheet. "
                    f"Please check the spelling or ensure they're in the roster."
                )
            
        except Exception as e:
            await interaction.followup.send(f"❌ **Error:** Could not remove LOA status. {e}")
    
    @app_commands.describe(timezone="Your timezone (e.g., EST, PST, GMT, BST)")
    async def clockin(self, interaction: discord.Interaction, timezone: str = None):
        if not await self._check_server(interaction):
            return
        
        if not timezone:
            await interaction.response.send_message(
                "⚠️ Timezone is required! Please use: `/clockin timezone:EST` (or PST, GMT, etc.)",
                ephemeral=True
            )
            return
        
        # Get username from spreadsheet by Discord ID
        username = self.sheets_manager.get_username_by_discord_id(str(interaction.user.id))

        user_id = interaction.user.id
        
        # Check if already clocked in
        if user_id in self.active_log:
            await interaction.response.send_message(
                "⚠️ You're already clocked in! Use `/clockout` to finish your session.",
                ephemeral=True
            )
            return
        
        # Start tracking
        self.active_log[user_id] = {
            "start_time": datetime.now(tz.utc),
            "timezone": timezone.upper() if timezone else None,
            "username": username
        }

        # Updates session board
        await self.update_status_board()
        
        tz_msg = f" ({timezone})" if timezone else ""
        await interaction.response.send_message(
            f"You are now **Online!** Timer started{tz_msg}",
            ephemeral=True
        )
    
    @app_commands.describe(note="Optional note to add to your activity log")
    async def clockout(self, interaction: discord.Interaction, note: str = None):
        if not await self._check_server(interaction):
            return
        
        user_id = interaction.user.id
        
        # Check if the user is currently clocked in
        if user_id not in self.active_log:
            await interaction.response.send_message(
                "⚠️ You are not currently clocked in. Use `/clockin` to start your session.",
                ephemeral=True
            )
            return
        
        session_data = self.active_log.pop(user_id)
        session_data["end_time"] = datetime.now(tz.utc)

        await self.update_status_board()
        
        # Calculate total time
        total_time_delta = session_data["end_time"] - session_data["start_time"]
        session_data["total_time"] = total_time_delta

        if note:
            session_data["note"] = note

        # Move session data to pending_proof
        self.pending_proof[user_id] = session_data
        
        # Calculate time components for display
        total_seconds = int(total_time_delta.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        
        # Send confirmation and request for proof
        await interaction.response.send_message(
            f"✅ **Clocked Out!**\n\n"
            f"Please send your proof image in your activity thread.\n"
            f"The log will be automatically posted after you send the image.\n",
            ephemeral=True
        )

    

    async def reset_weekly(self, interaction: discord.Interaction):
        if not await self._check_server(interaction):
            return
        # Test the weekly reset function
        try:
            await interaction.response.defer()
            await self.sheets_manager.reset_weekly_activity()
            await interaction.followup.send("✅ **Weekly reset completed!** All activity checkboxes have been reset.")
        except Exception as e:
            await interaction.followup.send(f"❌ **Error during reset:** {e}")