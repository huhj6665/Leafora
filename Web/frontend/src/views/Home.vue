<template>
  <main class="home">
    <header :class="['site-header', { 'is-scrolled': scrolled, 'menu-open': menuOpen }]">
      <div class="nav-shell">
        <router-link to="/" class="brand" aria-label="Leafora 烟草智能巡检平台首页" @click="closeMenu">
          <span class="brand-symbol" aria-hidden="true">
            <svg viewBox="0 0 32 32"><path d="M7 22C8 12 15 6 25 6c0 10-5 18-14 19"/><path d="M9 25c4-7 8-11 14-15"/></svg>
          </span>
          <span><b>Leafora</b><small>烟草智能巡检平台</small></span>
        </router-link>

        <button class="menu-toggle" type="button" :aria-expanded="menuOpen" aria-controls="primary-navigation" :aria-label="menuOpen ? '关闭导航菜单' : '打开导航菜单'" @click="menuOpen = !menuOpen">
          <span></span><span></span>
        </button>

        <nav id="primary-navigation" :class="['nav-links', { open: menuOpen }]" aria-label="首页导航">
          <a href="#capabilities" @click="closeMenu">平台能力</a>
          <a href="#workflow" @click="closeMenu">巡检流程</a>
          <a href="#preview" @click="closeMenu">平台预览</a>
          <router-link :to="platformTarget" class="nav-action" @click="closeMenu">
            {{ auth.authenticated ? '进入平台' : '登录' }}
            <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8h9M8 4l4 4-4 4"/></svg>
          </router-link>
        </nav>
      </div>
    </header>

    <section class="hero" aria-labelledby="hero-title">
      <picture class="hero-media" aria-hidden="true">
        <source :srcset="heroWebp" type="image/webp">
        <img :src="heroPng" width="1674" height="941" alt="" fetchpriority="high" decoding="async">
      </picture>
      <div class="hero-shade"></div>
      <div class="hero-grain" aria-hidden="true"></div>

      <div class="hero-content">
        <p class="hero-label">烟草智能巡检平台</p>
        <h1 id="hero-title"><span>从田间采集</span><span>到风险定位</span></h1>
        <p class="hero-summary">汇集巡检轨迹、环境数据与病害识别<br>让异常有位置 让现场可回看</p>
        <div class="hero-actions">
          <router-link :to="platformTarget" class="button button-primary">进入平台<svg viewBox="0 0 18 18" aria-hidden="true"><path d="M3 9h11M10 5l4 4-4 4"/></svg></router-link>
          <a href="#workflow" class="button button-secondary">了解巡检流程</a>
        </div>
      </div>

      <a class="scroll-cue" href="#capabilities" aria-label="向下查看平台能力"><span></span>向下了解</a>
    </section>

    <section id="capabilities" class="section capabilities reveal-section">
      <div class="section-intro">
        <p class="section-index">平台能力</p>
        <h2>看清烟田的每一面</h2>
        <p>轨迹、环境、图像和设备状态统一呈现，帮助用户快速查看每次巡检。</p>
      </div>
      <div class="capability-list">
        <article v-for="(item, index) in capabilities" :key="item.title">
          <span class="item-number">0{{ index + 1 }}</span><div class="line-icon" aria-hidden="true" v-html="item.icon"></div><h3>{{ item.title }}</h3><p>{{ item.text }}</p>
        </article>
      </div>
    </section>

    <section id="workflow" class="section workflow reveal-section">
      <div class="workflow-copy">
        <p class="section-index">巡检流程</p><h2>从现场到平台<br>让信息完整流转</h2><p>在小程序发起巡检，由设备采集与识别，在平台回看完整记录。</p>
      </div>
      <ol class="workflow-steps">
        <li v-for="(item, index) in workflow" :key="item.title"><span>{{ String(index + 1).padStart(2, '0') }}</span><div><h3>{{ item.title }}</h3><p>{{ item.text }}</p></div><svg viewBox="0 0 22 22" aria-hidden="true"><path d="M4 11h13M12 6l5 5-5 5"/></svg></li>
      </ol>
    </section>

    <section id="preview" class="product-preview reveal-section" aria-labelledby="preview-title">
      <div class="preview-heading">
        <div><p class="section-index">平台预览</p><h2 id="preview-title">把线索变成清晰的记录</h2></div>
        <p>轨迹、记录和现场图像在同一视图中彼此对应。以下为平台界面示意，不代表实时数据。</p>
      </div>
      <div class="preview-frame">
        <div class="preview-bar"><span class="preview-brand">Leafora</span><span>巡检详情 · 界面示意</span><i></i></div>
        <div class="preview-body">
          <aside class="preview-nav" aria-hidden="true"><b></b><span></span><span></span><span></span><span></span></aside>
          <div class="preview-canvas">
            <div class="preview-title-row"><div><small>巡检记录</small><strong>烟田巡检详情</strong></div><span>已完成</span></div>
            <div class="preview-grid">
              <div class="map-panel">
                <svg viewBox="0 0 760 400" role="img" aria-label="巡检范围与行进轨迹界面示意">
                  <defs><pattern id="field-grid" width="36" height="36" patternUnits="userSpaceOnUse"><path d="M36 0H0v36" fill="none" stroke="currentColor" stroke-width="1"/></pattern></defs>
                  <rect width="760" height="400" fill="url(#field-grid)"/><path class="field-shape" d="M72 304c73-91 164-44 205-125 45-90 127-72 185-14 49 49 113-8 219-83l28 188c-91 75-177 46-244 91-74 49-150-18-221 6-74 25-120-18-172-63z"/><path class="map-route" d="M103 310c83-55 89-116 171-123 89-7 105 99 197 57 67-31 108-101 190-138"/><g class="map-points"><circle cx="103" cy="310" r="7"/><circle cx="274" cy="187" r="7"/><circle cx="471" cy="244" r="7"/><circle cx="661" cy="106" r="8"/></g>
                </svg><span class="map-caption">巡检范围与行进轨迹</span>
              </div>
              <div class="records-panel">
                <div class="record-head"><b>现场记录</b><span>按时间排列</span></div>
                <div v-for="item in previewRecords" :key="item.title" class="record-row"><span :class="item.tone"></span><div><b>{{ item.title }}</b><small>{{ item.note }}</small></div><i>查看</i></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="final-cta reveal-section">
      <div><p class="section-index">Leafora</p><h2>每一次巡检都有据可循</h2></div>
      <router-link :to="platformTarget" class="button button-light">{{ auth.authenticated ? '进入数据平台' : '开始使用' }}<svg viewBox="0 0 18 18" aria-hidden="true"><path d="M3 9h11M10 5l4 4-4 4"/></svg></router-link>
    </section>

    <footer class="site-footer">
      <div class="footer-brand"><b>Leafora</b><span>烟草智能巡检平台</span></div><p>巡检结果仅用于现场辅助查看，不替代专业农业判断。</p><div><a href="#capabilities">平台能力</a><router-link :to="platformTarget">进入平台</router-link></div>
    </footer>
  </main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import heroPng from '@/assets/home/leafora-field-hero.png'
