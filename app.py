"""
IT Deal Intelligence Platform - Streamlit app.

Serper searches the web (and scrapes pages). Structuring uses Claude/OpenAI
when you supply an LLM key, or a built-in heuristic extractor when you only
have a Serper key - so the app works with a single API key.
Paste keys into the sidebar - nothing is hard-coded or saved to disk.

Run locally:  streamlit run app.py
"""

import datetime
import inspect
import io
import os
from urllib.parse import urlparse

import pandas as pd
import plotly.express as px
import streamlit as st
from openpyxl.utils import get_column_letter

import config
import db
import discover
import extraction
import process_pending
import rss_ingest
import ui_theme

st.set_page_config(
    page_title="IT Deal Intelligence",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)
ui_theme.inject()

PALETTE = ["#6366f1", "#06b6d4", "#22c55e", "#f59e0b", "#ec4899", "#8b5cf6",
           "#14b8a6", "#f97316", "#3b82f6", "#84cc16"]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def stretch(fn):
    """Streamlit renamed use_container_width -> width='stretch'. Return
    whichever keyword this installed version understands."""
    try:
        if "width" in inspect.signature(fn).parameters:
            return {"width": "stretch"}
    except (TypeError, ValueError):
        pass
    return {"use_container_width": True}


def show_chart(fig):
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=10, b=10), height=330,
        font=dict(family="Inter, system-ui, sans-serif"),
    )
    st.plotly_chart(fig, **stretch(st.plotly_chart))


def server_secret(name):
    """A key configured on the server (Streamlit secrets / environment).
    Optional - the sidebar boxes always win when filled in."""
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    return config.clean_key(value) or config.clean_key(os.environ.get(name, ""))


def set_notice(slot, kind, message):
    st.session_state[f"notice_{slot}"] = (kind, message)


def show_notice(slot):
    notice = st.session_state.get(f"notice_{slot}")
    if notice:
        kind, message = notice
        getattr(st, kind)(message)


class LiveProgress:
    """Animated step tracker + progress bar + status line."""

    def __init__(self, labels):
        self.labels = labels
        self._stepper = st.empty()
        self._bar = st.progress(0.0)
        self._msg = st.empty()
        self.update(0, 0.0, "Starting...")

    def update(self, step, fraction, message=""):
        fraction = max(0.0, min(1.0, float(fraction)))
        step = max(0, min(step, len(self.labels) - 1))
        self._stepper.markdown(ui_theme.stepper_html(self.labels, step), unsafe_allow_html=True)
        self._bar.progress(min(1.0, (step + fraction) / len(self.labels)))
        self._msg.markdown(ui_theme.live_message_html(message), unsafe_allow_html=True)

    def finish(self):
        self._stepper.empty()
        self._bar.empty()
        self._msg.empty()


def fraction(done, total):
    return done / total if total else 1.0


@st.cache_resource
def get_conn():
    # Streamlit re-runs this whole script on every click; caching means one
    # shared connection instead of a new (leaked) one each time.
    return db.get_connection()


def safe_cell(value):
    """Stop spreadsheet formula injection: text from the web that starts with
    = + - @ would otherwise be run as a formula when opened in Excel."""
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def to_excel_bytes(df):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="IT Deals")
        sheet = writer.sheets["IT Deals"]
        for idx, col in enumerate(df.columns, start=1):
            longest = max([len(str(col))] + [len(str(v)) for v in df[col].head(300)])
            sheet.column_dimensions[get_column_letter(idx)].width = min(max(12, longest + 2), 60)
        sheet.freeze_panes = "A2"
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Hero + sidebar (API keys live here)
# ---------------------------------------------------------------------------

ui_theme.hero(
    "IT Deal Intelligence",
    "Search the web for IT deals - acquisitions, outsourcing, managed services, "
    "cloud - and turn them into a clean table you can download. Works with just a Serper key.",
    chips=["🔎 Serper web search", "⚡ Heuristic or Claude / OpenAI", "📅 Real Google date filter", "📥 Excel export"],
)

for key, default in (("text_key", 0), ("upload_key", 0), ("last_batch_ids", None)):
    st.session_state.setdefault(key, default)

