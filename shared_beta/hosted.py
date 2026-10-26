"""ASGI API for university hosting behind HTTPS. No local test credentials accepted."""
import os
from fastapi import FastAPI,Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .identity import EntraValidator
from .store import Problem
from .sql_store import SQLStore,azure_engine


def create_app(store=None,validator=None):
    validator=validator or EntraValidator(os.environ['ACE_TENANT_ID'],os.environ['ACE_API_CLIENT_ID'],os.environ['ACE_DESKTOP_CLIENT_ID'])
    store=store or SQLStore(azure_engine(os.environ['ACE_SQL_ODBC']))
    app=FastAPI(title='A.C.E. Shared Save',docs_url=None,redoc_url=None,openapi_url=None)

    @app.middleware('http')
    async def security(request,call_next):
        if request.url.path=='/health':return JSONResponse({'status':'running'})
        try:
            header=request.headers.get('authorization','')
            if not header.startswith('Bearer '):raise Problem(401,'Sign in with Auburn.')
            if request.headers.get('origin'):raise Problem(403,'Browser origins are not enabled.')
            request.state.account=await run_in_threadpool(validator.authenticate,header[7:])
            response=await call_next(request)
        except Problem as exc:response=JSONResponse({'error':str(exc)},status_code=exc.status)
        except Exception:response=JSONResponse({'error':'Service unavailable. Retry the same operation.'},status_code=503)
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        return response

    @app.exception_handler(Problem)
    async def problem(request,exc):return JSONResponse({'error':str(exc)},status_code=exc.status)

    @app.get('/v1/state')
    def state(request:Request):
        result=store.snapshot();result['account']=request.state.account;return result

    @app.get('/v1/audit')
    def audit(start:str='',end:str=''):return store.history(start,end)

    @app.post('/v1/operations')
    async def mutate(request:Request):
        body=bytearray()
        async for part in request.stream():
            body.extend(part)
            if len(body)>32768:raise Problem(413,'Request is too large.')
        import json
        try:payload=json.loads(body)
        except ValueError:raise Problem(400,'Invalid JSON.')
        if not isinstance(payload,dict):raise Problem(400,'Expected a JSON object.')
        a=request.state.account
        return await run_in_threadpool(store.mutate,a['name'],a['role'],payload)
    return app
