"""
APScheduler job: sends daily P&L summary to owner at 10 PM IST.
Registered in main.py on startup.
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger("scheduler")
_scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")


def start_scheduler(app) -> None:
    """Call from main.py startup event."""
    _scheduler.add_job(
        _daily_summary_job,
        CronTrigger(hour=22, minute=0),  # 10 PM IST
        id="daily_summary",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Scheduler started: daily_summary at 22:00 IST")


async def _daily_summary_job() -> None:
    from datetime import date

    from core.database import AsyncSessionLocal
    from modules.notify.service import NotifyService
    from modules.pl_engine.service import PLService

    try:
        async with AsyncSessionLocal() as db:
            month = date.today().strftime("%Y-%m")
            pl_svc = PLService(db=db)
            pl = await pl_svc.get_monthly_pl(month)
            revenue = pl.get("rev_total", "0")
            profit = pl.get("net_profit", "0")

            # Count today's orders
            from sqlalchemy import func, select

            from modules.orders.models import Order

            today = date.today()
            count_r = await db.execute(
                select(func.count(Order.id)).where(
                    func.date(Order.created_at) == today,
                    Order.status != "cancelled",
                )
            )
            orders_today = count_r.scalar() or 0

            await NotifyService().daily_summary(orders_today, revenue, profit)
            logger.info(f"Daily summary sent: {orders_today} orders, rev={revenue}")
    except Exception as e:
        logger.error(f"Daily summary job failed: {e}")
