"""Real-time Web Dashboard (http://localhost:8050) for ESP32-S3 Wi-Fi CSI Motion Detection.

Clean, production-ready single-screen interface following UI/UX Pro Max standards:
- DSP + Adaptive Dual-Threshold Hysteresis (CFAR-style) motion detection
- Consistent, accurate Vietnamese technical terminology
- Automatic USB COM port discovery & TX link liveness monitoring
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wifisense.detectors import MotionConfig, MotionDetector
from wifisense.pipeline import Engine, ReplaySource, SerialSource

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CALIB = os.path.join(HERE, "..", "models", "motion_calib.json")

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Giám sát Chuyển động Wi-Fi CSI</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #090b10;
    --surface-1: #0f131c;
    --surface-2: #141925;
    --surface-3: #1b2232;
    --surface-plot: #0a0d14;
    --border: rgba(255, 255, 255, 0.08);
    --border-strong: rgba(255, 255, 255, 0.15);
    --text-primary: #f1f5f9;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
    --accent-idle: #10b981;
    --accent-motion: #38bdf8;
    --accent-warn: #f59e0b;
    --accent-thr: #f43f5e;
    --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    --font-mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }

  * {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }

  body {
    background-color: var(--bg);
    background-image:
      radial-gradient(ellipse 80% 50% at 50% -15%, rgba(56, 189, 248, 0.07), transparent),
      linear-gradient(180deg, #090b10 0%, #07090e 100%);
    color: var(--text-primary);
    font-family: var(--font-sans);
    min-height: 100dvh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 16px 20px;
    -webkit-font-smoothing: antialiased;
  }

  button {
    font-family: var(--font-sans);
    user-select: none;
    white-space: nowrap;
    cursor: pointer;
  }

  button:focus-visible {
    outline: 2px solid var(--accent-motion);
    outline-offset: 2px;
  }

  .num {
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
  }

  /* Main Shell */
  .shell {
    width: 100%;
    max-width: 1120px;
    background: var(--surface-1);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 20px 24px;
    display: flex;
    flex-direction: column;
    gap: 16px;
    box-shadow:
      0 1px 0 0 rgba(255, 255, 255, 0.04) inset,
      0 24px 48px -12px rgba(0, 0, 0, 0.65);
  }

  /* Top Header */
  .topbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 16px;
    padding-bottom: 14px;
    border-bottom: 1px solid var(--border);
    flex-wrap: wrap;
  }

  .brand {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .brand-mark {
    width: 36px;
    height: 36px;
    border-radius: 10px;
    background: var(--surface-2);
    border: 1px solid var(--border-strong);
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--accent-motion);
    flex-shrink: 0;
  }

  .brand-text h1 {
    font-size: 16px;
    font-weight: 700;
    letter-spacing: -0.01em;
    color: var(--text-primary);
    line-height: 1.25;
  }

  .brand-meta {
    font-size: 12px;
    color: var(--text-muted);
    margin-top: 2px;
  }

  .topbar-right {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }

  .source-btn {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    height: 34px;
    padding: 0 13px;
    border-radius: 8px;
    background: var(--surface-2);
    border: 1px solid var(--border);
    color: var(--text-primary);
    font-size: 12.5px;
    font-weight: 600;
    transition: background 160ms ease, border-color 160ms ease;
  }

  .source-btn:hover {
    background: var(--surface-3);
    border-color: var(--border-strong);
  }

  .source-btn:active {
    opacity: 0.88;
  }

  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--accent-idle);
    flex-shrink: 0;
  }

  .link-readout {
    display: inline-flex;
    align-items: center;
    gap: 12px;
    height: 34px;
    padding: 0 14px;
    border-radius: 8px;
    background: var(--surface-2);
    border: 1px solid var(--border);
    font-size: 12.5px;
    color: var(--text-secondary);
    user-select: none;
    white-space: nowrap;
  }

  .link-sep {
    width: 1px;
    height: 14px;
    background: var(--border);
  }

  /* Hero Status Card */
  .hero {
    position: relative;
    overflow: hidden;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 20px;
    padding: 16px 20px;
    border-radius: 12px;
    background: rgba(16, 185, 129, 0.06);
    border: 1px solid rgba(16, 185, 129, 0.24);
    transition: background 200ms ease, border-color 200ms ease;
  }

  .hero.state-motion {
    background: rgba(56, 189, 248, 0.09);
    border-color: rgba(56, 189, 248, 0.42);
  }

  .hero.state-warn {
    background: rgba(245, 158, 11, 0.08);
    border-color: rgba(245, 158, 11, 0.36);
  }

  .hero-main {
    display: flex;
    align-items: center;
    gap: 14px;
    min-width: 0;
  }

  .hero-beacon {
    position: relative;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: var(--accent-idle);
    flex-shrink: 0;
  }

  .hero-beacon::after {
    content: "";
    position: absolute;
    inset: -5px;
    border-radius: 50%;
    border: 1.5px solid currentColor;
    opacity: 0.35;
    animation: pulseRing 2.2s ease-out infinite;
  }

  @keyframes pulseRing {
    0% { transform: scale(0.75); opacity: 0.55; }
    100% { transform: scale(1.65); opacity: 0; }
  }

  .hero-title {
    font-size: 18px;
    font-weight: 700;
    letter-spacing: -0.01em;
    color: var(--text-primary);
    line-height: 1.3;
  }

  .hero-desc {
    font-size: 13px;
    color: var(--text-secondary);
    margin-top: 3px;
    line-height: 1.4;
  }

  .hero-readouts {
    display: flex;
    align-items: center;
    gap: 20px;
    flex-shrink: 0;
  }

  .hero-divider {
    width: 1px;
    height: 34px;
    background: var(--border);
  }

  .readout-block {
    text-align: right;
  }

  .readout-val {
    font-size: 20px;
    font-weight: 700;
    color: var(--text-primary);
    line-height: 1.2;
  }

  .readout-lbl {
    font-size: 11px;
    font-weight: 500;
    color: var(--text-muted);
    margin-top: 3px;
  }

  .calib-progress {
    position: absolute;
    left: 0;
    bottom: 0;
    height: 3px;
    background: var(--accent-warn);
    width: 0%;
    transition: width 150ms linear;
  }

  /* Chart Panel */
  .chart-panel {
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 14px 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .chart-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
  }

  .segmented {
    display: inline-flex;
    background: var(--surface-plot);
    border: 1px solid var(--border);
    padding: 3px;
    border-radius: 8px;
    gap: 2px;
  }

  .seg-btn {
    height: 28px;
    padding: 0 12px;
    border-radius: 6px;
    border: none;
    background: transparent;
    color: var(--text-secondary);
    font-size: 12px;
    font-weight: 600;
    transition: background 150ms ease, color 150ms ease;
  }

  .seg-btn:hover {
    color: var(--text-primary);
  }

  .seg-btn.active {
    background: var(--surface-3);
    color: var(--text-primary);
  }

  .legend {
    display: flex;
    align-items: center;
    gap: 16px;
    font-size: 12px;
    color: var(--text-secondary);
    user-select: none;
    flex-wrap: wrap;
  }

  .legend-item {
    display: inline-flex;
    align-items: center;
    gap: 7px;
  }

  .swatch-solid {
    width: 14px;
    height: 2.5px;
    border-radius: 2px;
  }

  .swatch-dashed {
    width: 14px;
    height: 0;
    border-top: 2px dashed;
  }

  .canvas-frame {
    width: 100%;
    height: 192px;
    background: var(--surface-plot);
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: 8px;
    position: relative;
    overflow: hidden;
  }

  canvas {
    width: 100%;
    height: 100%;
    display: block;
  }

  /* Bottom 3-Column Bento */
  .bento-grid {
    display: grid;
    grid-template-columns: 1.1fr 1.1fr 1fr;
    gap: 14px;
  }

  .card {
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 15px 16px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    gap: 12px;
  }

  .card-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
  }

  .card-title {
    font-size: 11.5px;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--text-secondary);
    user-select: none;
  }

  .card-meta {
    font-size: 11.5px;
    color: var(--text-muted);
  }

  /* Card 1: Signal Parameters */
  .kv-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }

  .kv-box {
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: 8px;
    padding: 9px 11px;
  }

  .kv-label {
    font-size: 11.5px;
    color: var(--text-muted);
    font-weight: 500;
  }

  .kv-value {
    font-size: 16px;
    font-weight: 700;
    color: var(--text-primary);
    margin-top: 3px;
  }

  .meter-wrap {
    display: flex;
    flex-direction: column;
    gap: 5px;
  }

  .meter-labels {
    display: flex;
    justify-content: space-between;
    font-size: 11.5px;
    color: var(--text-muted);
  }

  .meter-track {
    position: relative;
    width: 100%;
    height: 6px;
    background: var(--surface-plot);
    border-radius: 3px;
    overflow: hidden;
  }

  .meter-fill {
    height: 100%;
    border-radius: 3px;
    background: var(--accent-idle);
    width: 0%;
    transition: width 140ms ease, background 180ms ease;
  }

  .meter-marker {
    position: absolute;
    top: 0;
    bottom: 0;
    width: 2px;
    background: var(--accent-thr);
    left: 66.6%;
  }

  /* Card 2: Calibration & Sensitivity */
  .field-group {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .field-label {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 12px;
    font-weight: 500;
    color: var(--text-secondary);
  }

  .sens-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 4px;
    background: var(--surface-plot);
    border: 1px solid var(--border);
    padding: 3px;
    border-radius: 8px;
  }

  .sens-opt {
    height: 30px;
    border: none;
    border-radius: 6px;
    background: transparent;
    color: var(--text-secondary);
    font-size: 12px;
    font-weight: 600;
    transition: background 150ms ease, color 150ms ease;
  }

  .sens-opt:hover {
    color: var(--text-primary);
  }

  .sens-opt.active {
    background: var(--surface-3);
    color: var(--accent-motion);
  }

  .sens-note {
    font-size: 11.5px;
    color: var(--text-muted);
    line-height: 1.4;
    min-height: 32px;
  }

  .calib-btn {
    width: 100%;
    height: 36px;
    border-radius: 8px;
    border: 1px solid rgba(56, 189, 248, 0.35);
    background: rgba(56, 189, 248, 0.12);
    color: #e0f2fe;
    font-size: 12.5px;
    font-weight: 600;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    transition: background 150ms ease, border-color 150ms ease;
  }

  .calib-btn:hover {
    background: rgba(56, 189, 248, 0.2);
    border-color: rgba(56, 189, 248, 0.55);
  }

  .calib-btn.running {
    background: rgba(245, 158, 11, 0.16);
    border-color: rgba(245, 158, 11, 0.5);
    color: #fef3c7;
  }

  /* Card 3: Event Log */
  .ghost-btn {
    height: 24px;
    padding: 0 8px;
    border-radius: 5px;
    border: 1px solid var(--border);
    background: transparent;
    color: var(--text-muted);
    font-size: 11px;
    font-weight: 500;
    transition: color 150ms ease, border-color 150ms ease;
  }

  .ghost-btn:hover {
    color: var(--text-primary);
    border-color: var(--border-strong);
  }

  .log-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
    height: 118px;
    overflow-y: auto;
    padding-right: 4px;
  }

  .log-list::-webkit-scrollbar {
    width: 4px;
  }

  .log-list::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.12);
    border-radius: 2px;
  }

  .log-row {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    font-size: 12px;
    line-height: 1.4;
    color: var(--text-secondary);
  }

  .log-time {
    font-size: 11px;
    color: var(--text-muted);
    flex-shrink: 0;
    padding-top: 1px;
  }

  .tag {
    font-size: 10px;
    font-weight: 700;
    padding: 1px 6px;
    border-radius: 4px;
    flex-shrink: 0;
    letter-spacing: 0.02em;
    user-select: none;
  }

  .tag-mot { background: rgba(56, 189, 248, 0.16); color: #7dd3fc; }
  .tag-idle { background: rgba(16, 185, 129, 0.15); color: #6ee7b7; }
  .tag-cal { background: rgba(245, 158, 11, 0.18); color: #fcd34d; }
  .tag-sys { background: rgba(255, 255, 255, 0.07); color: var(--text-secondary); }

  @media (max-width: 920px) {
    .bento-grid {
      grid-template-columns: 1fr;
    }
    .hero {
      flex-direction: column;
      align-items: flex-start;
    }
    .hero-readouts {
      width: 100%;
      justify-content: flex-start;
    }
    .readout-block {
      text-align: left;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
      animation-duration: 0.01ms !important;
      animation-iteration-count: 1 !important;
      transition-duration: 0.01ms !important;
    }
  }
</style>
</head>
<body>

<main class="shell">

  <!-- Top Navigation -->
  <header class="topbar">
    <div class="brand">
      <div class="brand-mark" aria-hidden="true">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M4.9 19.1C1 15.2 1 8.8 4.9 4.9"/>
          <path d="M7.8 16.2c-2.3-2.3-2.3-6.1 0-8.5"/>
          <circle cx="12" cy="12" r="2"/>
          <path d="M16.2 7.8c2.3 2.3 2.3 6.1 0 8.5"/>
          <path d="M19.1 4.9C23 8.8 23 15.2 19.1 19.1"/>
        </svg>
      </div>
      <div class="brand-text">
        <h1>Giám sát Chuyển động Wi-Fi CSI</h1>
        <div class="brand-meta">ESP32-S3 · ESP-NOW HT20 · 52 sóng mang L-LTF</div>
      </div>
    </div>

    <div class="topbar-right">
      <button type="button" class="source-btn" onclick="api('/toggle_source')" title="Chuyển đổi giữa Cổng USB trực tiếp và Chế độ phát dữ liệu mẫu">
        <span class="status-dot" id="dotSource"></span>
        <span id="txtSource">Cổng USB: COM4</span>
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color:var(--text-muted);" aria-hidden="true">
          <path d="M7 16V4m0 0L3 8m4-4l4 4M17 8v12m0 0l4-4m-4 4l-4-4"/>
        </svg>
      </button>

      <div class="link-readout">
        <span>Tốc độ nhận: <strong class="num" id="txtRate" style="color:var(--text-primary);">0.0 gói/s</strong></span>
        <span class="link-sep" aria-hidden="true"></span>
        <span>RSSI: <strong class="num" id="txtRssi" style="color:var(--text-primary);">-- dBm</strong></span>
      </div>
    </div>
  </header>

  <!-- Primary Status Hero -->
  <section class="hero" id="heroBanner" role="status" aria-live="polite">
    <div class="hero-main">
      <div class="hero-beacon" id="heroBeacon" style="color:var(--accent-idle);"></div>
      <div>
        <div class="hero-title" id="heroTitle">Đang khởi tạo kết nối...</div>
        <div class="hero-desc" id="heroDesc">Đang thu thập cửa sổ mẫu CSI đầu tiên để phân tích phương sai biên độ.</div>
      </div>
    </div>

    <div class="hero-readouts">
      <div class="readout-block">
        <div class="readout-val num" id="heroScore">0.000 dB</div>
        <div class="readout-lbl">Độ biến thiên CSI</div>
      </div>
      <div style="width:1px; height:34px; background:var(--border);" aria-hidden="true"></div>
      <div class="readout-block">
        <div class="readout-val num" id="heroThr" style="color:var(--accent-thr);">0.000 dB</div>
        <div class="readout-lbl">Ngưỡng kích hoạt</div>
      </div>
    </div>

    <div class="calib-progress" id="calibBar"></div>
  </section>

  <!-- Signal Visualization -->
  <section class="chart-panel" aria-label="Biểu đồ tín hiệu CSI">
    <div class="chart-bar">
      <div class="segmented" role="tablist">
        <button type="button" role="tab" aria-selected="true" class="seg-btn active" id="tabWave" onclick="setTab('wave')">Độ biến thiên CSI theo thời gian</button>
        <button type="button" role="tab" aria-selected="false" class="seg-btn" id="tabWaterfall" onclick="setTab('waterfall')">Phổ biên độ 52 sóng mang</button>
      </div>

      <div class="legend" id="waveLegend">
        <span class="legend-item"><span class="swatch-solid" style="background:var(--accent-motion);"></span>Độ biến thiên CSI</span>
        <span class="legend-item"><span class="swatch-dashed" style="border-color:var(--accent-thr);"></span>Ngưỡng kích hoạt</span>
        <span class="legend-item"><span class="swatch-dashed" style="border-color:var(--accent-warn);"></span>Ngưỡng duy trì</span>
        <span class="legend-item"><span class="swatch-dashed" style="border-color:var(--text-muted);"></span>Mức nhiễu nền</span>
      </div>
    </div>

    <div class="canvas-frame">
      <canvas id="cvMain"></canvas>
    </div>
  </section>

  <!-- Bottom 3-Column Bento -->
  <section class="bento-grid">

    <!-- Column 1: Signal Metrics -->
    <div class="card">
      <div class="card-head">
        <span class="card-title">Thông số Tín hiệu & Nhiễu nền</span>
        <span class="card-meta num" id="txtTotalPkts">0 gói</span>
      </div>

      <div class="kv-grid">
        <div class="kv-box">
          <div class="kv-label">Độ biến thiên hiện tại</div>
          <div class="kv-value num" id="kvScore">0.000 dB</div>
        </div>
        <div class="kv-box">
          <div class="kv-label">Mức nhiễu nền (±σ)</div>
          <div class="kv-value num" id="kvBase">0.000 ± 0.000</div>
        </div>
        <div class="kv-box">
          <div class="kv-label">Ngưỡng kích hoạt</div>
          <div class="kv-value num" id="kvThrOn" style="color:#fda4af;">0.000 dB</div>
        </div>
        <div class="kv-box">
          <div class="kv-label">Ngưỡng duy trì</div>
          <div class="kv-value num" id="kvThrOff" style="color:#fcd34d;">0.000 dB</div>
        </div>
      </div>

      <div class="meter-wrap">
        <div class="meter-labels">
          <span>Tỉ lệ so với ngưỡng kích hoạt</span>
          <span class="num" id="txtRatio">0%</span>
        </div>
        <div class="meter-track" title="Vạch đỏ biểu thị vị trí 100% Ngưỡng kích hoạt">
          <div class="meter-fill" id="meterFill"></div>
          <div class="meter-marker"></div>
        </div>
      </div>
    </div>

    <!-- Column 2: Calibration & Sensitivity -->
    <div class="card">
      <div class="card-head">
        <span class="card-title">Hiệu chuẩn & Độ nhạy</span>
        <span class="card-meta">Cửa sổ lọc: 1.2s · 6 Hz</span>
      </div>

      <div class="field-group">
        <div class="field-label">
          <span>Độ nhạy phát hiện</span>
          <span class="num" id="txtSensFactor" style="color:var(--text-muted); font-size:11px;">Hệ số chuẩn</span>
        </div>
        <div class="sens-grid" role="group" aria-label="Chọn độ nhạy phát hiện">
          <button type="button" class="sens-opt" id="sens_high" onclick="setSens('high')">Cao</button>
          <button type="button" class="sens-opt active" id="sens_normal" onclick="setSens('normal')">Trung bình</button>
          <button type="button" class="sens-opt" id="sens_low" onclick="setSens('low')">Thấp</button>
        </div>
        <div class="sens-note" id="txtSensNote">Cân bằng giữa độ nhạy phát hiện và khả năng lọc nhiễu nền thông thường.</div>
      </div>

      <button type="button" class="calib-btn" id="btnCalib" onclick="api('/calibrate')">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3"/>
        </svg>
        <span id="txtCalib">Đo lại nhiễu nền (30 giây)</span>
      </button>
    </div>

    <!-- Column 3: State Log -->
    <div class="card">
      <div class="card-head">
        <span class="card-title">Nhật ký Trạng thái</span>
        <button type="button" class="ghost-btn" onclick="api('/clear_events')">Xóa nhật ký</button>
      </div>

      <div class="log-list" id="logList">
        <div class="log-row"><span class="log-time num">--:--:--</span><span>Đang kết nối...</span></div>
      </div>
    </div>

  </section>

</main>

<script>
let activeTab = 'wave';

const SENS_INFO = {
  high: {
    factor: 'Hệ số ×0.74',
    note: 'Ngưỡng thấp — nhạy hơn với cử động nhẹ, phù hợp khi phòng ít nhiễu sóng.'
  },
  normal: {
    factor: 'Hệ số ×1.00',
    note: 'Cân bằng giữa độ nhạy phát hiện và khả năng lọc nhiễu nền thông thường.'
  },
  low: {
    factor: 'Hệ số ×1.35',
    note: 'Ngưỡng cao — giảm khả năng báo nhầm khi môi trường có nhiều nhiễu RF.'
  }
};

function setTab(t) {
  activeTab = t;
  const isWave = t === 'wave';
  const bWave = document.getElementById('tabWave');
  const bWf = document.getElementById('tabWaterfall');
  bWave.className = 'seg-btn ' + (isWave ? 'active' : '');
  bWf.className = 'seg-btn ' + (!isWave ? 'active' : '');
  bWave.setAttribute('aria-selected', isWave ? 'true' : 'false');
  bWf.setAttribute('aria-selected', !isWave ? 'true' : 'false');
  document.getElementById('waveLegend').style.display = isWave ? 'flex' : 'none';
}

async function api(path) {
  try { await fetch(path, { method: 'POST' }); } catch (e) {}
}

async function setSens(level) {
  await api('/sensitivity?v=' + encodeURIComponent(level));
}

function colormap(t) {
  t = Math.max(0, Math.min(1, t));
  const r = Math.round(255 * Math.min(1, Math.max(0, 1.45 * t - 0.18)));
  const g = Math.round(255 * Math.sin(t * Math.PI * 0.85));
  const b = Math.round(255 * (0.52 + 0.48 * Math.cos(t * 2.4)));
  return `rgb(${r},${g},${b})`;
}

const canvas = document.getElementById('cvMain');
function prepareCanvas() {
  const rect = canvas.parentElement.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const w = Math.floor(rect.width * dpr);
  const h = Math.floor(rect.height * dpr);
  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w;
    canvas.height = h;
  }
  const ctx = canvas.getContext('2d');
  ctx.resetTransform?.();
  ctx.scale(dpr, dpr);
  return { ctx, W: rect.width, H: rect.height };
}

function drawWaveChart(s) {
  const { ctx, W, H } = prepareCanvas();
  ctx.clearRect(0, 0, W, H);

  const padL = 12, padR = 56, padT = 14, padB = 22;
  const plotW = Math.max(40, W - padL - padR);
  const plotH = Math.max(40, H - padT - padB);

  const scores = s.h_score || [];
  const motions = s.h_motion || [];
  const N = scores.length;

  const rawMax = Math.max(
    N ? Math.max(...scores) : 0.15,
    (s.thr_on || 0.18) * 1.38,
    0.22
  );
  const stepDb = rawMax <= 0.25 ? 0.05 : (rawMax <= 0.5 ? 0.10 : 0.20);
  const maxY = Math.ceil(rawMax / stepDb) * stepDb;

  const yOf = (val) => padT + plotH - (Math.min(Math.max(val, 0), maxY) / maxY) * plotH;

  // Grid & Right Y-Axis dB Labels
  ctx.font = '500 10.5px "JetBrains Mono", monospace';
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';

  for (let v = 0; v <= maxY + 1e-6; v += stepDb) {
    const y = Math.round(yOf(v)) + 0.5;
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.045)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padL, y);
    ctx.lineTo(padL + plotW, y);
    ctx.stroke();

    ctx.fillStyle = '#64748b';
    ctx.fillText(v.toFixed(2), padL + plotW + 8, y);
  }

  // Bottom Time Axis Labels (200 hops * ~0.08s ≈ 16s history)
  const histSec = 16;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillStyle = '#64748b';
  [0, 0.25, 0.5, 0.75, 1.0].forEach(frac => {
    const x = padL + frac * plotW;
    const secAgo = Math.round((1 - frac) * histSec);
    const lbl = secAgo === 0 ? 'Hiện tại' : `-${secAgo}s`;
    ctx.fillText(lbl, frac === 1 ? x - 14 : (frac === 0 ? x + 12 : x), padT + plotH + 6);
  });

  if (!N) return;

  const MAX_HIST = 200;
  const xOf = (i) => padL + ((MAX_HIST - N + i) / (MAX_HIST - 1)) * plotW;

  // Motion Interval Highlight
  ctx.fillStyle = 'rgba(56, 189, 248, 0.09)';
  const stepX = plotW / (MAX_HIST - 1);
  for (let i = 0; i < N; i++) {
    if (motions[i]) {
      ctx.fillRect(xOf(i), padT, Math.ceil(stepX) + 1, plotH);
    }
  }

  // Baseline Median Reference Line
  if (s.baseline_median > 0) {
    const yBase = yOf(s.baseline_median);
    ctx.strokeStyle = 'rgba(148, 163, 184, 0.35)';
    ctx.setLineDash([2, 4]);
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padL, yBase);
    ctx.lineTo(padL + plotW, yBase);
    ctx.stroke();
  }

  // Hysteresis Release Threshold (thr_off)
  if (s.thr_off > 0) {
    const yOff = yOf(s.thr_off);
    ctx.strokeStyle = 'rgba(245, 158, 11, 0.7)';
    ctx.setLineDash([4, 4]);
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.moveTo(padL, yOff);
    ctx.lineTo(padL + plotW, yOff);
    ctx.stroke();
  }

  // Activation Threshold (thr_on)
  if (s.thr_on > 0) {
    const yOn = yOf(s.thr_on);
    ctx.strokeStyle = '#f43f5e';
    ctx.setLineDash([6, 4]);
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(padL, yOn);
    ctx.lineTo(padL + plotW, yOn);
    ctx.stroke();
  }
  ctx.setLineDash([]);

  // Area Fill under CSI Variation Curve
  const grad = ctx.createLinearGradient(0, padT, 0, padT + plotH);
  grad.addColorStop(0, 'rgba(56, 189, 248, 0.22)');
  grad.addColorStop(1, 'rgba(56, 189, 248, 0.0)');
  ctx.fillStyle = grad;

  ctx.beginPath();
  ctx.moveTo(xOf(0), padT + plotH);
  for (let i = 0; i < N; i++) {
    ctx.lineTo(xOf(i), yOf(scores[i]));
  }
  ctx.lineTo(xOf(N - 1), padT + plotH);
  ctx.closePath();
  ctx.fill();

  // Smooth CSI Variation Line
  ctx.strokeStyle = '#38bdf8';
  ctx.lineWidth = 2;
  ctx.lineJoin = 'round';
  ctx.beginPath();
  for (let i = 0; i < N; i++) {
    const x = xOf(i);
    const y = yOf(scores[i]);
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }
  ctx.stroke();

  // Live Endpoint Dot
  const lastX = xOf(N - 1);
  const lastY = yOf(scores[N - 1]);
  ctx.fillStyle = s.motion ? '#38bdf8' : '#10b981';
  ctx.beginPath();
  ctx.arc(lastX, lastY, 3.5, 0, Math.PI * 2);
  ctx.fill();
}

function drawWaterfallChart(s) {
  const { ctx, W, H } = prepareCanvas();
  ctx.fillStyle = '#0a0d14';
  ctx.fillRect(0, 0, W, H);

  const wf = s.wf || [];
  const padL = 12, padR = 56, padT = 10, padB = 22;
  const plotW = Math.max(40, W - padL - padR);
  const plotH = Math.max(40, H - padT - padB);

  // Subcarrier index labels on right axis (-26 .. +26)
  ctx.font = '500 10.5px "JetBrains Mono", monospace';
  ctx.fillStyle = '#64748b';
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';
  [
    { frac: 0.0, lbl: '+26' },
    { frac: 0.25, lbl: '+13' },
    { frac: 0.5, lbl: '±1' },
    { frac: 0.75, lbl: '-13' },
    { frac: 1.0, lbl: '-26' }
  ].forEach(tk => {
    ctx.fillText(tk.lbl, padL + plotW + 8, padT + tk.frac * plotH);
  });

  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillText('Cũ hơn', padL + 22, padT + plotH + 6);
  ctx.fillText('Hiện tại', padL + plotW - 18, padT + plotH + 6);

  if (!wf.length) return;

  const MAX_WF = 150;
  const T = wf.length, S = wf[0].length;
  const cw = plotW / MAX_WF, ch = plotH / S;
  let maxV = 16;
  for (let i = 0; i < T; i++) {
    for (let j = 0; j < S; j++) {
      if (wf[i][j] > maxV) maxV = wf[i][j];
    }
  }

  for (let i = 0; i < T; i++) {
    const x = padL + (MAX_WF - T + i) * cw;
    for (let j = 0; j < S; j++) {
      ctx.fillStyle = colormap(wf[i][j] / maxV);
      ctx.fillRect(x, padT + plotH - (j + 1) * ch, Math.ceil(cw) + 0.5, Math.ceil(ch));
    }
  }
}

async function poll() {
  try {
    const r = await fetch('/state?lang=' + document.documentElement.lang, { cache: 'no-store' });
    const s = await r.json();

    // Header Source & Link Readouts
    const isReplay = s.source_mode === 'replay';
    const dot = document.getElementById('dotSource');
    const txtSrc = document.getElementById('txtSource');

    if (isReplay) {
      txtSrc.textContent = 'Chế độ phát mẫu';
      dot.style.background = '#38bdf8';
    } else if (s.connected && s.tx_alive) {
      txtSrc.textContent = `Cổng USB: ${s.port}`;
      dot.style.background = '#10b981';
    } else if (s.connected) {
      txtSrc.textContent = `Cổng USB: ${s.port} (Chờ TX)`;
      dot.style.background = '#f59e0b';
    } else {
      txtSrc.textContent = `Đang dò USB (${s.port})`;
      dot.style.background = '#f59e0b';
    }

    document.getElementById('txtRate').textContent = `${s.rate.toFixed(1)} gói/s`;
    document.getElementById('txtRssi').textContent = s.tx_alive ? `${s.rssi.toFixed(0)} dBm` : '-- dBm';

    // Hero Banner State
    const hero = document.getElementById('heroBanner');
    const beacon = document.getElementById('heroBeacon');
    const hTitle = document.getElementById('heroTitle');
    const hDesc = document.getElementById('heroDesc');
    const hScore = document.getElementById('heroScore');
    const hThr = document.getElementById('heroThr');
    const cBar = document.getElementById('calibBar');

    hScore.textContent = `${s.score.toFixed(3)} dB`;
    hThr.textContent = `${s.thr_on.toFixed(3)} dB`;

    if (s.calibrating) {
      hero.className = 'hero state-warn';
      beacon.style.background = 'var(--accent-warn)';
      beacon.style.color = 'var(--accent-warn)';
      const rem = Math.ceil(s.calib_remaining);
      const pct = Math.min(100, Math.max(0, ((30 - s.calib_remaining) / 30) * 100));
      cBar.style.width = `${pct}%`;
      if (rem > 27) {
        hTitle.textContent = `Chuẩn bị đo nhiễu nền (${rem}s)`;
        hDesc.textContent = 'Bỏ qua 3 giây đầu để ổn định tín hiệu — vui lòng đứng yên hoặc rời vùng đo.';
      } else {
        hTitle.textContent = `Đang đo nhiễu nền (còn ${rem} giây)`;
        hDesc.textContent = `Đã thu ${s.calib_samples} mẫu phương sai CSI — giữ không gian tĩnh cho đến khi hoàn tất.`;
      }
      hScore.style.color = 'var(--accent-warn)';
    } else {
      cBar.style.width = '0%';
      if (!isReplay && !s.connected) {
        hero.className = 'hero state-warn';
        beacon.style.background = 'var(--accent-warn)';
        beacon.style.color = 'var(--accent-warn)';
        hTitle.textContent = 'Chưa kết nối mạch thu (RX)';
        hDesc.textContent = 'Cắm cáp USB của mạch thu ESP32-S3 vào máy tính hoặc bấm nút góc phải để mở Chế độ phát mẫu.';
        hScore.style.color = 'var(--text-secondary)';
      } else if (!isReplay && !s.tx_alive) {
        hero.className = 'hero state-warn';
        beacon.style.background = 'var(--accent-warn)';
        beacon.style.color = 'var(--accent-warn)';
        hTitle.textContent = 'Đang chờ gói tin từ mạch phát (TX)';
        hDesc.textContent = `Đã kết nối mạch thu tại ${s.port} nhưng chưa thu được khung sóng ESP-NOW từ mạch phát.`;
        hScore.style.color = 'var(--text-secondary)';
      } else if (s.motion) {
        hero.className = 'hero state-motion';
        beacon.style.background = 'var(--accent-motion)';
        beacon.style.color = 'var(--accent-motion)';
        hTitle.textContent = 'Có chuyển động';
        hDesc.textContent = `Độ biến thiên CSI (${s.score.toFixed(3)} dB) vượt ngưỡng kích hoạt (${s.thr_on.toFixed(3)} dB).`;
        hScore.style.color = 'var(--accent-motion)';
      } else {
        hero.className = 'hero';
        beacon.style.background = 'var(--accent-idle)';
        beacon.style.color = 'var(--accent-idle)';
        hTitle.textContent = 'Không phát hiện chuyển động';
        hDesc.textContent = `Độ biến thiên CSI (${s.score.toFixed(3)} dB) nằm dưới ngưỡng kích hoạt — phòng trống hoặc người đứng yên.`;
        hScore.style.color = 'var(--accent-idle)';
      }
    }

    // Bento 1: Signal Metrics
    document.getElementById('txtTotalPkts').textContent = `${s.total_pkts.toLocaleString()} gói hợp lệ`;
    document.getElementById('kvScore').textContent = `${s.score.toFixed(3)} dB`;
    document.getElementById('kvBase').textContent = `${s.baseline_median.toFixed(3)} ± ${s.baseline_std.toFixed(3)}`;
    document.getElementById('kvThrOn').textContent = `${s.thr_on.toFixed(3)} dB`;
    document.getElementById('kvThrOff').textContent = `${s.thr_off.toFixed(3)} dB`;

    const ratio = s.thr_on > 0 ? (s.score / s.thr_on) * 100 : 0;
    document.getElementById('txtRatio').textContent = `${ratio.toFixed(0)}%`;
    const meterFill = document.getElementById('meterFill');
    // Marker sits at 66.6% of track -> 100% of thr_on maps to 66.6% width
    const barPct = Math.min(100, (ratio / 150) * 100);
    meterFill.style.width = `${barPct}%`;
    meterFill.style.background = s.motion ? 'var(--accent-motion)' : 'var(--accent-idle)';

    // Bento 2: Calibration & Sensitivity
    const sens = s.sensitivity === 'strict' ? 'low' : (s.sensitivity || 'normal');
    ['high', 'normal', 'low'].forEach(k => {
      const btn = document.getElementById('sens_' + k);
      if (btn) btn.className = 'sens-opt ' + (sens === k ? 'active' : '');
    });
    const info = SENS_INFO[sens] || SENS_INFO.normal;
    document.getElementById('txtSensFactor').textContent = info.factor;
    document.getElementById('txtSensNote').textContent = info.note;

    const btnCalib = document.getElementById('btnCalib');
    const txtCalib = document.getElementById('txtCalib');
    if (s.calibrating) {
      btnCalib.className = 'calib-btn running';
      txtCalib.textContent = s.calib_samples >= 20
        ? `Lưu sớm kết quả (${s.calib_samples} mẫu · còn ${Math.ceil(s.calib_remaining)}s)`
        : `Hủy đo nhiễu nền (còn ${Math.ceil(s.calib_remaining)}s)`;
    } else {
      btnCalib.className = 'calib-btn';
      txtCalib.textContent = 'Đo lại nhiễu nền (30 giây)';
    }

    // Chart Render
    if (activeTab === 'wave') {
      drawWaveChart(s);
    } else {
      drawWaterfallChart(s);
    }

    // Bento 3: Event Log
    const logList = document.getElementById('logList');
    if (s.events && s.events.length) {
      logList.innerHTML = s.events.slice(0, 15).map(e => {
        const sp = e.indexOf(' ');
        const t = sp > 0 ? e.slice(0, sp) : '--:--:--';
        const msg = sp > 0 ? e.slice(sp + 1) : e;
        let tag = '<span class="tag tag-sys">HỆ THỐNG</span>';
        if (msg.startsWith('Có chuyển động')) tag = '<span class="tag tag-mot">CHUYỂN ĐỘNG</span>';
        else if (msg.startsWith('Trở về tĩnh')) tag = '<span class="tag tag-idle">TĨNH</span>';
        else if (msg.includes('nhiễu nền') || msg.includes('Độ nhạy')) tag = '<span class="tag tag-cal">CẤU HÌNH</span>';
        return `<div class="log-row"><span class="log-time num">${t}</span>${tag}<span>${msg}</span></div>`;
      }).join('');
    } else {
      logList.innerHTML = '<div class="log-row"><span class="log-time num">--:--:--</span><span>Nhật ký trống.</span></div>';
    }
  } catch (e) {}
  setTimeout(poll, 100);
}

window.addEventListener('resize', () => {
  prepareCanvas();
});

poll();
</script>
</body>
</html>
"""


