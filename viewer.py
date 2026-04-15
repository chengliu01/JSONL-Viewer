#!/usr/bin/env python3
"""JSONL Viewer — 本地可视化 JSONL 文件工具"""

import json
import os
import sys
import urllib.parse
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

# ─────────────────────────────────────────────────────────────────────────────
# Global state
# ─────────────────────────────────────────────────────────────────────────────
_line_offsets: dict = {}   # filepath -> list of byte offsets (one per line)
_file_fields: dict = {}    # filepath -> list of field names


def build_index(filepath: str):
    """Scan file, build line offset index, collect field names from first 50 JSON object lines."""
    offsets = []
    all_fields = []
    fields_set = set()
    sampled = 0

    with open(filepath, "rb") as f:
        while True:
            pos = f.tell()
            line = f.readline()
            if not line:
                break
            offsets.append(pos)
            stripped = line.strip()
            if stripped and sampled < 50:
                try:
                    obj = json.loads(stripped)
                    if isinstance(obj, dict):
                        for k in obj.keys():
                            if k not in fields_set:
                                fields_set.add(k)
                                all_fields.append(k)
                        sampled += 1
                except Exception:
                    pass

    _line_offsets[filepath] = offsets
    _file_fields[filepath] = all_fields
    return len(offsets), all_fields


def read_line(filepath: str, line_num: int) -> str:
    """Read a specific 1-indexed line efficiently using cached offsets."""
    offsets = _line_offsets.get(filepath)
    if offsets and 1 <= line_num <= len(offsets):
        with open(filepath, "rb") as f:
            f.seek(offsets[line_num - 1])
            return f.readline().decode("utf-8", errors="replace").rstrip("\n\r")
    # Fallback: sequential
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f, 1):
            if i == line_num:
                return line.rstrip("\n\r")
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# HTML (embedded)
# ─────────────────────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>JSONL Viewer</title>
<script src="https://cdn.jsdelivr.net/npm/marked@9/marked.min.js"></script>
<style>
/* ── Variables ───────────────────────────────────────── */
:root{
  --bg:       #0f1117;
  --bg2:      #181c27;
  --bg3:      #1e2333;
  --bg4:      #252d40;
  --bg5:      #2e3750;
  --border:   #2a3347;
  --border2:  #3a4560;
  --fg:       #e2e8f0;
  --fg2:      #94a3b8;
  --fg3:      #4a5568;
  --accent:   #6366f1;
  --accent-l: #818cf8;
  --accent2:  #22d3ee;
  --accent2-l:#67e8f9;
  --green:    #34d399;
  --yellow:   #fbbf24;
  --red:      #f87171;
  --purple:   #a78bfa;
  --key:      #38bdf8;
  --str:      #4ade80;
  --num:      #fb923c;
  --bool:     #c084fc;
  --null:     #475569;
  --radius:   10px;
  --radius-sm:6px;
  --shadow:   0 4px 24px rgba(0,0,0,.4);
  --shadow-sm:0 2px 8px rgba(0,0,0,.3);
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;overflow:hidden}
body{
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Hiragino Sans GB',sans-serif;
  background:var(--bg);color:var(--fg);
  display:flex;flex-direction:column;height:100vh;font-size:14px;
}

/* ── Scrollbars ──────────────────────────────────────── */
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--bg5);border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:var(--border2)}

/* ── Toolbar ─────────────────────────────────────────── */
#toolbar{
  background:var(--bg2);
  border-bottom:1px solid var(--border);
  padding:9px 16px;
  display:flex;align-items:center;gap:8px;
  flex-shrink:0;
  box-shadow:0 1px 0 rgba(255,255,255,.03);
}
#logo{
  display:flex;align-items:center;gap:7px;
  flex-shrink:0;text-decoration:none;
}
#logo-icon{
  width:28px;height:28px;border-radius:7px;
  background:linear-gradient(135deg,var(--accent),var(--accent2));
  display:flex;align-items:center;justify-content:center;
  font-size:14px;flex-shrink:0;
  box-shadow:0 2px 8px rgba(99,102,241,.4);
}
#logo-text{font-size:13px;font-weight:700;color:var(--fg);letter-spacing:.3px;white-space:nowrap}

.path-wrap{
  flex:1;display:flex;align-items:center;
  background:var(--bg);border:1px solid var(--border);border-radius:8px;
  padding:0 4px 0 10px;gap:4px;
  transition:border-color .2s,box-shadow .2s;
}
.path-wrap:focus-within{
  border-color:var(--accent);
  box-shadow:0 0 0 3px rgba(99,102,241,.15);
}
#path-input{
  flex:1;background:transparent;border:none;color:var(--fg);
  padding:7px 4px;font-size:12px;outline:none;font-family:inherit;
  min-width:0;
}
#path-input::placeholder{color:var(--fg3)}

.tb-btn{
  display:inline-flex;align-items:center;gap:5px;
  background:var(--bg4);border:1px solid var(--border);color:var(--fg2);
  padding:6px 12px;border-radius:7px;cursor:pointer;font-family:inherit;
  font-size:12px;white-space:nowrap;font-weight:500;
  transition:all .15s;flex-shrink:0;
}
.tb-btn:hover{background:var(--bg5);border-color:var(--border2);color:var(--fg)}
.tb-btn.primary{
  background:linear-gradient(135deg,var(--accent),#4f46e5);
  border-color:transparent;color:#fff;font-weight:600;
  box-shadow:0 2px 8px rgba(99,102,241,.4);
}
.tb-btn.primary:hover{opacity:.9;box-shadow:0 4px 12px rgba(99,102,241,.5)}
#file-input{display:none}

/* ── Nav ─────────────────────────────────────────────── */
#nav{
  background:var(--bg2);border-bottom:1px solid var(--border);
  padding:8px 16px;display:flex;align-items:center;gap:10px;flex-shrink:0;
}
.nav-btn{
  width:28px;height:28px;border-radius:7px;flex-shrink:0;
  background:var(--bg4);border:1px solid var(--border);color:var(--fg2);
  cursor:pointer;display:flex;align-items:center;justify-content:center;
  font-size:13px;transition:all .15s;
}
.nav-btn:hover:not(:disabled){background:var(--bg5);color:var(--fg);border-color:var(--border2)}
.nav-btn:disabled{opacity:.3;cursor:not-allowed}

