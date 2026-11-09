"""Local synthetic-store application. Authenticated writes are transactional/idempotent."""
import hmac
import json
import os
import secrets
import time
from hashlib import sha256
from typing import Literal

import psycopg
from fastapi import FastAPI, Request, Response, HTTPException, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .common import ROOT,load_config,canonical
from .repository import connect,CURRENT,insert
from . import services as service, queries

app=FastAPI(title='Cart Recovery',version='1.0.0',description='Synthetic abandoned-cart recovery, traceability and deterministic attribution. Delivery is simulated.')
app.mount('/static',StaticFiles(directory=ROOT/'src/cart_recovery/static'),name='static')
SECRET=os.environ.get('SESSION_SECRET',secrets.token_hex(32)).encode()


class Body(BaseModel): model_config=ConfigDict(extra='forbid')
class Login(Body):
    username:Literal['manager','analyst','operator']='manager'
    password:str=Field(min_length=1,max_length=200)
class Scenario(Body):
    kind:Literal['recovery','withdrawal','retry','multidevice']='recovery'
    channel:Literal['email','sms']='email'
class ConsentChange(Body):
    channel:Literal['email','sms']
    state:Literal['granted','withdrawn']
class Advance(Body): minutes:int=Field(ge=1,le=20160,strict=True)
class Pause(Body): paused:bool
class Quantity(Body):
    line_id:str=Field(max_length=80)
    quantity:int=Field(ge=0,le=100,strict=True)
class Callback(Body):
    kind:Literal['delivered','opened','clicked']
class Review(Body): note:str=Field(min_length=3,max_length=1000)
class Refund(Body): amount_minor:int=Field(gt=0,strict=True)


def user(request:Request):
    token=request.cookies.get('recovery_session','')
    try:
        payload,signature=token.rsplit('.',1)
        if not hmac.compare_digest(signature,hmac.new(SECRET,payload.encode(),sha256).hexdigest()):raise ValueError()
        role,expiry=payload.split(':')
        if role not in ('manager','analyst','operator') or int(expiry)<time.time():raise ValueError()
        return role
    except (ValueError,TypeError):raise HTTPException(401,'Sign in to continue')


def manager(role=Depends(user)):
    if role!='manager':raise HTTPException(403,'Manager access required')
    return role


def mutate(request,actor,payload,fn):
    if request.headers.get('X-Recovery-Request')!='1':raise HTTPException(403,'Missing request protection header')
    origin=request.headers.get('origin')
    if origin and origin.rstrip('/')!=str(request.base_url).rstrip('/'):raise HTTPException(403,'Cross-origin writes are denied')
    key=request.headers.get('Idempotency-Key')
    if not key or len(key)>160:raise HTTPException(422,'An Idempotency-Key of at most 160 characters is required')
    fingerprint=sha256(canonical({'actor':actor,'path':request.url.path,'payload':payload}).encode()).hexdigest()
    with connect() as c:
        token=CURRENT.set(c)
        try:
            c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(key,))
            old=c.execute('SELECT * FROM ingest_receipt WHERE source_key=%s',(key,)).fetchone()
            if old:
                if old['request_hash']!=fingerprint:raise service.Conflict('Idempotency key was already used for a different request')
                return old['response']
            result=jsonable_encoder(fn())
            insert(c,'ingest_receipt',source_key=key,request_hash=fingerprint,response=result)
            return result
        finally:CURRENT.reset(token)


@app.exception_handler(service.Conflict)
def conflict(request,exc):return JSONResponse(status_code=409,content={'error':str(exc)})
@app.exception_handler(LookupError)
def missing(request,exc):return JSONResponse(status_code=404,content={'error':str(exc)})
@app.exception_handler(psycopg.Error)
def database_error(request,exc):
    import logging
    logging.getLogger('recovery').exception('Database operation failed')
    return JSONResponse(status_code=503,content={'error':'Database operation failed. Check the database connection and migration status.'})


@app.get('/')
def home():return FileResponse(ROOT/'src/cart_recovery/static/index.html')
@app.get('/healthz')
def health():return {'status':'ok','delivery_mode':'simulated','stage':'application'}
@app.get('/readyz')
def ready(response:Response):
    if not os.environ.get('DATABASE_URL'):
        response.status_code=503;return {'status':'not_ready','reason':'DATABASE_URL is unset'}
    try:
        with connect() as c:c.execute('SELECT clock FROM runtime_state LIMIT 1')
    except psycopg.Error:
        response.status_code=503;return {'status':'not_ready','reason':'database/schema unavailable'}
    return {'status':'ready'}
@app.get('/api/policy')
def policy():return load_config('policy')
@app.post('/api/login')
def login(body:Login,response:Response):
    if not hmac.compare_digest(body.password,os.environ.get('DEMO_PASSWORD','recovery-demo')):raise HTTPException(401,'Incorrect demo password')
    payload=f'{body.username}:{int(time.time())+8*3600}';signature=hmac.new(SECRET,payload.encode(),sha256).hexdigest()
    response.set_cookie('recovery_session',payload+'.'+signature,httponly=True,samesite='strict',max_age=8*3600,secure=os.environ.get('COOKIE_SECURE')=='1')
    return {'role':body.username}