# Translate presentation text only. Packet fields, experiment labels and saved
# calibration files retain their existing format in both interface languages.
ENGLISH_TEXT = {
    "Giám sát Chuyển động Wi-Fi CSI": "Wi-Fi CSI Motion Monitor",
    "Chuyển đổi giữa Cổng USB trực tiếp và Chế độ phát dữ liệu mẫu": "Switch between live USB and recorded demo",
    "Đang thu thập cửa sổ mẫu CSI đầu tiên để phân tích phương sai biên độ.": "Collecting the first CSI window to analyze amplitude variation.",
    "Đang khởi tạo kết nối...": "Initializing connection...",
    "Độ biến thiên CSI theo thời gian": "CSI variation over time",
    "Phổ biên độ 52 sóng mang": "Amplitude of 52 subcarriers",
    "Biểu đồ tín hiệu CSI": "CSI signal chart",
    "Thông số Tín hiệu & Nhiễu nền": "Signal & Baseline",
    "Độ biến thiên hiện tại": "Current variation",
    "Mức nhiễu nền (±σ)": "Baseline (±σ)",
    "Tỉ lệ so với ngưỡng kích hoạt": "Ratio to activation threshold",
    "Vạch đỏ biểu thị vị trí 100% Ngưỡng kích hoạt": "Red marker indicates 100% of the activation threshold",
    "Hiệu chuẩn & Độ nhạy": "Calibration & Sensitivity",
    "Cửa sổ lọc": "Filter window",
    "Chọn độ nhạy phát hiện": "Choose detection sensitivity",
    "Độ nhạy phát hiện": "Detection sensitivity",
    "Hệ số chuẩn": "Standard factor",
    "Cân bằng giữa độ nhạy phát hiện và khả năng lọc nhiễu nền thông thường.": "Balances motion sensitivity and typical background noise rejection.",
    "Ngưỡng thấp — nhạy hơn với cử động nhẹ, phù hợp khi phòng ít nhiễu sóng.": "Lower threshold for small movements in rooms with little RF noise.",
    "Ngưỡng cao — giảm khả năng báo nhầm khi môi trường có nhiều nhiễu RF.": "Higher threshold reduces false alarms in environments with RF interference.",
    "Đo lại nhiễu nền (30 giây)": "Recalibrate baseline (30 seconds)",
    "Nhật ký Trạng thái": "Status Log",
    "Xóa nhật ký": "Clear log",
    "Đang kết nối...": "Connecting...",
    "Nhật ký trống.": "No events yet.",
    "Chế độ phát mẫu": "Recorded demo",
    "Cổng USB trực tiếp": "Live USB",
    "Cổng USB": "USB port",
    "Chờ TX": "Waiting for TX",
    "Đang dò USB": "Searching for USB",
    "Tốc độ nhận": "Receive rate",
    "Chuẩn bị đo nhiễu nền": "Preparing baseline calibration",
    "Bỏ qua 3 giây đầu để ổn định tín hiệu — vui lòng đứng yên hoặc rời vùng đo.": "The first 3 seconds allow the signal to settle. Stay still or leave the sensing area.",
    "Đang đo nhiễu nền (còn ${rem} giây)": "Calibrating baseline (${rem} seconds remaining)",
    "Đã thu ${s.calib_samples} mẫu phương sai CSI — giữ không gian tĩnh cho đến khi hoàn tất.": "Collected ${s.calib_samples} CSI variation samples. Keep the room still until calibration finishes.",
    "Chưa kết nối mạch thu (RX)": "Receiver (RX) disconnected",
    "Cắm cáp USB của mạch thu ESP32-S3 vào máy tính hoặc bấm nút góc phải để mở Chế độ phát mẫu.": "Connect the ESP32-S3 receiver by USB or use the top-right button to open the recorded demo.",
    "Đang chờ gói tin từ mạch phát (TX)": "Waiting for transmitter (TX) packets",
    "Đã kết nối mạch thu tại ${s.port} nhưng chưa thu được khung sóng ESP-NOW từ mạch phát.": "Receiver connected at ${s.port}; waiting for ESP-NOW frames from the transmitter.",
    "Độ biến thiên CSI (${s.score.toFixed(3)} dB) vượt ngưỡng kích hoạt (${s.thr_on.toFixed(3)} dB).": "CSI variation (${s.score.toFixed(3)} dB) exceeded the activation threshold (${s.thr_on.toFixed(3)} dB).",
    "Độ biến thiên CSI (${s.score.toFixed(3)} dB) nằm dưới ngưỡng kích hoạt — phòng trống hoặc người đứng yên.": "CSI variation (${s.score.toFixed(3)} dB) is below the activation threshold. The room may be empty or occupants may be still.",
    "Không phát hiện chuyển động": "No motion detected",
    "Có chuyển động": "Motion detected",
    "Lưu sớm kết quả (${s.calib_samples} mẫu · còn ${Math.ceil(s.calib_remaining)}s)": "Save early (${s.calib_samples} samples · ${Math.ceil(s.calib_remaining)}s left)",
    "Hủy đo nhiễu nền (còn ${Math.ceil(s.calib_remaining)}s)": "Cancel calibration (${Math.ceil(s.calib_remaining)}s left)",
    "Khởi động giao diện giám sát": "Monitor started",
    "Đã hủy đo nhiễu nền: không đủ mẫu CSI hợp lệ": "Calibration cancelled: insufficient valid CSI samples",
    "Không lưu được cấu hình nhiễu nền": "Could not save baseline configuration",
    "Đo nhiễu nền xong": "Baseline calibration completed",
    "Không tìm thấy tệp dữ liệu mẫu — giữ kết nối USB": "Demo file not found; keeping the USB connection",
    "Chuyển sang": "Switched to",
    "Trở về tĩnh": "Returned to still",
    "Bắt đầu đo nhiễu nền": "Started baseline calibration",
    "Ngưỡng kích hoạt": "Activation threshold",
    "ngưỡng kích hoạt": "activation threshold",
    "Ngưỡng duy trì": "Release threshold",
    "Mức nhiễu nền": "Baseline noise",
    "Độ biến thiên CSI": "CSI variation",
    "Độ nhạy": "Sensitivity",
    "nhiễu nền": "baseline",
    "biến thiên": "variation",
    "kéo dài": "duration",
    "gói hợp lệ": "valid packets",
    "sóng mang": "subcarriers",
    "HỆ THỐNG": "SYSTEM",
    "CHUYỂN ĐỘNG": "MOTION",
    "CẤU HÌNH": "SETTINGS",
    "TĨNH": "STILL",
    "Hiện tại": "Now",
    "Cũ hơn": "Earlier",
    "Trung bình": "Normal",
    "Thấp": "Low",
    "Cao": "High",
    "Hệ số": "Factor",
    "gói": "packets",
}