.slider-wrap{
  flex:1;display:flex;align-items:center;gap:8px;
  background:var(--bg);border:1px solid var(--border);border-radius:8px;
  padding:0 12px;height:34px;
  transition:border-color .2s;
}
.slider-wrap:focus-within{border-color:var(--accent)}
.slider-label{font-size:11px;color:var(--fg3);white-space:nowrap;flex-shrink:0}
#line-slider{
  flex:1;-webkit-appearance:none;appearance:none;
  height:3px;border-radius:2px;background:var(--bg4);outline:none;cursor:pointer;
}
#line-slider::-webkit-slider-thumb{
  -webkit-appearance:none;appearance:none;
  width:16px;height:16px;border-radius:50%;
  background:linear-gradient(135deg,var(--accent),var(--accent2));
  cursor:pointer;transition:transform .1s,box-shadow .1s;
  box-shadow:0 0 0 3px rgba(99,102,241,.2);
}
#line-slider::-webkit-slider-thumb:hover{transform:scale(1.2);box-shadow:0 0 0 4px rgba(99,102,241,.3)}
#line-slider:disabled{opacity:.4;cursor:not-allowed}
.progress-pct{font-size:10px;color:var(--fg3);white-space:nowrap;flex-shrink:0;min-width:28px;text-align:right}

.line-num-wrap{
  display:flex;align-items:center;gap:4px;flex-shrink:0;
  background:var(--bg);border:1px solid var(--border);border-radius:8px;
  padding:0 8px;height:34px;
  transition:border-color .2s;
}
.line-num-wrap:focus-within{border-color:var(--accent)}
#line-input{
  width:52px;background:transparent;border:none;color:var(--fg);
  font-size:13px;font-weight:600;text-align:center;outline:none;font-family:inherit;
}
.line-sep{color:var(--fg3);font-size:12px}
#total-label{color:var(--fg2);font-size:12px;white-space:nowrap}

/* ── Body: sidebar + content ─────────────────────────── */
#body{flex:1;display:flex;min-height:0}

/* ── Sidebar ─────────────────────────────────────────── */
#sidebar{
  width:220px;flex-shrink:0;
  background:var(--bg2);border-right:1px solid var(--border);
  display:flex;flex-direction:column;overflow:hidden;
}
.sidebar-head{
  padding:10px 12px 6px;
  display:flex;align-items:center;justify-content:space-between;
  flex-shrink:0;
}
.sidebar-title{font-size:11px;font-weight:600;color:var(--fg3);text-transform:uppercase;letter-spacing:.8px}
.sidebar-actions{display:flex;gap:4px}
.mini-btn{
  font-size:10px;color:var(--fg3);background:var(--bg4);border:1px solid var(--border);
  padding:2px 6px;border-radius:4px;cursor:pointer;transition:all .12s;
}
.mini-btn:hover{color:var(--fg);border-color:var(--border2)}

.search-wrap{
  padding:0 10px 8px;flex-shrink:0;
}
.search-box{
  display:flex;align-items:center;gap:5px;
  background:var(--bg);border:1px solid var(--border);border-radius:7px;padding:5px 8px;
  transition:border-color .2s;
}
.search-box:focus-within{border-color:var(--accent)}
.search-icon{color:var(--fg3);font-size:11px;flex-shrink:0}
#field-search{
  flex:1;background:transparent;border:none;color:var(--fg);
  font-size:12px;outline:none;font-family:inherit;
}
#field-search::placeholder{color:var(--fg3)}

#field-list{flex:1;overflow-y:auto;padding:0 8px 10px}
.field-item{
  display:flex;align-items:center;gap:8px;
  padding:5px 8px;border-radius:6px;cursor:pointer;
  transition:background .12s;margin-bottom:1px;user-select:none;
}
.field-item:hover{background:var(--bg4)}
.field-item.active .fi-check{opacity:1;color:var(--accent-l)}
.field-item.active .fi-name{color:var(--fg)}
.fi-check{
  width:14px;height:14px;border-radius:4px;flex-shrink:0;
  border:1.5px solid var(--border2);display:flex;align-items:center;justify-content:center;
  font-size:9px;opacity:0;transition:all .12s;color:transparent;
  background:rgba(99,102,241,.1);
}
.field-item.active .fi-check{
  opacity:1;border-color:var(--accent);color:var(--accent-l);
  background:rgba(99,102,241,.2);
}
.fi-dot{
  width:7px;height:7px;border-radius:50%;flex-shrink:0;
  background:var(--fg3);opacity:.4;
}
.fi-name{font-size:12px;color:var(--fg2);font-family:'SF Mono','Fira Code',monospace;truncate:ellipsis;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.field-item.active .fi-dot{background:var(--accent-l);opacity:1}
.field-empty{color:var(--fg3);font-size:11px;padding:8px 8px;text-align:center}

/* ── Status bar ──────────────────────────────────────── */
#status-bar{
  flex-shrink:0;
  background:var(--bg2);border-top:1px solid var(--border);
  padding:4px 16px;font-size:11px;color:var(--fg3);
  display:flex;align-items:center;gap:8px;
}
#status-bar .dot{
  width:6px;height:6px;border-radius:50%;background:var(--fg3);flex-shrink:0;
}
#status-bar.ok .dot{background:var(--green)}
#status-bar.loading .dot{background:var(--yellow);animation:pulse .8s ease-in-out infinite}
#status-bar.error .dot{background:var(--red)}
#status-bar.ok{color:var(--fg2)}
#status-bar.error{color:var(--red)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}

/* ── Main content ────────────────────────────────────── */
#main{flex:1;overflow-y:auto;background:var(--bg);padding:20px 24px;min-width:0}

.empty-state{
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  height:100%;color:var(--fg3);gap:10px;padding:40px;
}
.empty-icon{
  width:64px;height:64px;border-radius:18px;
  background:linear-gradient(135deg,rgba(99,102,241,.1),rgba(34,211,238,.1));
  border:1px solid var(--border);
  display:flex;align-items:center;justify-content:center;font-size:26px;
}
.empty-title{font-size:15px;font-weight:600;color:var(--fg2)}
.empty-sub{font-size:12px;color:var(--fg3);text-align:center;line-height:1.6}

