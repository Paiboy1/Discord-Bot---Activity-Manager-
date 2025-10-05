# loa_handler.py - LOA request processing for Discord bot

import re
import discord
from config import *

class LOAHandler:
    def __init__(self, sheets_manager):
        self.sheets_manager = sheets_manager
    
    def is_valid_loa_format(self, content):
        # Check if message matches LOA format
        required_fields = ["Username:", "Start:", "End:", "Reason:"]
        return all(field in content for field in required_fields)
    
    def extract_loa_data(self, content):
        # Extract LOA data from message content
        try:
            lines = content.split('\n')
            data = {}
            
            for line in lines:
                if line.startswith("Username:"):
                    raw_username = line.replace("Username:", "").strip()
                    # Clean the username like the /loa command does
                    cleaned_username = re.sub(r'^(\[.*?\]|\(.*?\)|[A-Z]+\d*\s*-\s*)', '', raw_username).strip()
                    # Remove quotes if present
                    cleaned_username = cleaned_username.strip('"')
                    data['username'] = cleaned_username
                elif line.startswith("Start:"):
                    data['start'] = line.replace("Start:", "").strip()
                elif line.startswith("End:"):
                    data['end'] = line.replace("End:", "").strip()
                elif line.startswith("Reason:"):
                    data['reason'] = line.replace("Reason:", "").strip()
            
            return data
        except Exception as e:
            print(f"Error extracting LOA data: {e}")
            return None
    
    async def process_loa_approval(self, message, user_data):
        # Process approved LOA request
        try:
            username = user_data['username']
            
            # Update spreadsheet
            success = self.sheets_manager.update_loa_status(username, "LOA", make_black=True)
            
            if success:
                print(f"LOA approved for {username}")
            else:
                print(f"Error: Could not find {username} in the roster spreadsheet")
        
        except Exception as e:
            print(f"Error processing LOA approval: {e}")