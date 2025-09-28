# commands.py - Slash commands for Discord bot

import discord
from discord import app_commands
from datetime import datetime, timezone
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
            timestamp=datetime.now(timezone.utc)
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
    def __init__(self, bot, sheets_manager, user_points):
        self.bot = bot
        self.sheets_manager = sheets_manager
        self.user_points = user_points
    
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

    async def leaderboard(self, interaction: discord.Interaction):
        # Display the activity points leaderboard with pages
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
                    timestamp=datetime.now(timezone.utc)
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

    async def reset_weekly(self, interaction: discord.Interaction):
        # Test the weekly reset function
        try:
            await interaction.response.defer()
            await self.sheets_manager.reset_weekly_activity()
            await interaction.followup.send("✅ **Weekly reset completed!** All activity checkboxes have been reset.")
        except Exception as e:
            await interaction.followup.send(f"❌ **Error during reset:** {e}")