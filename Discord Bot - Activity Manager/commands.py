# commands.py - Slash commands for Discord bot

import discord
from discord import app_commands
from datetime import datetime, timezone as tz, timedelta
from config import *
import asyncio
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
    def __init__(self, bot, sheets_manager, user_points, active_log, pending_proof, timezone_offsets=None, role_manager=None):
        self.bot = bot
        self.sheets_manager = sheets_manager
        self.user_points = user_points
        self.active_log = active_log
        self.pending_proof = pending_proof
        self.status_board_message_id = None
        self.timezone_offsets = timezone_offsets or {}
        self.role_manager = role_manager

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
            name="time", 
            description="Check how long you've been clocked in",
            callback=self.check_time
        ))

        self.bot.tree.add_command(app_commands.Command(
            name="clockout",
            description="Clock out to stop log timer",
            callback=self.clockout
        ))

        self.bot.tree.add_command(app_commands.Command(
            name="deploy",
            description="Create a deployment announcement",
            callback=self.deploy
        ))

    def parse_timezone(self, timezone_str):
        # Handle every timezone using the loaded Timezones.txt file
        if not timezone_str:
            return None
        
        # Remove all spaces and convert to uppercase
        timezone_str = timezone_str.replace(" ", "").upper().strip()
        
        # First check the loaded timezone offsets from Timezones.txt
        if timezone_str in self.timezone_offsets:
            return self.timezone_offsets[timezone_str]
        
        # Handle GMT+X or UTC+X format (for custom offsets)
        match = re.match(r'(GMT|UTC)([+-])(\d+(?:\.\d+)?)', timezone_str)
        if match:
            sign = 1 if match.group(2) == '+' else -1
            offset = float(match.group(3))
            return sign * offset
        
        return None
    
    async def update_status_board(self):
        channel = self.bot.get_channel(SESSION_STATUS_CHANNEL_ID)
        if not channel:
            return
        
        rank_hierarchy = {
            "E9": 9, "E8": 8, "E7": 7, "E6": 6,
            "E5": 5, "E4": 4, "E3": 3, "E2": 2, "E1": 1
        }
        
        online_data = []
        
        # Batch get all user data at once instead of individual queries
        usernames_to_fetch = [session.get("username") for session in self.active_log.values()]
        
        # Get all at once from cache
        for user_id, session in self.active_log.items():
            user = self.bot.get_user(user_id)
            if not user:
                continue
            
            username = session.get("username")
            user_data = self.sheets_manager.get_cached_user_data(username)
            rank = user_data['rank'] if user_data else "E1"
            
            rank_value = rank_hierarchy.get(rank, 0)
            online_data.append({
                "user": user,
                "rank": rank,
                "rank_value": rank_value
            })
        
        # Sort by rank
        online_data.sort(key=lambda x: x["rank_value"], reverse=True)
        
        commander = None
        operatives = []
        
        if online_data:
            # Check if highest ranked person is E5 or above
            if online_data[0]["rank_value"] >= 5:  # E5 or higher
                commander = online_data[0]["user"].mention
                # Everyone else goes to operatives
                operatives = [person["user"].mention for person in online_data[1:]]
            else:
                # No one is E5+, no commander
                operatives = [person["user"].mention for person in online_data]
        
        # Build message content
        content = "**Commander**\n"
        content += commander if commander else "None"
        content += "\n\n**Operatives**\n"
        content += "\n".join(operatives) if operatives else "None"
        
        # Create or update message
        try:
            # Only fetch if we don't have the message ID cached
            if not self.status_board_message_id:
                messages = [msg async for msg in channel.history(limit=5)]
                bot_messages = [msg for msg in messages if msg.author.id == self.bot.user.id]
                
                if bot_messages:
                    message = bot_messages[0]
                    self.status_board_message_id = message.id
                else:
                    message = await channel.send(content, silent=True)
                    self.status_board_message_id = message.id
                    return
            else:
                # Use cached message ID
                try:
                    message = await channel.fetch_message(self.status_board_message_id)
                except discord.NotFound:
                    # Message was deleted, create new one
                    message = await channel.send(content, silent=True)
                    self.status_board_message_id = message.id
                    return
            
            await message.edit(content=content)
            
        except Exception as e:
            print(f"Error updating status board: {e}")

    # Display the activity points leaderboard with pages
    async def leaderboard(self, interaction: discord.Interaction):
        if not await self._check_server(interaction):
            return
        
        try:
            # Use cached data - ONE API call
            all_values = self.sheets_manager.get_all_users_cached()
            
            leaderboard_data = []
            valid_statuses = ["Active", "Inactive", "LOA"]
            
            # Process rows
            for i, row in enumerate(all_values[3:], start=4):
                if len(row) <= max(POINTS_COLUMN, STATUS_COLUMN, 1):
                    continue
                    
                username = row[1].strip() if len(row) > 1 and row[1] else ""
                
                # Skip empty usernames
                if not username:
                    continue
                
                status = row[STATUS_COLUMN] if len(row) > STATUS_COLUMN else ""
                status = status.strip()  # Remove whitespace
                
                # If status is completely blank/empty, we've reached the end
                if status == "":
                    break 
                
                # If status is "N/A" or "REMOVED" or anything invalid, skip but continue
                if not any(s in status for s in valid_statuses):
                    continue  
                
                points = row[POINTS_COLUMN] if len(row) > POINTS_COLUMN else "0"
                point_value = int(points) if points.isdigit() else 0
                
                discord_id = row[DISCORD_ID_COLUMN] if len(row) > DISCORD_ID_COLUMN else ""
                display_name = username
                
                # Only lookup Discord member if we have ID
                if discord_id:
                    try:
                        member = interaction.guild.get_member(int(discord_id))
                        if member:
                            display_name = member.nick or member.display_name
                    except:
                        pass
                
                leaderboard_data.append((display_name, point_value))
            
            print(f"DEBUG: Found {len(leaderboard_data)} users for leaderboard")
            
            if not leaderboard_data:
                embed = discord.Embed(
                    title="Leaderboard",
                    description="No users found.",
                    color=0x3498db
                )
                await interaction.response.send_message(embed=embed)
                return
            
            # Sort and create view
            sorted_users = sorted(leaderboard_data, key=lambda x: (-x[1], x[0].lower()))
            view = LeaderboardView(sorted_users, interaction)
            embed = view.get_embed()
            
            await interaction.response.send_message(embed=embed, view=view)
            
        except Exception as e:
            print(f"Leaderboard error: {e}")
            await interaction.response.send_message(f"⚠️ Error: {e}", ephemeral=True)

    # Check points for a specific user
    @app_commands.describe(user="Member to check points for (optional)")
    async def points(self, interaction: discord.Interaction, user: discord.Member = None):
        if not await self._check_server(interaction):
            return
    
        try:
            target_user = user or interaction.user
            discord_id = str(target_user.id)
            
            # Use cache instead of multiple API calls
            username = self.sheets_manager.get_username_by_discord_id(discord_id)
            
            if not username:
                await interaction.response.send_message(
                    f"❌ Error: Could not find user in roster.",
                    ephemeral=True
                )
                return
            
            # Get cached data
            user_data = self.sheets_manager.get_cached_user_data(username)
            
            if not user_data:
                await interaction.response.send_message(
                    f"❌ Error: Could not find data for {username}.",
                    ephemeral=True
                )
                return
            
            points = user_data['points']
            
            if user:
                await interaction.response.send_message(
                    f"**{username}** has **{points} points**"
                )
            else:
                await interaction.response.send_message(
                    f"You have **{points} points**"
                )
                
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error: {e}",
                ephemeral=True
            )

    # Manually add points to a user
    @app_commands.describe(amount="Number of points to add", member="Member to add points to")
    async def add_points(self, interaction: discord.Interaction, amount: int, member: discord.Member):
        if not await self._check_server(interaction):
            return
        
        # Defer the response since this might take a while
        await interaction.response.defer()
        
        try:
            # Get Discord ID
            discord_id = str(member.id)
            print(f"[DEBUG /add] Looking up Discord ID: {discord_id}")
            
            # Search spreadsheet by Discord ID to get username
            username = self.sheets_manager.get_username_by_discord_id(discord_id)
            
            if not username:
                await interaction.followup.send(
                    f"❌ **Error:** Could not find {member.display_name} in the roster. "
                    f"Make sure their Discord ID ({discord_id}) is in Column Q of the spreadsheet.",
                    ephemeral=True
                )
                return
            
            print(f"[DEBUG /add] Found username: {username} for Discord ID: {discord_id}")
            
            # Get user data using the username
            user_data = self.sheets_manager.batch_get_user_data(username)
            if not user_data:
                await interaction.followup.send(
                    f"❌ **Error:** Could not find data for {username}",
                    ephemeral=True
                )
                return
            
            current_points = user_data['points']
            current_rank = user_data['rank']
            
            # Add new points to current total
            new_total = current_points + amount
            
            # Save new total to spreadsheet
            self.sheets_manager.update_points(username, new_total)
            
            print(f"[DEBUG /add] Current rank: {current_rank}, Points: {current_points} -> {new_total}")
            
            # Check promotion eligibility
            promo_check = self.sheets_manager.check_promotion_eligibility_from_data(
                new_total, current_rank
            )
            print(f"[DEBUG /add] Promo check: {promo_check}")
            print(f"[DEBUG /add] Role manager exists: {self.role_manager is not None}")
            
            # Auto-promote if eligible and doesn't need application
            promo_message = ""
            if promo_check["eligible"] and not promo_check.get("needs_application", False) and self.role_manager:
                print(f"[DEBUG /add] Attempting auto-rank: {member.display_name} from {current_rank} to {promo_check['next_rank']}")
                result = await self.role_manager.auto_rank(member, promo_check['next_rank'])
                print(f"[DEBUG /add] Auto-rank result: {result}")
                
                if result:
                    promo_message = f"\n• **🏆 PROMOTED:** {member.display_name} has been promoted to **{promo_check['next_rank']}**!"
                else:
                    promo_message = f"\n• **⚠️ Promotion failed** - check console logs"
            elif promo_check["eligible"] and promo_check.get("needs_application", False):
                promo_message = f"\n• **🎖️ Promotion Available:** Eligible for **{promo_check['next_rank']}**\n• Please complete the MR Ascension form: {MR_ASCENSION_FORM_URL}"
            
            await interaction.followup.send(
                f"✅ **Points Added!**\n"
                f"• Added **{amount} points** to **{member.display_name}** ({username})\n"
                f"• Previous total: **{current_points} points**\n"
                f"• New total: **{new_total} points**"
                f"{promo_message}"
            )
                
        except Exception as e:
            print(f"[ERROR /add] {e}")
            import traceback
            traceback.print_exc()
            await interaction.followup.send(f"❌ **Error:** Could not add points. {e}", ephemeral=True)
    
    # Manually remove points from a user
    @app_commands.describe(amount="Number of points to remove", member="Member to remove points from")
    async def remove_points(self, interaction: discord.Interaction, amount: int, member: discord.Member):
        if not await self._check_server(interaction):
            return
        try:
            # Extract username from Discord member's display name
            import re
            username = str(member.id)
            
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
    
    # Remove member from LOA status
    @app_commands.describe(user="Member to remove from LOA status")
    async def loa_remove(self, interaction: discord.Interaction, user: discord.Member):
        if not await self._check_server(interaction):
            return

        try:
            # Defer immediately to prevent timeout
            await interaction.response.defer()
            
            # First try to get username by Discord ID from spreadsheet
            username = str(user.id)
            
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
    
    # Clock into session status
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
        
        # validate timezones
        offset_hours = self.parse_timezone(timezone.upper())
        if offset_hours is None:
            await interaction.response.send_message(
                f"❌ **Invalid timezone: `{timezone}` Ask foxhole if your timezone is in the list**\n\n",
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
        
        tz_msg = f" ({timezone.upper()})" if timezone else ""
        await interaction.response.send_message(
            f"✅ You are now **Online!** Timer started{tz_msg}",
            ephemeral=True
        )

        # Start tracking
        self.active_log[user_id] = {
            "start_time": datetime.now(tz.utc),
            "timezone": timezone.upper() if timezone else None,
            "username": username
        }

        print(f"[CLOCKIN] User {user_id} clocked in with timezone: {timezone.upper()}")

        # Updates session board
        await self.update_status_board()
        
    # Clockout of session status
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
        
        # Calculate total time BEFORE adding to pending_proof (prevents race condition)
        total_time_delta = session_data["end_time"] - session_data["start_time"]
        session_data["total_time"] = total_time_delta

        if note:
            session_data["note"] = note

        await interaction.response.send_message(
            "✅ You are now **Offline!**\n\n"
            "Please send your proof image in your activity thread.\n"
            "The log will be automatically posted after you send the image.\n\n"
            "If you don't send proof within **5 minutes**, your session will be cancelled.",
            ephemeral=True
        )

        # Start 5-minute timer
        asyncio.create_task(self._proof_timeout_handler(user_id, interaction.user))
        
        # Move session data to pending_proof (ALL data must be ready before this!)
        self.pending_proof[user_id] = session_data
        print(f"[CLOCKOUT] User {user_id} added to pending_proof. Current pending: {list(self.pending_proof.keys())}")

        await self.update_status_board()
        
        # Calculate time components for display
        total_seconds = int(total_time_delta.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
    
    async def _proof_timeout_handler(self, user_id, user):
        # Handle timeout if user doesn't send proof within 5 minutes
        await asyncio.sleep(300) 
        
        # Check if they're still in pending_proof (they didn't send image)
        if user_id in self.pending_proof:
            session_data = self.pending_proof.pop(user_id)
            
            total_seconds = int(session_data["total_time"].total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            
            print(f"[TIMEOUT] User {user_id} ({user.name}) failed to send proof within 5 minutes. Session cancelled: {hours}h {minutes}m")

    # Check current session time
    async def check_time(self, interaction: discord.Interaction):
        if not await self._check_server(interaction):
            return
        
        user_id = interaction.user.id
        
        # Check if user is clocked in
        if user_id not in self.active_log:
            await interaction.response.send_message(
                "⚠️ You are not currently clocked in.",
                ephemeral=True
            )
            return
        
        session_data = self.active_log[user_id]
        start_time = session_data["start_time"]
        current_time = datetime.now(tz.utc)
        
        # Calculate elapsed time
        elapsed = current_time - start_time
        total_seconds = int(elapsed.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        
        # Build simple response
        response = f"You have been clocked in for: **{hours} hours {minutes} mins**"
        
        await interaction.response.send_message(response, ephemeral=True)

    # Deployment command to start 
    @app_commands.describe(note="What the deployment is about")
    async def deploy(self, interaction: discord.Interaction, note: str):
        if not await self._check_server(interaction):
            return
        
        # Defer immediately to prevent timeout
        await interaction.response.defer(ephemeral=True)

        try:
            channel = self.bot.get_channel(DEPLOYMENT_ID)

            # Create the deployment message
            deployment_message = (
                f"<@&1332029491463065670>\n"
                f"# 🚨 SESSION DEPLOYMENT 🚨"
                f"\n\n"
                f"{note}\n\n"
                f"**Commander**\n{interaction.user.mention}\n\n"
                f"**Operatives**\n"
                f"None"
                f"\n\n"
                f"React to join the deployment and earn points!"
            )
            
            # Send the deployment announcement
            message = await channel.send(
                deployment_message,
                allowed_mentions=discord.AllowedMentions(roles=True)
            )

            await message.add_reaction("✅")

            await interaction.edit_original_response(content="✅ Deployment created!")
            
        except Exception as e:
            await interaction.followup.send(f"❌ **Error:** Could not create deployment. {e}", ephemeral=True)

    
    # Reset the weekly activity
    async def reset_weekly(self, interaction: discord.Interaction):
        if not await self._check_server(interaction):
            return
        
        try:
            await interaction.response.defer()
            await self.sheets_manager.reset_weekly_activity()
            await interaction.followup.send("✅ **Weekly reset completed!** All activity checkboxes have been reset.")
        except Exception as e:
            await interaction.followup.send(f"❌ **Error during reset:** {e}")