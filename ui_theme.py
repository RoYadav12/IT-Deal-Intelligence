"""
Look & feel for the app: animated hero banner, count-up style stat cards,
live pipeline stepper, glowing key-status pills, fading table rows.

Everything is plain CSS animation (no extra packages). Colours use
translucent greys so the same styling works in both light and dark themes,
and animations switch off for people who prefer reduced motion.
"""

import html

import streamlit as st


def esc(value):
    """HTML-escape untrusted text. '$' is also neutralised so Streamlit's
    markdown never mistakes a deal value like '$5M ... $2M' for LaTeX."""
    return html.escape(str(value if value is not None else "")).replace("$", "&#36;")


def flat(markup):
    """Collapse HTML to one line. Markdown treats blank lines / 4-space
    indents inside HTML as code blocks - flattening avoids that entirely."""
    return " ".join(line.strip() for line in markup.strip().splitlines() if line.strip())


_ROW_DELAYS = "".join(
    f".deal-table tbody tr:nth-child({i}){{animation-delay:{i * 0.045:.3f}s}}"
    for i in range(1, 21)
)

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

/* Inter only on our own components - overriding Streamlit's own elements would break its icon font. */
.hero, .stat-card, .section-title, .section-sub, .stepper, .live-msg, .pill, .callout, .empty, .table-wrap, .chip { font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif; }
.block-container { padding-top: 4rem; max-width: 1400px; }

@keyframes gradientShift { 0% {background-position: 0% 50%;} 50% {background-position: 100% 50%;} 100% {background-position: 0% 50%;} }
@keyframes fadeUp { from {opacity: 0; transform: translateY(14px);} to {opacity: 1; transform: translateY(0);} }
@keyframes popIn { 0% {opacity: 0; transform: translateY(12px) scale(.94);} 70% {transform: translateY(-2px) scale(1.02);} 100% {opacity: 1; transform: translateY(0) scale(1);} }
@keyframes floaty { 0%,100% {transform: translateY(0) translateX(0);} 50% {transform: translateY(-14px) translateX(8px);} }
@keyframes pulseRing { 0% {box-shadow: 0 0 0 0 rgba(99,102,241,.55);} 70% {box-shadow: 0 0 0 12px rgba(99,102,241,0);} 100% {box-shadow: 0 0 0 0 rgba(99,102,241,0);} }
@keyframes pulseGreen { 0% {box-shadow: 0 0 0 0 rgba(34,197,94,.6);} 70% {box-shadow: 0 0 0 8px rgba(34,197,94,0);} 100% {box-shadow: 0 0 0 0 rgba(34,197,94,0);} }
@keyframes shimmer { 0% {background-position: -200% 0;} 100% {background-position: 200% 0;} }
@keyframes rowIn { from {opacity: 0; transform: translateX(-10px);} to {opacity: 1; transform: translateX(0);} }
@keyframes ripple { 0% {transform: scale(.3); opacity: .8;} 100% {transform: scale(1.6); opacity: 0;} }
@keyframes nudge { 0%,100% {transform: translateX(0);} 50% {transform: translateX(-6px);} }

