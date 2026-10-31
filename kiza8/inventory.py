"""Transactional marketplace inventory. Every change = one SQLite write transaction (BEGIN IMMEDIATE) with a conditional UPDATE
(so two buyers can never reserve the same kilograms) and an append-only stock_movements row.
States per listing: available_kg (free), reserved_kg (accepted, not yet completed), sold_kg (completed)."""
import db

class StockError(Exception): pass

def _mv(c, lid, oid, kind, qty, actor):
    row = c.execute("SELECT available_kg, COALESCE(reserved_kg,0) FROM listings WHERE id=?", (lid,)).fetchone()
    c.execute("INSERT INTO stock_movements(listing_id,offer_id,kind,qty_kg,available_after,reserved_after,actor_id) VALUES(?,?,?,?,?,?,?)", (lid, oid, kind, qty, row[0], row[1], actor))

def _status(c, lid):
    a, r, s = c.execute("SELECT available_kg, COALESCE(reserved_kg,0), COALESCE(sold_kg,0) FROM listings WHERE id=?", (lid,)).fetchone()
    pend = c.execute("SELECT COUNT(*) FROM offers WHERE listing_id=? AND status='Pending'", (lid,)).fetchone()[0]
    st = ("Offer Received" if pend else "Available") if a > 0 and r <= 0 else ("Reserved" if a > 0 or r > 0 else "Sold")
    if a > 0 and r > 0: st = "Reserved"            # partially reserved, remainder still listed
    c.execute("UPDATE listings SET status=? WHERE id=? AND status NOT IN ('Withdrawn')", (st, lid))

def accept_offer(offer_id, seller_id):
    """Seller accepts: reserve qty. Fails (StockError) if not enough free stock or offer not pending / not theirs."""
    c = db.conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        o = c.execute("SELECT o.id,o.listing_id,o.qty_kg,o.status,l.seller_id,l.status ls FROM offers o JOIN listings l ON l.id=o.listing_id WHERE o.id=?", (offer_id,)).fetchone()
        if not o or o["seller_id"] != seller_id: raise StockError("forbidden")
        if o["status"] != "Pending": raise StockError("not_pending")
        if o["ls"] == "Withdrawn": raise StockError("withdrawn")
        cur = c.execute("UPDATE listings SET available_kg=available_kg-?, reserved_kg=COALESCE(reserved_kg,0)+? WHERE id=? AND available_kg>=?", (o["qty_kg"], o["qty_kg"], o["listing_id"], o["qty_kg"]))
        if cur.rowcount != 1: raise StockError("insufficient")
        c.execute("UPDATE offers SET status='Accepted' WHERE id=?", (offer_id,))
        _mv(c, o["listing_id"], offer_id, "reserve", o["qty_kg"], seller_id); _status(c, o["listing_id"]); c.commit()
        # competing pending offers that can no longer be satisfied stay Pending but cannot be accepted (insufficient) - farmer may reject them
        return True
    except Exception:
        c.rollback(); raise
    finally: c.close()

def release(offer_id, actor_id, new_status):
    """Cancel/reject-after-accept: give reserved kilograms back to free stock (buyer cancel or seller cancel)."""
    c = db.conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        o = c.execute("SELECT o.id,o.listing_id,o.qty_kg,o.status,o.buyer_id,l.seller_id FROM offers o JOIN listings l ON l.id=o.listing_id WHERE o.id=?", (offer_id,)).fetchone()
        if not o or actor_id not in (o["buyer_id"], o["seller_id"]): raise StockError("forbidden")
        if o["status"] == "Pending":
            c.execute("UPDATE offers SET status=? WHERE id=?", (new_status, offer_id)); _status(c, o["listing_id"]); c.commit(); return
        if o["status"] != "Accepted": raise StockError("not_cancellable")
        cur = c.execute("UPDATE listings SET available_kg=available_kg+?, reserved_kg=COALESCE(reserved_kg,0)-? WHERE id=? AND COALESCE(reserved_kg,0)>=?", (o["qty_kg"], o["qty_kg"], o["listing_id"], o["qty_kg"]))
        if cur.rowcount != 1: raise StockError("inconsistent")
        c.execute("UPDATE offers SET status=? WHERE id=?", (new_status, offer_id))
        _mv(c, o["listing_id"], offer_id, "release", o["qty_kg"], actor_id); _status(c, o["listing_id"]); c.commit()
    except Exception:
        c.rollback(); raise
    finally: c.close()

def complete(offer_id, buyer_id, rating, review, today):
    """Buyer confirms receipt: reserved -> sold. Stock never goes negative; remaining free stock stays listed."""
    c = db.conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        o = c.execute("SELECT o.id,o.listing_id,o.qty_kg,o.status,o.buyer_id FROM offers o WHERE o.id=?", (offer_id,)).fetchone()
        if not o or o["buyer_id"] != buyer_id: raise StockError("forbidden")
        if o["status"] != "Accepted": raise StockError("not_accepted")
        cur = c.execute("UPDATE listings SET reserved_kg=COALESCE(reserved_kg,0)-?, sold_kg=COALESCE(sold_kg,0)+? WHERE id=? AND COALESCE(reserved_kg,0)>=?", (o["qty_kg"], o["qty_kg"], o["listing_id"], o["qty_kg"]))
        if cur.rowcount != 1: raise StockError("inconsistent")
        c.execute("UPDATE offers SET status='Completed', completed_at=?, rating=?, review=? WHERE id=?", (today, rating, review, offer_id))
        _mv(c, o["listing_id"], offer_id, "sale", o["qty_kg"], buyer_id); _status(c, o["listing_id"]); c.commit()
    except Exception:
        c.rollback(); raise
    finally: c.close()

def create_offer(listing_id, buyer_id, qty, price):
    """Offer is only a request: it does NOT reserve stock. Validates against currently free stock."""
    c = db.conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        l = c.execute("SELECT id,available_kg,status,verify_status FROM listings WHERE id=?", (listing_id,)).fetchone()
        if not l or l["verify_status"] != "Verified" or l["status"] not in ("Available", "Offer Received", "Reserved"): raise StockError("unavailable")
        if qty <= 0 or qty > l["available_kg"]: raise StockError("insufficient")
        oid = c.execute("INSERT INTO offers(listing_id,buyer_id,qty_kg,price_kg) VALUES(?,?,?,?)", (listing_id, buyer_id, qty, price)).lastrowid
        _status(c, listing_id); c.commit(); return oid
    except Exception:
        c.rollback(); raise
    finally: c.close()

def initial_movement(listing_id, qty, actor):
    c = db.conn()
    try:
        if not c.execute("SELECT 1 FROM stock_movements WHERE listing_id=? AND kind='initial'", (listing_id,)).fetchone(): _mv(c, listing_id, None, "initial", qty, actor); c.commit()
    finally: c.close()

def reconcile():
    """Integrity check: free + reserved + sold must equal the original quantity for every listing. Returns offending ids."""
    c = db.conn()
    try: return [r[0] for r in c.execute("SELECT id FROM listings WHERE ABS(available_kg+COALESCE(reserved_kg,0)+COALESCE(sold_kg,0)-qty_kg)>0.001 AND status!='Withdrawn'")]
    finally: c.close()
