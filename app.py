import streamlit as st
import psycopg2
import pandas as pd
from fpdf import FPDF
import urllib.parse
from datetime import date, datetime, timedelta

# 🌐 CLOUD DATABASE CONNECTION
DB_URL = "postgresql://vinay:gsfY9fktXwqWFaCWQZxbBA@brassy-rugrat-16274.jxf.gcp-asia-south1.cockroachlabs.cloud:26257/defaultdb?sslmode=require"

# --- 1. DATABASE SETUP & UPGRADES ---
def init_db():
    conn = psycopg2.connect(DB_URL)
    c = conn.cursor()
    # Ensure base tables exist
    c.execute('''CREATE TABLE IF NOT EXISTS Clinics (clinic_id TEXT PRIMARY KEY, clinic_name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS Users (username TEXT PRIMARY KEY, password TEXT, role TEXT, clinic_id TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS Patients (patient_id SERIAL PRIMARY KEY, name TEXT, phone TEXT, clinic_id TEXT)''')
    
    # Create Schedule Table for Doctors
    c.execute('''CREATE TABLE IF NOT EXISTS Doctor_Schedules (
        schedule_id SERIAL PRIMARY KEY,
        clinic_id TEXT,
        doctor_username TEXT,
        schedule_date DATE,
        start_time TEXT,
        end_time TEXT
    )''')
    
    # Safely upgrade existing Patients table
    c.execute("ALTER TABLE Patients ADD COLUMN IF NOT EXISTS appointment_date DATE")
    c.execute("ALTER TABLE Patients ADD COLUMN IF NOT EXISTS appointment_time TEXT")
    c.execute("ALTER TABLE Patients ADD COLUMN IF NOT EXISTS doctor_username TEXT")
    
    # 👑 CREATE SUPER ADMIN ACCOUNT
    c.execute("INSERT INTO Users (username, password, role, clinic_id) VALUES ('superadmin', 'master123', 'SuperAdmin', 'SYSTEM') ON CONFLICT (username) DO NOTHING")
    
    conn.commit()
    conn.close()

init_db()

# --- HELPER FUNCTION: DYNAMIC TIME SLOTS ---
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
    st.session_state.username = ""
    st.session_state.role = ""
    st.session_state.clinic_id = ""

# --- 3. SAAS LOGIN SCREEN ---
if not st.session_state.logged_in:
    st.title("🏥 MediSaaS - Cloud Login")
    
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    
    if st.button("Login"):
        conn = psycopg2.connect(DB_URL)
        c = conn.cursor()
        c.execute("SELECT role, clinic_id FROM Users WHERE username=%s AND password=%s", (username, password))
        user = c.fetchone()
        conn.close()
        
        if user:
            st.session_state.logged_in = True
            st.session_state.username = username
            st.session_state.role = user[0]
            st.session_state.clinic_id = user[1]
            st.rerun()
        else:
            st.error("Invalid Username or Password")

