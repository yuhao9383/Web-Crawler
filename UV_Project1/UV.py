import requests
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # 先用非互動後端產生圖檔，圖片交給 Tkinter 視窗顯示
import matplotlib.pyplot as plt
import numpy as np
import urllib3
import json
import tkinter as tk
from tkinter import messagebox, ttk
from PIL import Image, ImageTk
from pathlib import Path

urllib3.disable_warnings()

plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei"]
plt.rcParams["axes.unicode_minus"] = False


# =====================
# 基本設定
# =====================
API_KEY = input("請輸入 CWA API 金鑰：").strip()
SAVE_HISTORY = input("是否儲存到歷史資料？(y/n)：").strip().lower() == "y"

# 固定以本程式所在資料夾為根目錄
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
RAW_DIR = DATA_DIR / "raw"

DATA_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
RAW_DIR.mkdir(exist_ok=True)

print(f"\n📂 專案根目錄：{BASE_DIR}")


# =====================
# 測站對照表
# =====================
station_map = {
    "467420": "臺北",
    "466880": "鞍部",
    "466870": "陽明山",
    "467080": "淡水",
    "467050": "桃園",
    "467110": "基隆",
    "467280": "新竹",
    "467290": "苗栗",
    "467350": "臺中",
    "467441": "彰化",
    "467480": "雲林",
    "467490": "嘉義縣",
    "467270": "嘉義",
    "467300": "臺南",
    "466910": "高雄",
    "466900": "屏東",
    "467650": "墾丁",
    "467660": "恆春",
    "466920": "臺東",
    "467610": "成功",
    "466950": "花蓮",
    "466881": "宜蘭",
    "467620": "南投",
    "467410": "日月潭",
    "467571": "阿里山",
    "467550": "玉山",
    "467540": "雪山",
    "466940": "澎湖",
    "467990": "金門",
    "466990": "馬祖",
    "467590": "綠島",
    "466930": "蘭嶼"
}


# =====================
# 1. 抓取 UV API
# =====================
url = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0005-001"
params = {
    "Authorization": API_KEY,
    "format": "JSON"
}

try:
    response = requests.get(url, params=params, verify=False, timeout=20)
    response.raise_for_status()
except requests.RequestException as e:
    print(f"❌ API 請求失敗：{e}")
    raise SystemExit

try:
    data = response.json()
except Exception:
    print("❌ JSON 解析失敗")
    print(response.text[:500])
    raise SystemExit


# =====================
# 2. 解析資料
# =====================
try:
    weather_element = data["records"]["weatherElement"]
    obs_date = weather_element["Date"]
    uv_list = weather_element["location"]
except KeyError as e:
    print(f"❌ API 結構不符，缺少欄位：{e}")
    raise SystemExit


# =====================
# 3. 儲存原始 JSON
# =====================
raw_json_path = RAW_DIR / f"uv_{obs_date}.json"
with open(raw_json_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)


# =====================
# 4. 整理今天資料 (已加入排除名單)
# =====================
rows = []
unknown_station_ids = []

# 定義要排除「圖表計算」的測站 ID：嘉義縣(467490)、嘉義(467270)、屏東(466900)
# 注意：這些站還是會出現在表格裡，只是不會拿去畫圖/算平均
exclude_ids = ["467490", "467270", "466900"]

for item in uv_list:
    sid = item.get("StationID", "")
    uv_raw = item.get("UVIndex", None)
    region = station_map.get(sid, sid)

    if sid not in station_map:
        unknown_station_ids.append(sid)

    rows.append([obs_date, sid, region, uv_raw])

df_today_full = pd.DataFrame(rows, columns=["日期", "StationID", "地區", "UV指數"])
df_today_full["UV指數"] = pd.to_numeric(df_today_full["UV指數"], errors="coerce")

# 標註每一筆資料的狀態，方便表格上看出「有的沒的」是為什麼被排除
def mark_note(row):
    if pd.isna(row["UV指數"]):
        return "缺值"
    if row["UV指數"] < 0:
        return "無效值(感測器異常/無觀測)"
    if row["StationID"] in exclude_ids:
        return "人工排除地區"
    return ""

df_today_full["備註"] = df_today_full.apply(mark_note, axis=1)
df_today_full = df_today_full.sort_values("UV指數", ascending=False, na_position="last").reset_index(drop=True)

# 圖表/物聯網計算只用「乾淨資料」：扣掉缺值、無效值(<0)、人工排除地區
df_today = df_today_full[
    df_today_full["UV指數"].notna()
    & (df_today_full["UV指數"] >= 0)
    & (~df_today_full["StationID"].isin(exclude_ids))
].drop(columns=["備註"]).sort_values("UV指數", ascending=False).reset_index(drop=True)

