"""StockManager — 미국 주식 장기/스윙 투자 관리 & 밸류에이션 워크벤치.

실행:  streamlit run app.py
기능: 워치리스트 대시보드 · 스코어카드(엑셀 재현) · Live 밸류에이션 ·
      정/역 DCF · 촉매(뉴스) 반영 추적 · 매매기록/손익.
"""
from __future__ import annotations

import datetime as dt
import time
import uuid

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import chart as CH
import export as EXP
import guides as GD
import market as MK
import narrative as NA
import scenarios as SN
import scorecard as SC
import storage as ST
import valuation as V

try:
    from lightweight_charts_v5 import lightweight_charts_v5_component
    _TV_AVAILABLE = True
except ImportError:  # 미설치 환경에선 plotly 차트로만 동작(폴백)
    _TV_AVAILABLE = False

st.set_page_config(page_title="StockManager", page_icon="📈", layout="wide")

# ─── Purple × Dark 디자인 시스템 (순수 CSS — JS/컴포넌트 불필요) ───────────────
# 팔레트(다크 서피스 #0D0A14 기준 대비·CVD 검증 완료):
#   accent  #A78BFA / deep #7C3AED   up #00E68A   down #FF5252
# 애니메이션: 카드 페이드인, hover 리프트+글로우, 그라디언트 타이틀, LIVE 펄스.
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&display=swap');

:root {
    --sm-accent: #A78BFA;
    --sm-accent-deep: #7C3AED;
    --sm-up: #00E68A;
    --sm-down: #FF5252;
    --sm-card: rgba(167, 139, 250, 0.05);
    --sm-border: rgba(167, 139, 250, 0.16);
}

