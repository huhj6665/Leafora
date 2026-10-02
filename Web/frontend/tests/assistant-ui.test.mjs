/** Isolated UI / SSE / citation safety checks; no production accounts or live APIs.
 * Start Vite on 5187, then run with Node and PLAYWRIGHT_MODULE_PATH if not installed locally.
 */
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { mkdir } from 'node:fs/promises'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
const require=createRequire(import.meta.url)
const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH||'playwright')
const browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})})
const screenshots=process.env.ASSISTANT_SCREENSHOT_DIR||join(tmpdir(),'leafora-assistant-ui')
await mkdir(screenshots,{recursive:true})
const failures=[],page=await browser.newPage({viewport:{width:1440,height:960}})
page.on('pageerror',error=>failures.push(error.message))
await page.route('https://fonts.googleapis.com/**',route=>route.abort())
await page.route('https://fonts.gstatic.com/**',route=>route.abort())
const now='2026-10-01T04:00:00Z',context={crop:'烟草',growth_stage:'旺长期',location:'北京',field_id:null,inspection_id:null}
const evidence=[{id:'E1',title:'巡检 · 环境统计',kind:'platform',url:'/platform/inspections/INS_TEST',retrieved_at:now,data:{sample_count:4,metrics:{temperature:{mean:25,valid_count:2,missing_count:2,unit:'°C'}},series:[{time:now,temperature:25,humidity:70,co2:400,light:300}]}},
  {id:'E2',title:'北京 · 天气预报',kind:'weather',url:'https://www.qweather.com',retrieved_at:now,data:{location:{name:'北京'},current:{temperature:{value:25,unit:'°C'},humidity:.7,condition:{text:'多云'},wind:{speed:{value:3,unit:'m/s'}},precipitation:{amount:{value:0,unit:'mm'}},metadata:{attributions:['https://developer.qweather.com/attribution.html']}},forecast:{days:[{forecastStartTime:now,temperatureMin:{value:19,unit:'°C'},temperatureMax:{value:28,unit:'°C'},daytime:{condition:{text:'多云'},precipitation:{probability:.3}},nighttime:{condition:{text:'晴'}}}]} }}]