def translate_text(text: str, language: str) -> str:
    if language == "en":
        for original in sorted(ENGLISH_TEXT, key=len, reverse=True):
            text = text.replace(original, ENGLISH_TEXT[original])
    return text


def dashboard_page(language: str = "en") -> str:
    page = translate_text(HTML_PAGE, language)
    return page.replace('<html lang="vi">', '<html lang="en">') if language == "en" else page


class WebState:
    def __init__(self, args):
        self.args = args
        cfg = MotionConfig.load(args.calib) if os.path.exists(args.calib) else MotionConfig()
        self.motion = MotionDetector(cfg, args.motion_model)
        self.engine = Engine(self.motion, None)
        self.mode = "replay" if args.replay else "live"
        self.demo_path = os.path.join(HERE, "..", "data", "sessions", "E1", "E1_baseline_3m.csv")
        self.src = (
            ReplaySource(args.replay or self.demo_path, args.speed, loop=True)
            if args.replay
            else SerialSource(args.port, args.baud)
        )
        self.wf = deque(maxlen=150)
        self.h_score = deque(maxlen=200)
        self.h_motion = deque(maxlen=200)
        self.events = deque(maxlen=50)
        self.calibrating_until: float | None = None
        self.calib_settle_until: float = 0.0
        self.calib_scores: list[float] = []
        self.motion_since: float | None = None
        self.lock = threading.RLock()
        self._stop = threading.Event()
        self._last_step_t: float | None = None
        self._next_step_t: float | None = None
        self.add_event(f"Khởi động giao diện giám sát ({args.replay or args.port})")
        self.src.start()

    def add_event(self, msg: str):
        self.events.appendleft(time.strftime("%H:%M:%S ") + msg)

    def clear_buffers(self):
        self.engine.reset()
        self.wf.clear()
        self.h_score.clear()
        self.h_motion.clear()
        self.motion_since = None
        self._last_step_t = None
        self._next_step_t = None

    def close(self):
        """Release the serial/replay source when the HTTP server exits."""
        self._stop.set()
        with self.lock:
            self.src.stop()
            self.src.join(timeout=2.0)

    def finish_calibration(self, min_samples: int = 10):
        self.calibrating_until = None
        if len(self.calib_scores) < min_samples:
            self.add_event("Đã hủy đo nhiễu nền: không đủ mẫu CSI hợp lệ")
            return
        self.motion.calibrate(np.array(self.calib_scores))
        # The previous result was evaluated against the old thresholds.
        self.engine.last_result = {}
        self.h_motion.clear()
        self.motion_since = None
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.args.calib)), exist_ok=True)
            self.motion.cfg.save(self.args.calib)
        except OSError as exc:
            self.add_event(f"Không lưu được cấu hình nhiễu nền: {exc}")
            return
        self.add_event(
            f"Đo nhiễu nền xong: {self.motion.cfg.baseline_median:.3f} dB, "
            f"Ngưỡng kích hoạt = {self.motion.cfg.thr_on:.3f} dB"
        )

    def toggle_source(self):
        with self.lock:
            if self.mode == "live" and not os.path.exists(self.demo_path):
                self.add_event("Không tìm thấy tệp dữ liệu mẫu — giữ kết nối USB")
                return
            self.src.stop()
            self.src.join(timeout=2.0)
            self.calibrating_until = None
            self.calib_scores.clear()
            self.clear_buffers()
            if self.mode == "live":
                self.mode = "replay"
                self.src = ReplaySource(self.demo_path, 1.0, loop=True)
                self.src.start()
                self.add_event("Chuyển sang Chế độ phát mẫu")
            else:
                self.mode = "live"
                self.src = SerialSource(self.args.port, self.args.baud)
                self.src.start()
                self.add_event(f"Chuyển sang Cổng USB trực tiếp ({self.args.port})")

    def loop(self):
        while not self._stop.is_set():
            time.sleep(0.08)
            with self.lock:
                got_new = 0
                while True:
                    try:
                        _, _, pkt = self.src.q.get_nowait()
                    except queue.Empty:
                        break
                    self.engine.push(pkt)
                    if got_new % 2 == 0:
                        self.wf.append(np.round(np.abs(pkt.csi), 1).tolist())
                    got_new += 1

                now = time.time()
                if self.calibrating_until is not None and now >= self.calibrating_until:
                    self.finish_calibration()
                tx_alive = (
                    self.engine.last_rx_walltime > 0.0
                    and (now - self.engine.last_rx_walltime) <= 2.5
                )

                if not tx_alive:
                    if self.motion.state:
                        self.motion.reset()
                        self.motion_since = None
                    continue

                if got_new == 0:
                    continue

                device_t = self.engine.now
                if (self._next_step_t is None
                        or (self._last_step_t is not None and device_t < self._last_step_t)
                        or device_t > self._next_step_t + 5.0):
                    self._next_step_t = device_t
                if device_t < self._next_step_t - 1e-9:
                    continue

                self._last_step_t = device_t
                while self._next_step_t <= device_t + 1e-9:
                    self._next_step_t += self.motion.cfg.hop_s
                res = self.engine.step()
                if res is None:
                    continue

                if self.calibrating_until is not None:
                    if now >= self.calib_settle_until:
                        self.calib_scores.append(res.get("raw_score", res["score"]))

                prev = self.h_motion[-1] if self.h_motion else False
                cur_mot = bool(res["motion"])
                if cur_mot != prev and self.calibrating_until is None:
                    if cur_mot:
                        self.motion_since = now
                        self.add_event(f"Có chuyển động (biến thiên {res['score']:.3f} dB)")
                    else:
                        dur = (now - self.motion_since) if self.motion_since else 0.0
                        self.motion_since = None
                        if dur >= 0.5:
                            self.add_event(f"Trở về tĩnh (kéo dài {dur:.1f}s)")
                        else:
                            self.add_event("Trở về tĩnh")

                self.h_score.append(round(float(res["score"]), 4))
                self.h_motion.append(cur_mot)

    def snapshot(self, language: str = "en") -> dict:
        with self.lock:
            now = time.time()
            res = self.engine.last_result
            cfg = self.motion.cfg
            is_calib = self.calibrating_until is not None
            calib_rem = max(0.0, self.calibrating_until - now) if is_calib else 0.0

            connected = bool(
                self.mode == "replay"
                or (isinstance(self.src, SerialSource) and self.src.ser and self.src.ser.is_open)
            )
            tx_alive = bool(
                self.engine.last_rx_walltime > 0.0
                and (now - self.engine.last_rx_walltime) <= 2.5
            )
            cur_port = (
                (self.src.port if isinstance(self.src, SerialSource) else self.args.port)
                if self.mode == "live"
                else "Demo"
            )

            is_motion = bool(res.get("motion")) if (res and tx_alive) else False
            live_rate = float(res.get("rate", 0.0)) if (res and tx_alive) else 0.0
            live_score = float(res.get("score", 0.0)) if (res and tx_alive) else 0.0
            live_rssi = float(res.get("rssi", -99.0)) if (res and tx_alive) else -99.0

            return {
                "port": cur_port,
                "source_mode": self.mode,
                "connected": connected,
                "tx_alive": tx_alive,
                "total_pkts": self.engine.n_packets,
                "rate": live_rate,
                "rssi": live_rssi,
                "score": live_score,
                "baseline_median": float(cfg.baseline_median),
                "baseline_std": float(cfg.baseline_std),
                "thr_on": float(cfg.thr_on),
                "thr_off": float(cfg.thr_off),
                "sensitivity": "low" if cfg.sensitivity == "strict" else cfg.sensitivity,
                "calib_samples": len(self.calib_scores),
                "motion": is_motion,
                "calibrating": is_calib,
                "calib_remaining": calib_rem,
                "wf": list(self.wf),
                "h_score": list(self.h_score),
                "h_motion": list(self.h_motion),
                "events": [translate_text(event, language) for event in self.events],
            }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="COM4")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--replay", default=None)
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--calib", default=os.path.abspath(DEFAULT_CALIB))
    ap.add_argument("--motion-model", default=None)
    ap.add_argument("--http-port", type=int, default=8050)
    ap.add_argument("--http-host", default="127.0.0.1", help="Bind address; use 0.0.0.0 for LAN access")
    ap.add_argument("--language", choices=("vi", "en"), default="en", help="Default dashboard language")
    args = ap.parse_args()

    state = WebState(args)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *a):
            pass

        def do_GET(self):
            request = urlparse(self.path)
            language = parse_qs(request.query).get("lang", [args.language])[0]
            if language not in ("vi", "en"):
                language = args.language
            if request.path == "/state":
                body = json.dumps(state.snapshot(language)).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            else:
                body = dashboard_page(language).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

        def do_POST(self):
            u = urlparse(self.path)
            qs = parse_qs(u.query)
            with state.lock:
                if u.path == "/toggle_source":
                    state.toggle_source()
                elif u.path == "/calibrate":
                    if state.calibrating_until is not None:
                        state.finish_calibration(min_samples=20)
                    else:
                        state.calib_scores = []
                        now = time.time()
                        state.calib_settle_until = now + 3.0
                        state.calibrating_until = now + 30.0
                        state.add_event("Bắt đầu đo nhiễu nền (30s)")
                elif u.path == "/sensitivity":
                    v = qs.get("v", ["normal"])[0]
                    if v in ("high", "normal", "low"):
                        state.motion.cfg.sensitivity = v
                        os.makedirs(os.path.dirname(os.path.abspath(state.args.calib)), exist_ok=True)
                        state.motion.cfg.save(state.args.calib)
                        names = {"high": "Cao", "normal": "Trung bình", "low": "Thấp"}
                        state.add_event(
                            f"Độ nhạy -> {names[v]} (Ngưỡng kích hoạt = {state.motion.cfg.thr_on:.3f} dB)"
                        )
                elif u.path == "/clear_events":
                    state.events.clear()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

    srv = None
    worker = None
    try:
        srv = ThreadingHTTPServer((args.http_host, args.http_port), Handler)
        worker = threading.Thread(target=state.loop, daemon=True)
        worker.start()
        print(f"Wi-Fi CSI Motion Dashboard running at http://{args.http_host}:{args.http_port}", flush=True)
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        state.close()
        if worker is not None:
            worker.join(timeout=2.0)
        if srv is not None:
            srv.server_close()


if __name__ == "__main__":
    main()