/* ── Cards (field rows) ──────────────────────────────── */
.field-cards{display:flex;flex-direction:column;gap:2px}

.fcard{
  background:var(--bg2);border:1px solid var(--border);
  border-radius:var(--radius-sm);overflow:hidden;
  transition:border-color .15s,box-shadow .15s;
}
.fcard:hover{border-color:var(--border2);box-shadow:var(--shadow-sm)}

.fcard-header{
  display:flex;align-items:flex-start;gap:0;cursor:pointer;
  min-height:40px;
}
.fcard-key{
  flex-shrink:0;width:180px;padding:10px 14px;
  display:flex;align-items:flex-start;gap:6px;
  border-right:1px solid var(--border);
  background:rgba(56,189,248,.04);
}
.fcard-key-text{
  font-family:'SF Mono','Fira Code','Cascadia Code',monospace;
  font-size:12px;font-weight:500;color:var(--key);
  word-break:break-all;line-height:1.5;
}
.fcard-type-badge{
  margin-left:auto;flex-shrink:0;
  font-size:9px;padding:1px 5px;border-radius:3px;
  font-family:monospace;font-weight:600;letter-spacing:.3px;
  white-space:nowrap;margin-top:2px;
}
.type-str{background:rgba(74,222,128,.1);color:var(--str);border:1px solid rgba(74,222,128,.2)}
.type-num{background:rgba(251,146,60,.1);color:var(--num);border:1px solid rgba(251,146,60,.2)}
.type-bool{background:rgba(192,132,252,.1);color:var(--bool);border:1px solid rgba(192,132,252,.2)}
.type-null{background:rgba(71,85,105,.15);color:var(--null);border:1px solid rgba(71,85,105,.3)}
.type-obj{background:rgba(99,102,241,.1);color:var(--accent-l);border:1px solid rgba(99,102,241,.2)}
.type-arr{background:rgba(34,211,238,.1);color:var(--accent2);border:1px solid rgba(34,211,238,.2)}

.fcard-val{
  flex:1;padding:10px 14px;min-width:0;
  display:flex;align-items:flex-start;justify-content:space-between;gap:8px;
}
.fcard-val-inner{flex:1;min-width:0}

/* ── Value types ─────────────────────────────────────── */
.v-str{
  font-size:13px;color:var(--str);line-height:1.6;
  word-break:break-word;white-space:pre-wrap;
}
.v-str.long{
  max-height:3.2em;overflow:hidden;position:relative;
  cursor:pointer;
}
.v-str.long::after{
  content:'';position:absolute;bottom:0;left:0;right:0;
  height:1.4em;background:linear-gradient(transparent,var(--bg2));
  pointer-events:none;
}
.v-str.long.expanded{max-height:none}
.v-str.long.expanded::after{display:none}

.v-num{font-size:14px;color:var(--num);font-family:'SF Mono','Fira Code',monospace;font-weight:600}
.v-bool-true{font-size:13px;color:var(--green);font-weight:600}
.v-bool-false{font-size:13px;color:var(--red);font-weight:600}
.v-null{font-size:13px;color:var(--null);font-style:italic}

/* ── MD toggle ───────────────────────────────────────── */
.val-actions{display:flex;gap:4px;flex-shrink:0;margin-top:1px}
.val-btn{
  display:inline-flex;align-items:center;gap:3px;
  background:var(--bg4);border:1px solid var(--border);
  color:var(--fg3);font-size:10px;padding:2px 7px;border-radius:4px;
  cursor:pointer;white-space:nowrap;font-family:inherit;
  transition:all .12s;
}
.val-btn:hover{border-color:var(--border2);color:var(--fg)}
.val-btn.active{background:rgba(34,211,238,.1);border-color:var(--accent2);color:var(--accent2)}

/* ── Markdown ────────────────────────────────────────── */
.md-view{
  background:var(--bg3);border:1px solid var(--border);border-radius:var(--radius-sm);
  padding:14px 16px;margin-top:8px;line-height:1.7;color:var(--fg2);
  word-break:break-word;
}
.md-view h1,.md-view h2,.md-view h3{color:var(--fg);margin:10px 0 4px;font-size:inherit;font-weight:700}
.md-view h1{font-size:15px}.md-view h2{font-size:14px}
.md-view p{margin:4px 0}
.md-view strong{color:var(--fg);font-weight:600}
.md-view em{color:var(--fg2)}
.md-view a{color:var(--accent-l);text-decoration:none}
.md-view a:hover{text-decoration:underline}
.md-view ul,.md-view ol{padding-left:18px;margin:4px 0}
.md-view li{margin:2px 0}
.md-view code{
  background:var(--bg4);padding:1px 5px;border-radius:4px;
  color:var(--accent2);font-family:'SF Mono','Fira Code',monospace;font-size:12px;
}
.md-view pre{background:var(--bg4);padding:12px;border-radius:var(--radius-sm);overflow-x:auto;margin:6px 0}
.md-view pre code{background:none;padding:0;color:var(--fg2)}
.md-view blockquote{border-left:3px solid var(--border2);padding-left:10px;color:var(--fg3);margin:4px 0}
.md-view table{border-collapse:collapse;width:100%;margin:6px 0;font-size:12px}
.md-view th{background:var(--bg4);color:var(--fg);font-weight:600;padding:6px 10px;border:1px solid var(--border2)}
.md-view td{padding:5px 10px;border:1px solid var(--border)}
.md-view hr{border:none;border-top:1px solid var(--border);margin:8px 0}

/* ── Nested JSON tree ────────────────────────────────── */
.json-tree{
  font-family:'SF Mono','Fira Code','Cascadia Code',monospace;
  font-size:12px;line-height:1.8;
}
.j-entry{display:flex;align-items:flex-start;padding-left:18px;position:relative}
.j-key{color:var(--key);font-weight:500}
.j-colon{color:var(--fg3);margin:0 5px 0 2px}
.j-str-v{color:var(--str)}
.j-num-v{color:var(--num)}
.j-bool-v{color:var(--bool)}
.j-null-v{color:var(--null);font-style:italic}
.j-bracket{color:var(--fg2)}
.j-comma{color:var(--border2)}
.j-idx{color:var(--fg3);font-size:10px;margin-right:2px}

