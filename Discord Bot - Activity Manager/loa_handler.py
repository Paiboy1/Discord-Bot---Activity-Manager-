# loa_handler.py - LOA request processing for Discord bot

import discord
from config import *
import re

import discord
from config import *

class LOAHandler:
    def __init__(self, sheets_manager, role_manager=None):
        self.sheets_manager = sheets_manager
        self.role_manager = role_manager

    def extract_end_date(self, content):
        # Extract end date from message content
        # Supports: "Ends: 12/31/2024" or "Ends: 31/12/2024"
        try:
            # Look for "Ends:" followed by a date
            match = re.search(r'Ends?:\s*(\d{1,2})/(\d{1,2})/(\d{2,4})', content, re.IGNORECASE)
            if match:
                part1, part2, year = match.groups()
                # Return the raw date string as found
                return f"{part1}/{part2}/{year}"
            return None
        except Exception as e:
            print(f"Error extracting end date: {e}")
            return None
    
    async def process_loa_approval(self, message):
        # Process LOA approval - just use Discord ID, update spreadsheet, add role, change nickname
        try:
            member = message.author
            guild = message.guild
            discord_id = str(member.id)

            # Check if user has any ignored roles
            ignored_role_ids = LOA_IGNORED_ROLE_IDS if 'LOA_IGNORED_ROLE_IDS' in globals() else []
            for role in member.roles:
                if role.id in ignored_role_ids:
                    return
            
            # Get username from Discord ID using cached data
            username = self.sheets_manager.get_username_by_discord_id(discord_id)
            if not username:
                print(f"Error: Could not find Discord ID {discord_id} in spreadsheet")
                await message.reply(
                    f"❌ **Error:** Could not find your Discord ID in the roster.",
                    mention_author=False
                )
                return
            
            # Extract end date from message
            end_date = self.extract_end_date(message.content)
            if end_date:
                print(f"[DEBUG LOA] Extracted end date: {end_date}")
            
            # Update LOA status in spreadsheet
            success = self.sheets_manager.update_loa_status(username, "LOA", make_black=True)
            if not success:
                print(f"Error: Failed to update LOA status for {username}")
                await message.reply(
                    f"❌ **Error:** Failed to update LOA status in spreadsheet.",
                    mention_author=False
                )
                return
            
            # Add note with end date if found
            if end_date:
                note_success = self.sheets_manager.add_loa_note(username, f"Ends: {end_date}")
                if note_success:
                    print(f"[DEBUG LOA] Added note to LOA cell: Ends: {end_date}")
            
            # Add LOA role using role_manager
            if self.role_manager:
                await self.role_manager.set_loa_role(member)
            
            # Change nickname to [LOA] format using role_manager
            if self.role_manager:
                await self.role_manager.set_loa_nickname(member)
            
            print(f"[DEBUG LOA] LOA approved for {username}")
        
        except Exception as e:
            print(f"Error processing LOA approval: {e}")
            import traceback
            traceback.print_exc()
            await message.reply(
                f"❌ **Error:** Failed to process LOA approval. Check console logs.",
                mention_author=False
            )





























