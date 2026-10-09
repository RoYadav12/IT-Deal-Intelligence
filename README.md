# IT Deal Intelligence

Searches the web for IT deals (acquisitions, outsourcing, managed services, cloud),
turns them into a clean table, and lets you download Excel/CSV.

* **Serper** runs the Google searches (with a real date filter) and scrapes pages.
* **Structuring** uses Claude or OpenAI when you supply an AI key, or a built-in
  **heuristic extractor** when you only have a Serper key — so the app works with
  a single API key.
* You paste your API key(s) **into the app's sidebar** - nothing is stored on disk.

## Files
| File | Purpose |
|---|---|
| `app.py` | The animated Streamlit app |
| `ui_theme.py` | Animations / styling |
| `discover.py` | Serper search + AI or heuristic structuring |
| `extraction.py` | Serper page scrape + Claude/OpenAI or heuristic extraction |
| `heuristic.py` | Built-in no-LLM extractor (Serper-only mode) |
| `process_pending.py`, `rss_ingest.py` | RSS pipeline |
| `db.py`, `config.py` | Database and settings |
| `requirements.txt` | Packages to install |

## Step-by-step: deploy on Streamlit Community Cloud
1. **Get a Serper key.** https://serper.dev -> Dashboard -> API key. (Optional: Claude at console.anthropic.com or OpenAI at platform.openai.com for higher-quality extraction.)
2. **Create a GitHub repo.** https://github.com/new -> name `it-deal-intelligence` -> Private -> Create.
3. **Upload the files.** On the repo page: Add file -> Upload files -> drag in everything from this folder (`app.py`, `ui_theme.py`, `config.py`, `db.py`, `extraction.py`, `discover.py`, `heuristic.py`, `process_pending.py`, `rss_ingest.py`, `requirements.txt`, `README.md`). Do NOT upload any `.db` file or `.env`. Click Commit changes.
   *Delete the old `firecrawl` version's files first if you reuse the same repo, so nothing old is left.*
4. **Deploy.** https://share.streamlit.io -> sign in with GitHub -> Create app -> pick the repo, branch `main`, main file `app.py` -> Deploy. (No secrets needed.)
5. **Keep it private.** App menu -> Share -> restrict viewing to yourself/invited emails.
6. **Use it.** Open the app link, paste your **Serper key** in the sidebar (AI key optional), click **Test my keys**, choose a Tenure, click **Search deals**, then **Download Excel**.

## Run on your own computer / Codespaces
`./run.sh` (Mac/Linux/Codespaces) or `run.bat` (Windows) - or `pip install -r requirements.txt` then `streamlit run app.py`.

## Good to know
* **Serper-only mode:** leave the AI key blank — titles/snippets are parsed with heuristics (free, no AI cost). Quality is lower but fully usable.
* Each "Search deals" click = about 6 Serper searches (+ a few AI calls only if you added an LLM key). Change this under **Search settings**.
* Streamlit Cloud forgets saved history when the app restarts - download your Excel after each run.
* A wrong Serper key or no credits stops the run immediately with a clear message.
* Optional: instead of typing keys each time, add `SERPER_API_KEY` (and optionally `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`) under App settings -> Secrets; the sidebar boxes still override them.
