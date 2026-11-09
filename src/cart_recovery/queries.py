from .repository import connect
from .services import clock,cart_state


def carts(search='',state='',page=1,limit=30):
    with connect() as c:
        now=clock(c)
        q='''WITH latest AS (SELECT DISTINCT ON(cart_id) cart_id,event_type,occurred_at FROM cart_event ORDER BY cart_id,revision DESC),
          activity AS (SELECT cart_id,max(occurred_at) AS last_activity FROM cart_event WHERE event_type IN ('created','updated','reopened','checkout_started') GROUP BY cart_id),
          line_latest AS (SELECT DISTINCT ON(cart_line_id) cart_id,quantity,unit_price_minor FROM cart_line_event ORDER BY cart_line_id,revision DESC),
          amounts AS (SELECT cart_id,sum(quantity*unit_price_minor) AS total_minor,sum(quantity) AS quantity FROM line_latest GROUP BY cart_id),
          rows AS (SELECT c.*,a.total_minor,a.quantity,activity.last_activity,o.order_id,
            CASE WHEN o.order_id IS NOT NULL THEN 'purchased' WHEN a.quantity=0 THEN 'empty'
            WHEN activity.last_activity<=%(now)s-interval '14 days' THEN 'expired'
            WHEN activity.last_activity<=%(now)s-interval '1 hour' THEN 'abandoned' ELSE 'active' END AS state,
            (SELECT j.state FROM campaign p JOIN campaign_message m USING(campaign_id) JOIN outbox_job j USING(dispatch_id) WHERE p.cart_id=c.cart_id ORDER BY p.episode DESC LIMIT 1) AS campaign_state
            FROM cart c LEFT JOIN amounts a USING(cart_id) LEFT JOIN activity USING(cart_id) LEFT JOIN recovery_order o USING(cart_id))
          SELECT *,count(*) OVER() AS result_count FROM rows WHERE (cart_id ILIKE %(search)s OR customer_id ILIKE %(search)s)
          AND (%(state)s='' OR state=%(state)s) ORDER BY cart_id DESC LIMIT %(limit)s OFFSET %(offset)s'''
        rows=c.execute(q,{'now':now,'search':'%'+search+'%','state':state,'limit':limit,'offset':(page-1)*limit}).fetchall()
        return {'rows':rows,'total':rows[0]['result_count'] if rows else 0,'page':page,'limit':limit}


def timeline(cart_id):
    with connect() as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        cart,lines,events,activity,order=cart_state(c,cart_id)
        customer=c.execute('SELECT * FROM customer WHERE customer_id=%s',(cart['customer_id'],)).fetchone()
        consent=c.execute('SELECT * FROM consent WHERE customer_id=%s ORDER BY effective_at,revision',(cart['customer_id'],)).fetchall()
        decisions=c.execute('SELECT * FROM decision_log WHERE cart_id=%s ORDER BY decided_at,decision_id',(cart_id,)).fetchall()
        sends=c.execute('''SELECT s.*,m.campaign_id,t.channel,t.body,a.accepted_at FROM send_attempt s JOIN campaign_message m USING(dispatch_id)
            JOIN message_template t USING(template_id) LEFT JOIN send_acceptance a USING(send_id) WHERE m.cart_id=%s ORDER BY attempted_at''',(cart_id,)).fetchall()
        receipts=c.execute('''SELECT e.* FROM send_event e JOIN send_attempt s USING(send_id) JOIN campaign_message m ON s.dispatch_id=m.dispatch_id WHERE m.cart_id=%s ORDER BY occurred_at''',(cart_id,)).fetchall()
        credit=c.execute('SELECT a.* FROM attribution a JOIN recovery_order o USING(order_id) WHERE o.cart_id=%s',(cart_id,)).fetchone()
        sessions=c.execute('SELECT s.* FROM session s JOIN cart_session cs USING(session_id) WHERE cs.cart_id=%s',(cart_id,)).fetchall()
        return {'cart':cart,'customer':customer,'lines':lines,'events':events,'consent':consent,'decisions':decisions,'sends':sends,
                'send_events':receipts,'order':order,'attribution':credit,'sessions':sessions,'last_activity':activity,'clock':clock(c)}


