import streamlit as st
import pandas as pd
from datetime import datetime

st.title("📊 Real-Time Attendance Dashboard")
st.markdown("---")

# Initialize session state
if 'records' not in st.session_state:
    st.session_state.records = []
    try:
        # Try to load existing CSV if available
        existing_df = pd.read_csv("attendance_records.csv")
        st.session_state.records = existing_df.to_dict(orient='records')
    except FileNotFoundError:
        pass

# Input Form
with st.form("attendance_form", clear_on_submit=True):
    name = st.text_input("👤 Employee Name", placeholder="Enter full name...")
    
    col1, col2 = st.columns(2)
    with col1:
        in_time = st.time_input("⏰ Clock In", value=datetime.now().time())
    with col2:
        out_time = st.time_input("⏰ Clock Out", value=datetime.now().time())
    
    date_str = st.date_input("📅 Date", value=datetime.now())
    
    submitted = st.form_submit_button("✅ Submit Attendance")
    
    if submitted and name:
        record = {
            "Date": date_str,
            "Employee Name": name,
            "In Time": in_time.strftime("%H:%M:%S"),
            "Out Time": out_time.strftime("%H:%M:%S"),
            "Status": "Present"
        }
        st.session_state.records.append(record)
        
        # Save to CSV
        df = pd.DataFrame(st.session_state.records)
        df.to_csv("attendance_records.csv", index=False)
        
        st.success(f"Attendance marked for {name}!")

st.markdown("---")

# Display Records
if st.session_state.records:
    df = pd.DataFrame(st.session_state.records)
    
    # Make dataframe editable for easy corrections
    edited_df = st.data_editor(
        df, 
        key="data_editor",
        column_config={
            "Date": st.column_config.DateColumn("Date", format="YYYY-MM-DD"),
            "In Time": st.column_config.TimeColumn("In Time", format="HH:mm:ss"),
            "Out Time": st.column_config.TimeColumn("Out Time", format="HH:mm:ss"),
        },
        use_container_width=True
    )
    
    # Save if edited
    if edited_df.to_dict(orient='records') != st.session_state.records:
        st.session_state.records = edited_df.to_dict(orient='records')
        edited_df.to_csv("attendance_records.csv", index=False)
        st.toast("Changes saved!")
        st.rerun()
else:
    st.info("No attendance records yet. Submit one above to get started.")

@st.cache_data
def load_data():
    try:
        return pd.read_csv("attendance_records.csv")
    except FileNotFoundError:
        return pd.DataFrame(columns=["Date", "Employee Name", "In Time", "Out Time", "Status"])

df = load_data()
st.subheader("📊 Attendance Records")
st.dataframe(df, use_container_width=True)

# Download button
st.download_button(
    "💾 Download CSV",
    data=df.to_csv(index=False).encode("utf-8"),
    file_name="attendance_records.csv",
    mime="text/csv",
    type="primary"
)