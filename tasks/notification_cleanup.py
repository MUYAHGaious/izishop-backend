"""
Notification Cleanup Task
Handles automatic deletion of old notifications after 30 days
"""

import asyncio
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from database.connection import get_db
from services.notification_service import NotificationService

logger = logging.getLogger(__name__)

class NotificationCleanupTask:
    """Task to handle automatic notification cleanup"""
    
    def __init__(self):
        self.is_running = False
    
    async def cleanup_old_notifications(self) -> dict:
        """Clean up old notifications (older than 30 days)"""
        
        try:
            db = next(get_db())
            notification_service = NotificationService(db)
            
            logger.info("Starting notification cleanup task...")
            
            # Run cleanup
            result = await notification_service.cleanup_notifications()
            
            logger.info(f"Notification cleanup completed: {result}")
            
            return {
                "success": True,
                "timestamp": datetime.utcnow().isoformat(),
                "results": result
            }
            
        except Exception as e:
            logger.error(f"Error during notification cleanup: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
        finally:
            if 'db' in locals():
                db.close()
    
    async def run_periodic_cleanup(self, interval_hours: int = 24):
        """Run cleanup task periodically"""
        
        if self.is_running:
            logger.warning("Cleanup task is already running")
            return
        
        self.is_running = True
        logger.info(f"Starting periodic notification cleanup (every {interval_hours} hours)")
        
        try:
            while self.is_running:
                # Run cleanup
                await self.cleanup_old_notifications()
                
                # Wait for next interval
                await asyncio.sleep(interval_hours * 3600)
                
        except Exception as e:
            logger.error(f"Error in periodic cleanup task: {str(e)}")
        finally:
            self.is_running = False
    
    def stop_periodic_cleanup(self):
        """Stop the periodic cleanup task"""
        self.is_running = False
        logger.info("Stopping periodic notification cleanup")

# Global instance
notification_cleanup_task = NotificationCleanupTask()

async def start_notification_cleanup():
    """Start the notification cleanup background task"""
    await notification_cleanup_task.run_periodic_cleanup()

def stop_notification_cleanup():
    """Stop the notification cleanup background task"""
    notification_cleanup_task.stop_periodic_cleanup()

# Manual cleanup function for admin endpoints
async def manual_cleanup() -> dict:
    """Manually trigger notification cleanup"""
    return await notification_cleanup_task.cleanup_old_notifications()