if (df_today_full["備註"] != "").any():
    print("\n⚠️ 以下測站因故未納入圖表計算（表格中仍會顯示，並標註原因）：")
    print(df_today_full.loc[df_today_full["備註"] != "", ["地區", "UV指數", "備註"]])


# =====================
# 5. 儲存今天資料
# =====================
latest_csv = DATA_DIR / f"uv_latest_{obs_date}.csv"
latest_html = DATA_DIR / f"uv_latest_{obs_date}.html"
history_csv = DATA_DIR / "uv_history.csv"

df_today_full.to_csv(latest_csv, index=False, encoding="utf-8-sig")
df_today_full.to_html(latest_html, index=False)


# =====================
# 6. 歷史資料處理
# =====================
if history_csv.exists():
    df_history = pd.read_csv(history_csv, encoding="utf-8-sig")
else:
    df_history = pd.DataFrame(columns=["日期", "StationID", "地區", "UV指數"])

if SAVE_HISTORY:
    df_all = pd.concat([df_history, df_today], ignore_index=True)
    df_all = df_all.drop_duplicates(subset=["日期", "StationID"], keep="last")
    df_all["UV指數"] = pd.to_numeric(df_all["UV指數"], errors="coerce")
    df_all = df_all[df_all["UV指數"] >= 0]  # 清掉舊資料裡可能存在的 -99 無效值
    df_all["日期"] = pd.to_datetime(df_all["日期"], errors="coerce")
    df_all = df_all.sort_values(["日期", "StationID"]).reset_index(drop=True)
    df_all.to_csv(history_csv, index=False, encoding="utf-8-sig")
    print("\n✅ 本次為正式儲存模式，已更新歷史資料")
else:
    df_all = df_history.copy()
    if not df_all.empty:
        df_all["UV指數"] = pd.to_numeric(df_all["UV指數"], errors="coerce")
        df_all = df_all[df_all["UV指數"] >= 0]
        df_all["日期"] = pd.to_datetime(df_all["日期"], errors="coerce")
    print("\n🧪 本次為測試模式，不會寫入歷史資料")


# =====================
# 7. 主控台顯示
# =====================
print(f"\n📅 觀測日期：{obs_date}")
print("\n📊 今日 UV 完整資料表（含被排除/無效的測站，備註欄會標示原因）：")
print(df_today_full)

print(f"\n✅ 已儲存：{latest_csv}")
print(f"✅ 已儲存：{latest_html}")
print(f"✅ 已儲存原始快照：{raw_json_path}")

if SAVE_HISTORY:
    print(f"✅ 已更新歷史資料：{history_csv}")

if unknown_station_ids:
    print("\n⚠️ 以下 StationID 尚未對應中文名稱：")
    print(sorted(set(unknown_station_ids)))


# =====================
# 8. 今日長條圖（存檔，不在主控台彈出，交給 GUI 顯示）
# =====================
def draw_bar_chart():
    plt.figure(figsize=(15, 7))
    bars = plt.bar(df_today["地區"], df_today["UV指數"])

    for bar, uv in zip(bars, df_today["UV指數"]):
        x = bar.get_x() + bar.get_width() / 2
        y = bar.get_height()
        plt.text(x, y + 0.2, f"{uv:.0f}", ha="center", fontsize=8)

    plt.title(f"台灣各地 UV 指數長條圖（觀測日期：{obs_date}）")
    plt.xlabel("地區")
    plt.ylabel("UV 指數")
    plt.xticks(rotation=60)
    plt.tight_layout()

    path = OUTPUT_DIR / f"today_uv_bar_{obs_date}.png"
    plt.savefig(path, dpi=200)
    plt.close()
    print(f"✅ 已儲存：{path}")
    return path


# =====================
# 9. 今日折線圖（修正版：數值跟圖對不起來、文字互相重疊的問題）
# =====================
def draw_line_chart():
    # 問題原因：
    # 1. 原本文字標籤同時印「地名+數值」又疊在 xtick 的地名上，互相重疊看起來很亂
    # 2. 沒有依 UV 高低固定 y 軸範圍，數值看起來忽高忽低、跟長條圖對不起來
    # 修正方式：
    # 1. 資料點上只標數值，地名只留在 x 軸（不重複）
    # 2. y 軸統一從 0 開始，並依資料留一點空間，視覺上跟長條圖一致
    # 3. 依 UV 等級上色，方便一眼看出偏高的地區（這部分也順便對應到下面的物聯網警示燈邏輯）

    x = range(len(df_today))
    y = df_today["UV指數"].values

    def uv_color(v):
        if v >= 11:
            return "purple"
        elif v >= 8:
            return "red"
        elif v >= 6:
            return "orange"
        elif v >= 3:
            return "gold"
        else:
            return "green"

    colors = [uv_color(v) for v in y]

    plt.figure(figsize=(15, 7))
    plt.plot(x, y, marker="o", linewidth=1.5, color="gray", zorder=1)
    plt.scatter(x, y, c=colors, s=70, zorder=2, edgecolors="black", linewidths=0.5)

    for i, uv in enumerate(y):
        plt.text(i, uv + 0.3, f"{uv:.0f}", ha="center", fontsize=8)

    plt.title(f"台灣各地 UV 指數折線圖（觀測日期：{obs_date}）")
    plt.xlabel("地區")
    plt.ylabel("UV 指數")
    plt.xticks(list(x), df_today["地區"], rotation=60)

    y_max = max(y.max() + 2, 5)
    plt.ylim(0, y_max)
    plt.grid(axis="y", linestyle="--", alpha=0.4)
    plt.tight_layout()

    path = OUTPUT_DIR / f"today_uv_line_{obs_date}.png"
    plt.savefig(path, dpi=200)
    plt.close()
    print(f"✅ 已儲存：{path}")
    return path