import heroWebp from '@/assets/home/leafora-field-hero.webp'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const scrolled = ref(false)
const menuOpen = ref(false)
const platformTarget = computed(() => auth.authenticated ? '/platform/overview' : '/login')

const capabilities = [
  { title:'巡检轨迹', text:'查看覆盖范围与行进路线，快速掌握本次巡检经过的区域。', icon:'<svg viewBox="0 0 36 36"><path d="M7 28c5-12 8-3 13-14 3-6 7-5 10-8"/><circle cx="7" cy="28" r="2.5"/><circle cx="20" cy="14" r="2.5"/><circle cx="30" cy="6" r="2.5"/></svg>' },
  { title:'异常位置', text:'对照关注位置与现场图像，进一步复核巡检中的异常线索。', icon:'<svg viewBox="0 0 36 36"><path d="M18 31s10-9 10-17a10 10 0 10-20 0c0 8 10 17 10 17z"/><circle cx="18" cy="14" r="3"/></svg>' },
  { title:'环境数据', text:'沿巡检时间回看温湿度、光照等现场环境变化。', icon:'<svg viewBox="0 0 36 36"><path d="M5 26l7-8 6 4 7-12 6 5"/><path d="M5 31h26"/></svg>' },
  { title:'设备状态', text:'掌握设备在线状态、现场图像和历史巡检任务。', icon:'<svg viewBox="0 0 36 36"><rect x="7" y="7" width="22" height="16" rx="2"/><path d="M13 29h10M18 23v6"/></svg>' },
]
const workflow = [
  { title:'准备设备', text:'在现场完成设备检查与安全配对。' }, { title:'开始巡检', text:'在微信小程序选择烟田和设备，等待设备确认开始。' },
  { title:'发现异常', text:'过程中的关注位置和现场图像被持续记录。' }, { title:'查看结果', text:'任务结束后，在平台回看轨迹、环境与图像。' },
]
const previewRecords = [
  { title:'行进轨迹', note:'完整过程可回看', tone:'green' }, { title:'关注位置', note:'与现场图像对应', tone:'amber' }, { title:'环境变化', note:'沿巡检时间呈现', tone:'blue' },
]

let revealObserver: IntersectionObserver | null = null
function closeMenu(){ menuOpen.value=false }
function onScroll(){ scrolled.value=window.scrollY>24 }
function onKeydown(event: KeyboardEvent){ if(event.key==='Escape')closeMenu() }
onMounted(()=>{
  onScroll(); window.addEventListener('scroll',onScroll,{passive:true}); window.addEventListener('keydown',onKeydown)
  const reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches
  if(reduced){document.querySelectorAll('.reveal-section').forEach((el)=>el.classList.add('is-visible'));return}
  revealObserver=new IntersectionObserver((entries)=>entries.forEach((entry)=>{if(entry.isIntersecting)entry.target.classList.add('is-visible')}),{threshold:.12})
  document.querySelectorAll('.reveal-section').forEach((el)=>revealObserver?.observe(el))
})
onBeforeUnmount(()=>{window.removeEventListener('scroll',onScroll);window.removeEventListener('keydown',onKeydown);revealObserver?.disconnect()})
</script>