with st.sidebar:
    st.markdown("## 🔐 Connect your APIs")
    st.caption(
        "Only the **Serper** key is required. An AI key is optional — without it, "
        "a built-in heuristic extractor structures the results. Keys stay in this "
        "browser session only and are never written to disk."
    )

    serper_typed = st.text_input(
        "Serper API key (required)", type="password", key="serper_key",
        placeholder="Paste your Serper key",
        help="Free key at serper.dev (Dashboard -> API key). Serper runs the Google searches and page scrapes.",
    )

    with st.expander("Optional: AI for higher-quality extraction", expanded=False):
        st.caption(
            "Leave blank to use free heuristic extraction from titles & snippets. "
            "Adding Claude or OpenAI improves party names, values, and summaries."
        )
        provider_label = st.selectbox(
            "AI provider", list(config.LLM_PROVIDERS), key="llm_provider_label",
        )
        provider = config.LLM_PROVIDERS[provider_label]
        llm_typed = st.text_input(
            f"{provider['short']} API key", type="password", key=f"llm_key_{provider['id']}",
            placeholder=provider["placeholder"], help=provider["help"],
        )
        model_typed = st.text_input(
            "Model (optional)", key=f"model_{provider['id']}",
            placeholder=provider["default_model"],
            help="Leave blank to use the recommended model.",
        )

    serper_from_server = not config.clean_key(serper_typed) and bool(server_secret("SERPER_API_KEY"))
    llm_from_server = not config.clean_key(llm_typed) and bool(server_secret(provider["key_env"]))
    creds = config.Credentials(
        serper_key=config.clean_key(serper_typed) or server_secret("SERPER_API_KEY"),
        llm_provider=provider["id"],
        llm_key=config.clean_key(llm_typed) or server_secret(provider["key_env"]),
        llm_model=config.clean_key(model_typed),
    )

    st.markdown(
        ui_theme.key_pill_html("Serper", bool(creds.serper_key), "server key" if serper_from_server else ""),
        unsafe_allow_html=True,
    )
    mode_note = "server key" if llm_from_server else ("active" if creds.has_llm else "heuristic mode")
    st.markdown(
        ui_theme.key_pill_html(
            provider["short"] if creds.has_llm else "Extraction",
            creds.has_llm,
            mode_note,
        ),
        unsafe_allow_html=True,
    )
    if not creds.has_llm and creds.serper_key:
        st.caption("Running in **Serper-only** mode (heuristic extraction). Add an AI key above for better quality.")

    problems = creds.problems()
    if st.button("Test my keys", disabled=bool(problems), **stretch(st.button)):
        with st.spinner("Checking keys..."):
            serper_ok, serper_msg = extraction.validate_serper(creds)
            (st.success if serper_ok else st.error)(f"Serper: {serper_msg}")
            if creds.has_llm:
                llm_ok, llm_msg = extraction.validate_llm(creds)
                (st.success if llm_ok else st.error)(f"{creds.llm_label}: {llm_msg}")
                if serper_ok and llm_ok:
                    st.toast("Both keys work - you're ready to go!", icon="✅")
            elif serper_ok:
                st.info("Serper key works. No AI key — heuristic extraction will be used.")
                st.toast("Serper key works - ready in heuristic mode!", icon="✅")
    st.caption(
        "Testing uses 1 Serper credit"
        + (" and a tiny AI call." if creds.has_llm else ".")
    )

conn = get_conn()
keys_missing = bool(problems)
if keys_missing:
    st.markdown(ui_theme.keys_callout_html(problems), unsafe_allow_html=True)

# Stat cards are drawn at the very end of the script (after any button has
# done its work) so the numbers are always current.
stats_slot = st.empty()

# ---------------------------------------------------------------------------
# Action tabs
# ---------------------------------------------------------------------------

counts_before = db.count_by_status(conn)
tab_discover, tab_rss, tab_urls = st.tabs(
    ["🔎 Discover deals", "📡 RSS pipeline", "🔗 Add URLs"]
)