/* ---------- hero ---------- */
.hero { position: relative; overflow: hidden; border-radius: 20px; padding: 30px 34px; margin-bottom: 18px; color: #fff;
  background: linear-gradient(120deg, #4f46e5, #7c3aed, #0ea5e9, #4f46e5); background-size: 300% 300%;
  animation: gradientShift 14s ease infinite, fadeUp .7s ease both; box-shadow: 0 18px 40px -18px rgba(79,70,229,.6); }
.hero::before, .hero::after { content: ""; position: absolute; border-radius: 50%; background: rgba(255,255,255,.12); animation: floaty 9s ease-in-out infinite; }
.hero::before { width: 220px; height: 220px; right: -50px; top: -80px; }
.hero::after { width: 140px; height: 140px; right: 180px; bottom: -70px; animation-delay: -4s; }
.hero h1 { margin: 0 0 6px 0; font-size: 2.1rem; font-weight: 800; letter-spacing: -.02em; color: #fff; padding: 0; }
.hero p { margin: 0; font-size: 1.02rem; opacity: .93; max-width: 760px; }
.chips { margin-top: 16px; display: flex; flex-wrap: wrap; gap: 8px; position: relative; z-index: 1; }
.chip { background: rgba(255,255,255,.18); border: 1px solid rgba(255,255,255,.3); backdrop-filter: blur(6px); padding: 5px 13px; border-radius: 999px; font-size: .82rem; font-weight: 600; animation: popIn .6s ease both; }
.chip:nth-child(2) { animation-delay: .1s; } .chip:nth-child(3) { animation-delay: .2s; } .chip:nth-child(4) { animation-delay: .3s; }

/* ---------- stat cards ---------- */
.stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 14px; margin: 6px 0 18px 0; }
.stat-card { position: relative; border-radius: 16px; padding: 16px 18px; background: rgba(127,127,127,.08); border: 1px solid rgba(127,127,127,.22);
  animation: popIn .6s ease both; transition: transform .2s ease, box-shadow .2s ease; overflow: hidden; }
.stat-card:hover { transform: translateY(-4px); box-shadow: 0 14px 28px -16px rgba(79,70,229,.55); }
.stat-card::before { content: ""; position: absolute; left: 0; top: 0; right: 0; height: 4px; background: linear-gradient(90deg, #6366f1, #06b6d4); background-size: 200% 100%; animation: shimmer 4s linear infinite; }
.stat-card.good::before { background: linear-gradient(90deg, #22c55e, #14b8a6); background-size: 200% 100%; }
.stat-card.warn::before { background: linear-gradient(90deg, #f59e0b, #f97316); background-size: 200% 100%; }
.stat-card.bad::before { background: linear-gradient(90deg, #ef4444, #ec4899); background-size: 200% 100%; }
.stat-card:nth-child(2) { animation-delay: .08s; } .stat-card:nth-child(3) { animation-delay: .16s; } .stat-card:nth-child(4) { animation-delay: .24s; }
.stat-icon { font-size: 1.25rem; }
.stat-value { font-size: 2rem; font-weight: 800; line-height: 1.15; margin-top: 4px; letter-spacing: -.02em; }
.stat-label { font-size: .8rem; opacity: .72; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; }

/* ---------- section headings ---------- */
.section-title { display: flex; align-items: center; gap: 10px; font-size: 1.45rem; font-weight: 800; margin: 26px 0 4px 0; animation: fadeUp .6s ease both; letter-spacing: -.01em; }
.section-title .bar { width: 5px; height: 26px; border-radius: 4px; background: linear-gradient(180deg, #6366f1, #06b6d4); }
.section-sub { opacity: .72; font-size: .92rem; margin-bottom: 10px; }

/* ---------- stepper ---------- */
.stepper { display: flex; align-items: center; gap: 0; margin: 10px 0 6px 0; flex-wrap: wrap; }
.step { display: flex; align-items: center; gap: 9px; font-weight: 600; font-size: .92rem; opacity: .55; transition: opacity .3s; }
.step .dot { width: 30px; height: 30px; border-radius: 50%; display: grid; place-items: center; font-size: .85rem; background: rgba(127,127,127,.2); font-weight: 700; }
.step.active { opacity: 1; } .step.active .dot { background: #6366f1; color: #fff; animation: pulseRing 1.5s infinite; }
.step.done { opacity: 1; } .step.done .dot { background: #22c55e; color: #fff; }
.step-line { height: 3px; width: 46px; margin: 0 10px; border-radius: 3px; background: rgba(127,127,127,.25); position: relative; overflow: hidden; }
.step-line.done { background: #22c55e; }
.step-line.active::after { content: ""; position: absolute; inset: 0; background: linear-gradient(90deg, transparent, #6366f1, transparent); background-size: 200% 100%; animation: shimmer 1.2s linear infinite; }
.live-msg { font-size: .85rem; opacity: .8; margin: 2px 0 6px 2px; word-break: break-all; }

/* ---------- key status pills (sidebar) ---------- */
.pill { display: flex; align-items: center; gap: 9px; padding: 7px 12px; border-radius: 12px; margin: 6px 0; font-size: .85rem; font-weight: 600; background: rgba(127,127,127,.1); border: 1px solid rgba(127,127,127,.2); animation: fadeUp .5s ease both; }
.pill .pdot { width: 10px; height: 10px; border-radius: 50%; background: #ef4444; flex: none; }
.pill.ok .pdot { background: #22c55e; animation: pulseGreen 1.8s infinite; }
.pill .note { opacity: .65; font-weight: 500; margin-left: auto; font-size: .75rem; }

/* ---------- call-out + empty state ---------- */
.callout { display: flex; align-items: center; gap: 14px; padding: 14px 18px; border-radius: 14px; margin: 4px 0 16px 0; background: rgba(245,158,11,.12); border: 1px solid rgba(245,158,11,.4); animation: fadeUp .6s ease both; }
.callout .arrow { font-size: 1.5rem; animation: nudge 1.4s ease-in-out infinite; }
.empty { text-align: center; padding: 34px 10px 24px 10px; animation: fadeUp .6s ease both; }
.radar { position: relative; width: 90px; height: 90px; margin: 0 auto 14px auto; }
.radar span { position: absolute; inset: 0; border-radius: 50%; border: 2px solid #6366f1; animation: ripple 2.6s ease-out infinite; }
.radar span:nth-child(2) { animation-delay: .85s; } .radar span:nth-child(3) { animation-delay: 1.7s; }
.radar i { position: absolute; inset: 34px; border-radius: 50%; background: #6366f1; }
.empty h3 { margin: 0 0 4px 0; } .empty p { opacity: .7; margin: 0; }

/* ---------- table ---------- */
.table-wrap { overflow: auto; max-height: 680px; border-radius: 14px; border: 1px solid rgba(127,127,127,.25); animation: fadeUp .7s ease both; }
.deal-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.deal-table th { position: sticky; top: 0; z-index: 5; background: #111827; color: #fff; text-align: left; font-weight: 600; padding: 11px 12px; white-space: nowrap; }
.deal-table td { padding: 10px 12px; vertical-align: top; border-bottom: 1px solid rgba(127,127,127,.15); overflow-wrap: break-word; min-width: 90px; }
.deal-table td:nth-child(9) { white-space: nowrap; }
.deal-table tbody tr { animation: rowIn .5s ease both; transition: background .15s; }
.deal-table tbody tr:hover { background: rgba(99,102,241,.13); }
.deal-table a { text-decoration: none; color: #6366f1; font-weight: 600; } .deal-table a:hover { text-decoration: underline; }
.clamp-cell { display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; text-overflow: ellipsis; line-height: 1.5; min-width: 220px; cursor: help; }
__ROW_DELAYS__

/* ---------- buttons & tabs ---------- */
div.stButton > button, div.stDownloadButton > button { border-radius: 12px; font-weight: 600; transition: transform .15s ease, box-shadow .15s ease; }
div.stButton > button:hover, div.stDownloadButton > button:hover { transform: translateY(-2px); box-shadow: 0 10px 22px -12px rgba(79,70,229,.7); }
div.stButton > button:active { transform: translateY(0); }
button[data-baseweb="tab"] { font-weight: 600; }
button[data-baseweb="tab"][aria-selected="true"] { color: #6366f1; }
[data-baseweb="tab-highlight"] { background-color: #6366f1 !important; }
button[kind="primary"], [data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primary"] > button { background: linear-gradient(120deg, #6366f1, #7c3aed) !important; border: none !important; color: #fff !important; background-size: 200% 200%; }
button[kind="primary"]:hover, [data-testid="stBaseButton-primary"]:hover { background-position: 100% 0; filter: brightness(1.06); }
button[kind="primary"]:disabled, [data-testid="stBaseButton-primary"]:disabled { opacity: .45; filter: grayscale(.4); }
section[data-testid="stSidebar"] .block-container { padding-top: 1rem; }

@media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation: none !important; transition: none !important; } }
""".replace("__ROW_DELAYS__", _ROW_DELAYS)


def inject():
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)


def hero(title, subtitle, chips=()):
    chip_html = "".join(f'<span class="chip">{esc(c)}</span>' for c in chips)
    st.markdown(
        flat(f'<div class="hero"><h1>{esc(title)}</h1><p>{esc(subtitle)}</p>'
             f'<div class="chips">{chip_html}</div></div>'),
        unsafe_allow_html=True,
    )


def section(title, icon="", subtitle=""):
    sub = f'<div class="section-sub">{esc(subtitle)}</div>' if subtitle else ""
    st.markdown(
        flat(f'<div class="section-title"><span class="bar"></span>{esc(icon)} {esc(title)}</div>{sub}'),
        unsafe_allow_html=True,
    )


def stat_cards_html(items):
    """items: [(label, value, icon, tone)] with tone in '', good, warn, bad."""
    cards = "".join(
        f'<div class="stat-card {esc(tone)}"><div class="stat-icon">{esc(icon)}</div>'
        f'<div class="stat-value">{esc(value)}</div><div class="stat-label">{esc(label)}</div></div>'
        for label, value, icon, tone in items
    )
    return flat(f'<div class="stat-grid">{cards}</div>')


def stepper_html(labels, active):
    """Render steps; those before `active` are done, `active` pulses."""
    parts = []
    for i, label in enumerate(labels):
        state = "done" if i < active else "active" if i == active else ""
        mark = "&#10003;" if state == "done" else str(i + 1)
        parts.append(f'<div class="step {state}"><span class="dot">{mark}</span>{esc(label)}</div>')
        if i < len(labels) - 1:
            line = "done" if i < active else "active" if i == active else ""
            parts.append(f'<div class="step-line {line}"></div>')
    return flat(f'<div class="stepper">{"".join(parts)}</div>')


def live_message_html(text):
    return flat(f'<div class="live-msg">{esc(text)}</div>')


def key_pill_html(label, ok, note=""):
    note_html = f'<span class="note">{esc(note)}</span>' if note else ""
    return flat(f'<div class="pill {"ok" if ok else ""}"><span class="pdot"></span>{esc(label)}{note_html}</div>')


def keys_callout_html(problems):
    return flat(
        '<div class="callout"><span class="arrow">&#128072;</span><div>'
        '<b>Add your Serper API key in the sidebar to get started.</b><br>'
        f'<span style="opacity:.75">{esc("; ".join(problems))} '
        '(An AI key is optional — heuristic extraction works without one.)</span></div></div>'
    )


def empty_state_html(title, text):
    return flat(
        '<div class="empty"><div class="radar"><span></span><span></span><span></span><i></i></div>'
        f'<h3>{esc(title)}</h3><p>{esc(text)}</p></div>'
    )
