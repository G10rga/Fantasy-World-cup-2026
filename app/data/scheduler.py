import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

_scheduler = None


def sync_live_scores_job():
    from app.data.sync import sync_live_scores
    try:
        result = sync_live_scores()
        logger.info("Live scores sync: %s", result)
    except Exception as exc:
        logger.error("Live scores sync failed: %s", exc)


def sync_fixtures_job():
    from app.data.sync import sync_fixtures
    try:
        result = sync_fixtures()
        logger.info("Fixtures sync: %s", result)
    except Exception as exc:
        logger.error("Fixtures sync failed: %s", exc)


def sync_finished_stats_job():
    from app.data.sync import sync_finished_stats
    try:
        result = sync_finished_stats()
        logger.info("Finished stats sync: %s", result)
    except Exception as exc:
        logger.error("Finished stats sync failed: %s", exc)


def sync_player_photos_job():
    from app.data.sync import _photo_stats, sync_player_photos

    try:
        stats = _photo_stats()
        if stats["untried"] > 0:
            result = sync_player_photos(batch_size=50)
            logger.info("Player photos sync: %s", result)
            return
        if stats["no_match"] > 0:
            result = sync_player_photos(batch_size=40, retry_failed=True)
            logger.info("Player photos retry: %s", result)
    except Exception as exc:
        logger.error("Player photos sync failed: %s", exc)


def init_scheduler(app):
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    if app.config.get("TESTING"):
        return None

    _scheduler = BackgroundScheduler(daemon=True)

    _scheduler.add_job(
        func=_run_with_app_context(app, sync_live_scores_job),
        trigger=IntervalTrigger(seconds=app.config.get("SCHEDULER_LIVESCORES_INTERVAL", 60)),
        id="sync_live_scores",
        replace_existing=True,
        max_instances=1,
    )

    _scheduler.add_job(
        func=_run_with_app_context(app, sync_fixtures_job),
        trigger=IntervalTrigger(seconds=app.config.get("SCHEDULER_FIXTURES_INTERVAL", 600)),
        id="sync_fixtures",
        replace_existing=True,
        max_instances=1,
    )

    _scheduler.add_job(
        func=_run_with_app_context(app, sync_finished_stats_job),
        trigger=IntervalTrigger(seconds=app.config.get("SCHEDULER_STATS_INTERVAL", 600)),
        id="sync_finished_stats",
        replace_existing=True,
        max_instances=1,
    )

    _scheduler.add_job(
        func=_run_with_app_context(app, sync_player_photos_job),
        trigger=IntervalTrigger(seconds=180),
        id="sync_player_photos",
        replace_existing=True,
        max_instances=1,
    )

    _scheduler.start()
    logger.info("APScheduler started")
    return _scheduler


def shutdown_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def _run_with_app_context(app, func):
    def wrapper():
        with app.app_context():
            func()
    return wrapper