# =====================
# 10. 歷史平均 UV 回歸分析圖
# =====================
def draw_regression_chart():
    df_avg = (
        df_all.groupby("日期", as_index=False)["UV指數"]
        .mean()
        .sort_values("日期")
        .reset_index(drop=True)
    ) if not df_all.empty else pd.DataFrame()

    if len(df_avg) < 2:
        print("\nℹ️ 目前歷史資料不足 2 天，還不能畫回歸分析圖。")
        if not SAVE_HISTORY:
            print("因為你現在是測試模式，這次資料也不會加入歷史檔。")
        return None

    df_avg["天數序號"] = np.arange(len(df_avg))
    x_num = df_avg["天數序號"].values
    y = df_avg["UV指數"].values

    coef = np.polyfit(x_num, y, 1)
    trend = np.poly1d(coef)
    y_pred = trend(x_num)

    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot != 0 else 0

    plt.figure(figsize=(11, 6))
    plt.scatter(df_avg["日期"], y, s=60, label="每日全站平均 UV")
    plt.plot(df_avg["日期"], y_pred, label="線性回歸趨勢線")

    for d, val in zip(df_avg["日期"], y):
        plt.text(d, val + 0.05, f"{val:.2f}", ha="center", fontsize=8)

    plt.title("全站平均 UV 歷史回歸分析圖")
    plt.xlabel("日期")
    plt.ylabel("平均 UV 指數")
    plt.xticks(rotation=45)
    plt.legend()
    plt.tight_layout()

    eq_text = f"y = {coef[0]:.4f}x + {coef[1]:.4f}\nR² = {r2:.4f}"
    plt.figtext(0.14, 0.02, eq_text, fontsize=10,
                bbox=dict(boxstyle="round", facecolor="white", edgecolor="gray", alpha=0.9))

    path = OUTPUT_DIR / "avg_uv_regression.png"
    plt.savefig(path, dpi=200)
    plt.close()

    print("\n📈 回歸方程：")
    print(f"y = {coef[0]:.4f}x + {coef[1]:.4f}")
    print(f"R² = {r2:.4f}")
    print(f"✅ 已儲存：{path}")
    return path


# 先把三張圖都產生好，存成檔案，等一下給 GUI 顯示用
bar_path = draw_bar_chart()
line_path = draw_line_chart()
reg_path = draw_regression_chart()


# =====================
# 11. 物聯網（IoT）簡易示範：模擬感測器 + 警示燈
# =====================
# 概念：把「今天全台平均 UV」當成感測器讀到的數值，
# 經過簡單的門檻判斷，輸出燈號狀態（綠燈安全 / 黃燈注意 / 紅燈警告）
# 這是大一物聯網課程常見的「感測 → 判斷 → 致動(燈號)」簡化版本，
# 之後若有真的感測器（例如 Arduino UV 模組），
# 只要把 avg_uv 換成感測器讀回來的值，邏輯完全不用改。

def get_uv_status(avg_uv: float):
    if avg_uv >= 8:
        return "紅燈：UV 過高，建議減少外出/做好防曬", "red"
    elif avg_uv >= 3:
        return "黃燈：UV 中等，外出請防曬", "#d4a900"
    else:
        return "綠燈：UV 偏低，安全", "green"


avg_uv_today = float(df_today["UV指數"].mean()) if not df_today.empty else 0.0
status_text, status_color = get_uv_status(avg_uv_today)

print(f"\n📡 [物聯網模擬] 今日全台平均 UV：{avg_uv_today:.2f}")
print(f"💡 警示燈狀態：{status_text}")


