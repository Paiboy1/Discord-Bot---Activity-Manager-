# tasks.py - Background tasks for Discord bot

import asyncio
from datetime import datetime, timezone

class BackgroundTasks:
    def __init__(self, sheets_manager):
        self.sheets_manager = sheets_manager
    
    async def weekly_reset_task(self):
        # Background task that runs weekly reset every Sunday at midnight GMT
        while True:
            now = datetime.now(timezone.utc)
            # Check if it's Sunday (weekday 6) and hour is 0 (midnight)
            if now.weekday() == 6 and now.hour == 0 and now.minute == 0:
                await self.sheets_manager.reset_weekly_activity()  # Now properly awaitable
                # Sleep for 61 minutes to avoid running multiple times in the same hour
                await asyncio.sleep(3660)
            else:
                # Check every minute
                await asyncio.sleep(60)
    
    def start_tasks(self, bot):
        # Start all background tasks
        bot.loop.create_task(self.weekly_reset_task())
        print("Weekly reset task started")