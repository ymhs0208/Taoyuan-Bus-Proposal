# Taoyuan-Bus-Proposal

115 年度桃園市「為桃園做研究」研究實作組提案，主題是捷運綠線北段通車後的公車路網重整。本儲存庫收錄提案文件、前期試行分析，以及展示用決策支援原型「綠線接駁決策平台」（Streamlit＋Folium）。

展示平台讀取 `pilot/` 的檔案做計算。平台說明標示本版為試行分析、數據待複核，情境為研究示意，不代表桃園市政府或營運業者的方案。

## 資料夾

| 路徑 | 內容 |
|---|---|
| `app/` | 綠線接駁決策平台。入口是 `app/app.py`（頁面在 `views/`，衍生資料在 `derived/`）。 |
| `pilot/` | 試行分析：腳本（`scripts/`）、設定（`config/`）、已提交的開放資料衍生物（`data/`）、輸出 CSV／PNG 等（`outputs/`）。 |
| `docs/proposal_draft.md` | 提案工作初稿。 |
| `docs/submission/` | 繳交版：`繳交版_研究計畫書.docx`、`繳交版_研究計畫書.pdf`、官方範本 `ref/`，以及 `build/`、`fig/`。 |

`app/` 與 `pilot/` 放在同一層。程式依 `app/lib/data.py` 的位置尋找旁邊的 `pilot/`，與啟動時的工作目錄無關。若資料夾在別處，設定環境變數 `TAOYUAN_PILOT_DIR`。

## 執行展示平台

建議 Python 3.12（`app/requirements.txt` 依此固定套件版本）。請在儲存庫根目錄執行，與 Streamlit Community Cloud 的工作目錄一致：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r app/requirements.txt
streamlit run app/app.py
```

Windows（PowerShell）啟用虛擬環境用 `.venv\Scripts\Activate.ps1`。

## 部署到 Streamlit Community Cloud

- **Main file path**：`app/app.py`
- **Advanced settings → Python version**：選 **3.12**。`app/requirements.txt` 固定 pandas 2.2.3、pyarrow 17.0.0、pyogrio 0.9.0、pyproj 3.6.1、geopandas 1.0.1；pyarrow 17 沒有 Python 3.13 的安裝檔。這些版本在 Windows 與 Linux 都有對應 wheel。
- Community Cloud 會先讀主程式目錄的 `app/requirements.txt`，再看儲存庫根目錄。本儲存庫只有這一份相依檔。不需要 `packages.txt`（pyogrio、pyproj 的 wheel 已含 GDAL／PROJ）。
- 不需要設定 Secrets。展示平台執行時只讀已提交的 `pilot/data/`、`pilot/outputs/` 與 `app/derived/`，不會連線 TDX。
- 設定檔放在儲存庫根目錄 `.streamlit/config.toml`（Community Cloud 只讀這個位置；`app/.streamlit/config.toml` 內容相同，供在 `app/` 目錄內啟動時使用）。

## TDX 金鑰

重新下載資料的試行分析腳本才會讀取 TDX 會員金鑰，而且只從環境變數讀取，不會把金鑰寫進檔案。展示平台上線時不要設定、也不要提交：

```bash
export TDX_CLIENT_ID=...
export TDX_CLIENT_SECRET=...
```
