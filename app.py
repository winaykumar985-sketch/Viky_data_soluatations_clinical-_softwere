import streamlit as st
import psycopg2
import pandas as pd
from fpdf import FPDF
import urllib.parse

# 🌐 CLOUD DATABASE CONNECTION
DB_URL = "postgresql://vinay:gsfY9fktXwqWFaCWQZxbBA@brassy-rugrat-16274.jxf.gcp-asia-south1.cockroachlabs.cloud:26257/defaultdb?sslmode=require"

# --- 1. DATABASE SETUP ---
def init_db():
    conn = psycopg2.connect(DB_URL)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS Clinics (clinic_id TEXT PRIMARY KEY, clinic_name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS Users (username TEXT PRIMARY KEY, password TEXT, role TEXT, clinic_id TEXT)''')
    # PostgreSQL uses SERIAL for auto-incrementing IDs
    c.execute('''CREATE TABLE IF NOT EXISTS Patients (patient_id SERIAL PRIMARY KEY, name TEXT, phone TEXT, clinic_id TEXT)''')
    
    c.execute("SELECT COUNT(*) FROM Clinics")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO Clinics (clinic_id, clinic_name) VALUES ('CLINIC_001', 'Demo Clinic')")
        c.execute("INSERT INTO Users (username, password, role, clinic_id) VALUES ('admin', '123', 'Admin', 'CLINIC_001')")
        c.execute("INSERT INTO Users (username, password, role, clinic_id) VALUES ('doc', '123', 'Doctor', 'CLINIC_001')")
        c.execute("INSERT INTO Users (username, password, role, clinic_id) VALUES ('rec', '123', 'Receptionist', 'CLINIC_001')")
        conn.commit()
    conn.close()

init_db()

# --- 2. APP STATE ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.role = ""
    st.session_state.clinic_id = ""

# --- 3. SAAS LOGIN SCREEN ---
if not st.session_state.logged_in:
    st.title("🏥 MediSaaS - Login")
    st.write("Test Accounts (Password is 123): `admin` | `doc` | `rec`")
    
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    
    if st.button("Login"):
        conn = psycopg2.connect(DB_URL)
        c = conn.cursor()
        # PostgreSQL uses %s instead of ? for variables
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

# --- 4. SECURE CLINIC WORKSPACE ---
else:
    st.sidebar.title(f"🏢 Clinic ID: {st.session_state.clinic_id}")
    st.sidebar.write(f"👤 User: {st.session_state.username} ({st.session_state.role})")
    
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()
    
    # --- RECEPTIONIST VIEW ---
    if st.session_state.role == "Receptionist":
        st.header("📝 Register New Patient")
        with st.form("new_patient", clear_on_submit=True):
            p_name = st.text_input("Patient Name")
            p_phone = st.text_input("Phone Number (Include country code without +, e.g., 91XXXXXXXXXX)")
            if st.form_submit_button("Add Patient to Queue"):
                conn = psycopg2.connect(DB_URL)
                c = conn.cursor()
                c.execute("INSERT INTO Patients (name, phone, clinic_id) VALUES (%s, %s, %s)", 
                          (p_name, p_phone, st.session_state.clinic_id))
                conn.commit()
                conn.close()
                st.success(f"{p_name} registered successfully!")

    # --- UPGRADED DOCTOR VIEW WITH WHATSAPP LINK ---
    elif st.session_state.role == "Doctor":
        st.header("🩺 Doctor's Consultation Desk")
        
        conn = psycopg2.connect(DB_URL)
        c = conn.cursor()
        c.execute("SELECT patient_id, name, phone FROM Patients WHERE clinic_id=%s", (st.session_state.clinic_id,))
        rows = c.fetchall()
        columns = [desc[0] for desc in c.description] if c.description else []
        df = pd.DataFrame(rows, columns=columns)
        conn.close()
        
        if df.empty:
            st.info("No patients in the queue right now.")
        else:
            patient_options = {f"ID: {row['patient_id']} - {row['name']}": (row['patient_id'], row['name'], row['phone']) for _, row in df.iterrows()}
            selected_patient_str = st.selectbox("Select Patient to Treat", list(patient_options.keys()))
            
            selected_patient_id, selected_patient_name, selected_patient_phone = patient_options[selected_patient_str]
            
            st.markdown("---")
            st.subheader(f"✍ *Prescription Pad for {selected_patient_name}*")
            
            symptoms = st.text_area("Symptoms / Diagnosis")
            medicines = st.text_area("Medicines (e.g., Paracetamol 650mg - 1-0-1 - 5 Days)")
            advice = st.text_input("General Advice / Follow-up Instructions")
            
            if st.button("Generate Rx & Complete Visit"):
                if not symptoms or not medicines:
                    st.error("Please fill in Symptoms and Medicines before generating.")
                else:
                    pdf = FPDF()
                    pdf.add_page()
                    pdf.set_font("Arial", "B", 20)
                    pdf.cell(0, 10, "MEDISAAS DIGITAL PRESCRIPTION", ln=True, align="C")
                    pdf.set_font("Arial", "", 12)
                    pdf.cell(0, 10, f"Clinic Workspace: {st.session_state.clinic_id}", ln=True, align="C")
                    pdf.line(10, 30, 200, 30)
                    pdf.ln(15)
                    
                    pdf.set_font("Arial", "B", 12)
                    pdf.cell(0, 10, f"Patient Name: {selected_patient_name} (ID: {selected_patient_id})", ln=True)
                    pdf.line(10, 48, 200, 48)
                    pdf.ln(5)
                    
                    pdf.set_font("Arial", "B", 12)
                    pdf.cell(0, 10, "Symptoms & Diagnosis:", ln=True)
                    pdf.set_font("Arial", "", 12)
                    pdf.multi_cell(0, 8, symptoms)
                    pdf.ln(5)
                    
                    pdf.set_font("Arial", "B", 12)
                    pdf.cell(0, 10, "Rx (Medicines):", ln=True)
                    pdf.set_font("Arial", "", 12)
                    pdf.multi_cell(0, 8, medicines)
                    pdf.ln(5)
                    
                    if advice:
                        pdf.set_font("Arial", "B", 12)
                        pdf.cell(0, 10, "Advice:", ln=True)
                        pdf.set_font("Arial", "", 12)
                        pdf.multi_cell(0, 8, advice)
                    
                    pdf_bytes = bytes(pdf.output(dest='S'))
                    
                    whatsapp_msg = (
                        f"🏥 *{st.session_state.clinic_id} PRESCRIPTION*\n\n"
                        f"👤 *Patient:* {selected_patient_name}\n"
                        f"🩺 *Symptoms:* {symptoms}\n"
                        f"💊 *Medicines:*\n{medicines}\n\n"
                        f"📝 *Advice:* {advice if advice else 'Take rest.'}\n\n"
                        f"Thank you! Get well soon."
                    )
                    encoded_msg = urllib.parse.quote(whatsapp_msg)
                    
                    clean_phone = ''.join(filter(str.isdigit, selected_patient_phone))
                    if len(clean_phone) == 10:
                        clean_phone = "91" + clean_phone
                        
                    wa_web_url = f"https://api.whatsapp.com/send/?phone={clean_phone}&text={encoded_msg}"
                    
                    conn = psycopg2.connect(DB_URL)
                    c = conn.cursor()
                    c.execute("DELETE FROM Patients WHERE patient_id=%s", (selected_patient_id,))
                    conn.commit()
                    conn.close()
                    
                    st.success("🎉 Treatment completed successfully!")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.download_button(
                            label="📥 Download Prescription PDF",
                            data=pdf_bytes,
                            file_name=f"Rx_Patient_{selected_patient_id}.pdf",
                            mime="application/pdf",
                            use_container_width=True
                        )
                    with col2:
                        st.link_button(
                            label="💬 Open Patient WhatsApp Chat",
                            url=wa_web_url,
                            use_container_width=True
                        )

    # --- ADMIN VIEW ---
    elif st.session_state.role == "Admin":
        st.header("⚙ Clinic Settings")
        st.write("Manage staff and view total clinic revenue here. (Feature coming soon)")
