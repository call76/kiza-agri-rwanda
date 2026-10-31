"""Scheduled jobs. Run from cron / task scheduler:  python -m kiza8.jobs   (or set KIZA_JOBS=1 to start the in-process loop). All jobs are idempotent."""
import os, time, threading, logging
import db
from . import schema, prices, alerts, sms, yieldml, inventory

log = logging.getLogger("kiza.jobs"); _started = False

def run_all():
    out = {}
    c = db.conn()
    try:
        out["price_backfill"] = prices.backfill(c); out["yield_monitor"] = yieldml.monitor(c)
    finally: c.close()
    try:
        from . import care; out["spray_reminders"] = care.send_reminders(); out["rain_reminders"] = care.send_rain_reminders()
    except Exception: log.exception("care")
    try:
        from . import datagov; out["datagov"] = datagov.run_all_sources()
    except Exception: log.exception("datagov")
    out["alerts_new"] = alerts.generate(); out["sms_queued"] = alerts.notify_farmers(); out["sms_dispatch"] = sms.dispatch(); out["stock_mismatch"] = inventory.reconcile()
    return out

def start_background(every_s=900):
    global _started
    if _started or os.environ.get("KIZA_JOBS", "0") != "1": return False
    _started = True
    def loop():
        time.sleep(10)
        while True:
            try: log.info("jobs: %s", run_all())
            except Exception: log.exception("jobs failed")
            time.sleep(every_s)
    threading.Thread(target=loop, daemon=True).start(); return True

if __name__ == "__main__":
    schema.migrate(); print(run_all())
