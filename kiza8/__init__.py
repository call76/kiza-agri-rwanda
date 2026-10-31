"""KIZA-AGRI v8 layer: additive blueprints on top of the v7 Flask app (v7 routes keep working)."""
import db
from . import schema, core, prices, inventory

def init_app(app):
    schema.migrate()
    from . import datagov as _dg; _dg.migrate()
    from . import learn as _ln; _ln.migrate()
    from . import hub as _hb; _hb.migrate()
    from . import care as _cr; _cr.migrate()
    c = db.conn()
    try:
        prices.backfill(c)
        for l in c.execute("SELECT id, qty_kg, seller_id FROM listings WHERE id NOT IN (SELECT listing_id FROM stock_movements WHERE kind='initial')").fetchall():
            c.execute("INSERT INTO stock_movements(listing_id,kind,qty_kg,available_after,reserved_after,actor_id) SELECT id,'initial',qty_kg,available_kg,COALESCE(reserved_kg,0),seller_id FROM listings WHERE id=?", (l["id"],))
        c.commit()
    finally: c.close()
    from . import security, farm, market, ops, dash, v10, v11, datagov, care, history, inputs, learn, hub
    security.init(app); dash.init(app)
    for m in (security, farm, market, ops, dash, v10, v11, datagov, care, history, inputs, learn, hub): app.register_blueprint(m.bp)
    app.jinja_env.globals.update(T=core.T, rwf=core.rwf, nf=core.num_fmt, lt=core.local_time)
    from . import jobs; jobs.start_background()
