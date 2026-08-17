from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timezone
import atexit
from utils.logger import app_logger

class FPLScheduler:
    """
    Background scheduler to periodically fetch data based on GW deadlines.
    (See Design Document Section 1.2 Caching Strategy)
    """
    def __init__(self, data_fetcher_callback):
        self.scheduler = BackgroundScheduler()
        self.data_fetcher_callback = data_fetcher_callback
        
        # Add baseline jobs
        self._add_jobs()
        
        # Ensure scheduler shuts down cleanly on app exit
        atexit.register(lambda: self.stop())

    def _add_jobs(self):
        """Sets up the initial polling jobs."""
        
        # 1. Bootstrap Static - Every 4 hours normally
        self.scheduler.add_job(
            self._wrap_callback,
            trigger=IntervalTrigger(hours=4),
            args=["bootstrap"],
            id="job_bootstrap",
            replace_existing=True
        )
        
        # 2. Fixtures - Once a day
        self.scheduler.add_job(
            self._wrap_callback,
            trigger=IntervalTrigger(days=1),
            args=["fixtures"],
            id="job_fixtures",
            replace_existing=True
        )
        
        app_logger.info("Background scheduler jobs configured.")

    def adjust_for_deadline(self, deadline_time: datetime):
        """
        Dynamically changes polling frequency as deadline approaches.
        """
        now = datetime.now(timezone.utc)
        delta = deadline_time - now
        
        hours_to_deadline = delta.total_seconds() / 3600.0
        
        if 0 < hours_to_deadline <= 24:
            app_logger.info(f"Deadline in {hours_to_deadline:.1f}h. Increasing polling frequency.")
            self.scheduler.reschedule_job("job_bootstrap", trigger=IntervalTrigger(minutes=30))
            self.scheduler.reschedule_job("job_fixtures", trigger=IntervalTrigger(hours=2))
        else:
            app_logger.debug("Reverting to standard polling frequency.")
            self.scheduler.reschedule_job("job_bootstrap", trigger=IntervalTrigger(hours=4))
            self.scheduler.reschedule_job("job_fixtures", trigger=IntervalTrigger(days=1))

    def _wrap_callback(self, job_type: str):
        """Wrapper to log and call the actual data fetching logic."""
        app_logger.info(f"Scheduler triggered: {job_type}")
        try:
            self.data_fetcher_callback(job_type)
        except Exception as e:
            app_logger.error(f"Scheduled job {job_type} failed: {e}")

    def start(self):
        if not self.scheduler.running:
            self.scheduler.start()
            app_logger.info("Background scheduler started.")

    def stop(self):
        if self.scheduler.running:
            self.scheduler.shutdown()
            app_logger.info("Background scheduler stopped.")
