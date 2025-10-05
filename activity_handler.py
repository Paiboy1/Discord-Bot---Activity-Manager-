# activity_handler.py - Activity log processing for Discord bot

import re
import discord
from config import *

class ActivityHandler:
    def __init__(self, sheets_manager, user_points):
        self.sheets_manager = sheets_manager
        self.user_points = user_points
    
    async def process_activity_log(self, message):
        # Main activity log processing logic - validation only, no automatic approval
        # Check if there's at least one attachment
        if not message.attachments:
            await message.reply(
                "❌ **Missing Proof Image**\n\n"
                "Your activity log must include an **image attachment** as proof of your activity.\n"
                "Please resubmit your log with a screenshot or photo attached to verify your time.\n\n"
                "**Required format:**\n"
                "```\n"
                "Start time: xx:xx (timezone)\n"
                "End time: xx:xx (timezone)\n"
                "Total time: xx hours xx mins\n"
                "Proof:\n"
                "```\n"
                "+ **Image attachment required**",
                mention_author=False
            )
            return

        # Validate and extract time data
        time_data = self.extract_time_data(message.content)
        if not time_data:
            await message.reply(
                "❌ **Error: Your `Total time:` line is incorrect.**\n"
                "Please check the format and try again. A correctly formatted log should look like this:\n"
                "`Total time: x hour xx mins`\n"
                "`Total time: x hour(s)`\n"
                "`Total time: xx mins`",
                mention_author=False
            )
            return
        
        hours, mins = time_data
        
        # Validate minutes
        if not (0 <= mins <= 59):
            await message.reply("❌ **Error:** The minutes value must be between 00 and 59.", mention_author=False)
            return

        # If we get here, the format is valid - do nothing else
        # Let manual reactions handle the approval/rejection
        print(f"Valid activity log format detected for: {message.channel.name}")

    async def process_activity_approval(self, message):
        # Process approved activity log
        try:
            # Extract and validate time data 
            time_data = self.extract_time_data(message.content)
            if not time_data:
                print("Error: Could not extract time data during approval")
                return
            
            hours, mins = time_data
            user_name = message.channel.name
            
            print(f"Processing approved activity for: {user_name}")

            # Check if user is on LOA before updating activity checkbox
            is_on_loa = self.sheets_manager.is_user_on_loa(user_name)
            
            if not is_on_loa:
                # Only update activity checkbox if user is NOT on LOA
                if not self.sheets_manager.update_activity_checkbox(user_name):
                    print(f"Error: Could not find {user_name} in spreadsheet")
                    return
            else:
                print(f"User {user_name} is on LOA - skipping activity checkbox update")

            # Handle points awarding (this should happen regardless of LOA status)
            if hours < MIN_HOURS_FOR_POINTS:
                # MAKE SURE THERE'S NO add_reaction HERE
                loa_note = " (LOA - activity not counted but time logged)" if is_on_loa else ""
                await message.reply(
                    f"✅ Logged! Please note that this log does not meet the minimum requirement of 1 hour and will not be counted towards points.",
                    mention_author=False
                )
            else:
                # MAKE SURE THERE'S NO add_reaction IN award_points EITHER
                await self.award_points(message.author.id, hours, mins, user_name, message, is_on_loa)

        except Exception as e:
            print(f"Error processing activity approval: {e}")
    
    def extract_time_data(self, content):
        # Extract and validate time data from message
        # Handles these formats:
        # - Total time: xx hours xx mins
        # - Total time: xx hour(s) 
        # - Total time: xx mins

        match = re.search(r'Total time:\s*(?P<hours>\d+)\s*hours?\s*(?P<mins>\d{1,2})\s*mins?', content, re.IGNORECASE)
        if match:
            hours = int(match.group('hours'))
            mins = int(match.group('mins'))
            return (hours, mins)
        
        # Try format: "xx hour(s)" (no minutes)
        match = re.search(r'Total time:\s*(?P<hours>\d+)\s*hours?', content, re.IGNORECASE)
        if match:
            hours = int(match.group('hours'))
            return (hours, 0)
        
        # Try format: "xx mins" (no hours)
        match = re.search(r'Total time:\s*(?P<mins>\d{1,2})\s*mins?', content, re.IGNORECASE)
        if match:
            mins = int(match.group('mins'))
            return (0, mins)
        
        return None
    
    async def award_points(self, discord_user_id, hours, mins, username, message, is_on_loa=False):
        points_to_award = hours * POINTS_PER_HOUR
        
        # Get current points from spreadsheet
        try:
            cell = self.sheets_manager.worksheet.find(username)
            row_index = cell.row
            
            # Get current points from spreadsheet
            current_points_cell = self.sheets_manager.worksheet.cell(row_index, POINTS_COLUMN + 1)
            current_points = int(current_points_cell.value) if current_points_cell.value and str(current_points_cell.value).isdigit() else 0
            
            # Calculate new total
            new_total = current_points + points_to_award
            
            # Save new total to spreadsheet
            self.sheets_manager.save_points_to_spreadsheet(str(discord_user_id), new_total, username)

             # Check promotion eligibility after updating points
            promo_check = self.sheets_manager.check_promotion_eligibility(username)
            
            # Build promotion message if eligible
            promo_message = ""
            if promo_check["eligible"]:
                if promo_check["needs_application"]:
                    promo_message = f"\n• **🎖️ Promotion Available:** Eligible for **{promo_check['next_rank']}**\n• Please complete the MR Ascension form: {MR_ASCENSION_FORM_URL} to be eligible for **E5**"
                else:
                    promo_message = f"\n• **🎖️ Promotion Available:** Eligible for **{promo_check['next_rank']}**"
        
            
            # Different messages based on LOA status
            if is_on_loa:
                await message.reply(
                    f"✅ **Activity Logged Successfully!**\n"
                    f"• Time logged: {hours} hours {mins} mins\n"
                    f"• Points awarded: {points_to_award} points\n"
                    f"• Total points: {new_total} points\n"
                    f"• **Note:** You are on LOA - points awarded but activity not counted",
                    mention_author=False
                )
            else:
                # Check if this is specifically the MR Ascension promotion
                mention_user = promo_check.get("needs_application", False)

                await message.reply(
                    f"✅ **Activity Logged Successfully!**\n"
                    f"• Time logged: {hours} hours {mins} mins\n"
                    f"• Points awarded: {points_to_award} points\n"
                    f"• Total points: {new_total} points\n"
                    f"{promo_message}",
                    mention_author=False
                )
            
        except Exception as e:
            print(f"Error getting current points for {username}: {e}")