# --- 4. ROLE-BASED DASHBOARDS ---
else:
    st.sidebar.title(f"🏢 Network: {st.session_state.clinic_id}")
    st.sidebar.write(f"👤 User: {st.session_state.username} ({st.session_state.role})")
    
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()
    
    # ==========================================
    # 👑 SUPER ADMIN VIEW
    # ==========================================
    if st.session_state.role == "SuperAdmin":
        st.header("👑 Platform Control Center")
        st.write("Create a new Clinic space and generate the initial Admin account for that hospital.")
        
        with st.form("create_clinic_form", clear_on_submit=True):
            new_clinic_id = st.text_input("New Clinic Code (e.g., APOLLO_BLR)")
            new_clinic_name = st.text_input("Full Clinic Name")
            st.markdown("---")
            st.write("**Create First Admin for this Clinic**")
            admin_user = st.text_input("Admin Username")
            admin_pass = st.text_input("Admin Password", type="password")
            
            if st.form_submit_button("Deploy New Clinic"):
                if new_clinic_id and admin_user:
                    conn = psycopg2.connect(DB_URL)
                    c = conn.cursor()
                    try:
                        c.execute("INSERT INTO Clinics (clinic_id, clinic_name) VALUES (%s, %s)", (new_clinic_id, new_clinic_name))
                        c.execute("INSERT INTO Users (username, password, role, clinic_id) VALUES (%s, %s, %s, %s)", 
                                  (admin_user, admin_pass, 'Admin', new_clinic_id))
                        conn.commit()
                        st.success(f"Successfully deployed {new_clinic_name} and created admin {admin_user}!")
                    except Exception as e:
                        st.error(f"Error: Username or Clinic Code might already exist.")
                    finally:
                        conn.close()

    # ==========================================
    # 🏢 HOSPITAL ADMIN VIEW (Manage Staff & Timings)
    # ==========================================
    elif st.session_state.role == "Admin":
        st.header("⚙️ Hospital Management")
        
        tab1, tab2 = st.tabs(["👥 Create Staff", "📅 Schedule Doctors"])
        
        with tab1:
            st.write(f"Manage staff accounts for **{st.session_state.clinic_id}**")
            with st.form("create_staff_form", clear_on_submit=True):
                staff_role = st.selectbox("Staff Role to Create", ["Doctor", "Receptionist"])
                staff_user = st.text_input("New Username")
                staff_pass = st.text_input("New Password", type="password")
                
                if st.form_submit_button("Create Staff Member"):
                    if staff_user and staff_pass:
                        conn = psycopg2.connect(DB_URL)
                        c = conn.cursor()
                        try:
                            c.execute("INSERT INTO Users (username, password, role, clinic_id) VALUES (%s, %s, %s, %s)", 
                                      (staff_user, staff_pass, staff_role, st.session_state.clinic_id))
                            conn.commit()
                            st.success(f"Successfully created {staff_role} account: {staff_user}")
                        except Exception as e:
                            st.error("Error: Username already exists.")
                        finally:
                            conn.close()
                            
        with tab2:
            st.write("Assign specific working hours for your Doctors on specific dates.")
            conn = psycopg2.connect(DB_URL)
            c = conn.cursor()
            c.execute("SELECT username FROM Users WHERE role='Doctor' AND clinic_id=%s", (st.session_state.clinic_id,))
            doctors = [row[0] for row in c.fetchall()]
            conn.close()
            
            if not doctors:
                st.warning("You need to create a Doctor account first.")
            else:
                with st.form("schedule_doctor_form"):
                    selected_doc = st.selectbox("Select Doctor", doctors)
                    sched_date = st.date_input("Working Date", min_value=date.today())
                    
                    time_opts = ["08:00 AM", "08:30 AM", "09:00 AM", "09:30 AM", "10:00 AM", "10:30 AM", 
                                 "11:00 AM", "11:30 AM", "12:00 PM", "12:30 PM", "01:00 PM", "01:30 PM", 
                                 "02:00 PM", "02:30 PM", "03:00 PM", "03:30 PM", "04:00 PM", "04:30 PM", 
                                 "05:00 PM", "05:30 PM", "06:00 PM", "06:30 PM", "07:00 PM", "07:30 PM", "08:00 PM"]
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        start_time = st.selectbox("Shift Start Time", time_opts, index=2) # Default 09:00 AM
                    with col2:
                        end_time = st.selectbox("Shift End Time", time_opts, index=18) # Default 05:00 PM
                        
                    if st.form_submit_button("Set Doctor Availability"):
                        conn = psycopg2.connect(DB_URL)
                        c = conn.cursor()
                        # Delete any existing schedule for this doctor on this date to prevent duplicates
                        c.execute("DELETE FROM Doctor_Schedules WHERE clinic_id=%s AND doctor_username=%s AND schedule_date=%s", 
                                  (st.session_state.clinic_id, selected_doc, sched_date))
                        # Insert new schedule
                        c.execute("INSERT INTO Doctor_Schedules (clinic_id, doctor_username, schedule_date, start_time, end_time) VALUES (%s, %s, %s, %s, %s)", 
                                  (st.session_state.clinic_id, selected_doc, sched_date, start_time, end_time))
                        conn.commit()
                        conn.close()
                        st.success(f"Schedule locked in for Dr. {selected_doc} on {sched_date} from {start_time} to {end_time}!")

    # ==========================================
    # 📝 RECEPTIONIST VIEW (Doctor-Specific Scheduling)
    # ==========================================
    elif st.session_state.role == "Receptionist":
        st.header("📝 Smart Appointment Booking")
        
        selected_date = st.date_input("1. Select Appointment Date", min_value=date.today())
        
        # Check which doctors are scheduled for this date
        conn = psycopg2.connect(DB_URL)
        c = conn.cursor()
        c.execute("SELECT doctor_username, start_time, end_time FROM Doctor_Schedules WHERE clinic_id=%s AND schedule_date=%s", 
                  (st.session_state.clinic_id, selected_date))
        schedules = c.fetchall()
        
        if not schedules:
            st.warning(f"No doctors have been scheduled by the Admin for {selected_date} yet.")
            conn.close()
        else:
            # Map available doctors to their shift times
            doc_schedule_map = {row[0]: (row[1], row[2]) for row in schedules}
            
            selected_doc = st.selectbox("2. Select Available Doctor", list(doc_schedule_map.keys()))
            doc_start, doc_end = doc_schedule_map[selected_doc]
            
            # Generate total slots for this specific doctor
            all_doc_slots = generate_slots(doc_start, doc_end)
            
            # Find slots already booked for THIS doctor on THIS date
            c.execute("SELECT appointment_time FROM Patients WHERE clinic_id=%s AND appointment_date=%s AND doctor_username=%s", 
                      (st.session_state.clinic_id, selected_date, selected_doc))
            booked_records = c.fetchall()
            conn.close()
            
            booked_slots = [record[0] for record in booked_records if record[0] is not None]
            available_slots = [slot for slot in all_doc_slots if slot not in booked_slots]
            
            if not available_slots:
                st.error(f"❌ Dr. {selected_doc} is completely booked on {selected_date}.")
            else:
                selected_time = st.selectbox("3. Available Time Slots", available_slots)
                
                st.markdown("---")
                st.write("**Patient Details**")
                p_name = st.text_input("Patient Name")
                p_phone = st.text_input("Phone Number (without +)")
                
                if st.button("Book Appointment"):
                    if not p_name or not p_phone:
                        st.warning("Please fill out Patient details.")
                    else:
                        conn = psycopg2.connect(DB_URL)
                        c = conn.cursor()
                        c.execute("INSERT INTO Patients (name, phone, clinic_id, appointment_date, appointment_time, doctor_username) VALUES (%s, %s, %s, %s, %s, %s)", 
                                  (p_name, p_phone, st.session_state.clinic_id, selected_date, selected_time, selected_doc))
                        conn.commit()
                        conn.close()
                        st.success(f"✅ {p_name} booked successfully with Dr. {selected_doc} for {selected_date} at {selected_time}!")

    # ==========================================
    # 🩺 DOCTOR VIEW (Only Sees Their Own Patients)
    # ==========================================
    elif st.session_state.role == "Doctor":
        st.header(f"🩺 Dr. {st.session_state.username}'s Consultation Desk")
        
        conn = psycopg2.connect(DB_URL)
        c = conn.cursor()
        # Fetch ONLY patients assigned to the logged-in doctor
        c.execute("SELECT patient_id, name, phone, appointment_date, appointment_time FROM Patients WHERE clinic_id=%s AND doctor_username=%s ORDER BY appointment_date ASC, appointment_time ASC", 
                  (st.session_state.clinic_id, st.session_state.username))
        rows = c.fetchall()
        columns = [desc[0] for desc in c.description] if c.description else []
        df = pd.DataFrame(rows, columns=columns)
        conn.close()
        
        if df.empty:
            st.info("You have no patients scheduled right now.")
        else:
            patient_options = {f"ID: {row['patient_id']} - {row['name']} ({row['appointment_date']} @ {row['appointment_time']})": (row['patient_id'], row['name'], row['phone']) for _, row in df.iterrows()}
            selected_patient_str = st.selectbox("Select Patient to Treat", list(patient_options.keys()))
            
            selected_patient_id, selected_patient_name, selected_patient_phone = patient_options[selected_patient_str]
            
            st.markdown("---")
            st.subheader(f"✍ Prescription Pad for {selected_patient_name}")
            
            symptoms = st.text_area("Symptoms / Diagnosis")
            medicines = st.text_area("Medicines")
            advice = st.text_input("General Advice")
            
            if st.button("Generate Rx & Complete Visit"):
                if not symptoms or not medicines:
                    st.error("Please fill in Symptoms and Medicines before generating.")
                else:
                    pdf = FPDF()
                    pdf.add_page()
                    pdf.set_font("Arial", "B", 20)
                    pdf.cell(0, 10, "MEDISAAS DIGITAL PRESCRIPTION", ln=True, align="C")
                    pdf.set_font("Arial", "", 12)
                    pdf.cell(0, 10, f"Clinic: {st.session_state.clinic_id} | Doctor: {st.session_state.username}", ln=True, align="C")
                    pdf.line(10, 30, 200, 30)
                    pdf.ln(15)
                    
                    pdf.set_font("Arial", "B", 12)
                    pdf.cell(0, 10, f"Patient Name: {selected_patient_name}", ln=True)
                    pdf.set_font("Arial", "", 12)
                    pdf.multi_cell(0, 8, f"Symptoms: {symptoms}\nRx: {medicines}\nAdvice: {advice}")
                    pdf_bytes = bytes(pdf.output(dest='S'))
                    
                    whatsapp_msg = f"🏥 *{st.session_state.clinic_id} PRESCRIPTION*\n👨‍⚕️ *Dr. {st.session_state.username}*\n👤 *Patient:* {selected_patient_name}\n🩺 *Symptoms:* {symptoms}\n💊 *Medicines:*\n{medicines}\n📝 *Advice:* {advice}"
                    encoded_msg = urllib.parse.quote(whatsapp_msg)
                    clean_phone = ''.join(filter(str.isdigit, selected_patient_phone))
                    if len(clean_phone) == 10: clean_phone = "91" + clean_phone
                    wa_web_url = f"https://api.whatsapp.com/send/?phone={clean_phone}&text={encoded_msg}"
                    
                    conn = psycopg2.connect(DB_URL)
                    c = conn.cursor()
                    c.execute("DELETE FROM Patients WHERE patient_id=%s", (selected_patient_id,))
                    conn.commit()
                    conn.close()
                    
                    st.success("🎉 Treatment completed! Patient removed from queue.")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.download_button("📥 Download PDF", data=pdf_bytes, file_name=f"Rx_{selected_patient_id}.pdf", mime="application/pdf", use_container_width=True)
                    with col2:
                        st.link_button("💬 Send via WhatsApp", url=wa_web_url, use_container_width=True)