.toggler{
  display:inline-flex;align-items:center;justify-content:center;
  width:16px;height:16px;margin-left:-18px;margin-right:2px;
  cursor:pointer;color:var(--fg3);font-size:9px;border-radius:3px;
  user-select:none;transition:color .12s,background .1s;flex-shrink:0;
}
.toggler:hover{color:var(--accent-l);background:rgba(99,102,241,.1)}
.j-children{border-left:1px solid var(--bg5);margin-left:8px}
.j-children.collapsed{display:none}
.j-preview{color:var(--fg3);font-size:11px;cursor:pointer;padding:0 4px;font-style:italic}
.j-preview:hover{color:var(--fg2)}

/* ── Raw text (non-JSON lines) ───────────────────────── */
.raw-card{
  background:var(--bg2);border:1px solid var(--border);border-radius:var(--radius-sm);
  padding:16px 18px;
}
.raw-label{font-size:10px;color:var(--fg3);text-transform:uppercase;letter-spacing:.8px;margin-bottom:8px}
.raw-text{color:var(--fg2);white-space:pre-wrap;word-break:break-all;line-height:1.7;font-size:13px}

/* ── Drag overlay ────────────────────────────────────── */
#drag-overlay{
  position:fixed;inset:0;background:rgba(15,17,23,.9);
  display:none;align-items:center;justify-content:center;
  z-index:999;pointer-events:none;
  border:2px dashed var(--accent);
}
body.drag-over #drag-overlay{display:flex}
.drag-inner{
  display:flex;flex-direction:column;align-items:center;gap:12px;
  color:var(--accent-l);
}
.drag-inner .d-icon{font-size:48px;opacity:.6}
.drag-inner .d-text{font-size:18px;font-weight:600}

/* ── Resizer ────────────────────────────────────────── */
#resizer{
  width:4px;flex-shrink:0;cursor:col-resize;
  background:var(--border);
  transition:background .15s;
  position:relative;
  z-index:10;
}
#resizer:hover,#resizer.dragging{background:var(--accent)}
#resizer::after{
  content:'';position:absolute;top:50%;left:50%;
  transform:translate(-50%,-50%);
  width:4px;height:32px;border-radius:2px;
  background:var(--border2);opacity:.6;
}
#resizer:hover::after,#resizer.dragging::after{background:var(--accent-l);opacity:1}

/* ── Misc ────────────────────────────────────────────── */
.hidden{display:none!important}
.spin{
  display:inline-block;width:10px;height:10px;
  border:2px solid var(--border2);border-top-color:var(--accent);
  border-radius:50%;animation:spin .6s linear infinite;vertical-align:middle;
}
@keyframes spin{to{transform:rotate(360deg)}}
</style>
</head>
<body>

<!-- Drag overlay -->
<div id="drag-overlay">
  <div class="drag-inner">
    <div class="d-icon">📂</div>
    <div class="d-text">松开以打开 JSONL 文件</div>
  </div>
</div>

<!-- Toolbar -->
<div id="toolbar">
  <div id="logo">
    <div id="logo-icon">⬡</div>
    <span id="logo-text">JSONL Viewer</span>
  </div>
  <div class="path-wrap">
    <span style="color:var(--fg3);font-size:12px;flex-shrink:0">📄</span>
    <input id="path-input" type="text" placeholder="输入文件路径，或点击「浏览」选择文件…" />
  </div>
  <button class="tb-btn" onclick="browseFile()">📂 浏览</button>
  <button class="tb-btn primary" onclick="openFile()">打开</button>
  <input id="file-input" type="file" accept=".jsonl,.jsonlines,.json,.txt,*" onchange="onFilePicked(this)">
</div>

<!-- Nav -->
<div id="nav">
  <button class="nav-btn" id="btn-prev" disabled title="上一行 ←" onclick="goDelta(-1)">‹</button>
  <button class="nav-btn" id="btn-next" disabled title="下一行 →" onclick="goDelta(1)">›</button>
  <div class="slider-wrap">
    <span class="slider-label">行</span>
    <input id="line-slider" type="range" min="1" max="1" value="1" disabled
           oninput="onSliderInput(this.value)" onchange="onSliderCommit(this.value)">
    <span class="progress-pct" id="progress-pct">—</span>
  </div>
  <div class="line-num-wrap">
    <input id="line-input" type="number" min="1" max="1" value="1" disabled
           onchange="onLineChange(this.value)" onkeydown="onLineKey(event)">
    <span class="line-sep">/</span>
    <span id="total-label" style="color:var(--fg2);font-size:12px">0</span>
  </div>
</div>

<!-- Body -->
<div id="body">
  <!-- Sidebar -->
  <div id="sidebar">
    <div class="sidebar-head">
      <span class="sidebar-title">字段筛选</span>
      <div class="sidebar-actions">
        <button class="mini-btn" onclick="setAllFields(true)">全选</button>
        <button class="mini-btn" onclick="setAllFields(false)">清空</button>
      </div>
    </div>
    <div class="search-wrap">
      <div class="search-box">
        <span class="search-icon">🔍</span>
        <input id="field-search" type="text" placeholder="搜索字段…" oninput="filterFields(this.value)">
      </div>
    </div>
    <div id="field-list">
      <div class="field-empty">— 加载文件后显示 —</div>
    </div>
  </div>

  <!-- Resizer -->
  <div id="resizer" title="拖动调整宽度"></div>

  <!-- Main -->
  <div id="main">
    <div class="empty-state" id="empty-state">
      <div class="empty-icon">📄</div>
      <div class="empty-title">请选择 JSONL 文件</div>
      <div class="empty-sub">支持路径输入 · 点击浏览按钮 · 直接拖放文件到窗口</div>
    </div>
    <div id="content" class="hidden field-cards"></div>
  </div>
</div>

<!-- Status bar -->
<div id="status-bar">
  <div class="dot"></div>
  <span id="status-text">就绪 — 请选择或输入 JSONL 文件路径</span>
</div>

