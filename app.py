import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, time

# ────────────────────────────────────────────────
# DATABASE SETUP
# ────────────────────────────────────────────────

DB_FILE = "attendance.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            date TEXT NOT NULL,          -- YYYY-MM-DD
            time_in TEXT,                -- HH:MM
            time_out TEXT,               -- HH:MM
            total_hours REAL,
            workload TEXT,
            remarks TEXT,
            inserted_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ────────────────────────────────────────────────
# HELPER FUNCTIONS
# ────────────────────────────────────────────────

def time_to_hours(t_in: str, t_out: str) -> float | None:
    if not (t_in and t_out):
        return None
    try:
        fmt = "%H:%M"
        delta = datetime.strptime(t_out, fmt) - datetime.strptime(t_in, fmt)
        hours = delta.total_seconds() / 3600
        if hours < 0:  # overnight
            hours += 24
        return round(hours, 2)
    except:
        return None

def get_all_records() -> pd.DataFrame:
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM attendance ORDER BY date DESC, name", conn)
    conn.close()
    return df

# ────────────────────────────────────────────────
# SIDEBAR + PAGE SELECTION
# ────────────────────────────────────────────────

st.set_page_config(page_title="Attendance System", layout="wide")

st.sidebar.title("Attendance System")
page = st.sidebar.radio("Select View", [
    "Clock In / Out (Employee)",
    "Employee Records",
    "Supervisor Dashboard",
    "Import from Excel (One-time)"
])

EMPLOYEES = [
  
]

# ────────────────────────────────────────────────
# PAGES
# ────────────────────────────────────────────────