@app.post('/api/logout')
def logout(response:Response):response.delete_cookie('recovery_session');return {'ok':True}
@app.get('/api/me')
def me(role=Depends(user)):return {'role':role}
@app.get('/api/metrics')
def metrics(role=Depends(user)):return queries.metrics()
@app.get('/api/carts')
def carts(search:str=Query('',max_length=80),state:Literal['','purchased','empty','expired','active','abandoned']='',page:int=Query(1,ge=1),role=Depends(user)):
    return queries.carts(search,state,page)
@app.get('/api/carts/{cart_id}')
def timeline(cart_id:str,role=Depends(user)):return queries.timeline(cart_id)
@app.get('/api/campaigns')
def campaigns(page:int=Query(1,ge=1),role=Depends(user)):return queries.campaigns(page)
@app.get('/api/issues')
def issues(role=Depends(user)):return queries.issues()
@app.get('/api/quality')
def quality(role=Depends(user)):
    folder=ROOT/'data'/os.environ.get('DATA_PROFILE','starter')/'metadata'
    result={}
    for name in ('validation-summary','evaluation','run','reproducibility'):
        path=folder/(name+'.json')
        if path.exists():result[name]=json.loads(path.read_text())
    return result
@app.post('/api/scenarios')
def scenario(body:Scenario,request:Request,actor=Depends(manager)):
    return mutate(request,actor,body.model_dump(),lambda:service.scenario(body.kind,body.channel))
@app.post('/api/scan')
def scan(request:Request,actor=Depends(manager)):return mutate(request,actor,{},lambda:service.scan())
@app.post('/api/worker')
def worker(request:Request,actor=Depends(manager)):
    def run():
        results=[]
        for _ in range(30):
            result=service.work_once();results.append(result)
            if result.get('idle') or result.get('paused'):break
        return {'results':results}
    return mutate(request,actor,{},run)
@app.post('/api/clock')
def advance(body:Advance,request:Request,actor=Depends(manager)):return mutate(request,actor,body.model_dump(),lambda:service.advance(body.minutes,actor))
@app.post('/api/settle')
def settle(request:Request,actor=Depends(manager)):return mutate(request,actor,{},service.settle)
@app.post('/api/pause')
def pause(body:Pause,request:Request,actor=Depends(manager)):
    def apply():
        with connect() as c:
            c.execute('UPDATE runtime_state SET paused=%s WHERE id=1',(body.paused,));service.audit(c,actor,'pause' if body.paused else 'resume')
        return {'paused':body.paused}
    return mutate(request,actor,body.model_dump(),apply)
@app.post('/api/customers/{customer_id}/consent')
def consent(customer_id:str,body:ConsentChange,request:Request,actor=Depends(manager)):
    return mutate(request,actor,body.model_dump(),lambda:service.set_consent(customer_id,body.channel,body.state,actor))
@app.post('/api/carts/{cart_id}/quantity')
def quantity(cart_id:str,body:Quantity,request:Request,actor=Depends(manager)):
    return mutate(request,actor,body.model_dump(),lambda:service.update_quantity(cart_id,body.line_id,body.quantity))
@app.post('/api/carts/{cart_id}/enroll')
def enroll(cart_id:str,request:Request,channel:Literal['email','sms']='email',actor=Depends(manager)):
    return mutate(request,actor,{'channel':channel},lambda:service.enroll(cart_id,channel))
@app.post('/api/sends/{send_id}/events')
def event(send_id:str,body:Callback,request:Request,actor=Depends(manager)):
    return mutate(request,actor,body.model_dump(),lambda:service.callback(send_id,body.kind,request.headers['Idempotency-Key']))
@app.post('/api/carts/{cart_id}/purchase')
def purchase(cart_id:str,request:Request,actor=Depends(manager)):
    return mutate(request,actor,{},lambda:service.pay(cart_id,request.headers['Idempotency-Key']))
@app.post('/api/orders/{order_id}/refund')
def refund(order_id:str,body:Refund,request:Request,actor=Depends(manager)):
    return mutate(request,actor,body.model_dump(),lambda:service.refund(order_id,body.amount_minor,request.headers['Idempotency-Key']))
@app.post('/api/issues/{issue_id}/reviews')
def review(issue_id:int,body:Review,request:Request,actor=Depends(manager)):
    def save():
        with connect() as c:
            if not c.execute('SELECT 1 FROM issue WHERE issue_id=%s',(issue_id,)).fetchone():raise LookupError('Issue not found')
            insert(c,'issue_review',issue_id=issue_id,actor=actor,note=body.note,created_at=service.clock(c))
        return {'reviewed':True}
    return mutate(request,actor,body.model_dump(),save)
@app.get('/api/downloads/{name}')
def download(name:Literal['validation-summary','evaluation','checksums','findings','run'],role=Depends(user)):
    path=ROOT/'data'/os.environ.get('DATA_PROFILE','starter')/'metadata'/(name+'.json')
    if not path.exists():raise HTTPException(404,'Generate the dataset first')
    return FileResponse(path,filename=name+'.json')

@app.post('/api/campaigns/{campaign_id}/cancel')
def cancel(campaign_id:str,request:Request,actor=Depends(manager)):
    return mutate(request,actor,{},lambda:service.cancel_campaign(campaign_id,actor))