# ---- Discover --------------------------------------------------------------
with tab_discover:
    ui_theme.section(
        "Discover deals from the web", "",
        "Serper searches Google with your exact date range; results are structured by AI (if keyed) or heuristics.",
    )

    c1, c2 = st.columns([1, 1])
    with c1:
        tenure_choices = list(config.TENURE_OPTIONS) + [config.CUSTOM_RANGE_LABEL]
        tenure_label = st.selectbox(
            "Tenure", tenure_choices, index=tenure_choices.index(config.DEFAULT_TENURE),
        )
    custom_start = custom_end = None
    with c2:
        if tenure_label == config.CUSTOM_RANGE_LABEL:
            d1, d2 = st.columns(2)
            today = datetime.date.today()
            custom_start = d1.date_input("Start date", value=today - datetime.timedelta(days=30), max_value=today)
            custom_end = d2.date_input("End date", value=today, max_value=today)
        else:
            start_d, end_d = discover.get_date_range(tenure_label)
            st.markdown(f"**Searching:** {start_d:%d %b %Y} -> {end_d:%d %b %Y}")

    f1, f2, f3, f4 = st.columns(4)
    selected_country = f1.selectbox("Country", config.DISCOVERY_COUNTRY_OPTIONS)
    selected_industry = f2.selectbox("Industry", config.DISCOVERY_INDUSTRY_OPTIONS)
    selected_technology = f3.selectbox("Technology", config.DISCOVERY_TECHNOLOGY_OPTIONS)
    selected_geography = f4.selectbox("Region", config.DISCOVERY_GEOGRAPHY_OPTIONS)

    extra_keywords = st.text_input(
        "Optional keywords (industry, region, deal type)",
        placeholder="e.g. healthcare, Europe, cybersecurity",
    )

    with st.expander("⚙️ Search settings (cost control)"):
        angles = st.multiselect(
            "Search angles (each one = 1 Serper search)",
            options=config.DISCOVERY_QUERIES, default=config.DISCOVERY_QUERIES,
        )
        s1, s2 = st.columns(2)
        results_per_query = s1.slider(
            "Results per search", min_value=10, max_value=50, step=10,
            value=config.DISCOVERY_RESULTS_PER_QUERY,
        )
        include_news = s2.checkbox(
            "Also search Google News", value=False,
            help="More coverage of fresh announcements, but doubles the Serper searches.",
        )
        keep_unknown = st.checkbox(
            "Include deals with no clear announcement date", value=True,
            help="Recommended: the date range is already applied at search time, so a "
                 "missing exact date in the text shouldn't hide a real deal.",
        )
        if angles:
            searches, ai_calls = discover.estimate_cost(len(angles), results_per_query, include_news)
            if creds.has_llm:
                st.caption(f"Each click uses about {searches} Serper search(es) and up to {ai_calls} AI call(s).")
            else:
                st.caption(f"Each click uses about {searches} Serper search(es). Structuring is free (heuristic mode).")

    go_discover = st.button(
        "🔎 Search deals", type="primary", disabled=keys_missing or not angles,
        key="go_discover", **stretch(st.button),
    )
    discover_slot = st.container()

    if go_discover:
        with discover_slot:
            structure_label = "AI reads results" if creds.has_llm else "Heuristic extract"
            live = LiveProgress(["Search the web", structure_label, "Save deals"])

            def on_discover_progress(stage, done, total, message):
                if stage == "search":
                    live.update(0, fraction(done, total), f"Searching ({min(done + 1, total)}/{total}): {message}")
                elif stage == "structure":
                    if creds.has_llm:
                        live.update(1, fraction(done - 1, total), f"AI is reading batch {done} of {total}...")
                    else:
                        live.update(1, fraction(done, total), message or "Extracting deals from titles & snippets...")
                else:
                    live.update(2, fraction(done, total), message)

            try:
                completed, batch_ids, dstats = discover.run(
                    creds,
                    tenure_label=tenure_label, custom_start=custom_start, custom_end=custom_end,
                    queries=angles,
                    country=selected_country, technology=selected_technology,
                    geography=selected_geography, industry=selected_industry,
                    extra_keywords=extra_keywords, results_per_query=results_per_query,
                    include_news=include_news, keep_unknown_dates=keep_unknown,
                    conn=conn, progress_callback=on_discover_progress,
                )
                live.finish()
                if batch_ids:
                    st.session_state["last_batch_ids"] = batch_ids
                rng = dstats["range_label"]
                if dstats["fatal"]:
                    set_notice("discover", "error",
                               f"Stopped: {dstats['fatal']} Fix the key / credits, then search again.")
                elif dstats["search_errors"] and dstats["found"] == 0:
                    q, e = dstats["search_errors"][0]
                    set_notice("discover", "error",
                               f"The web search failed for all {len(dstats['search_errors'])} search(es). "
                               f"Example: {e}")
                elif dstats["found"] == 0:
                    set_notice("discover", "warning",
                               f"The search worked but Google returned nothing for {rng}. Try a wider "
                               "tenure, fewer filters or different keywords.")
                elif completed == 0 and dstats["failed"] and not dstats["already_known"]:
                    sample = "; ".join(dstats["errors"]) or "no details captured"
                    set_notice("discover", "warning",
                               f"Reviewed {dstats['found']} result(s) for {rng} but structuring failed. "
                               f"Example: {sample}")
                elif completed == 0:
                    extra = f" {dstats['already_known']} were already in your history." if dstats["already_known"] else ""
                    set_notice("discover", "info",
                               f"Reviewed {dstats['found']} result(s) for {rng} - no new deals found.{extra} "
                               "Try a wider tenure or other keywords.")
                else:
                    set_notice("discover", "success",
                               f"Found {completed} new deal(s) for {rng} (from {dstats['found']} search "
                               f"results reviewed)."
                               + (f" {dstats['already_known']} result(s) were already known." if dstats["already_known"] else "")
                               + (f" {dstats['failed']} structuring batch(es) failed - run again to retry." if dstats["failed"] else ""))
                    st.toast(f"{completed} new deal(s) found!", icon="🎉")
                    st.balloons()
            except Exception as exc:
                live.finish()
                set_notice("discover", "error", f"Something went wrong: {exc}")
    with discover_slot:
        show_notice("discover")

