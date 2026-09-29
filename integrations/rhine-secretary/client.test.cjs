const test=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const client=require(path.resolve(process.argv[2] || 'dist/secretary-client-test/secretary-client.js'));
const catalog={schema_version:'1.0',timezone:'Asia/Shanghai',projects:[],widgets:client.widgetIds.map(id=>({id,title:id,sizes:['small'],default_size:'small',refresh_seconds:60}))};
test('standalone secretary catalog parses, missing and unknown widgets fail',()=>{
  assert.equal(client.parseCatalog(catalog).widgets.length,6);
  assert.throws(()=>client.parseCatalog({...catalog,widgets:catalog.widgets.slice(1)}));
  assert.throws(()=>client.parseCatalog({...catalog,widgets:[...catalog.widgets,{id:'unrelated.topic'}]}));
});
test('source navigation is restricted to local secretary pages',()=>{
  assert.equal(client.safeDetailUrl('http://127.0.0.1:8866/?item=demo'),'http://127.0.0.1:8866/?item=demo');
  for(const url of ['https://example.invalid','http://127.0.0.1:9999/','http://127.0.0.1:8866/a/../','http://127.0.0.1:8866/?token=x'])assert.equal(client.safeDetailUrl(url),null);
});
test('unknown routes cannot reach the transport',()=>{
  assert.throws(()=>client.readWorkbenchJSON('unrelated/topic',new URLSearchParams()));
});
