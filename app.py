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
    
    # ⬆️ UPGRADE: Add scheduling columns safely to the live database if they don't exist yet
    c.execute("ALTER TABLE Patients ADD COLUMN IF NOT EXISTS appointment_date DATE")
    c.execute("ALTER TABLE Patients ADD COLUMN IF NOT EXISTS appointment_time TEXT")
    
    # 👑 CREATE SUPER ADMIN ACCOUNT (This is for YOU)
    c.execute("INSERT INTO Users (username, password, role, clinic_id) VALUES ('superadmin', 'master123', 'SuperAdmin', 'SYSTEM') ON CONFLICT (username) DO NOTHING")
    
    conn.commit()
    conn.close()

init_db()

# --- HELPER FUNCTION: TIME SLOTS ---
def get_all_time_slots():
    # Generates time slots from 09:00 AM to 05:00 PM every 30 mins
    slots = []
    start = datetime.strptime("09:00 AM", "%I:%M %p")
    end = datetime.strptime("05:00 PM", "%I:%M %p")
    while start <= end:
        slots.append(start.strftime("%I:%M %p"))
        start += timedelta(minutes=30)
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
    st.info("Log in with **superadmin** | Password: **master123** to start creating clinics!")
    
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
    # 👑 SUPER ADMIN VIEW (You: Creating Clinics)
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
            admin_pass = st.text_input("Admin Password")
            
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
    # 🏢 HOSPITAL ADMIN VIEW (Managing Staff)
    # ==========================================
    elif st.session_state.role == "Admin":
        st.header("⚙️ Hospital Management")
        st.write(f"Manage staff accounts for **{st.session_state.clinic_id}**")
        
        with st.form("create_staff_form", clear_on_submit=True):
            staff_role = st.selectbox("Staff Role to Create", ["Doctor", "Receptionist"])
            staff_user = st.text_input("New Username")
            staff_pass = st.text_input("New Password")
            
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

    # ==========================================
    # 📝 RECEPTIONIST VIEW (Smart Scheduling)
    # ==========================================
    elif st.session_state.role == "Receptionist":
        st.header("📝 Smart Appointment Booking")
        
        p_name = st.text_input("Patient Name")
        p_phone = st.text_input("Phone Number (without +)")
        selected_date = st.date_input("Appointment Date", min_value=date.today())
        
        # Connect to DB to find which slots are already taken for THIS clinic on THIS date
        conn = psycopg2.connect(DB_URL)
        c = conn.cursor()
        c.execute("SELECT appointment_time FROM Patients WHERE clinic_id=%s AND appointment_date=%s", 
                  (st.session_state.clinic_id, selected_date))
        booked_records = c.fetchall()
        conn.close()
        
        # Flatten the list of booked times
        booked_slots = [record[0] for record in booked_records if record[0] is not None]
        all_slots = get_all_time_slots()
        
        # Filter out booked slots dynamically
        available_slots = [slot for slot in all_slots if slot not in booked_slots]
        
        if len(available_slots) == 0:
            st.error(f"❌ Fully Booked! There are no available slots for {selected_date}.")
        else:
            selected_time = st.selectbox("Available Time Slots", available_slots)
            
            if st.button("Book Appointment"):
                if not p_name or not p_phone:
                    st.warning("Please fill out Patient details.")
                else:
                    conn = psycopg2.connect(DB_URL)
                    c = conn.cursor()
                    c.execute("INSERT INTO Patients (name, phone, clinic_id, appointment_date, appointment_time) VALUES (%s, %s, %s, %s, %s)", 
                              (p_name, p_phone, st.session_state.clinic_id, selected_date, selected_time))
                    conn.commit()
                    conn.close()
                    st.success(f"✅ {p_name} booked successfully for {selected_date} at {selected_time}!")

    # ==========================================
    # 🩺 DOCTOR VIEW (Treat & Prescribe)
    # ==========================================
    elif st.session_state.role == "Doctor":
        st.header("🩺 Doctor's Consultation Desk")
        
        conn = psycopg2.connect(DB_URL)
        c = conn.cursor()
        # Fetch patients and order by date and time
        c.execute("SELECT patient_id, name, phone, appointment_date, appointment_time FROM Patients WHERE clinic_id=%s ORDER BY appointment_date ASC, appointment_time ASC", (st.session_state.clinic_id,))
        rows = c.fetchall()
        columns = [desc[0] for desc in c.description] if c.description else []
        df = pd.DataFrame(rows, columns=columns)
        conn.close()
        
        if df.empty:
            st.info("No patients scheduled right now.")
        else:
            # Display format: ID - Name (Date at Time)
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
                    # PDF Generation
                    pdf = FPDF()
                    pdf.add_page()
                    pdf.set_font("Arial", "B", 20)
                    pdf.cell(0, 10, "MEDISAAS DIGITAL PRESCRIPTION", ln=True, align="C")
                    pdf.set_font("Arial", "", 12)
                    pdf.cell(0, 10, f"Clinic: {st.session_state.clinic_id}", ln=True, align="C")
                    pdf.line(10, 30, 200, 30)
                    pdf.ln(15)
                    
                    pdf.set_font("Arial", "B", 12)
                    pdf.cell(0, 10, f"Patient Name: {selected_patient_name}", ln=True)
                    pdf.set_font("Arial", "", 12)
                    pdf.multi_cell(0, 8, f"Symptoms: {symptoms}\nRx: {medicines}\nAdvice: {advice}")
                    pdf_bytes = bytes(pdf.output(dest='S'))
                    
                    # WhatsApp Generation
                    whatsapp_msg = f"🏥 *{st.session_state.clinic_id} PRESCRIPTION*\n👤 *Patient:* {selected_patient_name}\n🩺 *Symptoms:* {symptoms}\n💊 *Medicines:*\n{medicines}\n📝 *Advice:* {advice}"
                    encoded_msg = urllib.parse.quote(whatsapp_msg)
                    clean_phone = ''.join(filter(str.isdigit, selected_patient_phone))
                    if len(clean_phone) == 10: clean_phone = "91" + clean_phone
                    wa_web_url = f"https://api.whatsapp.com/send/?phone={clean_phone}&text={encoded_msg}"
                    
                    # Remove patient from queue after treating
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