<script>
// ── State ────────────────────────────────────────────────
let currentFile   = '';
let totalLines    = 0;
let currentLine   = 1;
let allFields     = [];
let selectedFields= new Set();
let sliderTimer   = null;
let nodeId        = 0;
let clientLines   = null;
let fieldSearch   = '';

// ── File opening ─────────────────────────────────────────
async function browseFile() {
  setStatus('loading', '正在打开文件选择器…');
  try {
    const r = await fetch('/api/browse');
    const d = await r.json();
    if (d.fallback) { document.getElementById('file-input').click(); return; }
    if (d.path) {
      document.getElementById('path-input').value = d.path;
      await openFilePath(d.path);
    } else { setStatus('ok', '已取消'); }
  } catch(e) {
    document.getElementById('file-input').click();
    setStatus('ok', '就绪');
  }
}

function onFilePicked(input) {
  const file = input.files[0];
  if (!file) return;
  setStatus('loading', `正在读取：${file.name}…`);
  const reader = new FileReader();
  reader.onload = (e) => {
    const lines = e.target.result.split('\n');
    if (lines.length && !lines[lines.length-1].trim()) lines.pop();
    clientLines = lines;
    currentFile = file.name;
    totalLines  = lines.length;
    const {fields} = extractFields(lines);
    allFields = fields; selectedFields = new Set(fields);
    updateControls(); updateFieldsUI(); loadLine(1);
    setStatus('ok', `已加载：${file.name} — ${totalLines.toLocaleString()} 行`);
  };
  reader.onerror = () => setStatus('error', '读取文件失败');
  reader.readAsText(file);
}

function extractFields(lines) {
  const set = new Set(), fields = [];
  let sampled = 0;
  for (const line of lines) {
    if (sampled >= 50) break;
    const s = line.trim(); if (!s) continue;
    try {
      const obj = JSON.parse(s);
      if (obj && typeof obj === 'object' && !Array.isArray(obj)) {
        for (const k of Object.keys(obj)) { if (!set.has(k)){set.add(k);fields.push(k);} }
        sampled++;
      }
    } catch {}
  }
  return {fields};
}

async function openFile() {
  const path = document.getElementById('path-input').value.trim();
  if (!path) { setStatus('error', '请输入文件路径'); return; }
  await openFilePath(path);
}

async function openFilePath(path) {
  clientLines = null;
  setStatus('loading', `正在索引文件…`);
  try {
    const r = await fetch('/api/file_info?path=' + encodeURIComponent(path));
    const d = await r.json();
    if (d.error) { setStatus('error', d.error); return; }
    currentFile = path; totalLines = d.total;
    allFields = d.fields || []; selectedFields = new Set(allFields);
    updateControls(); updateFieldsUI(); await loadLine(1);
    const fname = path.split('/').pop();
    setStatus('ok', `${fname} — 共 ${totalLines.toLocaleString()} 行`);
  } catch(e) { setStatus('error', '加载失败：' + e.message); }
}

// ── Navigation ───────────────────────────────────────────
function updateControls() {
  const sl = document.getElementById('line-slider');
  const li = document.getElementById('line-input');
  sl.max = totalLines; sl.min = 1; sl.value = 1; sl.disabled = !totalLines;
  li.max = totalLines; li.min = 1; li.value = 1; li.disabled = !totalLines;
  document.getElementById('total-label').textContent = totalLines.toLocaleString();
  document.getElementById('btn-prev').disabled = true;
  document.getElementById('btn-next').disabled = !totalLines;
  document.getElementById('progress-pct').textContent = totalLines ? '0%' : '—';
  currentLine = 1;
}

function goDelta(d) { onLineChange(currentLine + d); }

function onSliderInput(val) {
  const n = parseInt(val);
  document.getElementById('line-input').value = n;
  updateProgress(n);
  clearTimeout(sliderTimer);
  sliderTimer = setTimeout(() => loadLine(n), 300);
}

function onSliderCommit(val) {
  clearTimeout(sliderTimer);
  loadLine(parseInt(val));
}

function onLineChange(val) {
  let n = parseInt(val);
  if (isNaN(n)) return;
  n = Math.max(1, Math.min(totalLines, n));
  document.getElementById('line-input').value = n;
  document.getElementById('line-slider').value = n;
  updateProgress(n);
  loadLine(n);
}

function onLineKey(e) {
  if (e.key === 'Enter')     { onLineChange(e.target.value); return; }
  if (e.key === 'ArrowUp')   { e.preventDefault(); onLineChange(currentLine + 1); }
  if (e.key === 'ArrowDown') { e.preventDefault(); onLineChange(currentLine - 1); }
}

function updateProgress(n) {
  if (!totalLines) return;
  const pct = Math.round((n / totalLines) * 100);
  document.getElementById('progress-pct').textContent = pct + '%';
  document.getElementById('btn-prev').disabled = n <= 1;
  document.getElementById('btn-next').disabled = n >= totalLines;
}

async function loadLine(n) {
  if (!totalLines) return;
  n = Math.max(1, Math.min(totalLines, n));
  currentLine = n;
  document.getElementById('line-slider').value = n;
  document.getElementById('line-input').value = n;
  updateProgress(n);

  let raw = '';
  if (clientLines) {
    raw = clientLines[n-1] ?? '';
  } else {
    try {
      const r = await fetch('/api/line?path=' + encodeURIComponent(currentFile) + '&line=' + n);
      const d = await r.json();
      if (d.error) { setStatus('error', d.error); return; }
      raw = d.content;
    } catch(e) { setStatus('error', '获取数据失败：' + e.message); return; }
  }
  renderContent(raw.trim());
}

// ── Fields UI ────────────────────────────────────────────
function updateFieldsUI() {
  renderFieldList(fieldSearch);
}

function filterFields(q) {
  fieldSearch = q.toLowerCase();
  renderFieldList(fieldSearch);
}

function renderFieldList(q) {
  const list = document.getElementById('field-list');
  if (!allFields.length) {
    list.innerHTML = '<div class="field-empty">— 非对象行，无字段 —</div>';
    return;
  }
  const filtered = q ? allFields.filter(f => f.toLowerCase().includes(q)) : allFields;
  if (!filtered.length) {
    list.innerHTML = `<div class="field-empty">没有匹配的字段</div>`;
    return;
  }
  list.innerHTML = filtered.map(f => {
    const active = selectedFields.has(f) ? 'active' : '';
    return `<div class="field-item ${active}" data-field="${escapeHtml(f)}" onclick="toggleField(this)">
      <div class="fi-check">✓</div>
      <div class="fi-dot"></div>
      <div class="fi-name" title="${escapeHtml(f)}">${escapeHtml(f)}</div>
    </div>`;
  }).join('');
}