let conversations=[],messages=[],runPosts=0
const answer='## 巡检与天气\n\n有效温度记录的平均值为 **25°C**。[E1]\n\n北京当前湿度为70%，天气不是现场实测。[E2]\n\n<img src="x" onerror="window.__unsafe=1"><script>window.__unsafe=1</script>[非法链接](javascript:alert(1))'
await page.route(url=>url.pathname.startsWith('/api/'),async route=>{
  const request=route.request(),u=new URL(request.url()),path=u.pathname,method=request.method()
  const respond=data=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({code:0,message:'success',data})})
  if(path.endsWith('/capabilities'))return respond({model:'deepseek-flash',model_configured:true,weather_configured:true,search_configured:true,vision_supported:true,limits:{images:3,document_mb:20,image_mb:10,run_seconds:180}})
  if(path==='/api/fields')return respond([{field_id:'FIELD_TEST',name:'试验烟田'}])
  if(path==='/api/platform/events')return respond({total:0,items:[]})
  if(path.endsWith('/attachments'))return respond([])
  if(path.endsWith('/conversations')&&method==='GET')return respond(conversations)
  if(path.endsWith('/conversations')&&method==='POST'){conversations=[{id:'CON_TEST',title:'新的对话',context,active_run_id:null,updated_at:now}];return respond(conversations[0])}
  if(path.endsWith('/conversations/CON_TEST/runs')){
    runPosts++;const body=request.postDataJSON();assert.ok(body.client_request_id)
    messages=[{id:'MSG_USER',role:'user',content:body.question,status:'COMPLETED',attachment_ids:[],evidence:[],created_at:now},{id:'MSG_ANSWER',run_id:'RUN_TEST',role:'assistant',content:'',status:'RUNNING',attachment_ids:[],evidence:[],created_at:now}]
    conversations[0].title=body.question;return respond({id:'RUN_TEST',status:'RUNNING',assistant_message_id:'MSG_ANSWER'})
  }
  if(path.endsWith('/conversations/CON_TEST'))return respond({...conversations[0],messages})
  if(path.endsWith('/runs/RUN_TEST/events')){
    const events=[['status',{text:'正在读取环境记录'}],['evidence',{items:evidence}],['delta',{text:answer}],['done',{status:'COMPLETED'}]]
    const body=events.map(([kind,payload],i)=>`id: ${i+1}\r\nevent: ${kind}\r\ndata: ${JSON.stringify(payload)}\r\n\r\n`).join('')
    return route.fulfill({status:200,contentType:'text/event-stream',body})
  }
  if(path.endsWith('/runs/RUN_TEST'))return respond({id:'RUN_TEST',status:'COMPLETED',message:{...messages[1],content:answer,status:'COMPLETED',evidence}})
  failures.push('Unexpected API: '+path);return route.fulfill({status:404,body:'unexpected test route'})
})
try{
  await page.goto(process.env.ASSISTANT_PREVIEW_URL||'http://127.0.0.1:5187/tests/assistant-preview.html')
  await page.getByRole('heading',{name:'Leafora 农业助手'}).waitFor()
  await page.getByText('智能分析已启用',{exact:true}).waitFor()
  assert.equal(await page.locator('.composer-footer').count(),0)
  async function checkComposerLayout(){
    const layout=await page.evaluate(()=>{
      const panel=document.querySelector('.chat-panel').getBoundingClientRect()
      const composer=document.querySelector('.composer').getBoundingClientRect()
      const send=document.querySelector('.send-button').getBoundingClientRect()
      return {bottomGap:panel.bottom-composer.bottom,sendBottom:send.bottom,viewport:window.innerHeight}
    })
    assert.ok(layout.bottomGap>=0&&layout.bottomGap<=11,'composer should sit close to the chat panel bottom')
    assert.ok(layout.sendBottom<=layout.viewport,'send button should remain visible')
  }
  await checkComposerLayout()
  await page.screenshot({path:join(screenshots,'desktop-welcome.png'),fullPage:true})
  await page.locator('textarea').fill('总结最近一次巡检并查看北京天气')
  await page.locator('textarea').press('Enter')
  await page.getByRole('heading',{name:'巡检与天气'}).waitFor()
  await page.getByRole('button',{name:'重新生成'}).waitFor()
  assert.equal(runPosts,1)
  assert.equal(await page.locator('.message.user .message-label').count(),0)
  assert.equal(await page.locator('.message.user .user-question').innerText(),'总结最近一次巡检并查看北京天气')
  assert.equal(await page.locator('.message.user time').count(),0)
  async function checkUserBubble(){
    const padding=await page.evaluate(()=>{
      const bubble=document.querySelector('.message.user').getBoundingClientRect()
      const question=document.querySelector('.message.user .user-question').getBoundingClientRect()
      return {top:question.top-bubble.top,bottom:bubble.bottom-question.bottom}
    })
    assert.equal(padding.top,12)
    assert.equal(padding.bottom,12)
  }
  await checkUserBubble()
  assert.equal(await page.locator('.answer-body img,.answer-body script,.answer-body a,.answer-body svg,.answer-body audio,.answer-body video').count(),0)
  assert.equal(await page.evaluate(()=>window.__unsafe),undefined)
  await page.locator('.answer-body [data-citation="E2"]').click()
  await page.getByText('湿度 70%',{exact:true}).waitFor()
  assert.equal(await page.getByRole('link',{name:'数据归因 1 ↗'}).count(),1)
  await page.screenshot({path:join(screenshots,'desktop-answer.png'),fullPage:true})
  await page.setViewportSize({width:390,height:844})
  await page.getByRole('button',{name:'关闭分析依据'}).click()
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),'mobile overflow')
  await checkComposerLayout()
  await checkUserBubble()
  await page.screenshot({path:join(screenshots,'mobile-answer.png'),fullPage:true})
  await page.getByRole('button',{name:'打开历史会话'}).click()
  await page.getByRole('button',{name:'总结最近一次巡检并查看北京天气',exact:true}).waitFor()
  await page.getByRole('button',{name:'关闭会话栏'}).click()
  const parsed=await page.evaluate(async()=>{const {parseEventBlock}=await import('/src/api/assistant.ts');return parseEventBlock('id: 5\nevent: delta\ndata: {"text":"中文"}')})
  assert.equal(parsed.payload.text,'中文');assert.equal(parsed.id,5)
  assert.deepEqual(failures,[])
  console.log(JSON.stringify({status:'passed',checks:['composer-layout','user-message-layout','send-once','SSE','citations','XSS','weather-units-attribution','mobile-no-overflow','history-drawer','event-parser'],screenshots}))
}catch(error){console.error(JSON.stringify({failures,body:(await page.locator('body').innerText()).slice(0,1500)}));await page.screenshot({path:join(screenshots,'failure.png'),fullPage:true});throw error}finally{await browser.close()}
