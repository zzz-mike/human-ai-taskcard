import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {createIntegrationBridge,secretaryTarget,checkLocalRequest,createSecretaryReviewClient,coalesceReads,fetchSecretary} from './integration-bridge.mjs';

async function serve(t,options={}) {
  let handle;
  const server=http.createServer(async(req,res)=>{
    if(!await handle(req,res)){res.writeHead(404);res.end();}
  });
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const port=server.address().port;
  handle=createIntegrationBridge({port,...options});
  t.after(()=>new Promise(r=>server.close(r)));
  return `http://127.0.0.1:${port}`;
}
const headers={'X-Rhine-Local':'1'};
const intent={request_id:'00000000-0000-4000-8000-000000000001',item_id:'fictional-item',expected_revision:'r1',action:'status',status:'completed'};

test('fixed route and bounded query allowlist',()=>{
  assert.equal(secretaryTarget(new URL('http://localhost/api/secretary/widgets/v1/todo?limit=20')),'/api/widgets/v1/todo?limit=20');
  for(const path of ['other','todo?limit=101','todo?limit=2&limit=3','todo?url=http://example.invalid','items?offset=-1','item?item_id=','project-detail?project_id=x&section=unknown'])
    assert.throws(()=>secretaryTarget(new URL('http://localhost/api/secretary/widgets/v1/'+path)));
});
test('duplicate security headers, remote hosts and cross origins denied',()=>{
  const req={headers:{host:'127.0.0.1:5180','x-rhine-local':'1'},rawHeaders:[],socket:{remoteAddress:'127.0.0.1'}};
  checkLocalRequest(req);
  for(const change of [{headers:{...req.headers,host:'example.invalid:5180'}},{headers:{...req.headers,origin:'http://example.invalid'}},{rawHeaders:['Host','a','HOST','b']},{socket:{remoteAddress:'192.0.2.1'}}])assert.throws(()=>checkLocalRequest({...req,...change}));
});
test('catalog exposes only the six supported secretary widgets',async t=>{
  const base=await serve(t,{secretary:async()=>({status:200,data:{schema_version:'1.0',widgets:[{id:'todo'},{id:'unrelated.topic'}],projects:[]}})});
  const res=await fetch(base+'/api/secretary/widgets/v1/catalog',{headers});
  assert.equal(res.status,200);assert.deepEqual((await res.json()).widgets,[{id:'todo'}]);
  assert.equal((await fetch(base+'/api/secretary/widgets/v1/unknown',{headers})).status,404);
  assert.equal((await fetch(base+'/api/secretary/widgets/v1/todo')).status,403);
});
test('review is disabled by default and never calls the upstream writer',async t=>{
  let calls=0;const base=await serve(t,{secretaryReview:async()=>{calls++;}});
  const cap=await fetch(base+'/api/local/v1/capabilities',{headers}).then(r=>r.json());
  assert.equal(cap.secretary_review,false);assert.equal(cap.secretary_review_token,null);
  const res=await fetch(base+'/api/secretary/widgets/v1/review',{method:'POST',headers:{...headers,Origin:base,'Content-Type':'application/json'},body:JSON.stringify(intent)});
  assert.equal(res.status,403);assert.equal(calls,0);
});
test('explicit review requires origin and nonce, preserves conflict, rejects extra fields',async t=>{
  let calls=0;const base=await serve(t,{enableReview:true,secretaryReview:async body=>{calls++;assert.deepEqual(body,intent);return {status:409,data:{code:'revision_conflict',current_item:{id:'fictional-item'},debug:'private-debug'}};}});
  const cap=await fetch(base+'/api/local/v1/capabilities',{headers}).then(r=>r.json());
  const h={...headers,Origin:base,'Content-Type':'application/json','X-Rhine-Action-Token':cap.secretary_review_token};
  assert.equal((await fetch(base+'/api/secretary/widgets/v1/review',{method:'POST',headers:{...h,'X-Rhine-Action-Token':'wrong'},body:JSON.stringify(intent)})).status,403);
  assert.equal((await fetch(base+'/api/secretary/widgets/v1/review',{method:'POST',headers:h,body:JSON.stringify({...intent,extra:true})})).status,400);
  const res=await fetch(base+'/api/secretary/widgets/v1/review',{method:'POST',headers:h,body:JSON.stringify(intent)});
  assert.equal(res.status,409);assert.deepEqual(await res.json(),{error:'revision_conflict',code:'revision_conflict',current_item:{id:'fictional-item'}});assert.equal(calls,1);
});
test('upstream errors do not expose arbitrary exception text',async t=>{
  const base=await serve(t,{secretary:async()=>({status:500,data:{error:'private-debug',code:'unknown',token:'private-token'}})});
  const res=await fetch(base+'/api/secretary/widgets/v1/todo',{headers});
  assert.deepEqual(await res.json(),{error:'secretary_request_failed',code:'secretary_request_failed'});
});
test('review session refresh reuses the exact original request',async()=>{
  let sessions=0;const bodies=[];
  const write=createSecretaryReviewClient({transport:async(method,path,opt)=>{
    if(method==='GET')return {status:200,data:{schema_version:'1.0',scope:'widgets:review',review_token:'fixture-'+(++sessions)}};
    bodies.push(opt.body);return bodies.length===1?{status:403,data:{code:'invalid_review_token'}}:{status:200,data:{ok:true}};
  }});
  assert.equal((await write(intent)).status,200);assert.equal(sessions,2);assert.deepEqual(bodies,[intent,intent]);
});
test('read coalescing does not reuse pre-write results after invalidation',async()=>{
  let calls=0;const resolve=[];
  const read=coalesceReads(()=>{calls++;return new Promise(r=>resolve.push(r));});
  const a=read('x'),b=read('x');await Promise.resolve();assert.equal(calls,1);
  read.invalidate();const c=read('x');await Promise.resolve();assert.equal(calls,2);
  resolve[0]('old');resolve[1]('new');assert.deepEqual(await Promise.all([a,b,c]),['old','old','new']);
});
test('direct upstream calls also reject unapproved paths',()=>{
  assert.throws(()=>fetchSecretary('http://example.invalid'));
  assert.throws(()=>fetchSecretary('/api/widgets/v1/unknown'));
});