def metrics():
    with connect() as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        now=clock(c)
        def scalar(q,args=()):return c.execute(q,args).fetchone()['n']
        result={'clock':now,'paused':c.execute('SELECT paused FROM runtime_state WHERE id=1').fetchone()['paused'],
            'carts':scalar('SELECT count(*) AS n FROM cart'),
            'ever_abandoned':scalar("SELECT count(DISTINCT cart_id) AS n FROM cart_event WHERE event_type='abandoned'"),
            'accepted':scalar('SELECT count(*) AS n FROM send_acceptance'),
            'attempts':scalar('SELECT count(*) AS n FROM send_attempt'),
            'delivered':scalar("SELECT count(DISTINCT send_id) AS n FROM send_event WHERE event_type='delivered'"),
            'clicked':scalar("SELECT count(DISTINCT send_id) AS n FROM send_event WHERE event_type='clicked'"),
            'suppressed':scalar("SELECT count(DISTINCT send_id) AS n FROM send_event WHERE event_type='suppressed'"),
            'queued':scalar("SELECT count(*) AS n FROM outbox_job WHERE state IN ('pending','retry','leased')"),
            'orders':scalar('SELECT count(*) AS n FROM recovery_order'),
            'credited_orders':scalar('SELECT count(*) AS n FROM attribution WHERE decided_at<=%s',(now,)),
            'gross_credited_minor':scalar('SELECT COALESCE(sum(revenue_minor),0) AS n FROM attribution WHERE decided_at<=%s',(now,)),
            'gross_paid_minor':scalar('SELECT COALESCE(sum(total_minor),0) AS n FROM recovery_order'),
            'refunds_minor':scalar("SELECT COALESCE(sum(amount_minor),0) AS n FROM order_event WHERE event_type='refunded'"),
            'credited_refunds_minor':scalar("SELECT COALESCE(sum(e.amount_minor),0) AS n FROM order_event e JOIN attribution a USING(order_id) WHERE e.event_type='refunded' AND a.decided_at<=%s",(now,)),
            'settled_orders':scalar('SELECT count(*) AS n FROM recovery_order WHERE ordered_at<=%s-interval \'1 day\'',(now,)),
            'late_orders':scalar('''SELECT count(*) AS n FROM recovery_order o WHERE ordered_at<=%s-interval '1 day'
                AND NOT EXISTS(SELECT 1 FROM attribution a WHERE a.order_id=o.order_id)
                AND EXISTS(SELECT 1 FROM send_event e JOIN send_attempt s USING(send_id) JOIN campaign_message m ON m.dispatch_id=s.dispatch_id
                    WHERE m.cart_id=o.cart_id AND e.event_type='clicked' AND e.occurred_at<o.ordered_at-interval '7 days')''',(now,)),
            'issues':scalar('SELECT count(*) AS n FROM issue')}
        result['organic_orders']=result['settled_orders']-result['credited_orders']-result['late_orders']
        result['pending_orders']=result['orders']-result['settled_orders']
        result['net_credited_minor']=result['gross_credited_minor']-result['credited_refunds_minor']
        result['net_paid_minor']=result['gross_paid_minor']-result['refunds_minor']
        result['conversion_rate']=result['credited_orders']/result['accepted'] if result['accepted'] else None
        result['reconciled']=result['organic_orders']>=0 and result['settled_orders']==result['credited_orders']+result['late_orders']+result['organic_orders']
        result['channels']=c.execute('''SELECT t.channel,count(DISTINCT a.dispatch_id) AS accepted,count(DISTINCT at.order_id) AS credited_orders,
            COALESCE(sum(at.revenue_minor),0) AS revenue_minor FROM send_acceptance a JOIN send_attempt s USING(send_id)
            JOIN campaign_message m ON m.dispatch_id=s.dispatch_id JOIN message_template t USING(template_id)
            LEFT JOIN attribution at USING(send_id) GROUP BY t.channel ORDER BY t.channel''').fetchall()
        result['variants']=c.execute('''SELECT p.variant,count(DISTINCT a.dispatch_id) AS accepted,count(DISTINCT at.order_id) AS credited_orders,
            COALESCE(sum(at.revenue_minor),0) AS revenue_minor FROM send_acceptance a JOIN send_attempt s USING(send_id)
            JOIN campaign_message m ON m.dispatch_id=s.dispatch_id JOIN campaign p USING(campaign_id)
            LEFT JOIN attribution at USING(send_id) GROUP BY p.variant ORDER BY p.variant''').fetchall()
        result['suppression_reasons']=c.execute("SELECT reason_code,count(*) AS count FROM send_event WHERE event_type='suppressed' GROUP BY reason_code ORDER BY count DESC").fetchall()
        result['recent']=c.execute('SELECT * FROM operation_event ORDER BY operation_id DESC LIMIT 8').fetchall()
        return result


def campaigns(page=1):
    with connect() as c:
        return c.execute('''SELECT p.*,m.dispatch_id,t.channel,t.body,j.state,j.last_error,j.available_at,j.attempt_count,a.send_id,
            count(*) OVER() AS result_count FROM campaign p JOIN campaign_message m USING(campaign_id) JOIN message_template t USING(template_id)
            JOIN outbox_job j USING(dispatch_id) LEFT JOIN send_acceptance a USING(dispatch_id) ORDER BY p.created_at DESC,p.campaign_id DESC LIMIT 30 OFFSET %s''',((page-1)*30,)).fetchall()


def issues():
    with connect() as c:
        return c.execute('''SELECT i.*,(SELECT count(*) FROM issue_review r WHERE r.issue_id=i.issue_id) AS review_count,
            (SELECT note FROM issue_review r WHERE r.issue_id=i.issue_id ORDER BY review_id DESC LIMIT 1) AS last_note
            FROM issue i ORDER BY issue_id''').fetchall()
