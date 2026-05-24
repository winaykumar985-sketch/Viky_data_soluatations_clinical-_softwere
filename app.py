import streamlit as st
import psycopg2
import pandas as pd
import urllib.parse
from datetime import date, datetime, timedelta

# 🌐 CLOUD DATABASE CONNECTION
DB_URL = "postgresql://vinay:gsfY9fktXwqWFaCWQZxbBA@brassy-rugrat-16274.jxf.gcp-asia-south1.cockroachlabs.cloud:26257/defaultdb?sslmode=require"

# --- 1. DATABASE SETUP & UPGRADES ---
def init_db():
    conn = psycopg2.connect(DB_URL)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS Clinics (clinic_id TEXT PRIMARY KEY, clinic_name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS Users (username TEXT PRIMARY KEY, password TEXT, role TEXT, clinic_id TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS Patients (patient_id SERIAL PRIMARY KEY, name TEXT, phone TEXT, clinic_id TEXT, appointment_date DATE, appointment_time TEXT, doctor_username TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS Doctor_Schedules (schedule_id SERIAL PRIMARY KEY, clinic_id TEXT, doctor_username TEXT, schedule_date DATE, start_time TEXT, end_time TEXT)''')
    
    # UPGRADE: Add Status column so we don't delete patients anymore!
    c.execute("ALTER TABLE Patients ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'Pending'")
    c.execute("UPDATE Patients SET status='Pending' WHERE status IS NULL")
    
    c.execute("INSERT INTO Users (username, password, role, clinic_id) VALUES ('superadmin', 'master123', 'SuperAdmin', 'SYSTEM') ON CONFLICT (username) DO NOTHING")
    conn.commit()
    conn.close()

init_db()

# --- HELPER FUNCTION: TIME SLOTS ---
def generate_slots(start_str, end_str):
    slots = []
    try:
        start = datetime.strptime(start_str, "%I:%M %p")
        end = datetime.strptime(end_str, "%I:%M %p")
        while start <= end:
            slots.append(start.strftime("%I:%M %p"))
            start += timedelta(minutes=30)
    except:
        pass
    return slots

# --- 2. APP STATE ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""
if "role" not in st.session_state:
    st.session_state.role = ""
if "clinic_id" not in st.session_state:
    st.session_state.clinic_id = ""
if "clinic_name" not in st.session_state:
    st.session_state.clinic_name = ""

# --- 3. LOGIN SCREEN ---
if not st.session_state.logged_in:
    st.title("🏥 MediSaaS - Cloud Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        conn = psycopg2.connect(DB_URL)
        c = conn.cursor()
        c.execute('''SELECT u.role, u.clinic_id, c.clinic_name FROM Users u LEFT JOIN Clinics c ON u.clinic_id = c.clinic_id WHERE u.username=%s AND u.password=%s''', (username, password))
        user = c.fetchone()
        conn.close()
        
        if user:
            st.session_state.logged_in = True
            st.session_state.username = username
            st.session_state.role = user[0]
            st.session_state.clinic_id = user[1]
            st.session_state.clinic_name = user[2] if user[2] else "System Dashboard"
            st.rerun()
        else:
            st.error("Invalid Username or Password")

# --- 4. ROLE-BASED DASHBOARDS ---
else:
    if st.session_state.role == "SuperAdmin":
        st.sidebar.title("👑 Platform Control")
    else:
        st.sidebar.title(f"🏥 {st.session_state.clinic_name}")
        st.sidebar.caption(f"Code: {st.session_state.clinic_id}")
        
    st.sidebar.write(f"👤 User: {st.session_state.username} ({st.session_state.role})")
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()
    
    # ==========================================
    # 👑 SUPER ADMIN VIEW
    # ==========================================
    if st.session_state.role == "SuperAdmin":
        st.header("👑 Platform Control Center")
        tab1, tab2, tab3, tab4 = st.tabs(["➕ Deploy Clinic", "🏥 Manage Clinics", "📥 Download Data", "🔒 Security"])
        
        with tab1: # Deploy Clinic logic (same as before)
            with st.form("create_clinic_form", clear_on_submit=True):
                new_clinic_id = st.text_input("New Clinic Code")
                new_clinic_name = st.text_input("Full Clinic Name")
                admin_user = st.text_input("First Admin Username")
                admin_pass = st.text_input("First Admin Password", type="password")
                if st.form_submit_button("Deploy New Clinic"):
                    if new_clinic_id and admin_user:
                        conn = psycopg2.connect(DB_URL)
                        c = conn.cursor()
                        try:
                            c.execute("INSERT INTO Clinics (clinic_id, clinic_name) VALUES (%s, %s)", (new_clinic_id, new_clinic_name))
                            c.execute("INSERT INTO Users (username, password, role, clinic_id) VALUES (%s, %s, %s, %s)", (admin_user, admin_pass, 'Admin', new_clinic_id))
                            conn.commit()
                            st.success("Successfully deployed!")
                        except:
                            st.error("Error: Database conflict.")
                        finally:
                            conn.close()

        with tab2: # Manage Clinics logic (same as before)
            conn = psycopg2.connect(DB_URL)
            c = conn.cursor()
            c.execute("SELECT clinic_id, clinic_name FROM Clinics")
            clinics = c.fetchall()
            conn.close()
            for cid, cname in clinics:
                col1, col2 = st.columns([4, 1])
                col1.info(f"**{cname}** (Code: {cid})")
                if col2.button("❌ Remove", key=f"del_clinic_{cid}"):
                    conn = psycopg2.connect(DB_URL)
                    c = conn.cursor()
                    c.execute("DELETE FROM Clinics WHERE clinic_id=%s", (cid,))
                    c.execute("DELETE FROM Users WHERE clinic_id=%s", (cid,))
                    c.execute("DELETE FROM Doctor_Schedules WHERE clinic_id=%s", (cid,))
                    c.execute("DELETE FROM Patients WHERE clinic_id=%s", (cid,))
                    conn.commit()
                    conn.close()
                    st.success("Clinic completely removed.")
                    st.rerun()

        with tab3: # Download logic (same as before)
            if clinics:
                for cid, cname in clinics:
                    conn = psycopg2.connect(DB_URL)
                    df = pd.read_sql_query(f"SELECT * FROM Patients WHERE clinic_id='{cid}'", conn)
                    conn.close()
                    csv = df.to_csv(index=False).encode('utf-8')
                    st.download_button(label=f"📥 Download Data for {cname}", data=csv, file_name=f"{cid}_Data.csv", mime="text/csv", key=f"dl_clinic_{cid}")
        
        # UPGRADE: SuperAdmin Security Tab
        with tab4:
            st.write("Update Admin Credentials without losing data.")
            with st.form("super_update_creds"):
                old_u = st.text_input("Old Username")
                new_u = st.text_input("New Username")
                new_p = st.text_input("New Password", type="password")
                if st.form_submit_button("Update Credentials"):
                    conn = psycopg2.connect(DB_URL)
                    c = conn.cursor()
                    try:
                        c.execute("UPDATE Users SET username=%s, password=%s WHERE username=%s", (new_u, new_p, old_u))
                        conn.commit()
                        st.success(f"Credentials updated for {new_u}!")
                    except Exception as e:
                        st.error("Failed. Ensure the new username isn't already taken.")
                    finally:
                        conn.close()

    # ==========================================
    # 🏢 HOSPITAL ADMIN VIEW 
    # ==========================================
    elif st.session_state.role == "Admin":
        st.header(f"⚙️ {st.session_state.clinic_name} Management")
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["➕ Add Staff", "👥 Manage Staff", "📅 Schedule Doctors", "📥 Database", "🔒 Security"])
        
        with tab1: # Add Staff
            with st.form("create_staff_form", clear_on_submit=True):
                staff_role = st.selectbox("Staff Role", ["Doctor", "Receptionist"])
                staff_user = st.text_input("New Username")
                staff_pass = st.text_input("New Password", type="password")
                if st.form_submit_button("Create Staff Account"):
                    if staff_user and staff_pass:
                        conn = psycopg2.connect(DB_URL)
                        c = conn.cursor()
                        try:
                            c.execute("INSERT INTO Users (username, password, role, clinic_id) VALUES (%s, %s, %s, %s)", (staff_user, staff_pass, staff_role, st.session_state.clinic_id))
                            conn.commit()
                            st.success(f"Created: {staff_user}")
                        except:
                            st.error("Error: Username exists.")
                        finally:
                            conn.close()

        with tab2: # Manage Staff
            conn = psycopg2.connect(DB_URL)
            c = conn.cursor()
            c.execute("SELECT username, role FROM Users WHERE clinic_id=%s AND role IN ('Doctor', 'Receptionist')", (st.session_state.clinic_id,))
            staff_members = c.fetchall()
            conn.close()
            for s_user, s_role in staff_members:
                col1, col2 = st.columns([4, 1])
                col1.info(f"👤 **{s_user}** ({s_role})")
                if col2.button("❌ Remove", key=f"del_staff_{s_user}"):
                    conn = psycopg2.connect(DB_URL)
                    c = conn.cursor()
                    c.execute("DELETE FROM Users WHERE username=%s", (s_user,))
                    conn.commit()
                    conn.close()
                    st.rerun()

        with tab3: # Schedule Doctors
            conn = psycopg2.connect(DB_URL)
            c = conn.cursor()
            c.execute("SELECT username FROM Users WHERE role='Doctor' AND clinic_id=%s", (st.session_state.clinic_id,))
            doctors = [row[0] for row in c.fetchall()]
            conn.close()
            if doctors:
                with st.form("schedule_doctor_form"):
                    selected_doc = st.selectbox("Select Doctor", doctors)
                    sched_date = st.date_input("Working Date", min_value=date.today())
                    time_opts = ["08:00 AM", "08:30 AM", "09:00 AM", "09:30 AM", "10:00 AM", "10:30 AM", "11:00 AM", "11:30 AM", "12:00 PM", "12:30 PM", "01:00 PM", "01:30 PM", "02:00 PM", "02:30 PM", "03:00 PM", "03:30 PM", "04:00 PM", "04:30 PM", "05:00 PM"]
                    col1, col2 = st.columns(2)
                    with col1: start_time = st.selectbox("Shift Start Time", time_opts, index=2)
                    with col2: end_time = st.selectbox("Shift End Time", time_opts, index=18)
                    if st.form_submit_button("Set Availability"):
                        conn = psycopg2.connect(DB_URL)
                        c = conn.cursor()
                        c.execute("DELETE FROM Doctor_Schedules WHERE clinic_id=%s AND doctor_username=%s AND schedule_date=%s", (st.session_state.clinic_id, selected_doc, sched_date))
                        c.execute("INSERT INTO Doctor_Schedules (clinic_id, doctor_username, schedule_date, start_time, end_time) VALUES (%s, %s, %s, %s, %s)", (st.session_state.clinic_id, selected_doc, sched_date, start_time, end_time))
                        conn.commit()
                        conn.close()
                        st.success("Schedule locked in!")

        with tab4: # Database
            conn = psycopg2.connect(DB_URL)
            df = pd.read_sql_query(f"SELECT * FROM Patients WHERE clinic_id='{st.session_state.clinic_id}'", conn)
            conn.close()
            if not df.empty:
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button(label="📥 Download Hospital Data", data=csv, file_name=f"{st.session_state.clinic_id}_Data.csv", mime="text/csv")
                
        # UPGRADE: Admin Security Tab
        with tab5:
            st.write("Update Staff Credentials. (Cascades safely so schedules/patients aren't lost).")
            with st.form("admin_update_creds"):
                old_u = st.text_input("Current Username")
                new_u = st.text_input("New Username")
                new_p = st.text_input("New Password", type="password")
                if st.form_submit_button("Update Credentials"):
                    conn = psycopg2.connect(DB_URL)
                    c = conn.cursor()
                    try:
                        # Update all tables linking to this username
                        c.execute("UPDATE Users SET username=%s, password=%s WHERE username=%s AND clinic_id=%s", (new_u, new_p, old_u, st.session_state.clinic_id))
                        c.execute("UPDATE Doctor_Schedules SET doctor_username=%s WHERE doctor_username=%s AND clinic_id=%s", (new_u, old_u, st.session_state.clinic_id))
                        c.execute("UPDATE Patients SET doctor_username=%s WHERE doctor_username=%s AND clinic_id=%s", (new_u, old_u, st.session_state.clinic_id))
                        conn.commit()
                        st.success(f"Credentials successfully updated to {new_u}!")
                    except Exception as e:
                        st.error("Failed. Ensure new username isn't taken.")
                    finally:
                        conn.close()

    # ==========================================
    # 📝 RECEPTIONIST VIEW 
    # ==========================================
    elif st.session_state.role == "Receptionist":
        st.header("📝 Front Desk Dashboard")
        
        tab1, tab2 = st.tabs(["📅 Book Appointment", "📋 Today's Board"])
        
        with tab1:
            selected_date = st.date_input("1. Select Date", min_value=date.today())
            conn = psycopg2.connect(DB_URL)
            c = conn.cursor()
            c.execute("SELECT doctor_username, start_time, end_time FROM Doctor_Schedules WHERE clinic_id=%s AND schedule_date=%s", (st.session_state.clinic_id, selected_date))
            schedules = c.fetchall()
            
            if not schedules:
                st.warning(f"No doctors scheduled for {selected_date}.")
                conn.close()
            else:
                doc_schedule_map = {row[0]: (row[1], row[2]) for row in schedules}
                selected_doc = st.selectbox("2. Select Doctor", list(doc_schedule_map.keys()))
                doc_start, doc_end = doc_schedule_map[selected_doc]
                all_doc_slots = generate_slots(doc_start, doc_end)
                
                c.execute("SELECT appointment_time FROM Patients WHERE clinic_id=%s AND appointment_date=%s AND doctor_username=%s", (st.session_state.clinic_id, selected_date, selected_doc))
                booked_slots = [record[0] for record in c.fetchall() if record[0] is not None]
                conn.close()
                
                available_slots = [slot for slot in all_doc_slots if slot not in booked_slots]
                
                if not available_slots:
                    st.error("❌ Fully booked.")
                else:
                    selected_time = st.selectbox("3. Available Times", available_slots)
                    p_name = st.text_input("Patient Name")
                    p_phone = st.text_input("Phone Number")
                    if st.button("Book Appointment"):
                        conn = psycopg2.connect(DB_URL)
                        c = conn.cursor()
                        c.execute("INSERT INTO Patients (name, phone, clinic_id, appointment_date, appointment_time, doctor_username, status) VALUES (%s, %s, %s, %s, %s, %s, 'Pending')", (p_name, p_phone, st.session_state.clinic_id, selected_date, selected_time, selected_doc))
                        conn.commit()
                        conn.close()
                        st.success(f"✅ Booked {p_name}!")
        
        # UPGRADE: Receptionist Daily Dashboard
        with tab2:
            st.subheader(f"Appointments for Today ({date.today()})")
            conn = psycopg2.connect(DB_URL)
            # Pull all patients for TODAY only, showing status. Tomorrow, this automatically resets!
            df_today = pd.read_sql_query(f"SELECT appointment_time AS Time, name AS Patient, doctor_username AS Doctor, status AS Status FROM Patients WHERE clinic_id='{st.session_state.clinic_id}' AND appointment_date='{date.today()}' ORDER BY appointment_time ASC", conn)
            conn.close()
            
            if df_today.empty:
                st.info("No appointments scheduled for today.")
            else:
                st.dataframe(df_today, use_container_width=True, hide_index=True)

    # ==========================================
    # 🩺 DOCTOR VIEW 
    # ==========================================
    elif st.session_state.role == "Doctor":
        st.header(f"🩺 Dr. {st.session_state.username}'s Desk")
        
        conn = psycopg2.connect(DB_URL)
        c = conn.cursor()
        # UPGRADE: Fetch ONLY Pending patients
        c.execute("SELECT patient_id, name, phone, appointment_date, appointment_time FROM Patients WHERE clinic_id=%s AND doctor_username=%s AND status='Pending' ORDER BY appointment_date ASC, appointment_time ASC", (st.session_state.clinic_id, st.session_state.username))
        rows = c.fetchall()
        columns = [desc[0] for desc in c.description] if c.description else []
        df = pd.DataFrame(rows, columns=columns)
        conn.close()
        
        if df.empty:
            st.info("You have no pending patients right now.")
        else:
            patient_options = {f"ID: {row['patient_id']} - {row['name']} ({row['appointment_date']} @ {row['appointment_time']})": (row['patient_id'], row['name'], row['phone']) for _, row in df.iterrows()}
            selected_patient_str = st.selectbox("Select Patient to Treat", list(patient_options.keys()))
            selected_patient_id, selected_patient_name, selected_patient_phone = patient_options[selected_patient_str]
            
            st.markdown("---")
            symptoms = st.text_area("Symptoms / Diagnosis")
            medicines = st.text_area("Medicines")
            advice = st.text_input("General Advice")
            
            st.markdown("---")
            # UPGRADE: Doctor Follow-Up Scheduler
            st.subheader("📅 Schedule Follow-up (Optional)")
            schedule_follow_up = st.checkbox("Require follow-up appointment?")
            if schedule_follow_up:
                col1, col2 = st.columns(2)
                with col1:
                    next_date = st.date_input("Next Date", min_value=date.today() + timedelta(days=1))
                with col2:
                    time_opts = ["09:00 AM", "09:30 AM", "10:00 AM", "10:30 AM", "11:00 AM", "11:30 AM", "12:00 PM", "12:30 PM", "01:00 PM", "01:30 PM", "02:00 PM", "02:30 PM", "03:00 PM", "03:30 PM", "04:00 PM", "04:30 PM", "05:00 PM"]
                    next_time = st.selectbox("Requested Time", time_opts)
            
            if st.button("Complete Visit & Send Rx"):
                if not symptoms or not medicines:
                    st.error("Please fill in Symptoms and Medicines.")
                else:
                    whatsapp_msg = f"🏥 *{st.session_state.clinic_name}*\n👨‍⚕️ *Dr. {st.session_state.username}*\n👤 *Patient:* {selected_patient_name}\n🩺 *Symptoms:* {symptoms}\n💊 *Medicines:*\n{medicines}\n📝 *Advice:* {advice}"
                    if schedule_follow_up:
                        whatsapp_msg += f"\n\n📅 *Next Appointment:* {next_date} at {next_time}"
                        
                    encoded_msg = urllib.parse.quote(whatsapp_msg)
                    clean_phone = ''.join(filter(str.isdigit, selected_patient_phone))
                    if len(clean_phone) == 10: clean_phone = "91" + clean_phone
                    wa_web_url = f"https://api.whatsapp.com/send/?phone={clean_phone}&text={encoded_msg}"
                    
                    conn = psycopg2.connect(DB_URL)
                    c = conn.cursor()
                    
                    # Instead of deleting, mark current appointment as Completed
                    c.execute("UPDATE Patients SET status='Completed' WHERE patient_id=%s", (selected_patient_id,))
                    
                    # If follow up requested, create a new pending appointment!
                    if schedule_follow_up:
                        c.execute("INSERT INTO Patients (name, phone, clinic_id, appointment_date, appointment_time, doctor_username, status) VALUES (%s, %s, %s, %s, %s, %s, 'Pending')", 
                                  (selected_patient_name, selected_patient_phone, st.session_state.clinic_id, next_date, next_time, st.session_state.username))
                    
                    conn.commit()
                    conn.close()
                    
                    st.success("🎉 Treatment completed! Patient marked as finished.")
                    st.link_button("💬 Send via WhatsApp", url=wa_web_url, use_container_width=True)