function toggleField(el) {
  const f = el.dataset.field;
  if (selectedFields.has(f)) { selectedFields.delete(f); el.classList.remove('active'); }
  else                        { selectedFields.add(f);    el.classList.add('active'); }
  loadLine(currentLine);
}

function setAllFields(all) {
  if (all) selectedFields = new Set(allFields);
  else selectedFields.clear();
  renderFieldList(fieldSearch);
  loadLine(currentLine);
}

// ── Rendering ────────────────────────────────────────────
function renderContent(raw) {
  nodeId = 0;
  const empty  = document.getElementById('empty-state');
  const content= document.getElementById('content');
  empty.classList.add('hidden');
  content.classList.remove('hidden');

  if (!raw) {
    content.innerHTML = `<div class="raw-card"><div class="raw-label">空行</div><div class="raw-text" style="color:var(--fg3)">(此行为空)</div></div>`;
    return;
  }

  let parsed;
  try { parsed = JSON.parse(raw); } catch {
    content.innerHTML = `<div class="raw-card"><div class="raw-label">原始文本</div><div class="raw-text">${escapeHtml(raw)}</div></div>`;
    return;
  }

  // Top-level object → card rows
  if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
    const keys = Object.keys(parsed).filter(k => !allFields.length || selectedFields.has(k));
    if (!keys.length) {
      content.innerHTML = `<div class="raw-card"><div class="raw-label">提示</div><div class="raw-text" style="color:var(--fg3)">没有选中的字段，请在左侧勾选字段</div></div>`;
      return;
    }
    content.innerHTML = keys.map(k => renderFieldCard(k, parsed[k])).join('');
    return;
  }

  // Array or primitive at root
  content.innerHTML = `<div class="raw-card"><div class="raw-label">内容</div><div class="json-tree">${renderVal(parsed, 0, true)}</div></div>`;
}

function typeBadge(v) {
  if (v === null) return '<span class="fcard-type-badge type-null">null</span>';
  if (v === undefined) return '<span class="fcard-type-badge type-null">undef</span>';
  if (typeof v === 'boolean') return `<span class="fcard-type-badge type-bool">bool</span>`;
  if (typeof v === 'number')  return `<span class="fcard-type-badge type-num">num</span>`;
  if (typeof v === 'string')  return `<span class="fcard-type-badge type-str">str</span>`;
  if (Array.isArray(v))       return `<span class="fcard-type-badge type-arr">array[${v.length}]</span>`;
  return `<span class="fcard-type-badge type-obj">obj</span>`;
}

function renderFieldCard(key, val) {
  const id = 'fc' + (nodeId++);
  let valHtml = '';
  let actions = '';

  if (val === null || val === undefined) {
    valHtml = `<span class="v-null">${val === null ? 'null' : 'undefined'}</span>`;
  } else if (typeof val === 'boolean') {
    valHtml = val
      ? `<span class="v-bool-true">✓ true</span>`
      : `<span class="v-bool-false">✗ false</span>`;
  } else if (typeof val === 'number') {
    valHtml = `<span class="v-num">${val}</span>`;
  } else if (typeof val === 'string') {
    valHtml = renderStringVal(val, id);
    actions = stringActions(val, id);
  } else if (Array.isArray(val) || typeof val === 'object') {
    valHtml = `<div class="json-tree" id="jt${id}">${renderVal(val, 0, true)}</div>`;
  }

  return `<div class="fcard">
    <div class="fcard-header">
      <div class="fcard-key">
        <span class="fcard-key-text">${escapeHtml(key)}</span>
        ${typeBadge(val)}
      </div>
      <div class="fcard-val">
        <div class="fcard-val-inner" id="vi${id}">${valHtml}</div>
        ${actions ? `<div class="val-actions">${actions}</div>` : ''}
      </div>
    </div>
  </div>`;
}

function tryParseJSON(s) {
  const t = s.trim();
  if (!((t.startsWith('{') && t.endsWith('}')) || (t.startsWith('[') && t.endsWith(']')))) return null;
  try { return JSON.parse(t); } catch { return null; }
}

function renderStringVal(s, id) {
  const escaped = escapeHtml(s);

  // 1. Embedded JSON string — show as JSON tree by default, raw toggle available
  const parsed = tryParseJSON(s);
  if (parsed !== null && typeof parsed === 'object') {
    nodeId++; // ensure unique sub-ids
    const treeHtml = `<div class="json-tree" id="jst${id}">${renderVal(parsed, 0, true)}</div>`;
    return `${treeHtml}<div class="v-str hidden" id="rs${id}" style="margin-top:6px">${escaped}</div>`;
  }

  // 2. Markdown
  if (looksLikeMD(s)) {
    let mdHtml = '';
    try { mdHtml = marked.parse(s); } catch { mdHtml = escaped; }
    return `<div class="md-view" id="md${id}">${mdHtml}</div>
            <div class="v-str hidden" id="rs${id}">${escaped}</div>`;
  }

  // 3. Long plain string — collapsible
  if (s.length > 120) {
    return `<div class="v-str long" id="ls${id}" onclick="expandStr('${id}')">${escaped}</div>`;
  }

  return `<span class="v-str">${escaped}</span>`;
}

function stringActions(s, id) {
  const parsed = tryParseJSON(s);
  if (parsed !== null && typeof parsed === 'object') {
    return `<button class="val-btn active" id="mdb${id}" onclick="toggleRawCard('${id}','jst')">{ } JSON</button>`;
  }
  if (looksLikeMD(s)) {
    return `<button class="val-btn active" id="mdb${id}" onclick="toggleMDCard('${id}')">🔤 MD</button>`;
  }
  return '';
}

