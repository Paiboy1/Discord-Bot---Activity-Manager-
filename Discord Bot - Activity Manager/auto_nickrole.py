import discord
from config import *

class RoleManager:
    def __init__(self, bot, sheets_manager):
        self.bot = bot
        self.sheets_manager = sheets_manager
        
        # Role ID mappings (Discord role ID -> spreadsheet rank)
        self.rank_role_ids = {
            1444642966781296701: "E1",  # E1 role ID
            1444643270926929990: "E2",  # E2 role ID
            1444643331111125114: "E3",  # E3 role ID
            1332029491463065677: "E4",  # E4 role ID
        }
        
        # Rank to nickname prefix mapping
        self.rank_prefixes = {
            "E1": "[PVT]",
            "E2": "[PV2]",
            "E3": "[PFC]",
            "E4": "[CPL]",
            "E5": "[SGT]",
            "E6": "[SSG]",
            "E7": "[SFC]",
            "E8": "[MSG]",
            "E9": "[SGM]",
        }
    
    async def auto_rank(self, member, new_rank):
        # Automatically promote user: remove old role, add new role, update nickname and sheets
        # Only auto-promote up to E4, E5+ requires manual promotion
        if new_rank not in ["E2", "E3", "E4"]:
            print(f"Auto-promotion not available for {new_rank} - requires manual promotion")
            return False
            
        try:
            guild = member.guild
            
            # Get username from spreadsheet using Discord ID
            username = self.sheets_manager.get_username_by_discord_id(str(member.id))
            if not username:
                print(f"Error: Could not find username for Discord ID {member.id}")
                return False
            
            # Get user's current rank and codename from spreadsheet
            user_data = self.sheets_manager.batch_get_user_data(username)
            if not user_data:
                print(f"Error: Could not find current rank for {username}")
                return False
            
            old_rank = user_data['rank']
            codename = user_data.get('codename', '').strip()
            
            # Check if codename is surrounded by quotes
            has_codename = codename.startswith('"') and codename.endswith('"')
            
            print(f"[DEBUG auto_rank] Username: {username}, Codename: {codename}, Has codename: {has_codename}")
            
            # Find new rank role ID
            new_role_id = None
            for role_id, rank in self.rank_role_ids.items():
                if rank == new_rank:
                    new_role_id = role_id
                    break
            
            if not new_role_id:
                print(f"Error: Could not find role ID for rank {new_rank}")
                return False
            
            new_role = guild.get_role(new_role_id)
            if not new_role:
                print(f"Error: Could not find role object for ID {new_role_id}")
                return False
            
            # Find old rank role ID using the rank from spreadsheet
            old_role = None
            for role_id, rank in self.rank_role_ids.items():
                if rank == old_rank:
                    old_role = guild.get_role(role_id)
                    break
            
            # Remove old rank role if found
            if old_role and old_role in member.roles:
                await member.remove_roles(old_role)
                print(f"Removed {old_rank} role from {username}")
            
            # Add new rank role
            if new_role not in member.roles:
                await member.add_roles(new_role)
                print(f"Added {new_rank} role to {username}")
            
            # Update nickname with new rank prefix using spreadsheet username
            new_prefix = self.rank_prefixes.get(new_rank, "")
            if new_prefix:
                # Format: [RANK] "CODENAME" | username OR [RANK] username
                if has_codename:
                    new_nickname = f"{new_prefix} {codename} | {username}"
                else:
                    new_nickname = f"{new_prefix} {username}"
                
                # Discord has 32 char limit on nicknames
                if len(new_nickname) > 32:
                    if has_codename:
                        # Try to fit: [RANK] "CODE" | user
                        max_length = 32
                        # If still too long, truncate username
                        prefix_and_codename = f"{new_prefix} {codename} | "
                        if len(prefix_and_codename) < 32:
                            remaining = 32 - len(prefix_and_codename)
                            username_truncated = username[:remaining]
                            new_nickname = f"{prefix_and_codename}{username_truncated}"
                        else:
                            # Codename itself is too long, just use rank + username
                            new_nickname = f"{new_prefix} {username}"
                            if len(new_nickname) > 32:
                                max_name_length = 32 - len(new_prefix) - 1
                                username_truncated = username[:max_name_length]
                                new_nickname = f"{new_prefix} {username_truncated}"
                    else:
                        max_name_length = 32 - len(new_prefix) - 1
                        username_truncated = username[:max_name_length]
                        new_nickname = f"{new_prefix} {username_truncated}"
                
                try:
                    print(f"[DEBUG auto_rank] Attempting to set nickname: {new_nickname}")
                    print(f"[DEBUG auto_rank] Member: {member.display_name}, ID: {member.id}")
                    print(f"[DEBUG auto_rank] Bot's top role: {member.guild.me.top_role.name} (pos: {member.guild.me.top_role.position})")
                    print(f"[DEBUG auto_rank] Member's top role: {member.top_role.name} (pos: {member.top_role.position})")
                    print(f"[DEBUG auto_rank] Is owner: {member.guild.owner_id == member.id}")
                    
                    await member.edit(nick=new_nickname)
                    print(f"Updated nickname to: {new_nickname}")
                except discord.Forbidden as e:
                    print(f"No permission to change nickname for {username}: {e}")
                except Exception as e:
                    print(f"Error changing nickname for {username}: {e}")
            
            # Update rank in Google Sheets
            self.sheets_manager.update_user_rank(username, new_rank)
            
            return True
            
        except Exception as e:
            print(f"Error in auto_rank: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def set_loa_nickname(self, member):
        # Set LOA nickname: [LOA] "CODENAME" | username OR [LOA] username
        try:
            # Get username from spreadsheet using Discord ID
            username = self.sheets_manager.get_username_by_discord_id(str(member.id))
            if not username:
                print(f"Error: Could not find username for Discord ID {member.id}")
                return False
            
            # Get user data from spreadsheet
            user_data = self.sheets_manager.batch_get_user_data(username)
            if not user_data:
                print(f"Error: Could not find user data for {username}")
                return False
            
            codename = user_data.get('codename', '').strip()
            has_codename = codename.startswith('"') and codename.endswith('"')
            
            # Format: [LOA] "CODENAME" | username OR [LOA] username
            if has_codename:
                new_nickname = f"[LOA] {codename} | {username}"
            else:
                new_nickname = f"[LOA] {username}"
            
            # Handle 32 character limit
            if len(new_nickname) > 32:
                if has_codename:
                    prefix_and_codename = f"[LOA] {codename} | "
                    if len(prefix_and_codename) < 32:
                        remaining = 32 - len(prefix_and_codename)
                        username_truncated = username[:remaining]
                        new_nickname = f"{prefix_and_codename}{username_truncated}"
                    else:
                        # Codename too long, just use [LOA] + username
                        new_nickname = f"[LOA] {username}"
                        if len(new_nickname) > 32:
                            username_truncated = username[:26]  # 32 - 6 for "[LOA] "
                            new_nickname = f"[LOA] {username_truncated}"
                else:
                    username_truncated = username[:26]
                    new_nickname = f"[LOA] {username_truncated}"
            
            try:
                if member.guild.owner_id != member.id:
                    await member.edit(nick=new_nickname)
                    return True
                else:
                    return False
            except discord.Forbidden as e:
                return False
            except Exception as e:
                return False
                
        except Exception as e:
            print(f"Error in set_loa_nickname: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def set_loa_role(self, member):
        # Add LOA role to member
        try:
            guild = member.guild
            loa_role = guild.get_role(LOA_ROLE_ID)
            
            if not loa_role:
                return False
            
            if loa_role not in member.roles:
                await member.add_roles(loa_role)
                return True
            else:
                return True
                
        except Exception as e:
            print(f"Error in set_loa_role: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def remove_loa_role(self, member):
        # Remove LOA role from member
        try:
            guild = member.guild
            loa_role = guild.get_role(LOA_ROLE_ID)
            
            if not loa_role:
                return False
            
            if loa_role in member.roles:
                await member.remove_roles(loa_role)
                return True
            else:
                return True
                
        except Exception as e:
            print(f"Error in remove_loa_role: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def restore_rank_nickname(self, member):
        # Restore rank nickname after LOA: [RANK] "CODENAME" | username OR [RANK] username
        try:
            # Get username from spreadsheet using Discord ID
            username = self.sheets_manager.get_username_by_discord_id(str(member.id))
            if not username:
                print(f"Error: Could not find username for Discord ID {member.id}")
                return False
            
            # Get user data from spreadsheet
            user_data = self.sheets_manager.batch_get_user_data(username)
            if not user_data:
                print(f"Error: Could not find user data for {username}")
                return False
            
            rank = user_data['rank']
            codename = user_data.get('codename', '').strip()
            has_codename = codename.startswith('"') and codename.endswith('"')
            
            print(f"[DEBUG restore_rank_nickname] Username: {username}, Rank: {rank}, Codename: {codename}")
            
            # Get rank prefix
            rank_prefix = self.rank_prefixes.get(rank, "")
            if not rank_prefix:
                print(f"Warning: No prefix found for rank {rank}, using [UNK]")
                rank_prefix = "[UNK]"
            
            # Format: [RANK] "CODENAME" | username OR [RANK] username
            if has_codename:
                new_nickname = f"{rank_prefix} {codename} | {username}"
            else:
                new_nickname = f"{rank_prefix} {username}"
            
            # Handle 32 character limit
            if len(new_nickname) > 32:
                if has_codename:
                    prefix_and_codename = f"{rank_prefix} {codename} | "
                    if len(prefix_and_codename) < 32:
                        remaining = 32 - len(prefix_and_codename)
                        username_truncated = username[:remaining]
                        new_nickname = f"{prefix_and_codename}{username_truncated}"
                    else:
                        # Codename too long, just use rank + username
                        new_nickname = f"{rank_prefix} {username}"
                        if len(new_nickname) > 32:
                            max_name_length = 32 - len(rank_prefix) - 1
                            username_truncated = username[:max_name_length]
                            new_nickname = f"{rank_prefix} {username_truncated}"
                else:
                    max_name_length = 32 - len(rank_prefix) - 1
                    username_truncated = username[:max_name_length]
                    new_nickname = f"{rank_prefix} {username_truncated}"
            
            try:
                print(f"[DEBUG restore_rank_nickname] Attempting to set nickname: {new_nickname}")
                if member.guild.owner_id != member.id:
                    await member.edit(nick=new_nickname)
                    print(f"[DEBUG restore_rank_nickname] Updated nickname to: {new_nickname}")
                    return True
                else:
                    print(f"[DEBUG restore_rank_nickname] Cannot change nickname - user is server owner")
                    return False
            except discord.Forbidden as e:
                print(f"[DEBUG restore_rank_nickname] No permission to change nickname: {e}")
                return False
            except Exception as e:
                print(f"[DEBUG restore_rank_nickname] Error changing nickname: {e}")
                return False
                
        except Exception as e:
            print(f"Error in restore_rank_nickname: {e}")
            import traceback
            traceback.print_exc()
            return False






























