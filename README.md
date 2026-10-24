# Taoyuan-Bus-Proposal

115 年度桃園市「為桃園做研究」研究實作組提案，主題是捷運綠線北段通車後的公車路網重整。本儲存庫收錄提案文件、前期試行分析，以及展示用決策支援原型「綠線接駁決策平台」（Streamlit＋Folium）。

展示平台讀取 `pilot/` 的檔案做計算。平台說明標示本版為試行分析、數據待複核，情境為研究示意，不代表桃園市政府或營運業者的方案。

## 資料夾

| 路徑 | 內容 |
|---|---|
| `app/` | 綠線接駁決策平台。入口是 `app/app.py`（頁面在 `views/`，衍生資料在 `derived/`）。 |
| `pilot/` | 試行分析：TDX 開放資料拉取、路線重疊與步行可及性腳本（`scripts/`）、設定（`config/`）、輸出 CSV／PNG 等（`outputs/`）。 |
| `docs/proposal_draft.md` | 提案工作初稿。 |
| `docs/submission/` | 繳交版：`繳交版_研究計畫書.docx`、`繳交版_研究計畫書.pdf`、官方範本 `ref/`，以及 `build/`、`fig/`。 |

`app/` 與 `pilot/` 放在同一層。程式預設尋找上一層的 `pilot/`；若資料夾在別處，設定環境變數 `TAOYUAN_PILOT_DIR`。

`pilot/data/`（原始下載與中間資料）列入 `.gitignore`，不進版控。重新取得方式見 `pilot/README.md`。

## 執行展示平台

建議 Python 3.12（`app/requirements.txt` 依此固定套件版本）。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r app/requirements.txt
streamlit run app/app.py
```

Windows（PowerShell）啟用虛擬環境用 `.venv\Scripts\Activate.ps1`。

## TDX 金鑰

試行分析腳本只從環境變數讀取 TDX 會員金鑰，不會把金鑰寫進檔案。請在自己的環境設定，不要提交：

```bash
export TDX_CLIENT_ID=...
export TDX_CLIENT_SECRET=...
```