function toggleRawCard(id, treeElemId) {
  const tree = document.getElementById(treeElemId + id);
  const raw  = document.getElementById('rs' + id);
  const btn  = document.getElementById('mdb' + id);
  if (!tree || !raw) return;
  const showingTree = !tree.classList.contains('hidden');
  tree.classList.toggle('hidden', showingTree);
  raw.classList.toggle('hidden', !showingTree);
  if (btn) {
    btn.classList.toggle('active', !showingTree);
    btn.textContent = showingTree ? '🔤 原文' : '{ } JSON';
  }
}

function expandStr(id) {
  const el = document.getElementById('ls' + id);
  if (el) el.classList.toggle('expanded');
}

function toggleMDCard(id) {
  const md  = document.getElementById('md' + id);
  const raw = document.getElementById('rs' + id);
  const btn = document.getElementById('mdb' + id);
  if (!md || !raw) return;
  const showingMD = !md.classList.contains('hidden');
  md.classList.toggle('hidden', showingMD);
  raw.classList.toggle('hidden', !showingMD);
  if (btn) btn.classList.toggle('active', !showingMD);
}

// ── Nested JSON tree ──────────────────────────────────────
function renderVal(v, depth, isRoot) {
  if (v === null)      return `<span class="j-null-v">null</span>`;
  if (v === undefined) return `<span class="j-null-v">undefined</span>`;
  if (typeof v === 'boolean') return `<span class="j-bool-v">${v}</span>`;
  if (typeof v === 'number')  return `<span class="j-num-v">${v}</span>`;
  if (typeof v === 'string')  return renderNestedStr(v);
  if (Array.isArray(v))       return renderArr(v, depth, isRoot);
  if (typeof v === 'object')  return renderObj(v, depth, isRoot);
  return escapeHtml(String(v));
}

// Renders a string value inside a JSON tree — detects embedded JSON / Markdown
function renderNestedStr(s) {
  const id = 'ns' + (nodeId++);

  // 1. Embedded JSON object/array
  const parsed = tryParseJSON(s);
  if (parsed !== null && typeof parsed === 'object') {
    const treeHtml = `<div class="json-tree" style="margin-top:4px" id="njst${id}">${renderVal(parsed, 0, true)}</div>`;
    const rawHtml  = `<span class="j-str-v hidden" id="njsr${id}">&quot;${escapeHtml(s)}&quot;</span>`;
    const btn      = `<button class="val-btn active" id="njsb${id}" style="margin-left:4px;vertical-align:middle" onclick="toggleNestedStr('${id}')">{ } JSON</button>`;
    return `<span>${btn}${treeHtml}${rawHtml}</span>`;
  }

  // 2. Markdown (multiline with markup)
  if (looksLikeMD(s)) {
    let mdHtml = '';
    try { mdHtml = marked.parse(s); } catch { mdHtml = escapeHtml(s); }
    const md  = `<div class="md-view" style="margin-top:4px" id="njsm${id}">${mdHtml}</div>`;
    const raw = `<span class="j-str-v hidden" id="njsr${id}">&quot;${escapeHtml(s)}&quot;</span>`;
    const btn = `<button class="val-btn active" id="njsb${id}" style="margin-left:4px;vertical-align:middle" onclick="toggleNestedMD('${id}')">🔤 MD</button>`;
    return `<span>${btn}${md}${raw}</span>`;
  }

  // 3. Plain string
  return `<span class="j-str-v">&quot;${escapeHtml(s)}&quot;</span>`;
}

function toggleNestedStr(id) {
  const tree = document.getElementById('njst' + id);
  const raw  = document.getElementById('njsr' + id);
  const btn  = document.getElementById('njsb' + id);
  if (!tree || !raw) return;
  const showTree = tree.classList.toggle('hidden');
  raw.classList.toggle('hidden', !showTree);
  if (btn) { btn.classList.toggle('active', !showTree); btn.textContent = showTree ? '{ } JSON' : '🔤 原文'; }
}

function toggleNestedMD(id) {
  const md  = document.getElementById('njsm' + id);
  const raw = document.getElementById('njsr' + id);
  const btn = document.getElementById('njsb' + id);
  if (!md || !raw) return;
  const showMD = md.classList.toggle('hidden');
  raw.classList.toggle('hidden', !showMD);
  if (btn) { btn.classList.toggle('active', !showMD); btn.textContent = showMD ? '🔤 MD' : '🔤 原文'; }
}

function renderObj(obj, depth, isRoot) {
  const keys = Object.keys(obj);
  const id = 'n' + (nodeId++);
  if (!keys.length) return `<span class="j-bracket">{}</span>`;
  const preview = keys.slice(0,3).map(k=>escapeHtml(k)).join(', ') + (keys.length>3?'…':'');
  let html = '';
  if (!isRoot) html += `<span class="toggler" data-id="${id}" onclick="toggleNode('${id}')">▾</span>`;
  html += `<span class="j-bracket">{</span>`;
  if (!isRoot) html += `<span class="j-preview hidden" id="pv${id}" onclick="toggleNode('${id}')">${keys.length} keys: ${preview}</span>`;
  html += `<div class="j-children" id="${id}">`;
  keys.forEach((k,i) => {
    html += `<div class="j-entry"><span class="j-key">"${escapeHtml(k)}"</span><span class="j-colon">:</span>${renderVal(obj[k],depth+1,false)}${i<keys.length-1?'<span class="j-comma">,</span>':''}</div>`;
  });
  html += `</div><span class="j-bracket">}</span>`;
  return html;
}

function renderArr(arr, depth, isRoot) {
  const id = 'n' + (nodeId++);
  if (!arr.length) return `<span class="j-bracket">[]</span>`;
  let html = '';
  if (!isRoot) html += `<span class="toggler" data-id="${id}" onclick="toggleNode('${id}')">▾</span>`;
  html += `<span class="j-bracket">[</span>`;
  if (!isRoot) html += `<span class="j-preview hidden" id="pv${id}" onclick="toggleNode('${id}')">${arr.length} items</span>`;
  html += `<div class="j-children" id="${id}">`;
  arr.forEach((item,i) => {
    html += `<div class="j-entry"><span class="j-idx">${i}</span><span class="j-colon">:</span>${renderVal(item,depth+1,false)}${i<arr.length-1?'<span class="j-comma">,</span>':''}</div>`;
  });
  html += `</div><span class="j-bracket">]</span>`;
  return html;
}