# ---- RSS pipeline ----------------------------------------------------------
with tab_rss:
    ui_theme.section(
        "RSS pipeline", "",
        "Reads your configured RSS feeds, then extracts every pending article "
        f"(up to {config.MAX_PENDING_PER_RUN} per run).",
    )
    if counts_before["failed"]:
        st.caption(
            f"{counts_before['failed']} row(s) failed earlier - their error is in the Status column "
            "of the full history. After fixing the cause (e.g. an API key) re-queue them:"
        )
        if st.button(f"Retry {counts_before['failed']} failed row(s)", key="retry_failed"):
            n = db.requeue_failed(conn)
            set_notice("rss", "info", f"{n} row(s) re-queued as Pending. Click 'Refresh pipeline' to process them.")

    go_rss = st.button(
        "🚀 Refresh pipeline", type="primary", disabled=keys_missing, key="go_rss", **stretch(st.button),
    )
    rss_slot = st.container()
    if go_rss:
        with rss_slot:
            live = LiveProgress(["Read RSS feeds", "Extract deals"])
            try:
                added, feed_stats = rss_ingest.run(
                    verbose=False, conn=conn,
                    progress_callback=lambda d, t, u: live.update(0, fraction(d, t), f"Checked {d}/{t} feeds - {u}"),
                )
                live.update(1, 0.0, f"{feed_stats['feeds_ok']} feed(s) loaded, added {added} new URL(s). Extracting...")
                completed, batch_ids, estats = process_pending.run(
                    creds, verbose=False, conn=conn,
                    progress_callback=lambda d, t, u: live.update(1, fraction(d, t), f"Processed {d}/{t} - {u}"),
                )
                live.finish()
                st.session_state["last_batch_ids"] = batch_ids
                if estats["fatal"]:
                    set_notice("rss", "error", f"Stopped: {estats['fatal']} Fix the key / credits and click "
                                               "Refresh again - unprocessed rows are still Pending.")
                elif feed_stats["feeds_ok"] == 0 and feed_stats["feeds_failed"]:
                    ex = feed_stats["feed_errors"][0] if feed_stats["feed_errors"] else ("?", "unknown error")
                    set_notice("rss", "error", f"Every RSS feed failed to load (e.g. {ex[0]}: {ex[1]}). "
                                               "Check the feed URLs in config.py and your network.")
                elif estats["found"] == 0:
                    set_notice("rss", "info", "Feeds loaded fine, but there were no new/pending URLs to extract.")
                elif completed == 0:
                    sample = "; ".join(estats["sample_errors"]) or "no details captured"
                    set_notice("rss", "warning", f"Found {estats['found']} pending URL(s) but all "
                                                 f"{estats['failed']} failed. Example: {sample}")
                else:
                    set_notice("rss", "success",
                               f"Pipeline complete: {completed} succeeded, {estats['failed']} failed."
                               + (f" {estats['remaining']} still pending (cap {config.MAX_PENDING_PER_RUN}/run); "
                                  "run again to continue." if estats["remaining"] else ""))
                    st.toast("Pipeline complete", icon="✅")
            except Exception as exc:
                live.finish()
                set_notice("rss", "error", f"Something went wrong: {exc}")
    with rss_slot:
        show_notice("rss")