/* ── 타이틀: 퍼플 그라디언트 + 은은한 흐름 ── */
h1 {
    font-family: 'Space Grotesk', sans-serif !important;
    background: linear-gradient(120deg, #EDEBF5 20%, var(--sm-accent) 45%,
                                #6EE7F9 70%, #EDEBF5 95%);
    background-size: 260% 100%;
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
    animation: sm-gradient-flow 9s ease-in-out infinite;
}
h2, h3 { font-family: 'Space Grotesk', sans-serif !important; }

/* ── metric 카드: 글래스 카드 + 진입 애니메이션 + hover 리프트 ── */
div[data-testid="stMetric"] {
    background: var(--sm-card);
    border: 1px solid var(--sm-border);
    border-radius: 14px;
    padding: 12px 14px;
    animation: sm-rise-in 0.45s cubic-bezier(0.22, 1, 0.36, 1) both;
    transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}
div[data-testid="stMetric"]:hover {
    transform: translateY(-3px);
    border-color: rgba(167, 139, 250, 0.45);
    box-shadow: 0 8px 26px rgba(124, 58, 237, 0.22);
}
/* 카드 순차 등장(스태거) */
div[data-testid="column"]:nth-of-type(2) div[data-testid="stMetric"] { animation-delay: 0.05s; }
div[data-testid="column"]:nth-of-type(3) div[data-testid="stMetric"] { animation-delay: 0.10s; }
div[data-testid="column"]:nth-of-type(4) div[data-testid="stMetric"] { animation-delay: 0.15s; }

/* ── 표·익스팬더·탭 패널 진입 ── */
div[data-testid="stDataFrame"], div[data-testid="stExpander"] {
    animation: sm-rise-in 0.5s cubic-bezier(0.22, 1, 0.36, 1) both;
}
div[data-testid="stExpander"] {
    border: 1px solid var(--sm-border);
    border-radius: 12px;
}

/* ── 탭: 퍼플 언더라인 글로우 + 살짝 튀는 클릭감 ── */
button[data-baseweb="tab"] {
    transition: color 0.15s ease, transform 0.25s cubic-bezier(.34,1.56,.64,1);
}
button[data-baseweb="tab"]:active { transform: scale(0.95); }
button[data-baseweb="tab"][aria-selected="true"] {
    text-shadow: 0 0 18px rgba(167, 139, 250, 0.65);
}
div[data-baseweb="tab-highlight"] {
    background: linear-gradient(90deg, var(--sm-accent-deep), var(--sm-accent)) !important;
    height: 3px !important;
    border-radius: 3px;
    box-shadow: 0 0 12px rgba(167, 139, 250, 0.55);
    transition: left 0.3s cubic-bezier(.34,1.56,.64,1), width 0.3s cubic-bezier(.34,1.56,.64,1);
}

/* ── 버튼: 퍼플 그라디언트(primary) + 통통 튀는 hover/클릭 ── */
button[kind="primary"], button[data-testid="stBaseButton-primary"] {
    background: linear-gradient(135deg, var(--sm-accent-deep), #9F5BFF) !important;
    border: none !important;
    transition: transform 0.28s cubic-bezier(.34,1.56,.64,1), box-shadow 0.2s ease, filter 0.18s ease;
}
button[kind="primary"]:hover, button[data-testid="stBaseButton-primary"]:hover {
    transform: translateY(-2px) scale(1.035);
    filter: brightness(1.12);
    box-shadow: 0 4px 20px rgba(124, 58, 237, 0.45);
}
button[kind="secondary"], button[data-testid="stBaseButton-secondary"] {
    border-color: var(--sm-border) !important;
    transition: transform 0.28s cubic-bezier(.34,1.56,.64,1), box-shadow 0.2s ease, border-color 0.18s ease;
}
button[kind="secondary"]:hover, button[data-testid="stBaseButton-secondary"]:hover {
    transform: translateY(-2px) scale(1.03);
    border-color: rgba(167, 139, 250, 0.55) !important;
    box-shadow: 0 3px 14px rgba(124, 58, 237, 0.28);
}
button[kind="primary"]:active, button[data-testid="stBaseButton-primary"]:active,
button[kind="secondary"]:active, button[data-testid="stBaseButton-secondary"]:active {
    transform: scale(0.94) !important;
    transition: transform 0.08s ease !important;
}

/* ── 버튼 공통(꾹 눌림): 종류 상관없이 모든 버튼(다운로드/익스팬더/사이드바 접기 등 포함) ── */
button {
    transition: transform 0.25s cubic-bezier(.34,1.56,.64,1);
}
button:active {
    transform: scale(0.93) !important;
    transition: transform 0.08s ease !important;
}

/* ── 사이드바: 미묘한 퍼플 그라디언트 배경 ── */
section[data-testid="stSidebar"] > div {
    background: linear-gradient(180deg, #131022 0%, #0D0A14 45%);
}

/* ── 우주 배경: 은은한 성운 + 반짝이는 별 + 떠다니는 행성 ── */
.stApp {
    background: radial-gradient(ellipse at 15% -8%, rgba(124,58,237,0.18), transparent 55%),
                radial-gradient(ellipse at 105% 8%, rgba(56,189,248,0.10), transparent 50%),
                radial-gradient(ellipse at 45% 105%, rgba(167,139,250,0.09), transparent 60%),
                #0D0A14;
}
.stApp::before {
    content: ""; position: fixed; inset: 0; z-index: -2; pointer-events: none;
    background-image:
        radial-gradient(1.6px 1.6px at 20% 30%, rgba(255,255,255,0.85), transparent),
        radial-gradient(1px 1px at 60% 72%, rgba(255,255,255,0.6), transparent),
        radial-gradient(1.6px 1.6px at 82% 18%, rgba(167,139,250,0.9), transparent),
        radial-gradient(1px 1px at 33% 88%, rgba(255,255,255,0.5), transparent),
        radial-gradient(1.6px 1.6px at 92% 62%, rgba(110,231,249,0.85), transparent),
        radial-gradient(1px 1px at 8% 62%, rgba(255,255,255,0.5), transparent),
        radial-gradient(1.6px 1.6px at 50% 42%, rgba(255,255,255,0.7), transparent),
        radial-gradient(1px 1px at 70% 95%, rgba(255,255,255,0.45), transparent);
    background-repeat: repeat; background-size: 360px 360px;
    animation: sm-twinkle 4.5s ease-in-out infinite alternate;
}
.stApp::after {
    content: ""; position: fixed; inset: 0; z-index: -1; pointer-events: none;
    background:
        radial-gradient(circle at 88% 22%, rgba(167,139,250,0.45),
                        rgba(124,58,237,0.16) 42%, transparent 62%),
        radial-gradient(circle at 38% 96%, rgba(56,189,248,0.30),
                        rgba(56,189,248,0.08) 45%, transparent 65%);
    background-size: 60vw 60vw, 34vw 34vw;
    background-repeat: no-repeat;
    background-position: 88% 22%, 38% 96%;
    filter: blur(2px);
    animation: sm-planet-drift 26s ease-in-out infinite;
}
@keyframes sm-twinkle {
    from { opacity: 0.5; }
    to   { opacity: 1; }
}
@keyframes sm-planet-drift {
    0%, 100%   { transform: translate(0, 0) scale(1); }
    50%        { transform: translate(-2.5%, 3%) scale(1.04); }
}

/* ── progress bar: 그라디언트 + 부드러운 채움 ── */
div[role="progressbar"] > div > div {
    background: linear-gradient(90deg, var(--sm-accent-deep), var(--sm-accent)) !important;
}
div[role="progressbar"] > div { transition: width 0.6s ease; }

/* ── 스크롤바 ── */
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-thumb {
    background: rgba(167, 139, 250, 0.25);
    border-radius: 8px;
}
::-webkit-scrollbar-thumb:hover { background: rgba(167, 139, 250, 0.45); }

/* ── Ticker 입력창: 명확한 박스 경계선 ── */
div[data-testid="stTextInputRootElement"]:has(input[aria-label="Ticker"]) {
    border: 1.5px solid rgba(167, 139, 250, 0.5) !important;
    border-radius: 10px !important;
    background: rgba(167, 139, 250, 0.05);
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
div[data-testid="stTextInputRootElement"]:has(input[aria-label="Ticker"]):focus-within {
    border-color: var(--sm-accent) !important;
    box-shadow: 0 0 0 3px rgba(167, 139, 250, 0.18);
}

/* ── 사이드바 지수 스트립 ── */
.sm-indices {
    display: flex; flex-direction: column; gap: 6px;
    padding: 10px 12px;
    border: 1px solid var(--sm-border);
    border-radius: 12px;
    background: var(--sm-card);
    animation: sm-rise-in 0.5s ease both;
}
.sm-indices .row { display: flex; justify-content: space-between; align-items: baseline; }
.sm-indices .name { font-size: 0.72rem; letter-spacing: 0.06em; opacity: 0.75; }
.sm-indices .val { font-size: 0.85rem; font-weight: 600; font-variant-numeric: tabular-nums; }
.sm-indices .up   { color: var(--sm-up); }
.sm-indices .down { color: var(--sm-down); }
.sm-live-dot {
    display: inline-block; width: 7px; height: 7px; border-radius: 50%;
    background: var(--sm-up); margin-right: 6px;
    animation: sm-pulse 1.6s ease-in-out infinite;
}

@keyframes sm-rise-in {
    0%   { opacity: 0; transform: translateY(10px) scale(0.96); }
    65%  { opacity: 1; transform: translateY(-2px) scale(1.012); }
    100% { transform: translateY(0) scale(1); }
}
@keyframes sm-gradient-flow {
    0%, 100% { background-position: 0% 50%; }
    50%      { background-position: 100% 50%; }
}
@keyframes sm-pulse {
    0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(0, 230, 138, 0.55); }
    55%      { opacity: 0.55; box-shadow: 0 0 0 6px rgba(0, 230, 138, 0); }
}

/* 모션 최소화 설정 존중(접근성) */
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation: none !important; transition: none !important; }
}
</style>
""", unsafe_allow_html=True)

# ─── BGM: 우주 분위기 절차적 생성 음악 (Web Audio API, 외부 파일/저작권 이슈 없음) ───
# iframe 안의 순수 JS로 버튼 클릭(=사용자 제스처)에서만 오디오를 시작하므로 브라우저
# 자동재생 정책과 충돌하지 않는다. Streamlit이 매 rerun마다 이 컴포넌트를 다시 그려도
# HTML 내용이 그대로면 프론트엔드가 동일 iframe을 재사용해 재생이 끊기지 않는다.
_BGM_HTML = """
<div style="font-family:'Space Grotesk',sans-serif; color:#EDEBF5; background:transparent;">
  <div style="display:flex; gap:6px; margin-bottom:8px;">
    <button id="sm-btn-off" class="sm-bgm-btn active" onclick="smSetMode('off')">🔇 Off</button>
    <button id="sm-btn-calm" class="sm-bgm-btn" onclick="smSetMode('calm')">🌙 Calm</button>
    <button id="sm-btn-energetic" class="sm-bgm-btn" onclick="smSetMode('energetic')">⚡ Energetic</button>
  </div>
  <div style="display:flex; align-items:center; gap:8px;">
    <div class="sm-eq" id="sm-eq"><span></span><span></span><span></span><span></span></div>
    <input id="sm-vol" type="range" min="0" max="0.35" step="0.01" value="0.16"
           style="flex:1; accent-color:#A78BFA;">
  </div>
</div>
<style>
  .sm-bgm-btn {
    flex: 1; padding: 6px 4px; font-size: 0.72rem; font-weight: 600;
    color: #C9C4DB; background: rgba(167,139,250,0.07);
    border: 1px solid rgba(167,139,250,0.18); border-radius: 9px;
    cursor: pointer; transition: transform .25s cubic-bezier(.34,1.56,.64,1),
    background .18s ease, border-color .18s ease, color .18s ease;
  }
  .sm-bgm-btn:hover { transform: translateY(-1px) scale(1.04); border-color: rgba(167,139,250,0.5); }
  .sm-bgm-btn:active { transform: scale(0.93); }
  .sm-bgm-btn.active {
    background: linear-gradient(135deg, #7C3AED, #9F5BFF); color: #fff; border-color: transparent;
  }
  .sm-eq { display:flex; align-items:flex-end; gap:2px; height:16px; }
  .sm-eq span {
    width:3px; height:4px; background:#A78BFA; border-radius:2px;
    animation: sm-eq-bounce 1s ease-in-out infinite; animation-play-state: paused; opacity: 0.35;
  }
  .sm-eq.playing span { animation-play-state: running; opacity: 1; }
  .sm-eq span:nth-child(1){animation-duration:.8s} .sm-eq span:nth-child(2){animation-duration:1.1s}
  .sm-eq span:nth-child(3){animation-duration:.7s} .sm-eq span:nth-child(4){animation-duration:1.3s}
  @keyframes sm-eq-bounce { 0%,100%{height:4px} 50%{height:16px} }
</style>
<script>
(function() {
  const AC = window.AudioContext || window.webkitAudioContext;
  let ctx = null, master = null, timer = null;

  function ensureCtx() {
    if (!ctx) {
      ctx = new AC();
      master = ctx.createGain();
      master.gain.value = 0;
      master.connect(ctx.destination);
    }
    if (ctx.state === 'suspended') ctx.resume();
  }

  function vol() { return parseFloat(document.getElementById('sm-vol').value); }

  function note(freq, dur, type, gainVal, filterFreq) {
    const now = ctx.currentTime;
    const osc = ctx.createOscillator();
    osc.type = type; osc.frequency.value = freq;
    const g = ctx.createGain(); g.gain.value = 0;
    const f = ctx.createBiquadFilter(); f.type = 'lowpass'; f.frequency.value = filterFreq || 2200;
    osc.connect(f); f.connect(g); g.connect(master);
    g.gain.linearRampToValueAtTime(gainVal, now + 0.06);
    g.gain.exponentialRampToValueAtTime(0.0008, now + dur);
    osc.start(now); osc.stop(now + dur + 0.05);
  }

  function stopAll() {
    if (timer) { clearInterval(timer); timer = null; }
    if (master) master.gain.setTargetAtTime(0, ctx.currentTime, 0.5);
    document.getElementById('sm-eq').classList.remove('playing');
  }

  function startCalm() {
    ensureCtx();
    master.gain.setTargetAtTime(vol(), ctx.currentTime, 0.8);
    const scale = [130.81, 155.56, 174.61, 196.00, 233.08, 261.63];
    if (timer) clearInterval(timer);
    const play = () => {
      const f = scale[Math.floor(Math.random() * scale.length)];
      note(f, 3.4, 'sine', 0.85, 900);
      note(f * 2, 3.0, 'sine', 0.3, 1600);
      if (Math.random() < 0.35) note(f * 4, 1.8, 'triangle', 0.22, 3400);
    };
    play();
    timer = setInterval(play, 1900);
    document.getElementById('sm-eq').classList.add('playing');
  }

  function startEnergetic() {
    ensureCtx();
    master.gain.setTargetAtTime(vol(), ctx.currentTime, 0.3);
    const root = 110;
    const arp = [1, 1.2, 1.5, 2, 1.5, 1.2];
    if (timer) clearInterval(timer);
    let step = 0;
    timer = setInterval(() => {
      note(root, 0.14, 'square', 0.7, 700);
      if (step % 2 === 0) {
        const ratio = arp[(step / 2) % arp.length];
        note(root * 2 * ratio, 0.16, 'sawtooth', 0.4, 2400);
      }
      step++;
    }, 150);
    document.getElementById('sm-eq').classList.add('playing');
  }

  window.smSetMode = function(mode) {
    document.querySelectorAll('.sm-bgm-btn').forEach(b => b.classList.remove('active'));
    document.getElementById('sm-btn-' + mode).classList.add('active');
    if (mode === 'off') stopAll();
    else if (mode === 'calm') startCalm();
    else if (mode === 'energetic') startEnergetic();
  };

  document.getElementById('sm-vol').addEventListener('input', () => {
    if (master && ctx) master.gain.setTargetAtTime(vol(), ctx.currentTime, 0.1);
  });
})();
</script>
"""

# ─── 로그인/회원가입 성공 시 전체화면 로딩 연출 (순수 HTML/CSS/SVG — JS 불필요) ───
# 화성 느낌의 붉은 행성 + 별빛 우주 배경 위로, 로켓이 위아래로 지그재그 튀며 우상향하는
# 차트 라인을 따라 "슈우웅" 날아간다. SVG <animateMotion>(SMIL, 스크립트 없이 브라우저가
# 직접 실행 — rotate="auto"로 진행 방향에 맞춰 로켓이 기울어진다)으로 구현.
_CHART_PATH_D = ("M0,210 L60,120 L120,165 L180,60 L240,110 L300,-10 "
                  "L360,55 L420,-90 L470,-40 L500,-130")
_LOGIN_LOADING_HTML_TMPL = f"""
<div class="sm-loading-overlay %%CLS%%">
  <div class="sm-loading-planet"></div>
  <svg class="sm-loading-chart" viewBox="-20 -150 560 380" preserveAspectRatio="xMidYMid meet">
    <defs>
      <linearGradient id="sm-chart-grad" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0%" stop-color="#FF8A65"/>
        <stop offset="50%" stop-color="#A78BFA"/>
        <stop offset="100%" stop-color="#00E68A"/>
      </linearGradient>
      <marker id="sm-arrowhead" markerWidth="10" markerHeight="10" refX="3" refY="5" orient="auto">
        <path d="M0,0 L7,5 L0,10 Z" fill="#00E68A"/>
      </marker>
    </defs>
    <path d="{_CHART_PATH_D}" fill="none" stroke="url(#sm-chart-grad)"
          stroke-width="5.5" stroke-linecap="round" stroke-linejoin="round"
          pathLength="1000" class="sm-loading-path" marker-end="url(#sm-arrowhead)"/>
    <circle r="5" fill="#A78BFA" opacity="0.55" class="sm-loading-trail">
      <animateMotion dur="1.5s" repeatCount="indefinite" begin="-0.28s" path="{_CHART_PATH_D}"/>
    </circle>
    <circle r="4" fill="#EDEBF5" opacity="0.35" class="sm-loading-trail">
      <animateMotion dur="1.5s" repeatCount="indefinite" begin="-0.16s" path="{_CHART_PATH_D}"/>
    </circle>
    <text font-size="34" text-anchor="middle" dominant-baseline="middle" class="sm-loading-rocket">
      🚀
      <animateMotion dur="1.5s" repeatCount="indefinite" rotate="auto" path="{_CHART_PATH_D}"/>
    </text>
  </svg>
  <div class="sm-loading-text">
    <div class="sm-loading-title">LET'S GET RICH 🚀</div>
    <div class="sm-loading-sub">Launching your portfolio<span class="sm-loading-dot">.</span><span class="sm-loading-dot">.</span><span class="sm-loading-dot">.</span></div>
  </div>
</div>
<style>
  .sm-loading-overlay {{
      position: fixed; inset: 0; z-index: 99999;
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      background: radial-gradient(ellipse at 25% 15%, rgba(167,139,250,0.20), transparent 55%),
                  radial-gradient(ellipse at 82% 88%, rgba(255,111,74,0.14), transparent 55%),
                  #0A0812;
      overflow: hidden;
      animation: sm-loading-fadein 0.4s ease both;
  }}
  .sm-loading-overlay.sm-loading-out {{
      animation: sm-loading-fadeout 0.45s cubic-bezier(.4,0,1,1) both;
  }}
  .sm-loading-overlay::before {{
      content: ""; position: absolute; inset: 0; pointer-events: none;
      background-image:
          radial-gradient(1.6px 1.6px at 18% 24%, rgba(255,255,255,0.85), transparent),
          radial-gradient(1px 1px at 55% 68%, rgba(255,255,255,0.6), transparent),
          radial-gradient(1.6px 1.6px at 78% 15%, rgba(167,139,250,0.9), transparent),
          radial-gradient(1px 1px at 30% 82%, rgba(255,255,255,0.5), transparent),
          radial-gradient(1.6px 1.6px at 88% 55%, rgba(255,138,101,0.7), transparent),
          radial-gradient(1px 1px at 8% 55%, rgba(255,255,255,0.5), transparent);
      background-repeat: repeat; background-size: 300px 300px;
      animation: sm-loading-twinkle 3.2s ease-in-out infinite alternate;
  }}
  .sm-loading-planet {{
      position: absolute; top: 8%; right: 8%;
      width: 220px; height: 220px; border-radius: 50%;
      background: radial-gradient(circle at 35% 30%, #FFA679 0%, #C1502C 48%, #6E2410 78%, #3c1207 100%);
      box-shadow: 0 0 80px 14px rgba(255, 111, 74, 0.34), inset -18px -18px 40px rgba(0,0,0,0.4);
      animation: sm-loading-drift 5s ease-in-out infinite;
  }}
  .sm-loading-chart {{
      width: min(88vw, 760px); height: 320px; margin-bottom: 22px;
      filter: drop-shadow(0 0 14px rgba(167, 139, 250, 0.55));
  }}
  .sm-loading-path {{
      stroke-dasharray: 1000; stroke-dashoffset: 1000;
      animation: sm-loading-draw 1.5s cubic-bezier(.16,.8,.28,1) infinite;
  }}
  .sm-loading-rocket {{ filter: drop-shadow(0 0 8px rgba(255,166,121,0.85)); }}
  .sm-loading-text {{ text-align: center; }}
  .sm-loading-title {{
      font-family: 'Space Grotesk', sans-serif; color: #EDEBF5;
      font-size: 2rem; font-weight: 700; letter-spacing: 0.02em;
      text-shadow: 0 0 22px rgba(167, 139, 250, 0.65);
      animation: sm-loading-pulse 1.1s ease-in-out infinite;
  }}
  .sm-loading-sub {{
      font-family: 'Space Grotesk', sans-serif; color: #C9C4DB;
      font-size: 1.05rem; letter-spacing: 0.02em; margin-top: 6px;
  }}
  .sm-loading-dot {{ display: inline-block; opacity: 0; animation: sm-loading-dotblink 1.4s infinite; }}
  .sm-loading-dot:nth-child(2) {{ animation-delay: 0.25s; }}
  .sm-loading-dot:nth-child(3) {{ animation-delay: 0.5s; }}
  @keyframes sm-loading-fadein {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
  @keyframes sm-loading-fadeout {{
      from {{ opacity: 1; transform: scale(1); }}
      to   {{ opacity: 0; transform: scale(1.06); }}
  }}
  @keyframes sm-loading-twinkle {{ from {{ opacity: 0.5; }} to {{ opacity: 1; }} }}
  @keyframes sm-loading-drift {{
      0%, 100% {{ transform: translate(0, 0) scale(1); }}
      50%      {{ transform: translate(-3%, 4%) scale(1.04); }}
  }}
  @keyframes sm-loading-draw {{
      0%   {{ stroke-dashoffset: 1000; }}
      70%  {{ stroke-dashoffset: 0; }}
      100% {{ stroke-dashoffset: 0; }}
  }}
  @keyframes sm-loading-pulse {{
      0%, 100% {{ transform: scale(1); }}
      50%      {{ transform: scale(1.045); }}
  }}
  @keyframes sm-loading-dotblink {{
      0%, 80%, 100% {{ opacity: 0; }}
      40%           {{ opacity: 1; }}
  }}
</style>
"""


def _play_login_loading():
    """로그인/회원가입 성공 직후 잠깐 보여주는 우주·화성 컨셉 로딩 연출(로켓 + 우상향 차트).
    SMIL(stroke-dasharray/animateMotion)만으로 그려서 별도 JS 컴포넌트 없이 st.markdown으로 충분.
    끝난 뒤 오버레이는 페이드아웃, 메인 페이지는 페이드인 되도록 플래그를 남긴다(화면 전환감)."""
    _ph = st.empty()
    _ph.markdown(_LOGIN_LOADING_HTML_TMPL.replace("%%CLS%%", ""), unsafe_allow_html=True)
    time.sleep(1.7)
    _ph.markdown(_LOGIN_LOADING_HTML_TMPL.replace("%%CLS%%", "sm-loading-out"), unsafe_allow_html=True)
    time.sleep(0.45)
    _ph.empty()
    st.session_state["_just_logged_in"] = True

# Neon(무료 Postgres) 등 st.secrets["DATABASE_URL"]이 설정돼 있으면 자동으로 영구 저장
# 백엔드로 전환된다(storage.py는 streamlit 비의존이라 여기서 값을 주입해준다).
if not ST.DATABASE_URL:
    try:
        ST.DATABASE_URL = st.secrets["DATABASE_URL"]
    except Exception:
        pass


def current_db() -> str:
    """현재 세션(사용자)의 DB 경로. session_state 기반이라 동시 접속에도 안전."""
    return st.session_state["db_path"]


def _login_db_path(name: str, pw: str) -> str:
    """계정별 데이터 격리 키(기존 사용자 데이터 경로 형식과 100% 동일하게 유지)."""
    return ST.user_db_path(f"{name.strip().lower()}::{pw}")


# ---------------------------------------------------------------- 사용자 게이트
# 이름+비밀번호로 로그인/회원가입. 비밀번호는 scrypt로 해시 저장(users 테이블)해
# 진짜 검증이 이뤄진다 — 오타로 새 빈 계정이 생기는 일이 없다.
if "db_path" not in st.session_state:
    st.title("StockManager")
    st.caption("이름과 비밀번호로 내 데이터를 분리·보호합니다. 친구와 다른 이름을 쓰면 "
               "서로의 기록이 보이지 않습니다. (※ 민감정보 입력 금지)")
    tab_login, tab_signup = st.tabs(["🔐 로그인", "✨ 회원가입"])

    with tab_login:
        with st.form("login_form"):
            _lname = st.text_input("이름 / 닉네임", key="li_name")
            _lpw = st.text_input("비밀번호", type="password", key="li_pw")
            _lok = st.form_submit_button("로그인 →", type="primary", use_container_width=True)
        if _lok:
            if not (_lname.strip() and _lpw):
                st.error("이름과 비밀번호를 모두 입력하세요.")
            elif not ST.user_exists(_lname):
                st.error("존재하지 않는 계정입니다. '회원가입' 탭에서 먼저 계정을 만드세요.")
            elif not ST.verify_password(_lname, _lpw):
                st.error("비밀번호가 올바르지 않습니다.")
            else:
                st.session_state["user_name"] = _lname.strip()
                st.session_state["db_path"] = _login_db_path(_lname, _lpw)
                ST.init_db(st.session_state["db_path"])
                _play_login_loading()
                st.rerun()

    with tab_signup:
        st.caption("기존 사용자는 예전과 동일한 이름·비밀번호로 가입하면 기존 데이터가 "
                   "그대로 이어집니다.")
        with st.form("signup_form"):
            _sname = st.text_input("이름 / 닉네임", key="su_name")
            _spw = st.text_input("비밀번호 (4자 이상)", type="password", key="su_pw")
            _spw2 = st.text_input("비밀번호 확인", type="password", key="su_pw2")
            _sok = st.form_submit_button("계정 만들기 →", type="primary", use_container_width=True)
        if _sok:
            if not (_sname.strip() and _spw):
                st.error("이름과 비밀번호를 모두 입력하세요.")
            elif len(_spw) < 4:
                st.error("비밀번호는 4자 이상으로 해주세요.")
            elif _spw != _spw2:
                st.error("비밀번호 확인이 일치하지 않습니다.")
            elif ST.user_exists(_sname):
                st.error("이미 있는 이름입니다. '로그인' 탭을 이용하세요.")
            else:
                ST.create_user(_sname, _spw)
                st.session_state["user_name"] = _sname.strip()
                st.session_state["db_path"] = _login_db_path(_sname, _spw)
                ST.init_db(st.session_state["db_path"])
                _play_login_loading()
                st.rerun()
    st.stop()

ST.init_db(current_db())

# 로그인 로딩 연출 직후 한 번만: 로딩 화면이 사라진 자리에 메인 페이지가 페이드인
# 되도록(화면 전환감). 플래그를 바로 pop하므로 이후 평범한 rerun에는 재생되지 않는다.
if st.session_state.pop("_just_logged_in", False):
    st.markdown("""
    <style>
    div[data-testid="stAppViewContainer"] {
        animation: sm-page-fadein 0.6s ease both;
    }
    @keyframes sm-page-fadein {
        from { opacity: 0; transform: translateY(6px) scale(0.995); }
        to   { opacity: 1; transform: translateY(0) scale(1); }
    }
    </style>
    """, unsafe_allow_html=True)


# ---------------------------------------------------------------- 캐시 래퍼
@st.cache_data(ttl=60, show_spinner=False)
def cached_quote(symbol: str) -> dict:
    return MK.get_quote(symbol)


@st.cache_data(ttl=300, show_spinner=False)
def cached_fundamentals(symbol: str) -> dict:
    return MK.get_fundamentals(symbol)


@st.cache_data(ttl=600, show_spinner=False)
def cached_history(symbol: str, period: str, interval: str):
    return MK.get_history(symbol, period, interval)


@st.cache_data(ttl=20, show_spinner=False)
def cached_history_live(symbol: str, period: str, interval: str):
    return MK.get_history(symbol, period, interval)


@st.cache_data(ttl=900, show_spinner=False)
def cached_news(symbol: str):
    return MK.get_recent_news(symbol)


@st.cache_data(ttl=3600 * 6, show_spinner=False)
def cached_analyst_recs(symbol: str):
    return MK.get_analyst_recommendations(symbol)


@st.cache_data(ttl=3600 * 12, show_spinner=False)
def cached_search_interest(keyword: str):
    r = NA.search_interest(keyword)
    return r.to_dict() if r is not None else None


# ---------------------------------------------------------------- 포맷 헬퍼
def fmt_money(x, dollar=True):
    if x is None or (isinstance(x, float) and x != x):  # None/NaN
        return "—"
    p = "$" if dollar else ""
    a = abs(x)
    if a >= 1e12:
        return f"{p}{x/1e12:.2f}T"
    if a >= 1e9:
        return f"{p}{x/1e9:.2f}B"
    if a >= 1e6:
        return f"{p}{x/1e6:.2f}M"
    return f"{p}{x:,.2f}"


def fmt_num(x, suffix="", pct=False):
    if x is None or (isinstance(x, float) and x != x):
        return "—"
    if pct:
        return f"{x*100:.2f}%" if abs(x) < 5 else f"{x:.2f}%"
    return f"{x:,.2f}{suffix}"


def fmt_ratio(x):
    if x is None or (isinstance(x, float) and x != x):
        return "—"
    return f"{x:.2f}x"


# ---------------------------------------------------------------- 가이드 팝업
@st.dialog("📖 StockManager 가이드", width="large")
def show_guide(kind: str):
    st.markdown(GD.GUIDES.get(kind, "설명 준비 중입니다."))


def guide_header(title: str, kind: str, key: str, *, level: str = "subheader",
                 btn_label: str = "❔ Guide"):
    """섹션 제목 + 우측 Guide 버튼(누르면 팝업). level='subheader'|'markdown'."""
    hc1, hc2 = st.columns([4, 1])
    with hc1:
        if level == "subheader":
            st.subheader(title)
        else:
            st.markdown(f"**{title}**")
    if hc2.button(btn_label, key=key, use_container_width=True,
                  help="이 섹션을 어떻게 보고 쓰는지 쉽게 설명"):
        show_guide(kind)


def _ma_plain_summary(a: dict) -> str:
    """MA 분석을 초보용 한 문단으로."""
    align = a["alignment"]
    if align == "정배열":
        s = ("단기·중기·장기선이 위에서부터 순서대로 놓인 **정배열**이라 전형적인 "
             "상승추세예요. ")
    elif align == "역배열":
        s = "선들이 뒤집힌 **역배열**이라 전형적인 하락추세예요. "
    else:
        s = "이동평균선이 서로 얽혀 있어 **뚜렷한 방향이 없는 국면**이에요. "
    above = a["above"]
    if all(above.values()):
        s += "현재가가 모든 이동평균선 **위**에 있어 매수세가 강합니다."
    elif not any(above.values()):
        s += "현재가가 모든 이동평균선 **아래**에 있어 매도세가 강합니다."
    else:
        s += "현재가가 일부 선 위/아래에 걸쳐 있어 **눈치보기 구간**입니다."
    return s


@st.dialog("📊 차트 분석 (이동평균선)", width="large")
def show_chart_analysis(sym: str):
    df = cached_history(sym, "1y", "1d")
    a = CH.ma_analysis(df)
    if not a.get("available"):
        st.info("분석에 필요한 일봉 데이터가 부족합니다. 다른 종목을 시도하세요.")
        st.markdown(GD.GUIDES["ma_howto"])
        return

    st.markdown(f"### {sym} · :{a['color']}[{a['verdict']}]")
    st.caption(f"현재가 ${a['price']:.2f} · 이동평균선 배열: **{a['alignment']}**")

    names = {5: "5일선", 20: "20일선", 60: "60일선", 120: "120일선"}
    rows = [{"이동평균": names.get(w, f"{w}일선"), "값": a["mas"][w],
             "현재가 대비": a["gap"][w],
             "위치": "위 ▲" if a["above"][w] else "아래 ▼"}
            for w in a["windows"] if w in a["mas"]]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                 column_config={
                     "값": st.column_config.NumberColumn(format="$%.2f"),
                     "현재가 대비": st.column_config.NumberColumn(format="%+.1f%%")})

    cx = a["crosses"]
    msgs = []
    for k, label in [("5x20", "단기(5·20일)"), ("20x60", "중기(20·60일)")]:
        c = cx.get(k)
        if not c:
            continue
        if c["type"] == "golden":
            msgs.append(f"🟢 {label} **골든크로스** {c['bars_ago']}일 전 — 상승 전환 신호")
        else:
            msgs.append(f"🔴 {label} **데드크로스** {c['bars_ago']}일 전 — 하락 전환 신호")
    if msgs:
        st.markdown("**최근 크로스 신호**")
        for m in msgs:
            st.markdown(f"- {m}")

    st.markdown("**쉽게 말하면**")
    st.markdown(_ma_plain_summary(a))
    st.divider()
    st.markdown(GD.GUIDES["ma_howto"])


# ---------------------------------------------------------------- 사이드바
st.sidebar.title("StockManager")
st.sidebar.caption(f"👤 {st.session_state.get('user_name','')} 님의 워크벤치")


# 주요 지수 스트립 — 어떤 페이지에서든 차트와 함께 항상 보이는 시장 온도계
@st.cache_data(ttl=60, show_spinner=False)
def cached_indices():
    return MK.get_market_indices()


with st.sidebar:
    @st.fragment(run_every="60s")
    def _indices_strip():
        rows_html = []
        for ix in cached_indices():
            price, chg = ix["price"], ix["change_pct"]
            if price is None:
                continue
            cls = "up" if (chg or 0) >= 0 else "down"
            arrow = "▲" if (chg or 0) >= 0 else "▼"
            chg_txt = f"{arrow} {abs(chg):.2f}%" if chg is not None else ""
            rows_html.append(
                f'<div class="row"><span class="name">{ix["name"]}</span>'
                f'<span class="val {cls}">{price:,.2f}&nbsp;<small>{chg_txt}</small>'
                f'</span></div>')
        if rows_html:
            st.markdown(
                '<div class="sm-indices">'
                '<div class="row"><span class="name"><span class="sm-live-dot">'
                '</span>MARKET</span></div>' + "".join(rows_html) + "</div>",
                unsafe_allow_html=True)

    _indices_strip()

with st.sidebar.expander("🎧 BGM (우주 분위기 음악)", expanded=False):
    st.caption("취향에 맞게 골라보세요 — 버튼을 누르면 재생됩니다(자동재생 정책).")
    st.components.v1.html(_BGM_HTML, height=70)

with st.sidebar.expander("👤 계정 / 데이터 백업", expanded=False):
    st.caption("이 앱은 휘발성 환경에 배포될 수 있습니다. 중요한 기록은 가끔 "
               "**백업**해 두고, 데이터가 초기화되면 **복원**하세요.")
    _bkp = ST.export_db_bytes(current_db())
    st.download_button("⬇️ 내 데이터 백업(.db)", _bkp,
                       file_name=f"stockmanager_{st.session_state.get('user_name','my')}.db",
                       use_container_width=True, disabled=not _bkp)
    _up = st.file_uploader("⬆️ 백업 복원", type=["db"], key="restore_up")
    if _up is not None and st.session_state.get("_restored_id") != _up.file_id:
        st.session_state["_restored_id"] = _up.file_id
        if ST.import_db_bytes(current_db(), _up.getvalue()):
            st.cache_data.clear()
            st.success("복원되었습니다.")
            st.rerun()
        else:
            st.error("올바른 백업 파일이 아닙니다.")
    if st.button("🚪 로그아웃", use_container_width=True):
        for _k in ("db_path", "user_name", "_restored_id", "_xlsx"):
            st.session_state.pop(_k, None)
        st.cache_data.clear()
        st.rerun()

with st.sidebar.expander("📄 엑셀 내보내기", expanded=False):
    st.caption("스코어카드·촉매·매매·시나리오를 하나의 .xlsx로 내려받습니다.")
    if st.button("📊 엑셀 생성", use_container_width=True):
        st.session_state["_xlsx"] = EXP.export_excel_bytes(current_db())
    if st.session_state.get("_xlsx"):
        st.download_button(
            "⬇️ 다운로드(.xlsx)", st.session_state["_xlsx"],
            file_name=f"stockmanager_{st.session_state.get('user_name','my')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True)

with st.sidebar.expander("➕ Add Ticker", expanded=False):
    new_sym = st.text_input("Ticker", key="new_sym").upper().strip()
    new_kind = st.radio("Type", ["long", "swing"], horizontal=True,
                        format_func=lambda k: "Long" if k == "long" else "Swing",
                        key="new_kind")
    if st.button("추가", type="primary", use_container_width=True) and new_sym:
        f = cached_fundamentals(new_sym)
        if f.get("price") is None and f.get("market_cap") is None:
            st.error(f"'{new_sym}' 시세를 찾을 수 없습니다. 티커를 확인하세요.")
        else:
            ST.add_ticker(new_sym, f.get("name", new_sym), new_kind, db_path=current_db())
            st.success(f"{new_sym} 추가됨")
            st.rerun()

tickers = ST.list_tickers(db_path=current_db())
symbols = [t["symbol"] for t in tickers]

# 대시보드에서 종목 행 클릭 → 상세로 이동 (page_nav 위젯 생성 전에 처리해야 함)
if st.session_state.pop("_nav_detail", False):
    st.session_state["page_nav"] = "🔍 종목 상세"

page = st.sidebar.radio("페이지", ["📊 대시보드", "🔎 스캐너", "🔍 종목 상세"],
                        key="page_nav")

selected = None
if page == "🔍 종목 상세":
    if symbols:
        # 대시보드에서 넘어온 종목을 선택값으로 지정 (selectbox 생성 전에)
        goto = st.session_state.pop("_goto_symbol", None)
        if goto in symbols:
            st.session_state["detail_sel"] = goto
        if st.session_state.get("detail_sel") not in symbols:
            st.session_state.pop("detail_sel", None)  # 삭제된 종목 방어
        selected = st.sidebar.selectbox("종목 선택", symbols, key="detail_sel")
    else:
        st.sidebar.info("먼저 종목을 추가하세요.")

if st.sidebar.button("🔄 시세 새로고침", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.sidebar.divider()
st.sidebar.caption("데이터: Yahoo Finance (무료, 실시간~15분 지연). "
                   "투자 판단 참고용이며 투자 권유가 아닙니다.")


# ================================================================ 대시보드
def render_dashboard():
    st.title("포트폴리오 대시보드")
    if not tickers:
        st.info("사이드바에서 종목을 추가하면 여기에 표시됩니다.")
        return

    rows = []
    invested = 0.0
    for t in tickers:
        sym = t["symbol"]
        q = cached_quote(sym)
        card = ST.load_scorecard(sym, db_path=current_db())
        total = SC.weighted_total(card) if card else None
        verdict = SC.verdict(total)[0] if total is not None else "—"
        pos = ST.position_summary(sym, db_path=current_db())
        price = q.get("price")
        pl_pct = None
        mkt_val = None
        if pos["shares"] > 0 and price:
            mkt_val = pos["shares"] * price
            invested += mkt_val
            if pos["avg_price"]:
                pl_pct = (price - pos["avg_price"]) / pos["avg_price"] * 100
        hist = cached_history(sym, "1mo", "1d")
        spark = hist["Close"].tolist() if hist is not None and not hist.empty else []
        # NumberColumn은 결측값을 "None" 텍스트로 그대로 보여줌(glide-data-grid 특성) —
        # 미보유 종목처럼 값이 없는 게 정상인 열은 미리 "—"로 포맷한 문자열로 넣는다.
        rows.append({
            "Ticker": sym,
            "Type": "Long" if t["kind"] == "long" else "Swing",
            "Price": price,
            "Change %": q.get("change_pct"),
            "30D Trend": spark,
            "Score": total,
            "Verdict": verdict,
            "Shares": f"{pos['shares']:.0f}" if pos["shares"] else "—",
            "Avg Cost": fmt_money(pos["avg_price"]) if pos["shares"] else "—",
            "Value": fmt_money(mkt_val),
            "P/L %": f"{pl_pct:+.2f}%" if pl_pct is not None else "—",
        })
    df = pd.DataFrame(rows)

    # 요약 메트릭
    c1, c2, c3 = st.columns(3)
    c1.metric("Watchlist", f"{len(rows)} 종목")
    c2.metric("Portfolio Value", fmt_money(invested) if invested else "—")
    scored = [r["Score"] for r in rows if r["Score"] is not None]
    c3.metric("Avg Score", f"{sum(scored)/len(scored):.1f}" if scored else "—")

    st.caption("💡 표에서 종목 행을 클릭하면 해당 종목 상세로 바로 이동합니다.")
    dk = st.session_state.get("_dash_key", 0)
    event = st.dataframe(
        df,
        use_container_width=True, hide_index=True,
        on_select="rerun", selection_mode="single-row",
        key=f"dash_table_{dk}",
        column_config={
            "Price": st.column_config.NumberColumn(format="$%.2f"),
            "Change %": st.column_config.NumberColumn(format="%.2f%%"),
            "30D Trend": st.column_config.LineChartColumn(width="small"),
            "Score": st.column_config.ProgressColumn(min_value=0, max_value=100,
                                                   format="%.1f"),
        },
    )
    if event.selection.rows:
        st.session_state["_goto_symbol"] = df.iloc[event.selection.rows[0]]["Ticker"]
        st.session_state["_nav_detail"] = True
        st.session_state["_dash_key"] = dk + 1  # 선택 초기화(재진입 시 무한 이동 방지)
        st.rerun()
    st.caption("점수 ≥70 매수 · 60~70 소액 · <60 보류 (사용자 규칙)")


# ============================================================ 종목 상세
def render_detail(sym: str):
    meta = next((t for t in tickers if t["symbol"] == sym), {})
    f = cached_fundamentals(sym)
    q = cached_quote(sym)

    # 헤더
    price = q.get("price") or f.get("price")
    chg = q.get("change_pct")
    h1, h2, h3, h4 = st.columns([3, 1.2, 1.2, 1.2])
    h1.title(f"{sym}")
    h1.caption(f"{f.get('name','')} · {f.get('sector') or ''} / {f.get('industry') or ''}")
    h2.metric("Price", fmt_money(price), f"{chg:.2f}%" if chg is not None else None)
    h3.metric("Market Cap", fmt_money(f.get("market_cap")))
    h4.metric("Target Price", fmt_money(f.get("target_mean")))

    tabs = st.tabs(["📈 개요/Live", "📋 스코어카드", "🧮 밸류에이션·DCF",
                    "🎯 시나리오", "📰 뉴스·Narrative", "🗒️ 촉매 반영", "💰 매매기록"])

    with tabs[0]:
        render_overview(sym, f, q)
    with tabs[1]:
        render_scorecard(sym, f)
    with tabs[2]:
        render_valuation(sym, f, price)
    with tabs[3]:
        render_scenarios(sym, f, price)
    with tabs[4]:
        render_narrative(sym, price)
    with tabs[5]:
        render_catalysts(sym, price)
    with tabs[6]:
        render_trades(sym, price)

    st.divider()
    cdel1, cdel2 = st.columns([4, 1])
    cdel2.button("🗑️ 종목 삭제", use_container_width=True,
                 on_click=lambda: (ST.remove_ticker(sym, db_path=current_db()),
                                   st.cache_data.clear()))


# 기간 라벨 → (yahoo period, 라인용 interval)
_PERIOD_YH = {"1D": "1d", "1W": "5d", "1M": "1mo", "3M": "3mo", "6M": "6mo",
              "1Y": "1y", "2Y": "2y", "5Y": "5y", "10Y": "10y", "MAX": "max"}
_LINE_INTERVAL = {"1D": "1m", "1W": "15m", "1M": "60m", "3M": "1d", "6M": "1d",
                  "1Y": "1d", "2Y": "1wk", "5Y": "1wk", "10Y": "1mo", "MAX": "1mo"}
# 캔들 종류별 기본 기간 선택지
_RANGE_OPTS = {
    "Line": ["1D", "1W", "1M", "3M", "1Y", "5Y", "10Y", "MAX"],
    "Daily": ["3M", "6M", "1Y", "2Y", "5Y", "10Y", "MAX"],
    "Weekly": ["1Y", "2Y", "5Y", "10Y", "MAX"],
    "Monthly": ["5Y", "10Y", "MAX"],
}
_CANDLE_INTERVAL = {"Daily": "1d", "Weekly": "1wk", "Monthly": "1mo"}


def _resolve_period_interval(gran: str, rng: str):
    yperiod = _PERIOD_YH.get(rng, "1y")
    if gran == "Line":
        return yperiod, _LINE_INTERVAL.get(rng, "1d"), "line"
    return yperiod, _CANDLE_INTERVAL.get(gran, "1d"), "candle"


def render_chart(sym: str):
    """Robinhood 스타일 인터랙티브 차트 + 실시간 + 추세전환/내러티브 오버레이."""
    catalysts = ST.list_catalysts(sym, db_path=current_db())

    gh1, gh2, gh3 = st.columns([3, 1, 1])
    gh1.markdown("**📈 Price Chart**")
    if gh2.button("📊 차트 분석", key=f"cta_{sym}", use_container_width=True,
                  help="5·20·60·120일선 기준 현재 추세 해석"):
        show_chart_analysis(sym)
    if gh3.button("❔ Guide", key=f"g_chart_{sym}", use_container_width=True,
                  help="차트 보는 법 설명"):
        show_guide("chart")
    c1, c2, c3, c4 = st.columns([2.0, 3.0, 1.3, 1.3])
    gran = c1.segmented_control("Chart", ["Line", "Daily", "Weekly", "Monthly"],
                                default="Line", key=f"gran_{sym}") or "Line"
    opts = _RANGE_OPTS[gran]
    default_rng = opts[len(opts) // 2] if gran != "Line" else "1Y"
    rng = c2.segmented_control("Range", opts, default=default_rng,
                               key=f"rng_{sym}") or opts[0]
    dynamic = c3.toggle("✨ Dynamic", value=_TV_AVAILABLE, key=f"dyn_{sym}",
                        disabled=not _TV_AVAILABLE,
                        help="증권앱 느낌의 부드러운 실시간 차트(TradingView). "
                             "끄면 기존 분석용 차트(plotly)로 봅니다.") if _TV_AVAILABLE else False
    live = c4.toggle("🔴 Live", key=f"live_{sym}",
                     help="30초마다 차트만 자동 갱신 (전체 새로고침 없음)")

    yperiod, interval, mode = _resolve_period_interval(gran, rng)
    oc1, oc2 = st.columns(2)
    show_trend = oc1.checkbox("추세 전환 구간 · 촉매 표시", value=True, key=f"trend_{sym}")
    show_volume = oc2.checkbox("📊 Volume", value=False, key=f"vol_{sym}")

    refresh = "30s" if live else None

    @st.fragment(run_every=refresh)
    def _draw():
        fetch = cached_history_live if live else cached_history
        df = fetch(sym, yperiod, interval)
        if df is None or df.empty:
            st.info("이 조합의 가격 데이터를 불러올 수 없습니다. 기간/종류를 바꿔보세요.")
            return
        if dynamic:
            panes = CH.build_tv_panes(df, mode, interval=interval, catalysts=catalysts,
                                      show_trend=show_trend, show_volume=show_volume)
            total_height = sum(p.get("height", 300) for p in panes) or 440
            lightweight_charts_v5_component(name=sym, charts=panes,
                                            height=total_height, key=f"tv_{sym}")
        else:
            fig = CH.build_figure(df, mode, interval=interval, catalysts=catalysts,
                                  show_trend=show_trend, show_volume=show_volume)
            st.plotly_chart(fig, use_container_width=True, key=f"plt_{sym}")
        if live:
            st.caption(f"🔴 실시간 갱신 중 · 마지막 {dt.datetime.now():%H:%M:%S} "
                       f"(데이터 ~1분 지연)")

    _draw()

    # 추세 전환 구간 & 내러티브 펼쳐보기
    if show_trend:
        df_sum = cached_history(sym, yperiod, interval)
        rows = CH.trend_summary(df_sum, interval, catalysts)
        with st.expander(f"📍 추세 전환 구간 & 내러티브 ({len(rows)}건 탐지) — 펼쳐보기"):
            if not rows:
                st.write("이 기간에서는 뚜렷한 추세 전환(SMA 크로스오버)이 없습니다. "
                         "기간을 늘리거나 종류를 바꿔보세요.")
            for r in rows:
                up = r["type"] == "up"
                head = ("🟢 **:green[▲ 상승 추세 시작]**" if up
                        else "🔴 **:red[▼ 하락 추세 시작]**")
                d = r["date"]
                dstr = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)
                st.markdown(f"{head} · {dstr} · ${r['price']:.2f}")
                if r["catalysts"]:
                    for m in r["catalysts"]:
                        icon = "🟢" if m["kind"] == "호재" else "🔴"
                        refl = (f" · 반영도 {m['reflected']:.0f}%"
                                if m.get("reflected") is not None else "")
                        note = f" — {m['note']}" if m.get("note") else ""
                        st.caption(f"&nbsp;&nbsp;{icon} {m['headline']}{refl}{note}")
                else:
                    st.caption("&nbsp;&nbsp;📝 기록된 촉매 없음 — '촉매 반영' 탭에서 "
                               "이 시점의 뉴스/내러티브를 추가하면 여기에 연결됩니다.")
        st.caption("음영: 🟩상승추세 / 🟥하락추세 · ★ 마커 = 내가 기록한 촉매(호버로 내용 확인)")


def render_overview(sym, f, q):
    render_chart(sym)
    st.divider()
    guide_header("Fundamental", "fundamental", key=f"gb_fund_{sym}",
                 btn_label="📖 Guidebook")
    g1, g2, g3, g4 = st.columns(4)
    g1.metric("Trailing P/E", fmt_num(f.get("trailing_pe")))
    g1.metric("Forward P/E", fmt_num(f.get("forward_pe")))
    g2.metric("P/B", fmt_num(f.get("price_to_book")))
    g2.metric("P/S", fmt_num(f.get("price_to_sales")))
    g3.metric("EV/EBITDA", fmt_ratio(f.get("ev_ebitda")))
    g3.metric("PEG", fmt_num(f.get("peg")))
    g4.metric("Short Interest (%Float)", fmt_num(f.get("short_pct_float"), pct=True))
    g4.metric("Beta", fmt_num(f.get("beta")))

    g5, g6, g7, g8 = st.columns(4)
    g5.metric("Revenue Growth", fmt_num(f.get("revenue_growth"), pct=True))
    g6.metric("Earnings Growth", fmt_num(f.get("earnings_growth"), pct=True))
    g7.metric("Profit Margin", fmt_num(f.get("profit_margin"), pct=True))
    net_debt = (f.get("total_debt") or 0) - (f.get("total_cash") or 0)
    g8.metric("Net Debt", fmt_money(net_debt))

    g9, g10, g11, g12 = st.columns(4)
    g9.metric("FCF (TTM)", fmt_money(f.get("free_cashflow")))
    g10.metric("EPS (TTM)", fmt_money(f.get("eps_trailing")))
    g11.metric("EPS (Fwd)", fmt_money(f.get("eps_forward")))
    g12.metric("Debt/Equity", fmt_num(f.get("debt_to_equity")))

    # 52-Week Range
    lo, hi = f.get("fifty_two_low"), f.get("fifty_two_high")
    price = q.get("price") or f.get("price")
    if lo and hi and price and hi > lo:
        pos = (price - lo) / (hi - lo) * 100
        st.caption(f"52-Week Range: {fmt_money(lo)} ─ {fmt_money(hi)}  "
                   f"(current position {pos:.0f}%)")
        st.progress(min(1.0, max(0.0, pos / 100)))


def render_scorecard(sym, f):
    guide_header("📋 투자 스코어카드", "scorecard", key=f"g_sc_{sym}")
    st.caption("각 항목 0~100점으로 평가. 가중치(weight)는 자유롭게 수정 가능. "
               "**Live 실측** 열은 Yahoo 지표(PER·PSR·PBR·CAGR·FCF)로 자동 채워집니다 "
               "— 이 값을 참고해 점수를 매기세요.")

    card = ST.load_scorecard(sym, db_path=current_db()) or SC.default_scorecard()
    card = SC.autofill_metrics(card, f)   # 'metric'(Live 실측) 자동 채움
    df = pd.DataFrame(card)
    for _c in ("hint", "metric"):
        if _c not in df.columns:
            df[_c] = ""

    edited = st.data_editor(
        df[["category", "item", "weight", "score", "metric", "comment", "hint"]],
        use_container_width=True, hide_index=True, num_rows="dynamic",
        column_config={
            "category": st.column_config.TextColumn("카테고리"),
            "item": st.column_config.TextColumn("항목", width="medium"),
            "weight": st.column_config.NumberColumn("가중치%", min_value=0, max_value=100,
                                                    step=1),
            "score": st.column_config.NumberColumn("내 점수", min_value=0, max_value=100,
                                                   step=1),
            "metric": st.column_config.TextColumn("Live 실측", disabled=True,
                                                  help="Yahoo 지표 자동 반영(읽기전용)"),
            "comment": st.column_config.TextColumn("코멘트", width="large"),
            "hint": st.column_config.TextColumn("설명(참고)", disabled=True),
        },
        key=f"sc_{sym}",
    )
    items = edited.to_dict("records")
    total = SC.weighted_total(items)
    tw = sum(float(i.get("weight", 0) or 0) for i in items)
    label, color = SC.verdict(total)

    m1, m2, m3 = st.columns(3)
    m1.metric("가중 총점", f"{total:.1f}")
    m2.markdown(f"### :{color}[{label}]")
    if abs(tw - 100) > 0.01:
        m3.warning(f"가중치 합 = {tw:.0f}% (100%로 맞추길 권장)")
    else:
        m3.success("가중치 합 = 100% ✓")

    # 카테고리 레이더
    bd = SC.category_breakdown(items)
    if bd:
        cats = list(bd.keys())
        vals = [bd[c]["avg_score"] for c in cats]
        fig = go.Figure(go.Scatterpolar(r=vals + [vals[0]], theta=cats + [cats[0]],
                                        fill="toself", name=sym))
        fig.update_layout(polar=dict(radialaxis=dict(range=[0, 100])), height=350,
                          margin=dict(l=40, r=40, t=20, b=20), showlegend=False)
        cc1, cc2 = st.columns([1, 1])
        cc1.plotly_chart(fig, use_container_width=True)
        with cc2:
            st.write("**카테고리별 가중점수**")
            for c in cats:
                st.write(f"- {c}: {bd[c]['avg_score']:.0f}점 "
                         f"(가중치 {bd[c]['weight']:.0f}%)")

    if st.button("💾 스코어카드 저장", type="primary"):
        # 'metric'은 Live 파생값 → 저장 제외(매 로드 시 재계산)
        save_items = [{k: v for k, v in it.items() if k != "metric"} for it in items]
        ST.save_scorecard(sym, save_items, db_path=current_db())
        st.success("저장됨")

    with st.expander("🤖 Live 지표 자동 채점 제안(참고용)"):
        st.caption("규칙 기반 단순 제안. 최종 점수는 본인 판단으로.")
        sugg = auto_score_hints(f)
        for k, v in sugg.items():
            st.write(f"- **{k}**: {v}")


def auto_score_hints(f) -> dict:
    """Live 지표로부터 단순 룰 기반 코멘트 생성(참고용)."""
    out = {}
    fpe = f.get("forward_pe")
    if fpe is not None:
        out["Forward P/E"] = (f"{fpe:.1f}x — "
                              + ("저평가권(<15)" if fpe < 15 else
                                 "적정(15~25)" if fpe < 25 else
                                 "고평가권(>25), 성장으로 정당화 필요"))
    rg = f.get("revenue_growth")
    if rg is not None:
        out["매출성장(CAGR)"] = f"{rg*100:.0f}% — " + ("우수(>20%)" if rg > 0.2 else
                                                      "양호(>10%)" if rg > 0.1 else "둔화")
    ps = f.get("price_to_sales")
    if ps is not None:
        out["PSR"] = f"{ps:.1f}x — " + ("부담(>10)" if ps > 10 else "보통")
    sd = f.get("short_pct_float")
    if sd is not None:
        out["공매도비율"] = f"{sd*100:.1f}% — " + ("높음(>10%) 변동성 주의" if sd > 0.1 else "보통")
    de = f.get("debt_to_equity")
    if de is not None:
        out["부채/자본"] = f"{de:.0f} — " + ("높음(>150)" if de > 150 else "관리가능")
    return out


def render_valuation(sym, f, price):
    guide_header("🧮 밸류에이션 & DCF", "valuation", key=f"g_val_{sym}")

    # --- 멀티플 스냅샷
    st.markdown("**멀티플 스냅샷**")
    snap = pd.DataFrame([{
        "Trailing P/E": f.get("trailing_pe"), "Forward P/E": f.get("forward_pe"),
        "PBR": f.get("price_to_book"), "PSR": f.get("price_to_sales"),
        "EV/EBITDA": f.get("ev_ebitda"), "PEG": f.get("peg"),
    }])
    st.dataframe(snap, use_container_width=True, hide_index=True)

    # --- Forward P/E 투영
    st.markdown("**Forward P/E 투영 (EPS 성장 가정)**")
    fc1, fc2, fc3 = st.columns(3)
    eps0 = fc1.number_input("기준 EPS", value=float(f.get("eps_forward")
                            or f.get("eps_trailing") or 1.0), step=0.1, format="%.2f")
    eps_g = fc2.number_input("EPS 성장률 %", value=float((f.get("earnings_growth") or 0.15)*100),
                             step=1.0) / 100
    n_years = fc3.number_input("투영 연수", value=5, min_value=1, max_value=15, step=1)
    if price and eps0:
        proj = V.forward_multiples(price, eps0, eps_g, int(n_years))
        pdf = pd.DataFrame([{"연차": f"+{r['year_offset']}y", "EPS": r["eps"],
                             "Forward P/E": r["forward_pe"]} for r in proj])
        vc1, vc2 = st.columns([1, 1])
        vc1.dataframe(pdf, use_container_width=True, hide_index=True,
                      column_config={"EPS": st.column_config.NumberColumn(format="$%.2f"),
                                     "Forward P/E": st.column_config.NumberColumn(format="%.1f")})
        fig = go.Figure(go.Bar(x=pdf["연차"], y=pdf["Forward P/E"]))
        fig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0),
                          yaxis_title="Forward P/E")
        vc2.plotly_chart(fig, use_container_width=True)

    st.divider()

    # --- DCF / Reverse DCF
    st.markdown("**정/역 DCF (Reverse DCF)**")
    saved = ST.load_assumptions(sym, db_path=current_db()) or {}
    default_fcf = f.get("free_cashflow") or f.get("operating_cashflow") or 0.0
    net_debt = (f.get("total_debt") or 0) - (f.get("total_cash") or 0)
    shares = f.get("shares_out") or 0.0

    d1, d2, d3 = st.columns(3)
    fcf0 = d1.number_input("기준 FCF ($)", value=float(saved.get("fcf0", default_fcf)),
                           step=1e6, format="%.0f")
    growth = d2.number_input("고성장 CAGR %", value=float(saved.get("growth", 0.12)*100),
                             step=1.0) / 100
    years = d3.number_input("고성장 연수", value=int(saved.get("years", 10)),
                            min_value=1, max_value=20)
    d4, d5, d6 = st.columns(3)
    wacc = d4.number_input("할인율 WACC %", value=float(saved.get("wacc", 0.10)*100),
                           step=0.5) / 100
    tg = d5.number_input("영구성장률 %", value=float(saved.get("terminal_growth", 0.025)*100),
                         step=0.5) / 100
    nd = d6.number_input("순부채 ($)", value=float(saved.get("net_debt", net_debt)),
                         step=1e6, format="%.0f")
    sh = st.number_input("발행주식수", value=float(saved.get("shares", shares)),
                         step=1e6, format="%.0f")

    a = V.DCFAssumptions(fcf0=fcf0, growth=growth, years=int(years), wacc=wacc,
                         terminal_growth=tg, net_debt=nd, shares=sh)

    colA, colB = st.columns(2)
    with colA:
        st.markdown("##### 정 DCF — 내재가치")
        try:
            iv = V.intrinsic_value(a)
            mos = V.margin_of_safety(iv["per_share"], price) if price else None
            st.metric("Intrinsic Value / Share", fmt_money(iv["per_share"]))
            st.metric("Enterprise Value", fmt_money(iv["enterprise_value"]))
            if mos is not None:
                st.metric("Margin of Safety", f"{mos*100:.1f}%",
                          delta="저평가" if mos > 0 else "고평가")
        except ValueError as e:
            st.error(str(e))

    with colB:
        st.markdown("##### 역 DCF — 시장 내재 성장률")
        st.caption("현재 시가총액을 정당화하려면 시장이 기대하는 FCF 성장률은?")
        mcap = f.get("market_cap")
        if mcap:
            g_impl = V.reverse_dcf_implied_growth(a, mcap)
            if g_impl is None:
                st.warning("역산 불가 (음수 FCF이거나 합리적 범위 내 해 없음).")
            else:
                st.metric("Implied FCF Growth", f"{g_impl*100:.1f}% / 년",
                          help="입력한 고성장 연수 동안 시장이 가정 중인 성장률")
                gap = g_impl - growth
                if gap > 0.02:
                    st.error(f"시장 기대({g_impl*100:.1f}%) > 내 가정({growth*100:.1f}%) "
                             f"→ 현재가가 공격적. 비싼 편.")
                elif gap < -0.02:
                    st.success(f"시장 기대({g_impl*100:.1f}%) < 내 가정({growth*100:.1f}%) "
                               f"→ 시장이 보수적. 저평가 가능.")
                else:
                    st.info("시장 기대와 내 가정이 비슷함.")
        else:
            st.info("시가총액 데이터 없음.")

    if st.button("💾 DCF 가정 저장"):
        ST.save_assumptions(sym, {"fcf0": fcf0, "growth": growth, "years": int(years),
                                  "wacc": wacc, "terminal_growth": tg, "net_debt": nd,
                                  "shares": sh}, db_path=current_db())
        st.success("저장됨")

    render_peer_comparison(sym, f)


def render_peer_comparison(sym, f):
    """동종업계(사용자 지정 티커) 멀티플 비교."""
    st.divider()
    st.markdown("**🏦 동종업계 멀티플 비교**")
    st.caption("경쟁사 티커를 입력하면 Forward P/E·PBR·PSR·EV/EBITDA를 나란히 비교합니다.")

    saved_peers = ST.load_peers(sym, db_path=current_db())
    pc1, pc2 = st.columns([4, 1])
    txt = pc1.text_input("비교 티커 (쉼표로 구분)", value=", ".join(saved_peers),
                         key=f"peers_{sym}", placeholder="예: UPST, AFRM, LC")
    if pc2.button("💾 저장", key=f"savepeers_{sym}"):
        ST.save_peers(sym, [p for p in txt.split(",")], db_path=current_db())
        st.success("저장됨")

    peers = []
    for p in txt.split(","):
        p = p.upper().strip()
        if p and p != sym and p not in peers:
            peers.append(p)

    def _row(symbol, data, is_self):
        return {"Ticker": ("⭐ " + symbol) if is_self else symbol,
                "Fwd P/E": data.get("forward_pe"), "P/E": data.get("trailing_pe"),
                "PBR": data.get("price_to_book"), "PSR": data.get("price_to_sales"),
                "EV/EBITDA": data.get("ev_ebitda")}

    rows = [_row(sym, f, True)]
    for p in peers:
        pf = cached_fundamentals(p)
        if pf.get("forward_pe") is None and pf.get("market_cap") is None:
            st.caption(f"⚠️ '{p}' 데이터를 찾을 수 없어 제외했습니다.")
            continue
        rows.append(_row(p, pf, False))

    if len(rows) <= 1:
        st.info("비교할 경쟁사 티커를 입력하세요.")
        return

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True, column_config={
        "Fwd P/E": st.column_config.NumberColumn(format="%.1f"),
        "P/E": st.column_config.NumberColumn(format="%.1f"),
        "PBR": st.column_config.NumberColumn(format="%.2f"),
        "PSR": st.column_config.NumberColumn(format="%.2f"),
        "EV/EBITDA": st.column_config.NumberColumn(format="%.1f"),
    })

    # Forward P/E: 자신 vs 피어 중앙값
    self_pe = f.get("forward_pe")
    peer_pe = [r["Fwd P/E"] for r in rows[1:] if r["Fwd P/E"]]
    if self_pe and peer_pe:
        import statistics
        med = statistics.median(peer_pe)
        pcmp1, pcmp2 = st.columns([1, 2])
        pcmp1.metric("피어 Fwd P/E 중앙값", f"{med:.1f}x")
        if self_pe < med * 0.9:
            pcmp2.success(f"{sym} {self_pe:.1f}x < 피어 중앙값 {med:.1f}x "
                          f"→ 상대적 **저평가**")
        elif self_pe > med * 1.1:
            pcmp2.error(f"{sym} {self_pe:.1f}x > 피어 중앙값 {med:.1f}x "
                        f"→ 상대적 **고평가**(성장 프리미엄 확인)")
        else:
            pcmp2.info(f"{sym} {self_pe:.1f}x ≈ 피어 중앙값 {med:.1f}x → 유사")

        bars = [r for r in rows if r["Fwd P/E"]]
        fig = go.Figure(go.Bar(
            x=[r["Ticker"] for r in bars], y=[r["Fwd P/E"] for r in bars],
            marker_color=[CH.GREEN if r["Ticker"].startswith("⭐") else CH.SMA_SHORT
                          for r in bars],
            text=[f"{r['Fwd P/E']:.1f}x" for r in bars], textposition="outside"))
        fig.add_hline(y=med, line_dash="dash", line_color="white",
                      annotation_text=f"중앙값 {med:.1f}x")
        fig.update_layout(template="plotly_dark", height=300,
                          margin=dict(l=0, r=0, t=10, b=0), yaxis_title="Forward P/E",
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True, key=f"peer_bar_{sym}")


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _ensure_ids(scn: dict) -> dict:
    """케이스/드라이버에 위젯 키용 안정적 _id 부여(없으면)."""
    for c in scn.get("cases", []):
        c.setdefault("_id", _new_id())
        for d in c.get("drivers", []):
            d.setdefault("_id", _new_id())
    return scn


def render_scenarios(sym, f, price):
    guide_header("🎯 시나리오 / 케이스 밸류에이션", "scenario", key=f"g_scn_{sym}")
    st.caption("Bear·Base·Bull·Super Bull 등 케이스별로 EPS·매출·사용자지정 지표의 "
               "연평균성장률(CAGR)을 슬라이더로 가정하고 목표주가·업사이드를 비교합니다. "
               "지표는 '➕ 지표 추가'로 회원수·계약건수·판매량 등 원하는 값을 넣을 수 있어요.")

    shares = f.get("shares_out")
    # 매출 절대값 추정: 시가총액 / PSR
    mcap, psr = f.get("market_cap"), f.get("price_to_sales")
    rev0 = (mcap / psr) if (mcap and psr) else 0.0

    key = f"scn_{sym}"
    if key not in st.session_state:
        saved = ST.load_scenario(sym, db_path=current_db())
        if not saved or not saved.get("cases"):
            saved = SN.default_scenario(
                eps0=f.get("eps_forward") or f.get("eps_trailing"),
                rev0=rev0, fwd_pe=f.get("forward_pe"),
                ps=f.get("price_to_sales"), shares=shares)
        st.session_state[key] = _ensure_ids(saved)
    scn = st.session_state[key]

    tc1, tc2 = st.columns([2, 3])
    hy = tc1.segmented_control("투자 기간 (CAGR 적용 연수)", [3, 5],
                               default=int(scn.get("horizon_years", 5)),
                               format_func=lambda y: f"{y}년",
                               key=f"hy_{sym}") or int(scn.get("horizon_years", 5))
    scn["horizon_years"] = hy
    tc2.caption(f"기준 시세 ${price:.2f} · EPS/매출은 exit 멀티플로, 사용자지정 지표는 "
                f"참고 투영값으로 표시됩니다." if price else "현재가 데이터 없음.")

    # ---- 케이스별 편집 ----
    for c in list(scn["cases"]):
        color = c.get("color", "gray")
        with st.container(border=True):
            hc1, hc2, hc3 = st.columns([3, 1.2, 1])
            c["name"] = hc1.text_input("케이스명", value=c.get("name", ""),
                                       key=f"nm_{c['_id']}")
            c["prob"] = hc2.number_input("확률", 0.0, 1.0,
                                         value=float(SN._f(c.get("prob"))), step=0.05,
                                         key=f"pr_{c['_id']}",
                                         help="확률가중 기대 목표주가(blended) 계산에 사용")
            if hc3.button("🗑 케이스", key=f"delc_{c['_id']}"):
                scn["cases"].remove(c)
                st.rerun()

            # 드라이버 헤더
            hh = st.columns([2.2, 1.8, 3.4, 1.5, 1.1, 0.7])
            for col, lbl in zip(hh, ["지표", "기준값", "CAGR(연 %)",
                                     "exit ×", "단위", ""]):
                col.caption(lbl)
            for d in list(c["drivers"]):
                dc = st.columns([2.2, 1.8, 3.4, 1.5, 1.1, 0.7])
                d["key"] = dc[0].text_input("지표", value=d.get("key", ""),
                                            key=f"k_{d['_id']}", label_visibility="collapsed")
                d["base"] = dc[1].number_input("기준값", value=float(SN._f(d.get("base"))),
                                               key=f"b_{d['_id']}", format="%.2f",
                                               label_visibility="collapsed")
                g = dc[2].slider("CAGR", -100, 100,
                                 int(round(SN._f(d.get("cagr")) * 100)), step=1,
                                 key=f"g_{d['_id']}", label_visibility="collapsed")
                d["cagr"] = g / 100.0
                if d.get("kind") in ("eps", "revenue"):
                    d["exit_multiple"] = dc[3].number_input(
                        "exit", value=float(SN._f(d.get("exit_multiple"))),
                        key=f"m_{d['_id']}", format="%.1f", label_visibility="collapsed")
                else:
                    dc[3].caption("—")
                d["unit"] = dc[4].text_input("단위", value=d.get("unit", "") or "",
                                             key=f"u_{d['_id']}", label_visibility="collapsed")
                if dc[5].button("🗑", key=f"deld_{d['_id']}"):
                    c["drivers"].remove(d)
                    st.rerun()

            ac1, ac2 = st.columns([2, 5])
            if ac1.button("➕ 지표 추가", key=f"add_{c['_id']}",
                          help="회원수·계약건수·판매량·결제금액 등 사용자지정 지표"):
                nd = SN.new_custom_driver()
                nd["_id"] = _new_id()
                c["drivers"].append(nd)
                st.rerun()

            c["comment"] = st.text_area("코멘트 (이 케이스의 핵심 가정/논리)",
                                        value=c.get("comment", ""),
                                        key=f"cm_{c['_id']}", height=68)

            cv = SN.case_valuation(c, hy, price, shares)
            r1, r2, r3 = st.columns(3)
            r1.metric(f"{c['name']} Target", fmt_money(cv["target_price"]))
            r2.metric("Upside",
                      f"{cv['upside']*100:+.1f}%" if cv["upside"] is not None else "—",
                      delta="상승" if (cv["upside"] or 0) > 0 else
                      ("하락" if cv["upside"] is not None else None))
            r3.caption(f"산출 근거: {cv['basis'] or '커스텀 지표만 — 목표가 미산출'}")
            # 커스텀 지표 투영값
            customs = [p for p in cv["projections"] if p["kind"] == "custom"]
            if customs:
                st.caption("· " + "  ·  ".join(
                    f"{p['key']}: {fmt_num(p['base'])}{p['unit']} → "
                    f"{fmt_num(p['future_value'])}{p['unit']} ({hy}년)"
                    for p in customs))

    if st.button("➕ 케이스 추가"):
        nc = {"name": "New Case", "color": "blue", "prob": 0.0, "comment": "",
              "_id": _new_id(),
              "drivers": [{"key": "EPS", "kind": "eps",
                           "base": float(SN._f(f.get("eps_forward")
                                        or f.get("eps_trailing") or 1.0)),
                           "cagr": 0.10, "unit": "$",
                           "exit_multiple": float(SN._f(f.get("forward_pe")) or 20.0),
                           "_id": _new_id()}]}
        scn["cases"].append(nc)
        st.rerun()

    st.divider()

    # ---- 케이스 비교 요약 ----
    summary = SN.scenario_summary(scn, price, shares)
    priced = [cv for cv in summary["cases"] if cv["target_price"] is not None]
    if priced:
        st.markdown("**케이스 비교**")
        _COLOR_HEX = {"red": CH.RED, "orange": CH.SMA_LONG, "green": CH.GREEN,
                      "violet": "#A78BFA", "blue": CH.SMA_SHORT, "gray": "#888"}
        fig = go.Figure(go.Bar(
            x=[cv["name"] for cv in priced],
            y=[cv["target_price"] for cv in priced],
            marker_color=[_COLOR_HEX.get(cv["color"], "#888") for cv in priced],
            text=[f"${cv['target_price']:.0f}" for cv in priced],
            textposition="outside"))
        if price:
            fig.add_hline(y=price, line_dash="dash", line_color="white",
                          annotation_text=f"현재가 ${price:.2f}",
                          annotation_position="top left")
        fig.update_layout(template="plotly_dark", height=340,
                          margin=dict(l=0, r=0, t=10, b=0),
                          yaxis_title="Target Price ($)",
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True, key=f"scn_bar_{sym}")

        bt = summary["blended_target"]
        b1, b2, b3 = st.columns(3)
        b1.metric("Blended Target Price", fmt_money(bt),
                  help="목표주가가 있는 케이스를 확률로 가중평균(확률가중 기대 목표주가)")
        b2.metric("Expected Upside",
                  f"{summary['blended_upside']*100:+.1f}%"
                  if summary["blended_upside"] is not None else "—")
        ps = summary["prob_sum"]
        if abs(ps - 1.0) > 0.01:
            b3.warning(f"확률 합 = {ps:.2f} (1.00 권장)")
        else:
            b3.success("확률 합 = 1.00 ✓")

        cmp_df = pd.DataFrame([{
            "Case": cv["name"], "Prob": cv["prob"],
            "Target": cv["target_price"],
            "Upside %": (cv["upside"] * 100 if cv["upside"] is not None else None),
            "코멘트": cv["comment"],
        } for cv in summary["cases"]])
        st.dataframe(cmp_df, use_container_width=True, hide_index=True,
                     column_config={
                         "Prob": st.column_config.NumberColumn(format="%.2f"),
                         "Target": st.column_config.NumberColumn(format="$%.2f"),
                         "Upside %": st.column_config.NumberColumn(format="%.1f%%"),
                     })
    else:
        st.info("EPS 또는 매출 드라이버에 exit 멀티플을 넣으면 목표주가가 계산됩니다.")

    sc1, sc2 = st.columns([1, 1])
    if sc1.button("💾 시나리오 저장", type="primary"):
        ST.save_scenario(sym, scn, db_path=current_db())
        st.success("저장됨")
    if sc2.button("↩️ Live 기본값으로 초기화", help="현재 지표로 4개 케이스 새로 생성"):
        st.session_state.pop(key, None)
        st.rerun()


def render_narrative(sym, price):
    guide_header("📰 뉴스 · Narrative", "narrative", key=f"g_narr_{sym}")
    st.caption("이 종목을 둘러싼 '이야기'가 뜨거워지는지 식는지 무료 데이터로 살펴봅니다.")

    news = cached_news(sym)
    narr = NA.news_narrative(news)
    n1, n2, n3 = st.columns(3)
    if narr["available"]:
        n1.metric("News Buzz", f"{narr['buzz']}/100", help="수집 한도 대비 현재 노출량")
        n2.metric("Headline Tone", f"{narr['sentiment']:+d}", narr["label"],
                  help="-100(매우부정)~+100(매우긍정)")
    else:
        n1.metric("News Buzz", "—")
        n2.metric("Headline Tone", "—")

    recs = cached_analyst_recs(sym)
    am = NA.analyst_momentum(recs)
    if am["available"]:
        n3.metric("Analyst Momentum", am["trend"], f"{am['delta']:+.2f}",
                  help="최근 수개월 컨센서스 변화(+면 강세로 이동)")
    else:
        n3.metric("Analyst Momentum", "—")

    si = cached_search_interest(sym)
    if si:
        with st.expander("🔍 Google 검색 관심도 (최근 12개월)"):
            st.line_chart(si)
            st.caption("비공식 데이터 소스라 가끔 조회에 실패할 수 있습니다(정상).")

    with st.expander("📡 최근 뉴스 헤드라인 (Yahoo)", expanded=True):
        if narr["available"]:
            for i, n in enumerate(narr["articles"]):
                t = n.get("title")
                link = n.get("link")
                pub = n.get("publisher") or ""
                s = n.get("sentiment", 0.0)
                tone = "🟢" if s > 0.15 else ("🔴" if s < -0.15 else "⚪")
                nc1, nc2 = st.columns([6, 1])
                if link:
                    nc1.markdown(f"{tone} [{t}]({link})  ·  _{pub}_")
                else:
                    nc1.markdown(f"{tone} {t}  ·  _{pub}_")
                if nc2.button("⭐ 촉매로 기록", key=f"quickcat_{sym}_{i}"):
                    kind = "악재" if s < 0 else "호재"
                    ST.add_catalyst(sym, str(dt.date.today()), kind, t,
                                    float(price or 0), 0, 50, "뉴스에서 원클릭 기록",
                                    db_path=current_db())
                    st.success("촉매로 기록했습니다 — 아래 목록에서 반영도를 조정하세요.")
                    st.rerun()
        else:
            st.write("뉴스 없음.")


def render_catalysts(sym, price):
    guide_header("📰 촉매(호재/악재) 반영 추적", "catalysts", key=f"g_cat_{sym}")
    st.caption("현재가가 최근 호재/악재를 얼마나 반영했는지 본인 평가로 기록·분석.")

    with st.form(f"cat_{sym}", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        cdate = c1.date_input("날짜", value=dt.date.today())
        ckind = c2.selectbox("구분", ["호재", "악재"])
        cprice = c3.number_input("당시 주가", value=float(price or 0), step=0.1, format="%.2f")
        headline = st.text_input("헤드라인 / 이슈")
        c4, c5 = st.columns(2)
        exp = c4.slider("기대 영향 (%)", -30, 30, 0,
                        help="이 이슈가 적정가에 줄 영향 추정(±)")
        refl = c5.slider("현재가 반영도 (%)", 0, 100, 50,
                         help="현재 주가가 이 이슈를 얼마나 반영했다고 보는가")
        note = st.text_area("메모", height=68)
        if st.form_submit_button("➕ 기록 추가", type="primary") and headline:
            ST.add_catalyst(sym, str(cdate), ckind, headline, cprice, exp, refl, note,
                            db_path=current_db())
            st.success("기록됨")
            st.rerun()

    cats = ST.list_catalysts(sym, db_path=current_db())
    if cats:
        for c in cats:
            icon = "🟢" if c["kind"] == "호재" else "🔴"
            with st.container(border=True):
                cc1, cc2 = st.columns([6, 1])
                cc1.markdown(f"{icon} **{c['headline']}**  ·  {c['date']}")
                cc1.caption(f"당시가 {fmt_money(c['price_at'])} · 기대영향 {c['expected_impact']:+.0f}% "
                            f"· 반영도 {c['reflected_pct']:.0f}%"
                            + (f" · {c['note']}" if c['note'] else ""))
                # 반영도 진행바
                cc1.progress(min(1.0, max(0.0, (c['reflected_pct'] or 0) / 100)))
                if cc2.button("삭제", key=f"delcat_{c['id']}"):
                    ST.delete_catalyst(c["id"], db_path=current_db())
                    st.rerun()
        # 미반영 기회 요약
        under = [c for c in cats if (c["reflected_pct"] or 0) < 50]
        if under:
            st.info(f"💡 반영도 50% 미만 이슈 {len(under)}건 — 아직 주가에 덜 반영된 "
                    f"촉매가 있을 수 있습니다.")
    else:
        st.write("기록된 촉매가 없습니다.")


def render_trades(sym, price):
    guide_header("💰 매매 기록 & 손익", "trades", key=f"g_tr_{sym}")

    with st.form(f"trade_{sym}", clear_on_submit=True):
        t1, t2, t3, t4 = st.columns(4)
        tdate = t1.date_input("날짜", value=dt.date.today())
        action = t2.selectbox("구분", ["BUY", "SELL"])
        tprice = t3.number_input("체결가", value=float(price or 0), step=0.1, format="%.2f")
        tshares = t4.number_input("수량", value=0.0, step=1.0, format="%.2f")
        reason = st.text_input("매매 근거 (필수 기록 권장)")
        if st.form_submit_button("➕ 기록 추가", type="primary") and tshares > 0:
            ST.add_trade(sym, str(tdate), action, tprice, tshares, reason,
                         db_path=current_db())
            st.success("기록됨")
            st.rerun()

    pos = ST.position_summary(sym, db_path=current_db())
    if pos["shares"] > 0:
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Shares", f"{pos['shares']:.0f}")
        p2.metric("Avg Cost", fmt_money(pos["avg_price"]))
        cur_val = pos["shares"] * price if price else None
        p3.metric("Market Value", fmt_money(cur_val))
        if price and pos["avg_price"]:
            pl = (price - pos["avg_price"]) * pos["shares"]
            pl_pct = (price - pos["avg_price"]) / pos["avg_price"] * 100
            p4.metric("Unrealized P/L", fmt_money(pl), f"{pl_pct:.1f}%")

    trades = ST.list_trades(sym, db_path=current_db())
    if trades:
        st.markdown("**거래 내역**")
        for tr in trades:
            with st.container(border=True):
                tc1, tc2 = st.columns([6, 1])
                badge = "🟩 매수" if tr["action"] == "BUY" else "🟥 매도"
                tc1.markdown(f"{badge}  ·  {tr['date']}  ·  "
                             f"{tr['shares']:.0f}주 @ {fmt_money(tr['price'])}")
                if tr["reason"]:
                    tc1.caption(tr["reason"])
                if tc2.button("삭제", key=f"deltr_{tr['id']}"):
                    ST.delete_trade(tr["id"], db_path=current_db())
                    st.rerun()
    else:
        st.write("매매 기록이 없습니다.")


# ============================================================ 스캐너 + 알림
def render_scanner():
    st.title("워치리스트 스캐너")
    st.caption("전체 종목을 한 번에 스캔 — 점수·판정·밸류에이션·현재 추세와 "
               "최근 추세 전환(알림)을 표로 봅니다. (일봉 SMA 기준)")
    if not tickers:
        st.info("사이드바에서 종목을 추가하면 여기서 일괄 스캔됩니다.")
        return

    alerts, rows = [], []
    for t in tickers:
        sym = t["symbol"]
        q = cached_quote(sym)
        f = cached_fundamentals(sym)
        df = cached_history(sym, "6mo", "1d")
        sig = CH.latest_signal(df, "1d")
        card = ST.load_scorecard(sym, db_path=current_db())
        total = SC.weighted_total(card) if card else None
        verdict = SC.verdict(total)[0] if total is not None else "—"
        if sig["recent"]:
            alerts.append((sym, sig["recent"]))
        trend = sig["trend"]
        trend_txt = "🟢 상승" if trend == "up" else ("🔴 하락" if trend == "down" else "—")
        rec = sig["recent"]
        rec_txt = "—"
        if rec:
            rec_txt = (f"{'▲' if rec['type']=='up' else '▼'} "
                       f"{rec['bars_ago']}봉 전 전환")
        rows.append({
            "Ticker": sym,
            "Type": "Long" if t["kind"] == "long" else "Swing",
            "Price": q.get("price"),
            "Change %": q.get("change_pct"),
            "Score": total,
            "Verdict": verdict,
            "Fwd P/E": f.get("forward_pe"),
            "Trend": trend_txt,
            "최근 전환": rec_txt,
        })

    # 추세전환 알림 배너
    if alerts:
        st.markdown("#### ⚠️ 추세 전환 알림 (최근 5봉 이내)")
        for sym, rec in alerts:
            if rec["type"] == "up":
                st.success(f"🟢 **{sym}** — {rec['bars_ago']}봉 전 **상승 전환**"
                           f"(골든크로스). 스윙 진입 후보.")
            else:
                st.error(f"🔴 **{sym}** — {rec['bars_ago']}봉 전 **하락 전환**"
                         f"(데드크로스). 리스크 점검 권장.")
    else:
        st.caption("최근 5봉 이내 추세 전환 없음.")

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True, column_config={
        "Price": st.column_config.NumberColumn(format="$%.2f"),
        "Change %": st.column_config.NumberColumn(format="%.2f%%"),
        "Score": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f"),
        "Fwd P/E": st.column_config.NumberColumn(format="%.1f"),
    })
    st.caption("추세: 일봉 SMA20 vs SMA50 · 점수 ≥70 매수 / 60~70 소액 / <60 보류")


# ================================================================ 라우팅
if page == "📊 대시보드":
    render_dashboard()
elif page == "🔎 스캐너":
    render_scanner()
elif page == "🔍 종목 상세":
    if selected:
        render_detail(selected)
    else:
        st.title("🔍 종목 상세")
        st.info("사이드바에서 종목을 추가/선택하세요.")