if page == "Clock In / Out (Employee)":
    st.title("Clock In / Out")

    with st.form("attendance_form", clear_on_submit=True):
        # Free text input instead of dropdown
        name_input = st.text_input("Your Name", placeholder="Type your full name here")
        name = name_input.strip() if name_input else ""

        today = datetime.now().strftime("%Y-%m-%d")

        col1, col2 = st.columns(2)
        with col1:
            time_in = st.time_input("Time In", value=time(8, 0))
        with col2:
            time_out = st.time_input("Time Out", value=time(17, 0))

        workload = st.text_input("Workload / Tasks")
        remarks = st.text_area("Remarks / Notes (OT, etc.)", height=80)

        submitted = st.form_submit_button("Submit Attendance")

    if submitted:
        if not name:
            st.error("Please enter your name.")
        else:
            ti_str = time_in.strftime("%H:%M")
            to_str = time_out.strftime("%H:%M")
            hours = time_to_hours(ti_str, to_str)

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('''
                INSERT INTO attendance (name, date, time_in, time_out, total_hours, workload, remarks)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (name, today, ti_str, to_str, hours, workload, remarks))
            conn.commit()
            conn.close()

            st.success(f"Recorded! {name} – {today} – {hours:.2f} hrs" if hours else f"Recorded! {name} – {today}")
            if hours and hours > 8:
                st.info(f"Overtime detected ({hours-8:.2f} hrs)")

elif page == "View My Records":
    st.title("My Attendance Records")
    name_filter = st.selectbox("Select Employee", ["All"] + EMPLOYEES)

    df = get_all_records()
    if name_filter != "All":
        df = df[df["name"] == name_filter]

    if df.empty:
        st.info("No records yet.")
    else:
        st.dataframe(
            df[["date", "time_in", "time_out", "total_hours", "workload", "remarks"]],
            use_container_width=True,
            hide_index=True
        )

elif page == "Supervisor Dashboard":
    st.title("Supervisor Dashboard")

    df = get_all_records()

    if df.empty:
        st.info("No attendance records yet.")
    else:
        summary = df.groupby("name").agg(
            Total_Hours=("total_hours", "sum"),
            Days_Worked=("date", "nunique"),
            Avg_Hours=("total_hours", "mean"),
        ).round(2).reset_index()

        st.subheader("Summary by Employee")
        st.dataframe(summary, use_container_width=True)

        st.subheader("All Records")
        st.dataframe(df, use_container_width=True)

        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download Full Data (CSV)",
            data=csv,
            file_name=f"attendance_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )

elif page == "Import from Excel (One-time)":
    st.title("Import Legacy Excel Data")
    st.warning("Run this only once – it will add existing records and update employee list.")

    uploaded_file = st.file_uploader("Upload your attendance_sheet.xlsx", type=["xlsx"])

    if uploaded_file and st.button("Start Import"):
        with st.spinner("Importing..."):
            try:
                xls = pd.ExcelFile(uploaded_file)
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()

                imported = 0
                skipped = 0

                for sheet_name in xls.sheet_names:
                    st.subheader(f"Sheet: {sheet_name}")

                    # Try different skiprows to find the data section
                    df = None
                    found_skip = None
                    for skip in [1, 2, 3, 4]:
                        temp_df = pd.read_excel(xls, sheet_name, skiprows=skip, header=None)
                        if temp_df.shape[1] >= 3 and pd.to_numeric(temp_df.iloc[:, 0], errors='coerce').any():
                            df = temp_df
                            found_skip = skip
                            break

                    if df is None:
                        st.warning(f"No valid data structure found in sheet '{sheet_name}'")
                        continue

                    st.info(f"Used skiprows={found_skip} for sheet '{sheet_name}'")

                    # Assign columns
                    df.columns = ['Date', 'Time In', 'Time Out', 'Total Hours', 'Workload', 'Remarks'][:df.shape[1]]

                    # Show first few rows for debugging
                    st.write("First 8 raw rows:")
                    st.dataframe(df.head(8))

                    # Keep only rows with numeric date (Excel serial number)
                    numeric_mask = pd.to_numeric(df['Date'], errors='coerce').notna()
                    df = df[numeric_mask]

                    if df.empty:
                        st.info("No rows with valid numeric dates found after filtering.")
                        continue

                    st.write(f"Found {len(df)} rows with numeric dates")

                    # Convert Excel serial date to YYYY-MM-DD
                    df['Date'] = pd.to_datetime(
                        df['Date'].astype(float),
                        origin='1899-12-30',
                        unit='D',
                        errors='coerce'
                    ).dt.strftime('%Y-%m-%d')

                    # Drop any failed date conversions
                    df = df[df['Date'].notna()]

                    # Convert decimal times to HH:MM
                    def dec_to_time(dec):
                        if pd.isna(dec):
                            return None
                        try:
                            total_h = float(dec) * 24
                            h = int(total_h)
                            m = round((total_h - h) * 60)
                            return f"{h:02d}:{m:02d}"
                        except:
                            return None

                    df['Time In'] = df['Time In'].apply(dec_to_time)
                    df['Time Out'] = df['Time Out'].apply(dec_to_time)

                    df['total_hours'] = df.apply(
                        lambda r: time_to_hours(r['Time In'], r['Time Out']), axis=1
                    )

                    # Determine employee name from sheet name
                    sheet_upper = sheet_name.strip().upper()
                    name = "Unknown Employee"
                    if "ROMMEL" in sheet_upper:
                        name = "ROMMEL DOMINGO"
                    elif "BENEDICT" in sheet_upper or "VERDE" in sheet_upper:
                        name = "BENEDICT CASTRO VERDE"
                    elif "JONNEL" in sheet_upper:
                        name = "JONNEL COJA"
                    elif "JOHN JORDAN" in sheet_upper or "CAMAT" in sheet_upper:
                        name = "JOHN JORDAN CAMAT"
                    elif "ZAROLD" in sheet_upper or "AMIGOS" in sheet_upper:
                        name = "ZAROLD AMIGOS"

                    # Automatically add to employee list if not already there
                    if name != "Unknown Employee" and name not in EMPLOYEES:
                        EMPLOYEES.append(name)
                        st.info(f"Added employee from sheet: {name}")

                    # Insert rows
                    for _, row in df.iterrows():
                        c.execute('''
                            INSERT OR IGNORE INTO attendance 
                            (name, date, time_in, time_out, total_hours, workload, remarks)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            name,
                            row['Date'],
                            row['Time In'],
                            row['Time Out'],
                            row['total_hours'],
                            str(row.get('Workload', '')),
                            str(row.get('Remarks', ''))
                        ))
                        imported += c.rowcount

                conn.commit()
                conn.close()

                st.markdown("---")
                st.success(f"**Import complete!** {imported} records added.")
                if imported == 0:
                    st.warning("No records were imported. Look at the debug tables above for each sheet.")
                else:
                    st.success(f"Employee list now has {len(EMPLOYEES)} names.")

            except Exception as e:
                st.error(f"Import failed: {str(e)}")
                import traceback
                st.code(traceback.format_exc(), language="python")