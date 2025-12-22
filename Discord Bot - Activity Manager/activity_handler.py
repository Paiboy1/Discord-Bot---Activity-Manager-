import re
import discord
from config import *

class ActivityHandler:
    def __init__(self, sheets_manager, user_points, role_manager=None):
        self.sheets_manager = sheets_manager
        self.user_points = user_points
        self.role_manager = role_manager
        
    # Main activity log processing logic
    async def process_activity_log(self, message):
        
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

        # Let manual reactions handle the approval/rejection
        print(f"Valid activity log format detected for: {message.channel.name}")

    # Process approved activity log
    async def process_activity_approval(self, message):
        try:
            time_data = self.extract_time_data(message.content)
            if not time_data:
                return
            
            hours, mins = time_data
            user_name = message.channel.name
            
            # ONE API call to get all user data
            user_data = self.sheets_manager.batch_get_user_data(user_name)
            if not user_data:
                print(f"Error: Could not find {user_name} in spreadsheet")
                return
            
            is_on_loa = user_data['loa_status'] == "LoA"
            
            # Prepare all updates
            updates = []
            
            if not is_on_loa:
                # Update activity checkbox
                updates.append({
                    'row': user_data['row_index'],
                    'col': ACTIVITY_COLUMN + 1,
                    'value': True
                })
            
            if hours >= MIN_HOURS_FOR_POINTS:
                points_to_award = hours * POINTS_PER_HOUR
                new_total = user_data['points'] + points_to_award
                
                # Update points
                updates.append({
                    'row': user_data['row_index'],
                    'col': POINTS_COLUMN + 1,
                    'value': new_total
                })
                
                # ONE API call for all updates
                if updates:
                    self.sheets_manager.batch_update_cells(updates)
                
                # Check promotion with data we already have
                promo_check = self.sheets_manager.check_promotion_eligibility_from_data(
                    new_total, user_data['rank']
                )
                
                # Auto-promote if eligible and doesn't need application
                if promo_check["eligible"] and not promo_check.get("needs_application", False) and self.role_manager:
                    member = message.channel.owner
                    if member:
                        await self.role_manager.auto_rank(member, promo_check['next_rank'])
                
                # Send response
                if hours >= MIN_HOURS_FOR_POINTS:
                    points_to_award = hours * POINTS_PER_HOUR
                    
                    # Make promotion message if eligible
                    promo_message = ""
                    if promo_check["eligible"]:
                        if promo_check.get("needs_application", False):
                            promo_message = f"\n• **🎖️ Promotion Available:** Eligible for **{promo_check['next_rank']}**\n• Please complete the MR Ascension form: {MR_ASCENSION_FORM_URL} to be eligible for **E5**"
                        else:
                            promo_message = f"\n• **🏆 PROMOTED:** You have been promoted to **{promo_check['next_rank']}**!"
                    
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
                        await message.reply(
                            f"✅ **Activity Logged Successfully!**\n"
                            f"• Time logged: {hours} hours {mins} mins\n"
                            f"• Points awarded: {points_to_award} points\n"
                            f"• Total points: {new_total} points\n"
                            f"{promo_message}",
                            mention_author=False
                        )
                else:
                    await message.reply(
                        f"✅ Logged! Please note that this log does not meet the minimum requirement of 1 hour.",
                        mention_author=False
                    )
                
            else:
                # Just update activity if needed
                if updates:
                    self.sheets_manager.batch_update_cells(updates)
                
                await message.reply(
                    f"✅ Logged! Please note that this log does not meet the minimum requirement of 1 hour.",
                    mention_author=False
                )
                
        except Exception as e:
            print(f"Error processing activity approval: {e}")

    # Extract and validate time data from their message    
    def extract_time_data(self, content):
        

        match = re.search(r'\*\*Total time:\*\*\s*(?P<hours>\d+)\s*hours?\s*(?P<mins>\d{1,2})\s*mins?', content, re.IGNORECASE)
        if match:
            hours = int(match.group('hours'))
            mins = int(match.group('mins'))
            return (hours, mins)
        
        # "xx hour(s)" 
        match = re.search(r'\*\*Total time:\*\*\s*(?P<hours>\d+)\s*hours?', content, re.IGNORECASE)
        if match:
            hours = int(match.group('hours'))
            return (hours, 0)
        
        # "xx mins"
        match = re.search(r'\*\*Total time:\*\*\s*(?P<mins>\d{1,2})\s*mins?', content, re.IGNORECASE)
        if match:
            mins = int(match.group('mins'))
            return (0, mins)
        
        return None