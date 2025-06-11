# app.py
import json, calendar, datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import streamlit as st
from passlib.hash import bcrypt

# ---------- 0. Google Sheets 連線 ---------- #
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

# 讀取 Secrets 裡的金鑰與試算表 ID
creds_dict = json.loads(st.secrets["GOOGLE_CREDS_JSON"])
sheet_key  = st.secrets["SHEET_KEY"]

gc = gspread.authorize(
    ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
)
sh = gc.open_by_key(sheet_key)
ws_shift = sh.worksheet("Sheet1") if "Sheet1" in [w.title for w in sh.worksheets()] else sh.sheet1
ws_user  = sh.worksheet("users")

# ---------- 1. 基本資料 ---------- #
users_df = pd.DataFrame(ws_user.get_all_values()[1:], columns=ws_user.row_values(1))
shift_options = ["休", "全天", "早", "午", "晚", "早午", "午晚", "早晚"]
color_map     = {"全天": "#d4edda", "休": "#f8d7da"}   # 其他→黃
weekday_map   = ["一", "二", "三", "四", "五", "六", "日"]

st.set_page_config(page_title="玩硬劇本排班系統", layout="wide")
st.markdown(
    '<meta name="viewport" content="width=device-width, initial-scale=1">',
    unsafe_allow_html=True,
)

# ---------- 2. 共用 CSS ---------- #
st.markdown("""
<style>
/* ===== 桌機 ===== */
#cal-area div[data-testid="column"] {
    flex: 1 1 70px !important;
    max-width: 70px !important;
}
""", unsafe_allow_html=True)

# ---------- 3. 產生總表 Styler ---------- #
def make_summary_df(year: int, month: int):
    _, days = calendar.monthrange(year, month)
    dates = [datetime.date(year, month, d) for d in range(1, days + 1)]
    date_cols  = [str(d.day) for d in dates] 
    weekday_row = [weekday_map[d.weekday()] for d in dates]

    df_shift = pd.DataFrame(
        ws_shift.get_all_values()[1:], columns=["date", "shift", "user", "status"]
    )
    df_shift["date"] = pd.to_datetime(df_shift["date"]).dt.strftime("%Y-%m-%d")

    rows = []
    for _, u in users_df.iterrows():
        role, name, uname = u["role"], u["display_name"], u["username"]
        one_row = [role, name]
        for d in dates:
            key = d.isoformat()
            hit = df_shift[(df_shift["user"] == uname) & (df_shift["date"] == key)]
            one_row.append(hit.iloc[0]["shift"] if not hit.empty else "休")
        rows.append(one_row)

    cols = ["職稱", "姓名"] + date_cols
    df = pd.DataFrame(rows, columns=cols)
    df = pd.concat([pd.DataFrame([["", "星期"] + weekday_row], columns=cols), df])

    df.columns = df.columns.str.strip().astype(str)
    df.index = range(len(df))

    def color(val):
        if val == "全天":
            return "background-color:#d4edda"
        if val == "休":
            return "background-color:#f8d7da"
        if val in shift_options[2:]:
            return "background-color:#fff9db"
        return ""

    return df.style.applymap(color, subset=pd.IndexSlice[:, df.columns[2:]])


# ---------- 4. 登入 ---------- #
if not st.session_state.get("authenticated"):
    _, c, _ = st.columns([3, 2, 3])
    with c:
        st.markdown("<div id='login-wrapper'>", unsafe_allow_html=True)
        st.subheader("🔐 請登入")
        with st.form("login"):
            u = st.text_input("帳號")
            p = st.text_input("密碼", type="password")
            if st.form_submit_button("登入"):
                rec = users_df[users_df.username == u]
                if not rec.empty and bcrypt.verify(p, rec.password_hash.iloc[0]):
                    st.session_state.update(
                        {
                            "authenticated": True,
                            "username": u,
                            "display_name": rec.display_name.iloc[0],
                            "role": rec.role.iloc[0],
                        }
                    )
                    st.rerun()
                else:
                    st.error("帳號或密碼錯誤")
        st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

