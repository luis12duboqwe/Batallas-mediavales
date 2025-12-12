import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from .database import SessionLocal
from .services import barbarian_ai, queue as queue_service

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()

def run_barbarian_ai_job():
    """
    Job to run barbarian AI logic.
    """
    logger.info("Running Barbarian AI Job...")
    db = SessionLocal()
    try:
        barbarian_ai.process_barbarian_growth(db)
        db.commit()
    except Exception as e:
        logger.error(f"Error in Barbarian AI Job: {e}")
        db.rollback()
    finally:
        db.close()

def run_queue_processing_job():
    """
    Job to process game queues (buildings, troops, etc).
    """
    # logger.debug("Processing queues...") # Too verbose for every 5s
    db = SessionLocal()
    try:
        queue_service.process_all_queues(db)
        db.commit()
    except Exception as e:
        logger.error(f"Error in Queue Processing Job: {e}")
        db.rollback()
    finally:
        db.close()

def start_scheduler():
    """
    Starts the scheduler and adds jobs.
    """
    if not scheduler.running:
        # Barbarian AI: Every 5 minutes
        scheduler.add_job(
            run_barbarian_ai_job,
            trigger=IntervalTrigger(minutes=5),
            id='barbarian_ai',
            name='Barbarian AI Growth',
            replace_existing=True
        )
        
        # Queue Processing: Every 5 seconds (critical for game responsiveness)
        scheduler.add_job(
            run_queue_processing_job,
            trigger=IntervalTrigger(seconds=5),
            id='queue_processing',
            name='Queue Processing',
            replace_existing=True
        )
        
        scheduler.start()
        logger.info("Scheduler started.")

def shutdown_scheduler():
    """
    Shuts down the scheduler.
    """
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler shut down.")
