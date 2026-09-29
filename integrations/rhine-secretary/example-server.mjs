import http from 'node:http';
import {createIntegrationBridge} from './integration-bridge.mjs';

// Keep this example local. A production host mounts the same handler before static routes.
const port=Number(process.env.RHINE_PORT || 5180);
if(!Number.isInteger(port) || port<1 || port>65535)throw new Error('Invalid RHINE_PORT');
const bridge=createIntegrationBridge({port});
const page=`<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>秘书接口连接检查</title>
<h1>秘书接口连接检查</h1><p>这是只读接入示例。需要本机已有兼容秘书服务。</p>
<button id="read">检查秘书目录</button><pre id="result">尚未读取</pre>
<script>document.getElementById('read').onclick=async()=>{const out=document.getElementById('result');try{const r=await fetch('/api/secretary/widgets/v1/catalog',{headers:{'X-Rhine-Local':'1'}});const data=await r.json();out.textContent=JSON.stringify(data,null,2);}catch(e){out.textContent='连接失败：'+e.message;}};</script></html>`;
const server=http.createServer(async(req,res)=>{
  if(await bridge(req,res))return;
  if(req.method==='GET' && req.url==='/'){
    res.writeHead(200,{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store'});res.end(page);return;
  }
  res.writeHead(404);res.end('Not found');
});
server.listen(port,'127.0.0.1',()=>console.log(`Secretary bridge: http://127.0.0.1:${port}`));