# ---------- 5. 主介面 ---------- #
st.sidebar.success(f"👋 {st.session_state['display_name']}")
if st.sidebar.button("🚪 登出"):
    for k in ["authenticated", "username", "display_name", "role"]:
        st.session_state.pop(k, None)
    st.rerun()

tab_my, tab_sum = st.tabs(["🧑‍💼我的排班", "🗂️員工排班總表"])

# === 5-1 我的排班 === #
with tab_my:
    today = datetime.date.today()
    year  = st.selectbox("年份", list(range(today.year-1, today.year+2)), 1, key="y")
    month = st.selectbox("月份", list(range(1, 13)), today.month-1,    key="m")

    # 讀取本月自己的資料 → preset
    df_all = (
        pd.DataFrame(ws_shift.get_all_values()[1:], columns=["date","shift","user","status"])
          .assign(date=lambda d: pd.to_datetime(d["date"]))
    )
    mask   = (df_all["user"]==st.session_state["username"]) & \
             (df_all["date"].dt.year==year) & (df_all["date"].dt.month==month)
    df_me  = df_all[mask]
    preset = dict(zip(df_me["date"].dt.strftime("%Y-%m-%d"), df_me["shift"]))

    cal = calendar.Calendar(firstweekday=6)

    with st.form("my_form"):
        st.markdown(f"### 📆 {year} 年 {month} 月排班表")

        # ❶❷❸————— 月曆區域開始 —————
        with st.container():
            st.markdown("<div id='cal-area'>", unsafe_allow_html=True)

            # ─── 星期列 ───
            with st.container():
                cols_week = st.columns(7)
                for i, lbl in enumerate(["日","一","二","三","四","五","六"]):
                    bg, fg = ("#004085","#fff") if i in (0,6) else ("#fff","#000")
                    cols_week[i].markdown(
                        f"<div style='background:{bg};color:{fg};padding:6px 0;border-radius:4px;"
                        f"text-align:center;font-size:16px'><strong>{lbl}</strong></div>",
                        unsafe_allow_html=True
                    )

            # ─── 日期 + Selectbox ───
            shift_data = {}
            for wk in cal.monthdatescalendar(year, month):
                with st.container():  # 每個星期獨立容器，確保 Grid 佈局
                    cols = st.columns(7)
                    for i, d in enumerate(wk):
                        with cols[i]:
                            if d.month != month:
                                st.markdown("<div style='padding:30px'> </div>", unsafe_allow_html=True)
                                continue
                            key  = d.isoformat()
                            init = preset.get(key, "休")
                            bg   = color_map.get(init, "#fff9db")

                            st.markdown(
                                f"<div class='calendar-date' style='background:{bg};border-radius:6px;"
                                f"text-align:center;padding:4px 0'>{d.day}</div>",
                                unsafe_allow_html=True
                            )
                            val = st.selectbox(
                                "\u200b", shift_options,
                                key=key, index=shift_options.index(init),
                                label_visibility="collapsed"
                            )
                            shift_data[key] = val

            st.markdown("</div>", unsafe_allow_html=True)
        # ❹❺————— 月曆區域結束 —————

        # ─── 儲存按鈕 ───
        if st.form_submit_button("💾 儲存排班"):
            for day, s in shift_data.items():
                hit = df_me[df_me["date"].dt.strftime("%Y-%m-%d")==day]
                if not hit.empty:
                    ws_shift.update_cell(hit.index[0]+2, 2, s)
                else:
                    ws_shift.append_row([day, s, st.session_state["username"], "scheduled"])
            st.success("✅ 已更新"); st.rerun()

# === 5-2 月總表（admin 可見） === #
with tab_sum:
    if st.session_state["role"] != "admin":
        st.info("此分頁僅管理員可見")
    else:
        sy = st.selectbox("年份", list(range(today.year - 1, today.year + 2)), 1, key="sy")
        sm = st.selectbox("月份", list(range(1, 13)), today.month - 1, key="sm")
        if st.button("📊 載入 / 產生 總表"):
            st.dataframe(make_summary_df(sy, sm), use_container_width=True, height=600)