function looksLikeMD(s) {
  // must have actual newlines (real multiline) OR enough markdown syntax
  const hasNewline = s.includes('\n');
  if (!hasNewline) return false;
  return s.length > 20 && /(#{1,6} |```|\*\*|__|\n- |\n\* |\n\d+\. )/.test(s);
}

function toggleNode(id) {
  const ch = document.getElementById(id);
  const pv = document.getElementById('pv'+id);
  if (!ch) return;
  const collapsed = ch.classList.toggle('collapsed');
  if (pv) pv.classList.toggle('hidden', !collapsed);
  const t = document.querySelector(`.toggler[data-id="${id}"]`);
  if (t) t.textContent = collapsed ? '▸' : '▾';
}

// ── Utilities ────────────────────────────────────────────
function escapeHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

function setStatus(type, msg) {
  const bar = document.getElementById('status-bar');
  bar.className = type;
  document.getElementById('status-text').textContent = msg;
}

// ── Drag & Drop ───────────────────────────────────────────
let dragCnt = 0;
document.addEventListener('dragenter', e => { e.preventDefault(); dragCnt++; document.body.classList.add('drag-over'); });
document.addEventListener('dragleave', e => { if(--dragCnt<=0){dragCnt=0;document.body.classList.remove('drag-over');} });
document.addEventListener('dragover',  e => e.preventDefault());
document.addEventListener('drop', e => {
  e.preventDefault(); dragCnt=0; document.body.classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (!file) return;
  if (file.path) {
    document.getElementById('path-input').value = file.path;
    openFilePath(file.path);
  } else {
    const dt = new DataTransfer(); dt.items.add(file);
    const fi = document.getElementById('file-input');
    fi.files = dt.files; onFilePicked(fi);
  }
});

document.getElementById('path-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') openFile();
});

// ── Resizable sidebar ────────────────────────────────────
(function() {
  const resizer = document.getElementById('resizer');
  const sidebar = document.getElementById('sidebar');
  const MIN_W = 120, MAX_W = 520;
  let startX, startW;

  resizer.addEventListener('mousedown', e => {
    startX = e.clientX;
    startW = sidebar.offsetWidth;
    resizer.classList.add('dragging');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';

    function onMove(e) {
      const w = Math.min(MAX_W, Math.max(MIN_W, startW + (e.clientX - startX)));
      sidebar.style.width = w + 'px';
    }
    function onUp() {
      resizer.classList.remove('dragging');
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    }
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  });
})();

// Keyboard shortcuts: ← → navigate lines
document.addEventListener('keydown', e => {
  if (['INPUT','TEXTAREA'].includes(e.target.tagName)) return;
  if (e.key === 'ArrowLeft')  goDelta(-1);
  if (e.key === 'ArrowRight') goDelta(1);
});
</script>
</body>
</html>
"""


# ─────────────────────────────────────────────────────────────────────────────
# HTTP Handler
# ─────────────────────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        route  = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        if route == '/':
            self._serve_html()
        elif route == '/api/browse':
            self._serve_browse()
        elif route == '/api/file_info':
            self._serve_file_info(params)
        elif route == '/api/line':
            self._serve_line(params)
        else:
            self.send_error(404)

    # ── routes ────────────────────────────────────────────────────────────────

    def _serve_html(self):
        body = HTML.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()

    def _serve_browse(self):
        import subprocess
        try:
            # Use macOS osascript (AppleScript) — no tkinter needed, works on any macOS version
            apple_script = (
                'tell application "System Events"\n'
                '    activate\n'
                'end tell\n'
                'set f to choose file with prompt "选择 JSONL 文件" '
                'of type {"jsonl", "jsonlines", "json", "txt", ""}\n'
                'return POSIX path of f'
            )
            result = subprocess.run(
                ['osascript', '-e', apple_script],
                capture_output=True, text=True, timeout=120
            )
            path = result.stdout.strip()
            if result.returncode != 0 or not path:
                # User cancelled or error
                self._send_json({'path': ''})
            else:
                self._send_json({'path': path})
        except Exception as e:
            self._send_json({'path': '', 'fallback': True, 'error': str(e)})

    def _serve_file_info(self, params):
        fp = params.get('path', [''])[0]
        if not fp:
            self._send_json({'error': '未指定文件路径'}, 400)
            return
        if not os.path.isfile(fp):
            self._send_json({'error': f'文件不存在：{fp}'}, 404)
            return
        try:
            total, fields = build_index(fp)
            self._send_json({'total': total, 'fields': fields})
        except Exception as e:
            self._send_json({'error': str(e)}, 500)

    def _serve_line(self, params):
        fp  = params.get('path', [''])[0]
        raw = params.get('line', ['1'])[0]
        try:
            n = int(raw)
        except ValueError:
            self._send_json({'error': '无效行号'}, 400)
            return
        if not fp or not os.path.isfile(fp):
            self._send_json({'error': '文件不存在'}, 404)
            return
        try:
            content = read_line(fp, n)
            self._send_json({'line': n, 'content': content})
        except Exception as e:
            self._send_json({'error': str(e)}, 500)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()

    def log_message(self, fmt, *args):
        pass  # suppress default access log


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    PORT = 5174
    # Allow overriding port via env
    PORT = int(os.environ.get('JSONL_PORT', PORT))

    # Try to bind; if port busy, find a free one
    import socket
    for p in range(PORT, PORT + 20):
        try:
            httpd = ThreadingHTTPServer(('127.0.0.1', p), Handler)
            PORT = p
            break
        except OSError:
            continue
    else:
        print('无法找到可用端口，退出', file=sys.stderr)
        sys.exit(1)
    url   = f'http://127.0.0.1:{PORT}'
    print(f'JSONL Viewer  →  {url}')
    print('按 Ctrl+C 退出')

    threading.Timer(0.4, lambda: webbrowser.open(url)).start()

    # If a file path is passed as CLI argument, open it automatically
    if len(sys.argv) > 1:
        initial = sys.argv[1]
        if os.path.isfile(initial):
            # The frontend will handle it; we just pre-build the index
            build_index(initial)
            print(f'预加载文件：{initial}')

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\n已退出')
