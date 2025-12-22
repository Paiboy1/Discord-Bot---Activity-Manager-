import gspread
from oauth2client.service_account import ServiceAccountCredentials
from config import *
from datetime import datetime, timedelta

class SheetsManager:
    def __init__(self):
        self.client = None
        self.spreadsheet = None
        self.worksheet = None
        self.connect()
        self.user_cache = {}
        self.cache_duration = timedelta(minutes=1)
        self.last_full_load = None
        self.all_users_cache = []
    
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
    
    def get_cached_user_data(self, username):
        # Get user data from cache or fetch
        cache_key = username.lower()
        
        if cache_key in self.user_cache:
            cached_data, timestamp = self.user_cache[cache_key]
            if datetime.now() - timestamp < self.cache_duration:
                return cached_data
        
        # Cache miss or stale - fetch from sheets
        user_data = self.batch_get_user_data(username)
        if user_data:
            self.user_cache[cache_key] = (user_data, datetime.now())
        return user_data

    def invalidate_user_cache(self, username):
        # Clear cache for specific user after updates
        cache_key = username.lower()
        if cache_key in self.user_cache:
            del self.user_cache[cache_key]
    
    def get_all_users_cached(self):
        # Cache the entire roster for leaderboard
        now = datetime.now()
        
        if self.last_full_load and (now - self.last_full_load < self.cache_duration):
            return self.all_users_cache
        
        # Refresh cache
        all_values = self.worksheet.get_all_values()
        self.all_users_cache = all_values
        self.last_full_load = now
        return all_values
    
    def batch_get_user_data(self, username):
        # Get all user data in one API call
        try:
            cell = self.worksheet.find(username)
            row_index = cell.row
            
            # Get entire row in ONE API call instead of multiple
            row_data = self.worksheet.row_values(row_index)
            
            return {
                'row_index': row_index,
                'points': int(row_data[POINTS_COLUMN]) if len(row_data) > POINTS_COLUMN and row_data[POINTS_COLUMN].isdigit() else 0,
                'rank': row_data[RANK_COLUMN-1] if len(row_data) > RANK_COLUMN-1 else "",
                'status': row_data[STATUS_COLUMN] if len(row_data) > STATUS_COLUMN else "",
                'loa_status': row_data[LOA_NOTICE_COLUMN] if len(row_data) > LOA_NOTICE_COLUMN else "",
                'activity_checked': row_data[ACTIVITY_COLUMN] if len(row_data) > ACTIVITY_COLUMN else False,
                'codename': row_data[CODENAME_COLUMN] if len(row_data) > CODENAME_COLUMN else ""
            }
        except Exception as e:
            print(f"Error getting user data: {e}")
            return None
    
    def batch_update_cells(self, updates):
        # Update multiple cells in one API call updates: list of dicts with 'row', 'col', 'value'
        try:
            # Build batch update request
            batch_data = []
            for update in updates:
                cell_range = f"{chr(64 + update['col'])}{update['row']}"
                batch_data.append({
                    'range': cell_range,
                    'values': [[update['value']]]
                })
            
            # Single API call for all updates
            self.worksheet.batch_update(batch_data, value_input_option='USER_ENTERED')
            return True
        except Exception as e:
            print(f"Error in batch update: {e}")
            return False
        
    def load_timezones_from_txt(self):
        timezones = {}
        try:
            with open('Timezones.txt', mode='r', encoding='utf-8') as file:
                for line in file:
                        line = line.strip()
                        # Skip empty lines or comment lines starting with '#'
                        if not line or line.startswith('#'):
                            continue
                                
                        # Split the line by the comma
                        parts = line.split(',')
                            
                        if len(parts) == 2:
                            # [0] is the abbreviation, [1] is the offset
                            abbrev = parts[0].strip().upper() 
                            offset = float(parts[1].strip())
                            timezones[abbrev] = offset
            return timezones
        except FileNotFoundError:
            print(f"Timezone broke")
            return {}
        
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
    
    def is_user_on_loa(self, username):
        # Check if a user is currently on LOA
        try:
            cell = self.worksheet.find(username)
            row_index = cell.row
            
            # Check the LOA Notice column
            loa_notice_cell = self.worksheet.cell(row_index, LOA_NOTICE_COLUMN + 1)
            loa_status = loa_notice_cell.value
            
            # User is on LOA if the LOA Notice column contains "LoA"
            return loa_status == "LoA"
            
        except Exception as e:
            print(f"Error checking LOA status for {username}: {e}")
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
            
            # Set Discord ID
            self.worksheet.update_cell(next_row, DISCORD_ID_COLUMN + 1, discord_id)
            
            # Set initial points to 0
            self.worksheet.update_cell(next_row, POINTS_COLUMN + 1, 0)
            
            # Set Activity checkbox to False (unchecked)
            self.worksheet.update_cell(next_row, ACTIVITY_COLUMN + 1, False)
            
            # Set LoA status to N/A
            self.worksheet.update_cell(next_row, LOA_NOTICE_COLUMN + 1, "N/A")
            
            return True
            
        except Exception as e:
            print(f"Error creating new user entry: {e}")
            return False

    def find_next_empty_row(self):
        # Find the first empty row in the worksheet
        try:
            all_values = self.worksheet.get_all_values()
            
            # Start from row 4
            for i in range(3, len(all_values)):
                row = all_values[i]
                
                # Check if username column (B/index 1) is empty
                if len(row) <= 1 or not row[1].strip():
                    return i + 1
            
            # Return the next row after all data
            return len(all_values) + 1
            
        except Exception as e:
            print(f"Error finding next empty row: {e}")
            return 4  # Default starting row
    
    def load_points_from_spreadsheet(self, user_points):
        # Load all points into the user_points dictionary
        try:
            all_values = self.worksheet.get_all_values()
            
            for row in all_values[3:]:  # Skip header rows
                if len(row) > POINTS_COLUMN:
                    username = row[USERNAME_COLUMN].strip() if row[USERNAME_COLUMN] else ""
                    points_str = row[POINTS_COLUMN].strip() if row[POINTS_COLUMN] else "0"
                    
                    if username:
                        try:
                            user_points[username] = int(points_str) if points_str.isdigit() else 0
                        except ValueError:
                            user_points[username] = 0
            
            print(f"Loaded points for {len(user_points)} users")
        except Exception as e:
            print(f"Error loading points from spreadsheet: {e}")
    
    def update_points(self, username, points):
        # Update user's points in the spreadsheet
        try:
            cell = self.worksheet.find(username)
            row_index = cell.row
            self.worksheet.update_cell(row_index, POINTS_COLUMN + 1, points)
            
            # Invalidate cache
            self.invalidate_user_cache(username)
            
            return True
        except Exception as e:
            print(f"Error updating points for {username}: {e}")
            return False
    
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
    
    def check_promotion_eligibility_from_data(self, points, current_rank):
        # Check promotion without additional API calls
        promotions = {
            "E1": {"next_rank": "E2", "points_needed": 10, "needs_app": False},
            "E2": {"next_rank": "E3", "points_needed": 30, "needs_app": False},
            "E3": {"next_rank": "E4", "points_needed": 50, "needs_app": False},
            "E4": {"next_rank": "E5", "points_needed": 70, "needs_app": True},
        }
        
        if current_rank in promotions:
            promo_info = promotions[current_rank]
            if points >= promo_info["points_needed"]:
                return {
                    "eligible": True,
                    "next_rank": promo_info["next_rank"],
                    "needs_application": promo_info["needs_app"]
                }
        
        return {"eligible": False}
    
    def update_user_rank(self, username, new_rank):
        # Update user's rank in the spreadsheet
        try:
            cell = self.worksheet.find(username)
            row_index = cell.row
            
            # Update the rank column
            self.worksheet.update_cell(row_index, RANK_COLUMN, new_rank)
            
            # Invalidate cache for this user
            self.invalidate_user_cache(username)
            
            print(f"Updated {username}'s rank to {new_rank} in spreadsheet")
            return True
            
        except Exception as e:
            print(f"Error updating rank for {username}: {e}")
            return False

    def get_user_rank(self, username):
        # Get user's rank from spreadsheet
        try:
            cell = self.worksheet.find(username)
            row_index = cell.row
            
            rank_cell = self.worksheet.cell(row_index, RANK_COLUMN)
            return rank_cell.value if rank_cell.value else None
        except Exception as e:
            print(f"Error getting rank for {username}: {e}")
            return None