<style scoped>
:global(html.route-home){scroll-behavior:smooth;scroll-padding-top:82px}.home{--home-bg:#09100c;--home-panel:#0d1711;--home-panel-2:#111d16;--home-line:rgba(235,241,232,.14);--home-text:#f1f3ed;--home-muted:#a7b0a8;--home-green:#a9d35e;min-height:100vh;background:radial-gradient(circle at 82% 42%,rgba(70,112,72,.13),transparent 30%),var(--home-bg);color:var(--home-text);overflow-x:clip}.home a:focus-visible,.home button:focus-visible{outline:2px solid var(--home-green);outline-offset:4px}.site-header{position:fixed;z-index:50;inset:0 0 auto;height:82px;transition:background .3s,border-color .3s,backdrop-filter .3s,box-shadow .3s;border-bottom:1px solid transparent}.site-header.is-scrolled,.site-header.menu-open{background:rgba(9,15,12,.9);border-color:var(--home-line);backdrop-filter:blur(14px);box-shadow:0 14px 36px rgba(0,0,0,.2)}.nav-shell{width:min(100% - 64px,1440px);height:100%;margin:auto;display:flex;align-items:center;justify-content:space-between}.brand{display:flex;align-items:center;gap:11px;color:white}.brand-symbol{width:34px;height:34px;border:1px solid rgba(182,219,112,.55);display:grid;place-items:center}.brand-symbol svg{width:23px;fill:none;stroke:var(--home-green);stroke-width:1.5;stroke-linecap:round}.brand b{display:block;font:600 15px/1 var(--display);letter-spacing:.03em}.brand small{display:block;margin-top:5px;color:#aab3ac;font-size:9px;letter-spacing:.12em}.nav-links{display:flex;align-items:center;gap:30px;color:#bdc5bf;font-size:12px}.nav-links>a{transition:color .2s}.nav-links>a:hover,.nav-links>a:focus-visible{color:white}.nav-action{border:1px solid rgba(236,242,232,.32);padding:10px 14px;color:white!important;display:flex;align-items:center;gap:12px}.nav-action svg,.button svg{width:17px;fill:none;stroke:currentColor;stroke-width:1.5}.menu-toggle{display:none;width:42px;height:42px;border:1px solid var(--home-line);background:transparent;padding:12px;cursor:pointer}.menu-toggle span{display:block;height:1px;background:white;margin:5px 0;transition:transform .2s}.hero{position:relative;min-height:clamp(720px,100vh,980px);display:flex;align-items:center;isolation:isolate}.hero-media,.hero-shade,.hero-grain{position:absolute;inset:0}.hero-media{z-index:-3;overflow:hidden}.hero-media img{width:100%;height:100%;display:block;object-fit:cover;object-position:center;transform:scale(1.012);animation:hero-settle 1.4s ease-out both}.hero-shade{z-index:-2;background:linear-gradient(90deg,rgba(5,10,8,.97) 0%,rgba(5,10,8,.87) 28%,rgba(5,10,8,.46) 56%,rgba(5,10,8,.08) 82%),linear-gradient(0deg,var(--home-bg) 0%,transparent 31%,rgba(5,10,8,.25) 100%)}.hero-grain{z-index:-1;opacity:.15;background-image:radial-gradient(rgba(255,255,255,.22) .55px,transparent .55px);background-size:5px 5px;mask-image:linear-gradient(90deg,#000,transparent 62%)}.hero-content{width:min(100% - 64px,1440px);margin:0 auto;padding-top:74px}.hero-label{display:flex;align-items:center;gap:12px;color:#b7c2ba;font:500 10px var(--mono);letter-spacing:.16em}.hero-label span{width:38px;height:1px;background:var(--home-green)}.hero h1{max-width:980px;margin:25px 0 28px;font:600 clamp(52px,5.4vw,82px)/1.04 var(--display);letter-spacing:-.055em}.hero h1 small{display:block;margin-bottom:22px;color:#d9ded9;font:500 clamp(17px,1.7vw,25px)/1.2 'Noto Sans SC',sans-serif;letter-spacing:.01em}.hero h1>span{display:block;white-space:nowrap}.hero-summary{max-width:560px;margin:0;color:#c1c9c2;font-size:16px;line-height:1.85}.hero-actions{display:flex;gap:12px;margin-top:38px}.button{min-height:52px;padding:0 20px;display:inline-flex;align-items:center;justify-content:center;gap:34px;border:1px solid transparent;font-weight:600;font-size:13px;transition:transform .2s,background .2s,border-color .2s}.button:hover{transform:translateY(-2px)}.button-primary{background:var(--home-green);color:#102013}.button-secondary{border-color:rgba(255,255,255,.36);color:white;background:rgba(8,14,11,.28)}.field-route{position:absolute;right:5%;top:16%;width:min(42vw,650px);height:58%;pointer-events:none;opacity:.82}.field-route svg{width:100%;height:100%;overflow:visible}.route-halo,.route-line{fill:none;stroke-linecap:round}.route-halo{stroke:rgba(196,235,119,.18);stroke-width:13}.route-line{stroke:#c3e67c;stroke-width:2;stroke-dasharray:800;stroke-dashoffset:800;animation:draw-route 2.2s .5s ease-out forwards}.route-points{fill:#142018;stroke:#c3e67c;stroke-width:2;opacity:0;animation:route-points .5s 2.2s forwards}.route-note{position:absolute;padding:6px 9px;background:rgba(9,15,12,.82);border:1px solid rgba(195,230,124,.4);font-size:9px;color:#dbe5d6;letter-spacing:.08em}.route-start{left:5%;bottom:3%}.route-focus{right:4%;top:2%}.scroll-cue{position:absolute;left:50%;bottom:28px;transform:translateX(-50%);display:flex;align-items:center;gap:10px;color:#aab4ac;font-size:9px;letter-spacing:.13em}.scroll-cue span{width:1px;height:30px;background:linear-gradient(var(--home-green),transparent)}.section{padding:130px max(32px,calc((100vw - 1376px)/2));border-top:1px solid rgba(235,241,232,.06)}.section-index{margin:0 0 24px;color:#8f9c92;font:500 10px var(--mono);letter-spacing:.16em}.section-intro{display:grid;grid-template-columns:150px minmax(0,1.2fr) minmax(290px,.65fr);gap:50px;align-items:end}.section-intro .section-index{align-self:start}.section h2,.product-preview h2,.final-cta h2{margin:0;font:600 clamp(38px,4.2vw,64px)/1.08 var(--display);letter-spacing:-.045em}.section-intro>p:last-child,.preview-heading>p,.workflow-copy>p:last-child{margin:0;color:var(--home-muted);line-height:1.9;font-size:14px}.capabilities{background:linear-gradient(180deg,var(--home-bg),var(--home-panel))}.capability-list{display:grid;grid-template-columns:repeat(4,1fr);margin-top:90px;border-top:1px solid var(--home-line)}.capability-list article{min-height:350px;padding:28px 28px 30px 0;border-right:1px solid var(--home-line);position:relative;transition:background .25s,transform .25s}.capability-list article:hover{background:rgba(255,255,255,.018);transform:translateY(-4px)}.capability-list article+article{padding-left:28px}.capability-list article:last-child{border-right:0}.item-number{color:#6f7d73;font:10px var(--mono)}.line-icon{width:42px;height:42px;margin:64px 0 28px;color:var(--home-green)}.line-icon :deep(svg){width:100%;height:100%;fill:none;stroke:currentColor;stroke-width:1.35;stroke-linecap:round;stroke-linejoin:round}.capability-list h3{margin:0 0 16px;font:600 19px var(--display)}.capability-list p{margin:0;color:#909d93;font-size:13px;line-height:1.8}.workflow{display:grid;grid-template-columns:.78fr 1.22fr;gap:12vw;background:linear-gradient(135deg,var(--home-panel),#0a120e);color:var(--home-text)}.workflow-copy>p:last-child{max-width:470px;margin-top:30px;color:var(--home-muted)}.workflow-steps{list-style:none;margin:0;padding:0;border-top:1px solid var(--home-line)}.workflow-steps li{display:grid;grid-template-columns:48px 1fr 24px;gap:18px;align-items:center;min-height:116px;border-bottom:1px solid var(--home-line);transition:padding-left .25s,background .25s}.workflow-steps li:hover{padding-left:12px;background:rgba(255,255,255,.018)}.workflow-steps>li>span{color:#718077;font:10px var(--mono)}.workflow-steps h3{margin:0 0 7px;font:600 18px var(--display)}.workflow-steps p{margin:0;color:#8f9c93;font-size:12px}.workflow-steps svg{fill:none;stroke:#7d8d82;stroke-width:1.3}.product-preview{padding:130px max(32px,calc((100vw - 1376px)/2)) 150px;background:linear-gradient(180deg,#0a120e,var(--home-panel-2));border-top:1px solid rgba(235,241,232,.06)}.preview-heading{display:grid;grid-template-columns:1.15fr .55fr;gap:90px;align-items:end}.preview-heading>p{max-width:430px}.preview-frame{margin-top:70px;border:1px solid rgba(230,237,228,.17);background:#131e18;box-shadow:0 34px 90px rgba(0,0,0,.3);color:#e8eee8}.preview-bar{height:48px;padding:0 18px;display:flex;align-items:center;gap:28px;background:#17241c;color:#9eaaa2;font:9px var(--mono);letter-spacing:.08em;border-bottom:1px solid var(--home-line)}.preview-brand{color:#dce4dc;font:600 13px var(--display)}.preview-bar i{width:7px;height:7px;border-radius:50%;background:#93bd57;margin-left:auto}.preview-body{display:grid;grid-template-columns:64px 1fr;min-height:570px}.preview-nav{background:#101a14;padding-top:28px;display:flex;align-items:center;flex-direction:column;gap:28px;border-right:1px solid var(--home-line)}.preview-nav b,.preview-nav span{display:block;width:19px;height:19px;border:1px solid #536459}.preview-nav b{background:#a9d35e;border-color:#a9d35e}.preview-canvas{padding:34px;background:radial-gradient(circle at 28% 55%,rgba(80,121,75,.1),transparent 36%)}.preview-title-row{display:flex;justify-content:space-between;align-items:center;margin-bottom:26px}.preview-title-row small,.preview-title-row strong{display:block}.preview-title-row small{color:#768179;font-size:9px}.preview-title-row strong{margin-top:6px;font:600 24px var(--display)}.preview-title-row>span{padding:7px 10px;background:rgba(169,211,94,.12);color:#bddd84;font-size:9px}.preview-grid{display:grid;grid-template-columns:1.45fr .55fr;gap:14px}.map-panel,.records-panel{border:1px solid rgba(220,231,220,.12);background:#18231d}.map-panel{position:relative;min-height:430px;overflow:hidden;color:rgba(169,211,94,.07)}.map-panel svg{width:100%;height:100%}.field-shape{fill:rgba(111,149,83,.12);stroke:rgba(137,171,115,.3);stroke-width:2}.map-route{fill:none;stroke:#a9d35e;stroke-width:4;stroke-linecap:round}.map-points{fill:#18231d;stroke:#b6dd70;stroke-width:3}.map-caption{position:absolute;left:18px;bottom:18px;padding:8px 10px;background:#0d1711;color:#dce4dc;font-size:9px}.records-panel{padding:18px}.record-head{display:flex;justify-content:space-between;padding-bottom:18px;border-bottom:1px solid rgba(220,231,220,.12)}.record-head b{font-size:12px}.record-head span{color:#87918a;font-size:8px}.record-row{display:grid;grid-template-columns:8px 1fr auto;gap:10px;align-items:center;padding:19px 0;border-bottom:1px solid rgba(220,231,220,.1)}.record-row>span{width:7px;height:7px;border-radius:50%;background:#87b567}.record-row>span.amber{background:#c79843}.record-row>span.blue{background:#698692}.record-row b,.record-row small{display:block}.record-row b{font-size:10px}.record-row small{margin-top:5px;color:#87918a;font-size:8px}.record-row i{font:normal 8px var(--mono);color:#8d9c92}.outcomes{background:linear-gradient(180deg,var(--home-panel-2),#0b140f);color:var(--home-text)}.outcomes-heading{display:grid;grid-template-columns:150px 1fr;gap:50px}.outcome-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:82px}.outcome-grid article{background:rgba(255,255,255,.025);border:1px solid rgba(235,241,232,.1);padding:34px;min-height:350px;transition:transform .25s,border-color .25s}.outcome-grid article:hover{transform:translateY(-5px);border-color:rgba(169,211,94,.32)}.outcome-visual{position:relative;height:145px;margin-bottom:46px;border-bottom:1px solid #405047}.outcome-visual span{position:absolute;left:9%;right:9%;bottom:25px;height:1px;background:#65756b;transform:rotate(-8deg)}.outcome-visual i,.outcome-visual b{position:absolute;width:12px;height:12px;border:2px solid #86a476;border-radius:50%;bottom:38px}.outcome-visual i{left:22%}.outcome-visual b{right:21%;bottom:58px;background:#a9d35e}.outcome-grid article:nth-child(2) .outcome-visual span{height:72px;left:18%;right:18%;bottom:20px;border:1px solid #4d5e53;background:repeating-linear-gradient(90deg,transparent 0 26px,rgba(169,211,94,.08) 26px 27px);transform:none}.outcome-grid article:nth-child(3) .outcome-visual span{height:70px;left:12%;right:12%;bottom:22px;background:none;border-left:1px solid #526359;border-bottom:1px solid #526359;transform:none}.outcome-grid h3{margin:0 0 13px;font:600 20px var(--display)}.outcome-grid p{margin:0;color:#8f9b93;font-size:13px;line-height:1.8}.final-cta{padding:120px max(32px,calc((100vw - 1376px)/2));background:linear-gradient(135deg,#173022,#102119);border-top:1px solid rgba(235,241,232,.08);display:flex;align-items:end;justify-content:space-between;gap:50px}.final-cta .section-index{color:#aabaad}.button-light{background:#eef3e8;color:#183025;min-width:180px}.site-footer{padding:34px max(32px,calc((100vw - 1376px)/2));display:grid;grid-template-columns:1fr 1fr 1fr;align-items:center;border-top:1px solid var(--home-line);background:#080e0b;color:#7f8c83;font-size:10px}.footer-brand b,.footer-brand span{display:block}.footer-brand b{color:#dbe2dc;font:600 15px var(--display)}.footer-brand span{margin-top:5px}.site-footer p{text-align:center}.site-footer>div:last-child{display:flex;justify-content:flex-end;gap:24px}.reveal-section{opacity:0;transform:translateY(26px);transition:opacity .7s ease,transform .7s ease}.reveal-section.is-visible{opacity:1;transform:none}.reveal-section .capability-list article,.reveal-section .workflow-steps li,.reveal-section .outcome-grid article{opacity:0;transform:translateY(18px)}.reveal-section.is-visible .capability-list article,.reveal-section.is-visible .workflow-steps li,.reveal-section.is-visible .outcome-grid article{opacity:1;transform:none;transition:opacity .55s ease,transform .55s ease,border-color .25s,background .25s}.reveal-section.is-visible :is(.capability-list article,.workflow-steps li,.outcome-grid article):nth-child(2){transition-delay:.08s}.reveal-section.is-visible :is(.capability-list article,.workflow-steps li,.outcome-grid article):nth-child(3){transition-delay:.16s}.reveal-section.is-visible :is(.capability-list article,.workflow-steps li,.outcome-grid article):nth-child(4){transition-delay:.24s}@keyframes hero-settle{from{opacity:.72;transform:scale(1.035)}to{opacity:1;transform:scale(1.012)}}@keyframes draw-route{to{stroke-dashoffset:0}}@keyframes route-points{to{opacity:1}}
@media(max-width:1050px){.nav-links{gap:18px}.section-intro{grid-template-columns:1fr 1fr}.section-intro .section-index{grid-column:1/-1}.capability-list{grid-template-columns:1fr 1fr}.capability-list article:nth-child(2){border-right:0}.capability-list article:nth-child(-n+2){border-bottom:1px solid var(--home-line)}.workflow{gap:60px}.preview-heading{grid-template-columns:1fr 1fr}.preview-grid{grid-template-columns:1fr}.records-panel{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.record-head{grid-column:1/-1}.record-row{border:0}.outcome-grid article{padding:26px}.field-route{right:0;width:50vw}}
@media(max-width:760px){.site-header{height:68px}.nav-shell{width:calc(100% - 36px)}.brand small{font-size:8px}.menu-toggle{display:block}.site-header.menu-open .menu-toggle span:first-child{transform:translateY(3px) rotate(45deg)}.site-header.menu-open .menu-toggle span:last-child{transform:translateY(-3px) rotate(-45deg)}.nav-links{position:absolute;left:0;right:0;top:67px;padding:18px;display:none;align-items:stretch;flex-direction:column;gap:0;background:rgba(9,15,12,.97);border-bottom:1px solid var(--home-line)}.nav-links.open{display:flex}.nav-links>a{padding:14px 8px;border-bottom:1px solid rgba(255,255,255,.08)}.nav-action{margin-top:10px;justify-content:space-between;border:1px solid rgba(236,242,232,.28)!important}.hero{min-height:760px;align-items:flex-end;padding-bottom:96px}.hero-media img{object-position:63% center}.hero-shade{background:linear-gradient(90deg,rgba(5,10,8,.94),rgba(5,10,8,.43)),linear-gradient(0deg,rgba(5,10,8,.94) 0%,rgba(5,10,8,.15) 62%)}.hero-content{width:calc(100% - 36px);padding:0}.hero h1{font-size:clamp(44px,12vw,62px);max-width:520px}.hero h1>span{white-space:normal}.hero h1 small{font-size:15px;margin-bottom:18px}.hero-summary{font-size:14px;max-width:340px}.hero-actions{align-items:stretch;flex-direction:column;width:min(100%,330px)}.button{justify-content:space-between}.field-route{right:-22%;top:16%;width:90vw;height:43%;opacity:.62}.route-note{display:none}.scroll-cue{display:none}.section,.product-preview{padding:88px 18px}.section-intro,.workflow,.preview-heading,.outcomes-heading{grid-template-columns:1fr;gap:28px}.section-intro .section-index{grid-column:auto}.section h2,.product-preview h2,.final-cta h2{font-size:clamp(38px,11vw,54px)}.capability-list{grid-template-columns:1fr;margin-top:55px}.capability-list article,.capability-list article+article{min-height:auto;padding:26px 0 34px;border-right:0;border-bottom:1px solid var(--home-line)}.line-icon{margin:38px 0 22px}.workflow-copy>p:last-child{margin-top:22px}.workflow-steps li{min-height:104px;grid-template-columns:34px 1fr 20px}.preview-frame{margin-top:45px}.preview-body{grid-template-columns:1fr;min-height:0}.preview-nav{display:none}.preview-canvas{padding:16px}.preview-title-row strong{font-size:19px}.map-panel{min-height:330px}.records-panel{display:block}.outcome-grid{grid-template-columns:1fr;margin-top:50px}.outcome-grid article{min-height:300px}.final-cta{padding:82px 18px;align-items:stretch;flex-direction:column}.button-light{align-self:flex-start}.site-footer{padding:32px 18px;grid-template-columns:1fr;gap:22px}.site-footer p{text-align:left;margin:0}.site-footer>div:last-child{justify-content:flex-start}.hero-grain{display:none}}
@media(max-width:390px){.brand-symbol{width:30px;height:30px}.brand b{font-size:13px}.hero h1{font-size:44px}.hero-content{width:calc(100% - 32px)}.hero-actions{width:100%}.map-panel{min-height:280px}.preview-bar{gap:12px}.preview-bar span:nth-child(2){display:none}}
@media(prefers-reduced-motion:reduce){:global(html.route-home){scroll-behavior:auto}.hero-media img{animation:none}.route-line{stroke-dashoffset:0;animation:none}.route-points{opacity:1;animation:none}.reveal-section,.reveal-section .capability-list article,.reveal-section .workflow-steps li,.reveal-section .outcome-grid article{opacity:1;transform:none;transition:none}.button{transition:none}}
.hero-content{padding-top:0;transform:translateY(-5vh)}
.hero-label{opacity:0;transform:translateY(10px);animation:hero-copy-in .42s .08s ease-out forwards;color:#c8d2ca;letter-spacing:.18em}
.hero h1 small{opacity:0;transform:translateY(12px);animation:hero-copy-in .48s .18s ease-out forwards;margin-bottom:18px;color:#9eaaa2;font:500 10px/1.2 var(--mono);letter-spacing:.18em}
.hero h1>span{white-space:normal;max-width:820px;clip-path:inset(0 0 100% 0);transform:translateY(16px);animation:hero-title-reveal .7s .24s cubic-bezier(.22,.75,.2,1) forwards}
.hero-summary{opacity:0;transform:translateY(12px);animation:hero-copy-in .5s .55s ease-out forwards}
.hero-actions{opacity:0;transform:translateY(12px);animation:hero-copy-in .5s .68s ease-out forwards}
.route-points{animation:hero-copy-in .45s .52s ease-out forwards}
@keyframes hero-copy-in{to{opacity:1;transform:none}}
@keyframes hero-title-reveal{to{clip-path:inset(0 0 0 0);transform:none}}
@media(max-width:760px){.hero-content{transform:none}.hero h1 small{font-size:9px}.hero-summary br{display:none}}
@media(prefers-reduced-motion:reduce){.hero-label,.hero h1 small,.hero h1>span,.hero-summary,.hero-actions,.route-points{opacity:1;transform:none;clip-path:none;animation:none}}
</style>
<style scoped>
.nav-shell,.hero-content{width:min(100% - 96px,1320px)}.brand b{font-size:20px}.brand small{font-size:11px;letter-spacing:0}.brand-symbol{border:0;border-radius:10px;background:#b7de6112;width:38px;height:38px}.nav-links{font-size:14px;gap:32px}.nav-action{border-radius:8px;padding:9px 16px}.hero{min-height:clamp(680px,94dvh,960px)}.hero-content{transform:none;padding-top:72px}.hero-label{font:500 14px/1.5 var(--display);letter-spacing:.12em;margin:0 0 28px;color:#c6d6c8}.hero h1{margin:0 0 30px;font:600 clamp(52px,6.3vw,96px)/1.15 var(--display);letter-spacing:-.055em;max-width:850px}.hero h1>span{white-space:normal;clip-path:none;transform:none;animation:hero-copy-in .7s ease-out both}.hero h1>span:nth-child(2){color:#c3dbb2;animation-delay:.1s}.hero-summary{font-size:clamp(14px,1.2vw,17px);line-height:1.95;color:#bccdbf;max-width:540px}.hero-actions{margin-top:36px;gap:14px}.button{min-height:50px;font-size:14px;padding:0 22px;border-radius:8px;gap:28px}.hero-shade{background:linear-gradient(90deg,#07110df2 0%,#07110dd9 27%,#07110d66 58%,#07110d15 87%),linear-gradient(0deg,var(--home-bg),transparent 27%)}.hero-grain{opacity:.055}.scroll-cue{font-size:11px;bottom:24px}.section,.product-preview{padding:96px max(48px,calc((100vw - 1320px)/2))}.section-index{font:500 13px var(--display);letter-spacing:.08em;margin-bottom:18px;color:#a5b6a7}.section h2,.product-preview h2,.final-cta h2{font-size:clamp(30px,3.4vw,48px);line-height:1.35;letter-spacing:-.035em}.section-intro{grid-template-columns:110px minmax(0,1fr) minmax(240px,.75fr);gap:32px;align-items:center}.section-intro>p:last-child,.preview-heading>p,.workflow-copy>p:last-child{font-size:14px;color:#a7b8aa}.capability-list{margin-top:52px;gap:16px;border:0}.capability-list article,.capability-list article+article{padding:24px;min-height:260px;border:1px solid var(--home-line);border-radius:12px;background:#ffffff02}.capability-list article:last-child{border:1px solid var(--home-line)}.line-icon{margin:32px 0 22px}.capability-list h3{font-size:20px}.capability-list p{font-size:14px;color:#a2b2a5}.item-number{font-size:11px}.workflow{gap:7vw;grid-template-columns:1fr 1.25fr}.workflow-steps li{min-height:106px}.workflow-steps h3{font-size:18px}.workflow-steps p{font-size:13px;color:#a2b2a5;line-height:1.7}.workflow-steps>li>span{font-size:12px}.preview-heading{gap:48px}.preview-frame{margin-top:42px;border-radius:14px;overflow:hidden}.preview-title-row strong{font-size:18px}.record-head{font-size:13px}.record-row b{font-size:13px}.record-row small{font-size:11px}.final-cta{padding:64px max(48px,calc((100vw - 1320px)/2));gap:32px}.final-cta h2{font-size:clamp(28px,3vw,42px)}.site-footer{padding:32px max(48px,calc((100vw - 1320px)/2))}.site-footer p{font-size:12px}.reveal-section{transform:translateY(18px);transition:opacity .65s ease,transform .65s ease}
@media(max-width:1000px){.section-intro{grid-template-columns:1fr 1fr;gap:18px}.section-intro .section-index{grid-column:1/-1;margin-bottom:0}.capability-list{grid-template-columns:repeat(2,1fr)}.nav-links{gap:22px;font-size:13px}.hero h1{font-size:clamp(48px,7.5vw,76px)}}
@media(max-width:760px){.nav-shell,.hero-content{width:calc(100% - 40px)}.hero{min-height:720px;min-height:92svh}.hero-content{padding-top:88px;transform:none}.hero h1{font-size:clamp(42px,8.5vw,64px);margin-bottom:24px}.hero-label{font-size:12px;margin-bottom:22px}.hero-summary{font-size:14px}.hero-shade{background:linear-gradient(90deg,#07110de6,#07110d73),linear-gradient(0deg,var(--home-bg),transparent 40%)}.section,.product-preview{padding:64px 20px}.section-intro,.preview-heading,.workflow{grid-template-columns:1fr;gap:24px}.capability-list{gap:12px;margin-top:32px}.capability-list article,.capability-list article+article{padding:20px;min-height:230px}.line-icon{margin:26px 0 20px}.capability-list h3{font-size:17px}.capability-list p{font-size:13px}.final-cta{padding:48px 20px;flex-direction:column;align-items:flex-start}.site-footer{padding:28px 20px;gap:18px}.hero-actions{gap:10px}.button{font-size:13px;padding:0 18px;gap:18px}.nav-links{font-size:14px}.preview-frame{margin-top:30px}}
@media(max-width:420px){.hero h1{font-size:42px}.hero-label{letter-spacing:.06em}.capability-list{grid-template-columns:1fr}.capability-list article,.capability-list article+article{min-height:0}.line-icon{margin:20px 0}.hero-actions{flex-wrap:wrap}.hero-summary br{display:none}}
@media(max-width:420px){.hero-summary br{display:initial}}
.hero h1>span{
  --title-color:#f1f3ed;
  --title-glint:#fff;
  color:var(--title-color);
  animation:hero-heading-enter .95s .12s cubic-bezier(.22,.75,.2,1) backwards;
}
.hero h1>span:nth-child(2){--title-color:#c3dbb2;--title-glint:#f5ffe9;color:var(--title-color);animation-delay:.3s}
@keyframes hero-heading-enter{
  from{opacity:0;transform:translateY(24px);filter:blur(5px)}
  to{opacity:1;transform:none;filter:blur(0)}
}
@supports (background-clip:text) or (-webkit-background-clip:text){
  .hero h1>span{
    background-image:linear-gradient(110deg,var(--title-color) 40%,var(--title-glint) 50%,var(--title-color) 60%);
    background-size:250% 100%;
    background-position:100% 0;
    background-clip:text;
    -webkit-background-clip:text;
    color:transparent;
    animation:hero-heading-enter .95s .12s cubic-bezier(.22,.75,.2,1) backwards,hero-heading-sheen 7s 1.2s ease-in-out infinite;
  }
  .hero h1>span:nth-child(2){color:transparent;animation-delay:.3s,1.4s}
}
@keyframes hero-heading-sheen{
  0%,20%{background-position:100% 0}
  60%,100%{background-position:0% 0}
}
@media(prefers-reduced-motion:reduce){.hero h1>span,.hero h1>span:nth-child(2){animation:none;background-image:none;color:var(--title-color);opacity:1;transform:none;filter:none}.reveal-section{transform:none}}
</style>