# =====================
# 12. 人機介面（GUI）：可以點選三張圖切換顯示，並顯示警示燈
# =====================
class UVApp:
    def __init__(self, root):
        self.root = root
        self.root.title("台灣 UV 指數監測系統")
        self.root.geometry("950x800")

        # 上方：標題 + 觀測日期
        title_label = tk.Label(
            root, text=f"台灣各地 UV 指數監測（觀測日期：{obs_date}）",
            font=("Microsoft JhengHei", 16, "bold")
        )
        title_label.pack(pady=10)

        # 物聯網警示燈區塊
        iot_frame = tk.Frame(root)
        iot_frame.pack(pady=5)

        self.light_canvas = tk.Canvas(iot_frame, width=30, height=30, highlightthickness=0)
        self.light_canvas.pack(side="left", padx=5)
        self.light_canvas.create_oval(2, 2, 28, 28, fill=status_color, outline="black")

        iot_label = tk.Label(
            iot_frame,
            text=f"[物聯網模擬] 今日平均 UV：{avg_uv_today:.2f}　{status_text}",
            font=("Microsoft JhengHei", 11)
        )
        iot_label.pack(side="left")

        # 按鈕區：選擇要看哪張圖
        btn_frame = tk.Frame(root)
        btn_frame.pack(pady=10)

        tk.Button(
            btn_frame, text="📊 今日長條圖", width=15, height=2,
            command=lambda: self.show_image(bar_path, "今日長條圖")
        ).pack(side="left", padx=8)

        tk.Button(
            btn_frame, text="📈 今日折線圖", width=15, height=2,
            command=lambda: self.show_image(line_path, "今日折線圖")
        ).pack(side="left", padx=8)

        tk.Button(
            btn_frame, text="📉 歷史回歸圖", width=15, height=2,
            command=lambda: self.show_image(reg_path, "歷史回歸圖")
        ).pack(side="left", padx=8)

        tk.Button(
            btn_frame, text="📋 完整資料表", width=15, height=2,
            command=self.show_table
        ).pack(side="left", padx=8)

        # 圖片顯示區
        self.image_label = tk.Label(root, text="請點選上方按鈕來選取要顯示的圖表", font=("Microsoft JhengHei", 12))
        self.image_label.pack(pady=10, expand=True, fill="both")

        self.current_photo = None  # 保留參照避免被垃圾回收

        # 預設先顯示長條圖
        self.show_image(bar_path, "今日長條圖")

    def show_table(self):
        win = tk.Toplevel(self.root)
        win.title("今日 UV 完整資料表（含排除/無效測站）")
        win.geometry("560x620")
        win.minsize(360, 300)
        win.resizable(True, True)  # 視窗可以自由拉大縮小

        container = tk.Frame(win)
        container.pack(fill="both", expand=True, padx=10, pady=10)

        cols = ["地區", "UV指數", "備註"]
        tree = ttk.Treeview(container, columns=cols, show="headings", height=28)

        col_widths = {"地區": 120, "UV指數": 100, "備註": 260}
        for c in cols:
            tree.heading(c, text=c)
            # minwidth + stretch=True：欄位可以用滑鼠拖曳調整寬度，
            # 視窗變大變小時欄位也會跟著等比縮放
            tree.column(c, width=col_widths[c], minwidth=60, anchor="center", stretch=True)

        # 垂直捲軸，資料多的時候可以滑動，行高也會隨字型自動撐開
        vsb = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)

        # 可以直接調整字型大小，連帶讓每一列的高度跟著變高/變矮
        style = ttk.Style()
        style.configure("Treeview", rowheight=26, font=("Microsoft JhengHei", 10))
        style.configure("Treeview.Heading", font=("Microsoft JhengHei", 10, "bold"))

        # 不一樣的列用不同顏色標出來，一眼看出哪些是正常/排除/無效
        tree.tag_configure("normal", background="white")
        tree.tag_configure("excluded", background="#fff3cd")  # 黃：人工排除
        tree.tag_configure("invalid", background="#f8d7da")   # 紅：無效值/缺值

        for _, r in df_today_full.iterrows():
            note = r["備註"]
            if note == "":
                tag = "normal"
            elif note == "人工排除地區":
                tag = "excluded"
            else:
                tag = "invalid"
            uv_display = "" if pd.isna(r["UV指數"]) else f"{r['UV指數']:.0f}"
            tree.insert("", "end", values=(r["地區"], uv_display, note), tags=(tag,))

    def show_image(self, path, name):
        if path is None or not Path(path).exists():
            messagebox.showinfo("提示", f"{name} 尚無資料可顯示（例如歷史資料不足 2 天）。")
            return

        img = Image.open(path)
        # 依視窗大小縮放，避免圖片太大塞不下
        max_w, max_h = 880, 600
        ratio = min(max_w / img.width, max_h / img.height, 1.0)
        new_size = (int(img.width * ratio), int(img.height * ratio))
        img = img.resize(new_size, Image.LANCZOS)

        self.current_photo = ImageTk.PhotoImage(img)
        self.image_label.config(image=self.current_photo, text="")


if __name__ == "__main__":
    root = tk.Tk()
    app = UVApp(root)
    root.mainloop()