# ---- Manual URLs -----------------------------------------------------------
with tab_urls:
    ui_theme.section("Add URLs", "", "Paste article links or upload a file - each page is read and extracted.")
    urls_input = st.text_area(
        "Paste one URL per line", key=f"text_{st.session_state['text_key']}", height=130,
    )
    uploaded_file = st.file_uploader(
        "Or upload a CSV, TXT or Excel file containing URLs (first column)",
        type=["csv", "txt", "xlsx"], key=f"upload_{st.session_state['upload_key']}",
    )

    uploaded_urls = []
    if uploaded_file is not None:
        try:
            name = uploaded_file.name.lower()
            if name.endswith(".csv"):
                uploaded_urls = pd.read_csv(uploaded_file).iloc[:, 0].dropna().astype(str).tolist()
            elif name.endswith(".txt"):
                uploaded_urls = uploaded_file.read().decode("utf-8", errors="ignore").splitlines()
            elif name.endswith(".xlsx"):
                uploaded_urls = pd.read_excel(uploaded_file).iloc[:, 0].dropna().astype(str).tolist()
            st.success(f"Loaded {len(uploaded_urls)} line(s) from the file")
        except Exception as exc:
            st.error(f"Upload error: {exc}")

    go_urls = st.button("⚡ Process URLs", type="primary", disabled=keys_missing, key="go_urls", **stretch(st.button))
    urls_slot = st.container()
    if go_urls:
        candidates = [u.strip() for u in urls_input.split("\n") + uploaded_urls if u.strip()]
        valid = [u for u in candidates if u.lower().startswith(("http://", "https://"))]
        urls = list(dict.fromkeys(valid))  # de-duplicate, keep order
        skipped = len(candidates) - len(urls)

        with urls_slot:
            if not urls:
                set_notice("urls", "warning", "No valid URLs provided (they must start with http:// or https://).")
            else:
                live = LiveProgress(["Fetch & extract"])
                completed = failed = 0
                fatal = None
                batch_ids = []
                try:
                    for index, url in enumerate(urls, start=1):
                        live.update(0, (index - 1) / len(urls), f"Processing {index}/{len(urls)} - {url}")
                        state = db.get_deal_state(conn, url)
                        if state is not None and state[1] == "Done":
                            batch_ids.append(state[0])   # already extracted earlier
                            continue
                        try:
                            fields = extraction.process_url(url, creds)
                            ok = True
                        except extraction.FatalAPIError as exc:
                            fatal = str(exc)
                            break
                        except Exception as exc:
                            fields = extraction.failed_fields(exc)
                            ok = False
                        batch_ids.append(db.save_deal(conn, url, fields))
                        completed += 1 if ok else 0
                        failed += 0 if ok else 1
                    live.finish()
                    if batch_ids:
                        st.session_state["last_batch_ids"] = batch_ids
                    if fatal:
                        set_notice("urls", "error", f"Stopped: {fatal} {completed} URL(s) were processed before that.")
                    else:
                        msg = f"Processed {completed} URL(s) successfully"
                        if failed:
                            msg += f", {failed} failed (error shown in the Status column of the full history)"
                        if skipped:
                            msg += f"; ignored {skipped} invalid/duplicate line(s)"
                        set_notice("urls", "success" if not failed else "warning", msg + ".")
                        if completed:
                            st.toast(f"{completed} URL(s) processed", icon="✅")
                except Exception as exc:
                    live.finish()
                    set_notice("urls", "error", f"Something went wrong: {exc}")
    with urls_slot:
        show_notice("urls")

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

ui_theme.section("Deal dashboard", "📊")

all_df = db.fetch_all_deals_df(conn)
batch_ids_state = st.session_state.get("last_batch_ids")
has_batch = bool(batch_ids_state)
show_latest_only = st.checkbox(
    "Show only the latest run", value=True, disabled=not has_batch,
    help="When checked, the table shows only deals from your most recent search / pipeline / URL run. "
         "Uncheck to see the full history.",
)

