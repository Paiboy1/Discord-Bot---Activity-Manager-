import gspread
from oauth2client.service_account import ServiceAccountCredentials
from config import *

class SheetsManager:
    def __init__(self):
        self.client = None
        self.spreadsheet = None
        self.worksheet = None
        self.connect()
    
    def connect(self):
        # Connect to Google Sheets using service account credentials
        try:
            scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
            self.client = gspread.authorize(creds)
            self.spreadsheet = self.client.open_by_key(SPREADSHEET_ID)
            self.worksheet = self.spreadsheet.worksheet(SHEET_NAME)
            print("Successfully connected to Google Sheets")
        except Exception as e:
            print(f"Error connecting to Google Sheets: {e}")
            raise e
        
    def user_exists(self, username):
        # Check if a username already exists in the spreadsheet
        try:
            all_values = self.worksheet.get_all_values()
            
            for row in all_values[3:]: 
                if len(row) > 1:
                    existing_username = row[1].strip() if row[1] else ""  
                    if existing_username.lower() == username.lower():
                        return True
            return False
        except Exception as e:
            print(f"Error checking if user exists: {e}")
            return False
    
    def create_new_user_entry(self, username, discord_id, squadron):
        # Create a new user entry by copying the last user row and modifying values
        try:
            next_row = self.find_next_empty_row()
            print(f"Adding new user {username} at row {next_row}")
            
            # Find the last valid user row to copy from (before the empty rows)
            template_row = next_row - 1
            if template_row < 4:  
                template_row = 4  
            
            print(f"Using row {template_row} as template for new user")
            
            # Copy the entire row from template to new position
            # This preserves all formatting, dropdowns, formulas, etc.
            source_range = f'A{template_row}:Q{template_row}'
            target_range = f'A{next_row}:Q{next_row}'
            
            # Get the template row data
            template_data = self.worksheet.get(source_range)[0]
            
            # Update the new row with template data
            self.worksheet.update(target_range, [template_data])
            
            # Now modify only the fields we want to change for the new user
            # Username 
            self.worksheet.update_cell(next_row, 2, username)
            
            # Clear Codename/OC name 
            self.worksheet.update_cell(next_row, 4, "")
            
            # Set Rank to E1 
            self.worksheet.update_cell(next_row, 6, "E1")
            
            # Set Squadron 
            self.worksheet.update_cell(next_row, 7, squadron)
            
            # Set Status to Inactive
            self.worksheet.update_cell(next_row, 9, "Inactive")
            
            # Uncheck Activity checkbox 
            self.worksheet.update_cell(next_row, 10, False)
            
            # Set LoA Notice to N/A 
            self.worksheet.update_cell(next_row, 11, "N/A")
            
            # Set Removal to N/A 
            self.worksheet.update_cell(next_row, 12, "N/A")
            
            # Set C+D ACCRED to N/A 
            self.worksheet.update_cell(next_row, 13, "N/A")
            
            # Clear Notes 
            self.worksheet.update_cell(next_row, 14, "")
            
            # Reset Points to 0 
            self.worksheet.update_cell(next_row, 16, 0)
            
            # Set Discord ID 
            self.worksheet.update_cell(next_row, 17, discord_id)
            
            print(f"Successfully created entry for {username} with rank E1 and squadron {squadron}")
            return True
            
        except Exception as e:
            print(f"Error creating new user entry for {username}: {e}")
            return False

    def find_next_empty_row(self):
        # Find the next empty row to add a new user
        try:
            all_values = self.worksheet.get_all_values()
            
            for i, row in enumerate(all_values[3:], start=4):
                if len(row) <= 1 or not row[1].strip():  
                    return i
            
            # If no empty row found, add to the end
            return len(all_values) + 1
            
        except Exception as e:
            print(f"Error finding next empty row: {e}")
            return 4  # Default to row 4 if error
    
    def load_points_from_spreadsheet(self, user_points):
        # Load points from spreadsheet using Discord IDs
        try:
            print("Loading points from spreadsheet...")
            all_values = self.worksheet.get_all_values()
            
            # Load points using Discord IDs
            for i, row in enumerate(all_values[3:], start=4):
                if len(row) > max(POINTS_COLUMN, DISCORD_ID_COLUMN):
                    discord_id = row[DISCORD_ID_COLUMN] if len(row) > DISCORD_ID_COLUMN else ""
                    points = row[POINTS_COLUMN] if len(row) > POINTS_COLUMN else "0"
                    
                    if discord_id and points.isdigit():
                        user_points[discord_id] = int(points)
            
            print(f"Loaded {len(user_points)} user points from spreadsheet")
            
        except Exception as e:
            print(f"Error loading points from spreadsheet: {e}")
            user_points.clear()
    
    def save_points_to_spreadsheet(self, discord_user_id, points, username=None):
        """Save points to spreadsheet using username from thread title"""
        try:
            if not username:
                print(f"No username provided, cannot save points")
                return
                
            print(f"DEBUG: Saving {points} points for username: {username}")
            
            # Find the user's row by username in column B
            cell = self.worksheet.find(username)
            row_index = cell.row
            
            print(f"DEBUG: Found {username} at row {row_index}, updating column {POINTS_COLUMN + 1}")
            
            # Update the points column (P) for this user
            self.worksheet.update_cell(row_index, POINTS_COLUMN + 1, points)
            
            print(f"DEBUG: Successfully saved {points} points for {username}")
            
        except Exception as e:
            print(f"Error saving points for {username}: {e}")
    
    def format_cell_black(self, row, col):
        # Make a cell have black background
        try:
            cell_range = f"{chr(64 + col)}{row}"  # Convert to A1 notation
            
            format_request = {
                "backgroundColor": {
                    "red": 0.0,
                    "green": 0.0,
                    "blue": 0.0,
                    "alpha": 1.0
                },
                "textFormat": {
                    "foregroundColor": {
                        "red": 0.0,
                        "green": 0.0, 
                        "blue": 0.0,
                        "alpha": 0.0
                    }
                }
            }
            
            self.worksheet.format(cell_range, format_request)
            print(f"Formatted cell {cell_range} with black background")
            
        except Exception as e:
            print(f"Error formatting cell black: {e}")
    
    def format_cell_red(self, row, col):
        # Turn status back to red
        try:
            from gspread.utils import rowcol_to_a1
            
            cell_range = rowcol_to_a1(row, col)
            
            format_request = {
                "backgroundColor": {
                    "red": 0.6,
                    "green": 0.0,
                    "blue": 0.0
                },
            }
            
            self.worksheet.format(cell_range, format_request)
            print(f"Applied red background to cell {cell_range}")
            
        except Exception as e:
            print(f"Error formatting cell red at row {row}, col {col}: {e}")

    def remove_loa_status(self, username):
        # Remove LOA status and restore red background
        try:
            cell = self.worksheet.find(username)
            row_index = cell.row
            print(f"Found {username} at row {row_index}")
            
            # Update LoA NOTICE column back to N/A
            self.worksheet.update_cell(row_index, LOA_NOTICE_COLUMN + 1, "N/A")
            print(f"Updated LoA NOTICE to N/A")
            
            # The STATUS column should use a formula that checks the activity checkbox
            original_formula = f'=IF(J{row_index}=TRUE;"Active";"Inactive")'
            self.worksheet.update_cell(row_index, STATUS_COLUMN + 1, original_formula)
            
            # Then apply the red background formatting
            self.format_cell_red(row_index, STATUS_COLUMN + 1)
            print(f"Updated STATUS to original formula with red background")
            
            return True
            
        except Exception as e:
            print(f"Error removing LOA status for {username}: {e}")
            return False

    def update_loa_status(self, username, status, make_black=False):
        # Update LOA status
        try:
            # Find the user's row
            cell = self.worksheet.find(username)
            row_index = cell.row
            
            # Update LoA NOTICE column - use exact dropdown value
            self.worksheet.update_cell(row_index, LOA_NOTICE_COLUMN + 1, "LoA")
            
            # Uncheck the activity checkbox (set to False)
            self.worksheet.update_cell(row_index, ACTIVITY_COLUMN + 1, False)
            print(f"Unchecked activity checkbox for {username}")
            
            if make_black:
                # Update STATUS column and make it black
                self.format_cell_black(row_index, STATUS_COLUMN + 1)
            
            return True
            
        except Exception as e:
            print(f"Error updating LOA status for {username}: {e}")
            return False
    
    def get_username_by_discord_id(self, discord_user_id):
        # Get Roblox username by Discord ID from spreadsheet - B+C merged cell
        try:
            all_values = self.worksheet.get_all_values()
            
            for row in all_values[3:]:
                if len(row) > DISCORD_ID_COLUMN and row[DISCORD_ID_COLUMN] == discord_user_id:
                    # For merged B+C cells, the username will be in column B position
                    # (merged cells typically store their value in the leftmost cell)
                    username = row[1].strip() if len(row) > 1 and row[1] else ""
                    return username if username else None
            
            return None
        except Exception as e:
            print(f"Error getting username by Discord ID: {e}")
            return None
    
    async def reset_weekly_activity(self):
        # Reset all activity checkboxes to False
        try:
            print("Resetting weekly activity checkboxes...")
            
            all_values = self.worksheet.get_all_values()
            
            # Find the last row with actual user data (not just any data)
            last_user_row = 3  # Start from row 3 (index for row 4)
            for i, row in enumerate(all_values[3:], start=4):  # Start checking from row 4
                # Check if this row has a username (column A or B)
                if len(row) > 1 and (row[0].strip() or row[1].strip()):
                    last_user_row = i
                else:
                    break  # Stop when we hit the first empty username row
            
            if last_user_row >= 4:
                # Create list of False values for the range
                false_values = [[False] for _ in range(4, last_user_row + 1)]
                
                # Use batch update instead of individual cell updates
                range_name = f'J4:J{last_user_row}'
                self.worksheet.update(range_name, false_values)
                
                print(f"Reset activity checkboxes for {last_user_row - 3} users (rows 4-{last_user_row})")
            else:
                print("No user data found to reset")
            
        except Exception as e:
            print(f"Error resetting weekly activity: {e}")
    
    def update_activity_checkbox(self, username):
        # Update activity checkbox to True for a specific person
        try:
            cell = self.worksheet.find(username)
            row_index = cell.row
            self.worksheet.update_cell(row_index, ACTIVITY_COLUMN + 1, True)
            return True
        except Exception as e:
            print(f"Error updating activity checkbox for {username}: {e}")
            return False