df = all_df
if show_latest_only and has_batch:
    df = df[df["id"].isin(batch_ids_state)]

dashboard_df = (
    df[df["Status"] == "Done"].fillna("Unknown").sort_values("id", ascending=False).reset_index(drop=True)
    if not df.empty else pd.DataFrame()
)

if len(dashboard_df) == 0 and show_latest_only and has_batch:
    st.info("The latest run didn't produce any completed rows yet (they may still be Pending or failed). "
            "Untick 'Show only the latest run' to see the full history.")
elif len(dashboard_df) == 0:
    st.markdown(
        ui_theme.empty_state_html(
            "No deals yet",
            "Add your keys in the sidebar, pick a tenure and hit “Search deals” to see results here.",
        ),
        unsafe_allow_html=True,
    )
else:
    for col in ("DealType", "Country", "Technology", "SecondaryMarket", "Vendor", "Customer"):
        dashboard_df[col] = dashboard_df[col].replace("", "Unknown")

    with st.expander("🎛️ Filters", expanded=False):
        fc1, fc2, fc3, fc4 = st.columns(4)
        country_filter = fc1.multiselect(
            "Country", sorted(dashboard_df["Country"].unique()), default=list(dashboard_df["Country"].unique()))
        type_filter = fc2.multiselect(
            "Deal type", sorted(dashboard_df["DealType"].unique()), default=list(dashboard_df["DealType"].unique()))
        technology_filter = fc3.multiselect(
            "Technology", sorted(dashboard_df["Technology"].unique()), default=list(dashboard_df["Technology"].unique()))
        market_filter = fc4.multiselect(
            "Secondary market", sorted(dashboard_df["SecondaryMarket"].unique()),
            default=list(dashboard_df["SecondaryMarket"].unique()))

    filtered_df = dashboard_df[
        dashboard_df["Country"].isin(country_filter)
        & dashboard_df["DealType"].isin(type_filter)
        & dashboard_df["Technology"].isin(technology_filter)
        & dashboard_df["SecondaryMarket"].isin(market_filter)
    ]

    st.markdown(
        ui_theme.stat_cards_html([
            ("Total deals", len(filtered_df), "💼", ""),
            ("Unique vendors", filtered_df["Vendor"].nunique(), "🏢", ""),
            ("Unique customers", filtered_df["Customer"].nunique(), "🤝", ""),
            ("Countries", filtered_df["Country"].nunique(), "🌍", ""),
        ]),
        unsafe_allow_html=True,
    )

    if filtered_df.empty:
        st.info("No rows match the current filters.")
    else:
        ch1, ch2 = st.columns(2)
        with ch1:
            st.markdown("**Deals by country**")
            by_country = filtered_df["Country"].value_counts().reset_index()
            by_country.columns = ["Country", "count"]
            show_chart(px.bar(by_country, x="Country", y="count", color="Country",
                              color_discrete_sequence=PALETTE).update_layout(showlegend=False))
        with ch2:
            st.markdown("**Deals by type**")
            by_type = filtered_df["DealType"].value_counts().reset_index()
            by_type.columns = ["DealType", "count"]
            show_chart(px.pie(by_type, names="DealType", values="count", hole=0.5,
                              color_discrete_sequence=PALETTE))
        ch3, ch4 = st.columns(2)
        with ch3:
            st.markdown("**Top vendors / targets**")
            by_vendor = filtered_df["Vendor"].value_counts().head(10).reset_index()
            by_vendor.columns = ["Vendor", "count"]
            show_chart(px.bar(by_vendor, x="count", y="Vendor", orientation="h", color="Vendor",
                              color_discrete_sequence=PALETTE).update_layout(
                showlegend=False, yaxis=dict(autorange="reversed")))
        with ch4:
            st.markdown("**Deals by secondary market**")
            by_market = filtered_df["SecondaryMarket"].value_counts().reset_index()
            by_market.columns = ["SecondaryMarket", "count"]
            show_chart(px.pie(by_market, names="SecondaryMarket", values="count", hole=0.5,
                              color_discrete_sequence=PALETTE[::-1]))

        st.markdown("### Deal data")
        shown = filtered_df.head(300)
        if len(filtered_df) > len(shown):
            st.caption(f"Showing the newest {len(shown)} of {len(filtered_df)} rows - the downloads include all of them.")

        # Everything below came from web pages / an AI, and the table is
        # rendered as raw HTML - so escape every text column first.
        display_df = shown.copy()
        display_df.insert(0, "Sr", range(1, len(display_df) + 1))
        plain_columns = ["Customer", "Vendor", "DealType", "Deal Value", "Country", "Date",
                         "CustomerIndustry", "VendorIndustry", "SecondaryMarket"]
        for col in plain_columns:
            display_df[col] = display_df[col].apply(lambda v: ui_theme.esc(v) if pd.notna(v) else "")

        def make_link(url):
            url = str(url).strip()
            if url.lower().startswith(("http://", "https://")):
                return (f'<a href="{ui_theme.esc(url).replace(chr(34), "%22")}" target="_blank" '
                        'rel="noopener noreferrer">Open</a>')
            return ""

        def source_name(url):
            host = urlparse(str(url)).netloc.lower()
            return ui_theme.esc(host[4:] if host.startswith("www.") else host)

        def clamp(value):
            text = ui_theme.esc(value) if pd.notna(value) else ""
            return f'<div class="clamp-cell" title="{text}">{text}</div>'

        display_df["Article"] = display_df["URL"].apply(make_link)
        display_df["Source"] = display_df["URL"].apply(source_name)
        display_df["Summary"] = display_df["Summary"].apply(clamp)
        display_df["Technology"] = display_df["Technology"].apply(clamp)
        display_df["Confidence"] = display_df["Confidence"].replace(
            {"High": "🟢 High", "Medium": "🟡 Medium", "Low": "🔴 Low"})
        display_df = display_df.rename(columns={
            "Customer": "Customer / Buyer", "Vendor": "Vendor / Target", "DealType": "Deal Type",
            "CustomerIndustry": "Customer Industry", "VendorIndustry": "Vendor Industry",
            "SecondaryMarket": "Secondary Market",
        })
        order = ["Sr", "Article", "Customer / Buyer", "Vendor / Target", "Deal Type", "Deal Value",
                 "Country", "Technology", "Date", "Confidence", "Customer Industry",
                 "Vendor Industry", "Secondary Market", "Summary", "Source"]
        table_html = display_df[order].to_html(escape=False, index=False, border=0, classes="deal-table", justify="left")
        st.markdown(f'<div class="table-wrap">{ui_theme.flat(table_html)}</div>', unsafe_allow_html=True)

        # ---- downloads ---------------------------------------------------
        export_df = filtered_df.rename(columns={
            "Customer": "Customer / Buyer", "Vendor": "Vendor / Target", "DealType": "Deal Type",
            "CustomerIndustry": "Customer Industry", "VendorIndustry": "Vendor Industry",
            "SecondaryMarket": "Secondary Market", "CustomerWebsite": "Customer Website",
            "VendorWebsite": "Vendor Website", "URL": "Source URL",
        })[["Customer / Buyer", "Vendor / Target", "Deal Type", "Deal Value", "Country", "Technology",
            "Date", "Confidence", "Customer Industry", "Vendor Industry", "Secondary Market",
            "Summary", "Customer Website", "Vendor Website", "Source URL"]].copy()
        for col in export_df.columns:
            export_df[col] = export_df[col].apply(safe_cell)

        d1, d2, _ = st.columns([1, 1, 3])
        with d1:
            st.download_button(
                "📥 Download Excel", data=to_excel_bytes(export_df), file_name="it_deals.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary", **stretch(st.download_button),
            )
        with d2:
            st.download_button(
                "⬇️ Download CSV", data=export_df.to_csv(index=False).encode("utf-8-sig"),
                file_name="it_deals_export.csv", mime="text/csv", **stretch(st.download_button),
            )

# ---------------------------------------------------------------------------
# Top stat cards (drawn last so they reflect whatever just ran)
# ---------------------------------------------------------------------------

counts_now = db.count_by_status(conn)
stats_slot.markdown(
    ui_theme.stat_cards_html([
        ("Extracted (done)", counts_now["done"], "✅", "good"),
        ("Pending", counts_now["pending"], "⏳", "warn" if counts_now["pending"] else ""),
        ("Failed", counts_now["failed"], "⚠️", "bad" if counts_now["failed"] else ""),
    ]),
    unsafe_allow_html=True,
)
