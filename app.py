import streamlit as st
import pandas as pd
import os
from datetime import datetime, date, timedelta
import bcrypt
import plotly.express as px
import plotly.graph_objects as go
import warnings
import time
import json
import streamlit.components.v1 as components
import psycopg2
from psycopg2.extras import RealDictCursor
import plotly.io as pio
import sqlalchemy
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from supabase import create_client, Client
import requests
from PIL import Image
import io

# Suppress warnings
warnings.filterwarnings("ignore", message="The behavior of DatetimeProperties.to_pydatetime is deprecated")
warnings.filterwarnings('ignore', message='pandas only supports SQLAlchemy connectable')

# -----------------------------------------------------------------------------
# 📄 PAGE SETTINGS
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Sustainability Data Portal",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="auto"
)


# -----------------------------------------------------------------------------
# 🛠️ SESSION MANAGEMENT
# -----------------------------------------------------------------------------
SESSION_TIMEOUT = 3600  # 1 hour

def init_session_state():
    defaults = {
        "authentication_status": None,
        "username": None,
        "name": None,
        "role": None,
        "login_time": None,
        "last_activity": None,
        "mess_form_data": {},
        "waste_form_data": {},
        "session_token": None,
        "persistent_auth": None,
        "persistent_username": None,
        "persistent_name": None,
        "persistent_role": None,
        "edit_record": None,
        "edit_key": None,
        "verify_record": None,
        "verify_key": None,
        "show_waste_details": None,
        "waste_details_key": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

def preserve_session_state():
    if "persistent_auth" in st.session_state and st.session_state.persistent_auth:
        st.session_state.authentication_status = st.session_state.persistent_auth
    if "persistent_username" in st.session_state and st.session_state.persistent_username:
        st.session_state.username = st.session_state.persistent_username
    if "persistent_name" in st.session_state and st.session_state.persistent_name:
        st.session_state.name = st.session_state.persistent_name
    if "persistent_role" in st.session_state and st.session_state.persistent_role:
        st.session_state.role = st.session_state.persistent_role

def generate_session_token():
    import secrets
    return secrets.token_urlsafe(32)

def is_session_active():
    if st.session_state.get('last_activity') is None:
        return False
    return (time.time() - st.session_state['last_activity']) < SESSION_TIMEOUT

def update_activity_time():
    st.session_state['last_activity'] = time.time()

def check_session_validity():
    preserve_session_state()
    if st.session_state.get('authentication_status'):
        if st.session_state.get('last_activity') is None:
            update_activity_time()
        elif not is_session_active():
            clear_session_state()
            st.warning("⏰ Session expired. Please login again.")
            st.rerun()
        else:
            update_activity_time()

def clear_session_state():
    keys_to_clear = [
        "authentication_status", "username", "name", "role", "login_time",
        "last_activity", "session_token", "persistent_auth", "persistent_username",
        "persistent_name", "persistent_role"
    ]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]

def save_form_data(form_key, data):
    st.session_state[form_key] = data

def load_form_data(form_key, default=None):
    if form_key in st.session_state:
        return st.session_state[form_key]
    return default if default is not None else {}

def clear_form_data(form_key):
    if form_key in st.session_state:
        del st.session_state[form_key]


# -----------------------------------------------------------------------------
# 🏨 DYNAMIC HOSTEL LIST (NEW)
# -----------------------------------------------------------------------------
def get_dynamic_hostels():
    """Fetch all unique hostels from PHO and pho_supervisor users."""
    users = get_all_users()
    hostels = set()
    for u in users:
        if u['role'] in ['pho_supervisor']:
            hostel = get_hostel_from_username(u['username'])
            if hostel:
                hostels.add(hostel)
    return sorted(list(hostels)) if hostels else ["2", "10", "12-13-14", "11", "18"]

# -----------------------------------------------------------------------------
# 🗄️ DATABASE CONNECTION AND SETUP
# -----------------------------------------------------------------------------
def get_db_connection():
    """Get database connection using environment variables"""
    try:
        # Fallback to Streamlit secrets (Streamlit Cloud)
        if hasattr(st, 'secrets') and 'connections' in st.secrets:
            conn = psycopg2.connect(
                host=st.secrets.connections.postgresql.host,
                database=st.secrets.connections.postgresql.database,
                user=st.secrets.connections.postgresql.username,
                password=st.secrets.connections.postgresql.password,
                port=st.secrets.connections.postgresql.port
            )
        else:
            st.error("No database configuration found!")
            return None
        return conn
    except Exception as e:
        st.error(f"Database connection failed: {e}")
        return None

def get_sqlalchemy_engine():
    """Get SQLAlchemy engine for pandas operations using URL.create()"""
    try:
        from sqlalchemy.engine import URL
        
        if hasattr(st, 'secrets') and 'connections' in st.secrets:
            url = URL.create(
                drivername="postgresql",
                username=st.secrets.connections.postgresql.username,
                password=st.secrets.connections.postgresql.password,
                host=st.secrets.connections.postgresql.host,
                port=int(st.secrets.connections.postgresql.port),
                database=st.secrets.connections.postgresql.database
            )
        else:
            return None
        
        engine = create_engine(url)
        return engine
    except Exception as e:
        st.error(f"SQLAlchemy engine creation failed: {e}")
        return None

    

def get_supabase_client():
    """Get Supabase client for storage operations"""
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets.get["SUPABASE_ANON_KEY"]
        
        if not url or not key:
            st.error("Supabase credentials not found!")
            return None
            
        return create_client(url, key)
    except Exception as e:
        st.error(f"Supabase client creation failed: {e}")
        return None


def get_hostel_from_username(username: str) -> str:
    """Extract hostel from waste collector username"""
    if username.startswith("pho_supervisor_"):
        hostel_part = username.replace("pho_supervisor_", "")
        return hostel_part.replace("_", "-")
    return ""

def create_tables():
    """Create all necessary tables with proper connection handling"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        
        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                name VARCHAR(100) NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(20) NOT NULL CHECK (role IN ('admin', 'pho_supervisor', 'pho')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Mess waste submissions
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mess_waste_submissions (
                id SERIAL PRIMARY KEY,
                submission_id VARCHAR(100) UNIQUE NOT NULL,
                submission_date DATE NOT NULL,
                hostel VARCHAR(20) NOT NULL,
                breakfast_students INTEGER DEFAULT 0,
                breakfast_student_waste DECIMAL(10,2) DEFAULT 0,
                breakfast_counter_waste DECIMAL(10,2) DEFAULT 0,
                breakfast_vegetable_peels DECIMAL(10,2) DEFAULT 0,
                lunch_students INTEGER DEFAULT 0,
                lunch_student_waste DECIMAL(10,2) DEFAULT 0,
                lunch_counter_waste DECIMAL(10,2) DEFAULT 0,
                lunch_vegetable_peels DECIMAL(10,2) DEFAULT 0,
                snacks_students INTEGER DEFAULT 0,
                snacks_student_waste DECIMAL(10,2) DEFAULT 0,
                snacks_counter_waste DECIMAL(10,2) DEFAULT 0,
                snacks_vegetable_peels DECIMAL(10,2) DEFAULT 0,
                dinner_students INTEGER DEFAULT 0,
                dinner_student_waste DECIMAL(10,2) DEFAULT 0,
                dinner_counter_waste DECIMAL(10,2) DEFAULT 0,
                dinner_vegetable_peels DECIMAL(10,2) DEFAULT 0,
                mess_dry_waste DECIMAL(10,2) DEFAULT 0,
                total_students INTEGER DEFAULT 0,
                total_mess_waste DECIMAL(10,2) DEFAULT 0,
                remarks TEXT,
                image_paths TEXT,
                submitted_by VARCHAR(50) NOT NULL,
                submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'verified', 'rejected')),
                verified_by VARCHAR(50),
                verified_at TIMESTAMP
            )
        """)
        
        # Hostel waste submissions
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hostel_waste_submissions (
                id SERIAL PRIMARY KEY,
                submission_id VARCHAR(100) UNIQUE NOT NULL,
                submission_date DATE NOT NULL,
                hostel VARCHAR(20) NOT NULL,
                dry_waste DECIMAL(10,2) DEFAULT 0,
                wet_waste DECIMAL(10,2) DEFAULT 0,
                e_waste DECIMAL(10,2) DEFAULT 0,
                biomedical_waste DECIMAL(10,2) DEFAULT 0,
                hazardous_waste DECIMAL(10,2) DEFAULT 0,
                total_waste DECIMAL(10,2) DEFAULT 0,
                remarks TEXT,
                image_paths TEXT,
                submitted_by VARCHAR(50) NOT NULL,
                submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'verified', 'rejected')),
                verified_by VARCHAR(50),
                verified_at TIMESTAMP
            )
        """)
        
        # Master aggregated data with detailed mess waste categories
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS master_waste_data (
                id SERIAL PRIMARY KEY,
                date DATE NOT NULL,
                hostel VARCHAR(20) NOT NULL,
                total_students INTEGER DEFAULT 0,
                breakfast_student_waste DECIMAL(10,2) DEFAULT 0,
                breakfast_counter_waste DECIMAL(10,2) DEFAULT 0,
                breakfast_vegetable_peels DECIMAL(10,2) DEFAULT 0,
                lunch_student_waste DECIMAL(10,2) DEFAULT 0,
                lunch_counter_waste DECIMAL(10,2) DEFAULT 0,
                lunch_vegetable_peels DECIMAL(10,2) DEFAULT 0,
                snacks_student_waste DECIMAL(10,2) DEFAULT 0,
                snacks_counter_waste DECIMAL(10,2) DEFAULT 0,
                snacks_vegetable_peels DECIMAL(10,2) DEFAULT 0,
                dinner_student_waste DECIMAL(10,2) DEFAULT 0,
                dinner_counter_waste DECIMAL(10,2) DEFAULT 0,
                dinner_vegetable_peels DECIMAL(10,2) DEFAULT 0,
                total_mess_waste DECIMAL(10,2) DEFAULT 0,
                total_mess_waste_no_peels DECIMAL(10,2) DEFAULT 0,
                per_capita_mess_waste DECIMAL(10,4) DEFAULT 0,
                per_capita_mess_waste_no_peels DECIMAL(10,4) DEFAULT 0,
                mess_dry_waste DECIMAL(10,2) DEFAULT 0,
                total_hostel_waste DECIMAL(10,2) DEFAULT 0,
                dry_waste DECIMAL(10,2) DEFAULT 0,
                wet_waste DECIMAL(10,2) DEFAULT 0,
                e_waste DECIMAL(10,2) DEFAULT 0,
                biomedical_waste DECIMAL(10,2) DEFAULT 0,
                hazardous_waste DECIMAL(10,2) DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, hostel)
            )
        """)
        
        # Images table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS submission_images (
                id SERIAL PRIMARY KEY,
                submission_id VARCHAR(100) NOT NULL,
                submission_type VARCHAR(20) NOT NULL CHECK (submission_type IN ('mess_waste', 'hostel_waste')),
                image_filename VARCHAR(255) NOT NULL,
                image_path VARCHAR(500) NOT NULL,
                file_size INTEGER,
                upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # PHO edits tracking table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pho_edits (
                id SERIAL PRIMARY KEY,
                submission_id VARCHAR(100) NOT NULL,
                submission_type VARCHAR(20) NOT NULL CHECK (submission_type IN ('mess_waste', 'hostel_waste')),
                original_data JSONB NOT NULL,
                edited_data JSONB NOT NULL,
                edited_by VARCHAR(50) NOT NULL,
                edited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                edit_reason TEXT
            )
        """)
        
        conn.commit()
        return True
        
    except Exception as e:
        st.error(f"Error creating tables: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def upload_image_to_supabase(file, bucket_name, file_name):
    """Upload image to Supabase storage"""
    try:
        supabase = get_supabase_client()
        if not supabase:
            return None
        
        # Upload file
        result = supabase.storage.from_(bucket_name).upload(
            file_name, 
            file.getvalue(),
            file_options={"content-type": file.type}
        )
        
        if hasattr(result, 'error') and result.error:
            st.error(f"Upload failed: {result.error}")
            return None
        
        # Get public URL
        public_url = supabase.storage.from_(bucket_name).get_public_url(file_name)
        return public_url
        
    except Exception as e:
        st.error(f"Error uploading image: {e}")
        return None

def display_image_from_supabase(image_url):
    """Display image from Supabase storage"""
    try:
        if image_url and image_url.strip():
            # Download image from URL
            response = requests.get(image_url)
            if response.status_code == 200:
                image = Image.open(io.BytesIO(response.content))
                st.image(image, caption="Uploaded Image", use_column_width=True)
            else:
                st.warning("Could not load image")
    except Exception as e:
        st.warning(f"Error displaying image: {e}")

def display_submission_images(submission_id, submission_type):
    """Display images for a submission from Supabase storage"""
    conn = get_db_connection()
    if not conn:
        return
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT image_url, image_filename 
            FROM submission_images 
            WHERE submission_id = %s AND submission_type = %s
        """, (submission_id, submission_type))
        
        images = cursor.fetchall()
        
        if images:
            st.write("**📸 Uploaded Images:**")
            cols = st.columns(min(len(images), 3))
            
            for idx, (image_url, filename) in enumerate(images):
                with cols[idx % 3]:
                    display_image_from_supabase(image_url)
                    st.caption(filename)
        
    except Exception as e:
        st.warning(f"Error loading images: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()



def handle_image_uploads(uploaded_files, username, form_type):
    """Handle image uploads to Supabase storage"""
    if not uploaded_files:
        return ""
    
    image_urls = []
    bucket_name = "mess-images" if form_type == "mess" else "hostel-images"
    
    for idx, file in enumerate(uploaded_files):
        # Generate unique filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_extension = file.name.split('.')[-1] if '.' in file.name else 'jpg'
        file_name = f"{username}_{timestamp}_{idx}.{file_extension}"
        
        # Upload to Supabase
        url = upload_image_to_supabase(file, bucket_name, file_name)
        
        if url:
            image_urls.append(url)
            st.success(f"✅ Uploaded: {file.name}")
        else:
            st.error(f"❌ Failed to upload: {file.name}")
    
    return ','.join(image_urls)

def save_mess_waste_data_with_images(username: str, data: dict, uploaded_files):
    """Save mess waste data with Supabase image uploads"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        
        # Handle image uploads
        image_urls = handle_image_uploads(uploaded_files, username, "mess")
        
        # Generate submission ID
        submission_id = f"MESS_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{username}"
        
        # Insert mess waste submission
        cursor.execute("""
            INSERT INTO mess_waste_submissions (
                hostel, submission_date, collection_time,
                breakfast_students, breakfast_student_waste, breakfast_counter_waste, breakfast_vegetable_peels,
                lunch_students, lunch_student_waste, lunch_counter_waste, lunch_vegetable_peels,
                snacks_students, snacks_student_waste, snacks_counter_waste, snacks_vegetable_peels,
                dinner_students, dinner_student_waste, dinner_counter_waste, dinner_vegetable_peels,
                mess_dry_waste, total_students, total_mess_waste,
                remarks, status, submitted_by, submitted_at
            ) VALUES (
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s
            ) RETURNING submission_id
        """, (
            data['hostel'], data['submission_date'], data['collection_time'],
            data['breakfast_students'], data['breakfast_student_waste'], data['breakfast_counter_waste'], data['breakfast_vegetable_peels'],
            data['lunch_students'], data['lunch_student_waste'], data['lunch_counter_waste'], data['lunch_vegetable_peels'],
            data['snacks_students'], data['snacks_student_waste'], data['snacks_counter_waste'], data['snacks_vegetable_peels'],
            data['dinner_students'], data['dinner_student_waste'], data['dinner_counter_waste'], data['dinner_vegetable_peels'],
            data['mess_dry_waste'], data['total_students'], data['total_mess_waste'],
            data.get('remarks', ''), 'pending', username, datetime.now()
        ))
        
        submission_id = cursor.fetchone()[0]
        
        # Save image URLs to submission_images table if any images were uploaded
        if image_urls:
            for url in image_urls.split(','):
                if url.strip():
                    cursor.execute("""
                        INSERT INTO submission_images (submission_type, submission_id, image_url, image_filename)
                        VALUES (%s, %s, %s, %s)
                    """, ('mess_waste', submission_id, url.strip(), url.split('/')[-1]))
        
        conn.commit()
        return True
        
    except Exception as e:
        st.error(f"Error saving mess waste data: {e}")
        conn.rollback()
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def save_hostel_waste_data_with_images(username: str, data: dict, uploaded_files):
    """Save hostel waste data with Supabase image uploads"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        
        # Handle image uploads
        image_urls = handle_image_uploads(uploaded_files, username, "hostel")
        
        # Generate submission ID
        submission_id = f"HOSTEL_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{username}"
        
        # Insert hostel waste submission
        cursor.execute("""
            INSERT INTO hostel_waste_submissions (
                hostel, submission_date, collection_time,
                dry_waste, wet_waste, e_waste, biomedical_waste, hazardous_waste,
                remarks, status, submitted_by, submitted_at
            ) VALUES (
                %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s
            ) RETURNING submission_id
        """, (
            data['hostel'], data['submission_date'], data['collection_time'],
            data['dry_waste'], data['wet_waste'], data['e_waste'], data['biomedical_waste'], data['hazardous_waste'],
            data.get('remarks', ''), 'pending', username, datetime.now()
        ))
        
        submission_id = cursor.fetchone()[0]
        
        # Save image URLs to submission_images table if any images were uploaded
        if image_urls:
            for url in image_urls.split(','):
                if url.strip():
                    cursor.execute("""
                        INSERT INTO submission_images (submission_type, submission_id, image_url, image_filename)
                        VALUES (%s, %s, %s, %s)
                    """, ('hostel_waste', submission_id, url.strip(), url.split('/')[-1]))
        
        conn.commit()
        return True
        
    except Exception as e:
        st.error(f"Error saving hostel waste data: {e}")
        conn.rollback()
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def create_default_admin():
    """Create default admin user if not exists"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        
        # Check if admin exists
        cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
        count = cursor.fetchone()[0]
        
        if count == 0:
            # Create admin user
            admin_password = bcrypt.hashpw("admin123".encode(), bcrypt.gensalt()).decode()
            cursor.execute("""
                INSERT INTO users (username, name, password_hash, role) 
                VALUES (%s, %s, %s, %s)
            """, ("admin", "Administrator", admin_password, "admin"))
            conn.commit()
            
        return True
        
    except Exception as e:
        st.error(f"Error creating admin user: {e}")
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def show_edit_comparison(edit_record):
    """Show side-by-side comparison of original vs edited data"""
    try:
        # Parse JSON data
        original = json.loads(edit_record['original_data'])
        edited = json.loads(edit_record['edited_data'])
        
        # Create expandable section for each edit
        with st.expander(f"📝 Edit by {edit_record['edited_by']} on {edit_record['edited_at']}", expanded=False):
            # Show edit reason if provided
            if edit_record.get('reason'):
                st.info(f"**Reason:** {edit_record['reason']}")
            
            # Side-by-side comparison
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("### 📋 Original Data")
                st.markdown("---")
                for key, value in original.items():
                    # Format the key for better display
                    display_key = key.replace('_', ' ').title()
                    if isinstance(value, (int, float)):
                        st.write(f"**{display_key}:** {value}")
                    else:
                        st.write(f"**{display_key}:** {value}")
            
            with col2:
                st.markdown("### ✏️ Edited Data")
                st.markdown("---")
                for key, value in edited.items():
                    display_key = key.replace('_', ' ').title()
                    original_value = original.get(key)
                    
                    # Highlight changes
                    if value != original_value:
                        if isinstance(value, (int, float)) and isinstance(original_value, (int, float)):
                            diff = value - original_value
                            diff_text = f" ({diff:+.2f})" if diff != 0 else ""
                            st.write(f"**{display_key}:** {value}{diff_text} ⚠️ **CHANGED**")
                        else:
                            st.write(f"**{display_key}:** {value} ⚠️ **CHANGED**")
                    else:
                        st.write(f"**{display_key}:** {value}")
            
            # Summary of changes
            changes = []
            for key, value in edited.items():
                if value != original.get(key):
                    changes.append(key.replace('_', ' ').title())
            
            if changes:
                st.markdown("---")
                st.warning(f"**Fields Modified:** {', '.join(changes)}")
            else:
                st.success("**No changes detected**")
                
    except Exception as e:
        st.error(f"Error displaying edit comparison: {e}")

def get_pho_edits_data():
    """Get all PHO edits with submission details"""
    conn = get_db_connection()
    if not conn:
        return pd.DataFrame()
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get edits with submission details
        cursor.execute("""
            SELECT 
                pe.edit_id,
                pe.submission_type,
                pe.submission_id,
                pe.original_data,
                pe.edited_data,
                pe.edited_by,
                pe.edited_at,
                pe.reason,
                CASE 
                    WHEN pe.submission_type = 'mess_waste' THEN mws.hostel
                    WHEN pe.submission_type = 'hostel_waste' THEN hws.hostel
                END as hostel,
                CASE 
                    WHEN pe.submission_type = 'mess_waste' THEN mws.submission_date
                    WHEN pe.submission_type = 'hostel_waste' THEN hws.submission_date
                END as submission_date
            FROM pho_edits pe
            LEFT JOIN mess_waste_submissions mws ON pe.submission_type = 'mess_waste' AND pe.submission_id = mws.submission_id
            LEFT JOIN hostel_waste_submissions hws ON pe.submission_type = 'hostel_waste' AND pe.submission_id = hws.submission_id
            ORDER BY pe.edited_at DESC
        """)
        
        edits = cursor.fetchall()
        return pd.DataFrame([dict(edit) for edit in edits])
        
    except Exception as e:
        st.error(f"Error loading PHO edits: {e}")
        return pd.DataFrame()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# -----------------------------------------------------------------------------
# 🔐 AUTHENTICATION
# -----------------------------------------------------------------------------
def verify_password(username: str, password: str) -> bool:
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT password_hash FROM users WHERE username = %s", (username,))
        result = cursor.fetchone()
        
        if result:
            stored_password = result[0]
            return bcrypt.checkpw(password.encode(), stored_password.encode())
        return False
        
    except Exception as e:
        st.error(f"Authentication error: {e}")
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def get_user_role(username: str) -> str:
    conn = get_db_connection()
    if not conn:
        return ""
    
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT role FROM users WHERE username = %s", (username,))
        result = cursor.fetchone()
        return result[0] if result else ""
        
    except Exception as e:
        st.error(f"Error getting user role: {e}")
        return ""
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def get_user_name(username: str) -> str:
    conn = get_db_connection()
    if not conn:
        return ""
    
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM users WHERE username = %s", (username,))
        result = cursor.fetchone()
        return result[0] if result else ""
        
    except Exception as e:
        st.error(f"Error getting user name: {e}")
        return ""
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# -----------------------------------------------------------------------------
# 👥 USER MANAGEMENT FUNCTIONS
# -----------------------------------------------------------------------------
def add_user(username, name, password, role):
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        hashed_password = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        
        cursor.execute("""
            INSERT INTO users (username, name, password_hash, role) 
            VALUES (%s, %s, %s, %s)
        """, (username, name, hashed_password, role))
        
        conn.commit()
        return True
        
    except Exception as e:
        st.error(f"Error adding user: {e}")
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def delete_user(username):
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE username = %s", (username,))
        conn.commit()
        return True
        
    except Exception as e:
        st.error(f"Error deleting user: {e}")
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def get_all_users():
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT username, name, role FROM users ORDER BY username")
        users = cursor.fetchall()
        return [dict(user) for user in users]
        
    except Exception as e:
        st.error(f"Error getting users: {e}")
        return []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# -----------------------------------------------------------------------------
# 📦 DATA HELPERS
# -----------------------------------------------------------------------------
def ensure_data_structure():
    """Ensure database tables exist"""
    # Create database tables
    if not create_tables():
        return False
    # Create default admin user
    if not create_default_admin():
        return False
    return True



def save_mess_waste_data(username: str, data: dict):
    """Save mess waste data to PostgreSQL database"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        submission_id = str(int(time.time()))
        
        cursor.execute("""
            INSERT INTO mess_waste_submissions 
            (submission_id, submission_date, hostel, breakfast_students, breakfast_student_waste, 
             breakfast_counter_waste, breakfast_vegetable_peels, lunch_students, lunch_student_waste, 
             lunch_counter_waste, lunch_vegetable_peels, snacks_students, snacks_student_waste, 
             snacks_counter_waste, snacks_vegetable_peels, dinner_students, dinner_student_waste, 
             dinner_counter_waste, dinner_vegetable_peels, mess_dry_waste, total_students, 
             total_mess_waste, remarks, image_paths, submitted_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            submission_id, data['submission_date'], data['hostel'],
            data['breakfast_students'], data['breakfast_student_waste'], 
            data['breakfast_counter_waste'], data['breakfast_vegetable_peels'],
            data['lunch_students'], data['lunch_student_waste'], 
            data['lunch_counter_waste'], data['lunch_vegetable_peels'],
            data['snacks_students'], data['snacks_student_waste'], 
            data['snacks_counter_waste'], data['snacks_vegetable_peels'],
            data['dinner_students'], data['dinner_student_waste'], 
            data['dinner_counter_waste'], data['dinner_vegetable_peels'],
            data['mess_dry_waste'], data['total_students'], data['total_mess_waste'],
            data['remarks'], data.get('image_paths', ''), username
        ))
        
        conn.commit()
        return True
        
    except Exception as e:
        st.error(f"Database error: {e}")
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def save_hostel_waste_data(username: str, data: dict):
    """Save hostel waste data to PostgreSQL database"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        submission_id = str(int(time.time()))
        
        cursor.execute("""
            INSERT INTO hostel_waste_submissions 
            (submission_id, submission_date, hostel, dry_waste, wet_waste, e_waste, 
             biomedical_waste, hazardous_waste, total_waste, remarks, image_paths, submitted_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            submission_id, data['submission_date'], data['hostel'],
            data['dry_waste'], data['wet_waste'], data['e_waste'],
            data['biomedical_waste'], data['hazardous_waste'], data['total_waste'],
            data['remarks'], data.get('image_paths', ''), username
        ))
        
        conn.commit()
        return True
        
    except Exception as e:
        st.error(f"Database error: {e}")
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@st.cache_data(ttl=300)
def load_master_data():
    """Load ALL master waste data without limits"""
    engine = get_sqlalchemy_engine()
    if not engine:
        return pd.DataFrame()
    
    try:
        # Load ALL master data (remove any LIMIT clauses)
        query = """
            SELECT * FROM master_waste_data 
            ORDER BY date DESC, hostel
        """
        df = pd.read_sql(query, engine)
        return df
    except Exception as e:
        st.error(f"Error loading master data: {e}")
        return pd.DataFrame()
    finally:
        engine.dispose()


@st.cache_data(ttl=300)
def load_pending_data_for_pho():
    """Load ONLY pending data for PHO verification"""
    conn = get_db_connection()
    if not conn:
        return {}
    
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Load ONLY pending mess waste
        cursor.execute("""
            SELECT * FROM mess_waste_submissions 
            WHERE status = 'pending' 
            ORDER BY submission_date DESC, hostel
        """)
        mess_pending = cursor.fetchall()
        
        # Load ONLY pending hostel waste
        cursor.execute("""
            SELECT * FROM hostel_waste_submissions 
            WHERE status = 'pending' 
            ORDER BY submission_date DESC, hostel
        """)
        hostel_pending = cursor.fetchall()
        
        # Group by hostel and date
        data_by_hostel_date = {}
        
        # Process only pending mess waste
        for record in mess_pending:
            if record['status'] == 'pending':  # Double-check
                date_str = str(record['submission_date'])
                key = f"{record['hostel']}_{date_str}_mess_waste"
                if key not in data_by_hostel_date:
                    data_by_hostel_date[key] = []
                record_dict = dict(record)
                record_dict['data_type'] = 'mess_waste'
                data_by_hostel_date[key].append(record_dict)
        
        # Process only pending hostel waste
        for record in hostel_pending:
            if record['status'] == 'pending':  # Double-check
                date_str = str(record['submission_date'])
                key = f"{record['hostel']}_{date_str}_hostel_waste"
                if key not in data_by_hostel_date:
                    data_by_hostel_date[key] = []
                record_dict = dict(record)
                record_dict['data_type'] = 'hostel_waste'
                data_by_hostel_date[key].append(record_dict)
        
        return data_by_hostel_date
        
    except Exception as e:
        st.error(f"Error loading pending data: {e}")
        return {}
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()



def aggregate_hostel_waste_collections(records):
    """Aggregate multiple hostel waste collections into totals"""
    if not records:
        return {}
    
    totals = {
        'dry_waste': 0,
        'wet_waste': 0,
        'e_waste': 0,
        'biomedical_waste': 0,
        'hazardous_waste': 0,
        'total_waste': 0,
        'collection_count': len(records),
        'submitted_by': records[0].get('submitted_by', 'N/A'),
        'submitted_at': records[0].get('submitted_at', 'N/A'),
        'hostel': records[0].get('hostel', 'N/A'),
        'submission_date': records[0].get('submission_date', 'N/A')
    }
    
    for record in records:
        totals['dry_waste'] += float(record.get('dry_waste', 0))
        totals['wet_waste'] += float(record.get('wet_waste', 0))
        totals['e_waste'] += float(record.get('e_waste', 0))
        totals['biomedical_waste'] += float(record.get('biomedical_waste', 0))
        totals['hazardous_waste'] += float(record.get('hazardous_waste', 0))
        totals['total_waste'] += float(record.get('total_waste', 0))
    
    return totals

def save_pho_edit(submission_id, submission_type, original_data, edited_data, pho_username, edit_reason=""):
    """Save PHO edit to tracking table"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO pho_edits 
            (submission_id, submission_type, original_data, edited_data, edited_by, edit_reason)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            submission_id, submission_type, 
            json.dumps(original_data), json.dumps(edited_data), 
            pho_username, edit_reason
        ))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error saving PHO edit: {e}")
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def approve_submission(record_data, pho_username):
    """Approve submission and move to verified status"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        timestamp = datetime.now()
        
        if 'breakfast_students' in record_data:
            # Update mess waste submission
            cursor.execute("""
                UPDATE mess_waste_submissions 
                SET status = 'verified', verified_by = %s, verified_at = %s
                WHERE submission_id = %s
            """, (pho_username, timestamp, record_data['submission_id']))
            
            # Add to master data
            add_to_master_file_mess(record_data)
            
        else:
            # Update hostel waste submission
            cursor.execute("""
                UPDATE hostel_waste_submissions 
                SET status = 'verified', verified_by = %s, verified_at = %s
                WHERE submission_id = %s
            """, (pho_username, timestamp, record_data['submission_id']))
            
            # Add to master data
            add_to_master_file_hostel(record_data)
        
        conn.commit()
        
        # Clear cache
        load_pending_data_for_pho.clear()
        load_master_data.clear()
        
        return True
        
    except Exception as e:
        st.error(f"Error approving submission: {e}")
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def approve_all_collections(records, pho_username):
    """Approve all collections for a hostel-date combination"""
    for record in records:
        approve_submission(record, pho_username)

def add_to_master_file_mess(data):
    """Add verified mess waste data to master file with detailed breakdown"""
    conn = get_db_connection()
    if not conn:
        return
    
    try:
        cursor = conn.cursor()
        
        # Calculate totals
        total_students = (
            data.get("breakfast_students", 0) + data.get("lunch_students", 0) + 
            data.get("snacks_students", 0) + data.get("dinner_students", 0)
        )
        
        total_mess_waste = (
            data.get("breakfast_student_waste", 0) + data.get("breakfast_counter_waste", 0) + 
            data.get("breakfast_vegetable_peels", 0) + data.get("lunch_student_waste", 0) + 
            data.get("lunch_counter_waste", 0) + data.get("lunch_vegetable_peels", 0) + 
            data.get("snacks_student_waste", 0) + data.get("snacks_counter_waste", 0) + 
            data.get("snacks_vegetable_peels", 0) + data.get("dinner_student_waste", 0) + 
            data.get("dinner_counter_waste", 0) + data.get("dinner_vegetable_peels", 0) +
            data.get("mess_dry_waste", 0)
        )
        
        total_mess_waste_no_peels = (
            data.get("breakfast_student_waste", 0) + data.get("breakfast_counter_waste", 0) + 
            data.get("lunch_student_waste", 0) + data.get("lunch_counter_waste", 0) + 
            data.get("snacks_student_waste", 0) + data.get("snacks_counter_waste", 0) + 
            data.get("dinner_student_waste", 0) + data.get("dinner_counter_waste", 0) +
            data.get("mess_dry_waste", 0)
        )
        
        # Handle zero student count
        per_capita_mess_waste = total_mess_waste / total_students if total_students > 0 else 0
        per_capita_mess_waste_no_peels = total_mess_waste_no_peels / total_students if total_students > 0 else 0
        
        # Insert or update master data with detailed breakdown
        cursor.execute("""
            INSERT INTO master_waste_data 
            (date, hostel, total_students, 
             breakfast_student_waste, breakfast_counter_waste, breakfast_vegetable_peels,
             lunch_student_waste, lunch_counter_waste, lunch_vegetable_peels,
             snacks_student_waste, snacks_counter_waste, snacks_vegetable_peels,
             dinner_student_waste, dinner_counter_waste, dinner_vegetable_peels,
             total_mess_waste, total_mess_waste_no_peels, per_capita_mess_waste, 
             per_capita_mess_waste_no_peels, mess_dry_waste)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (date, hostel) 
            DO UPDATE SET 
                total_students = EXCLUDED.total_students,
                total_mess_waste = EXCLUDED.total_mess_waste,
                total_mess_waste_no_peels = EXCLUDED.total_mess_waste_no_peels,
                per_capita_mess_waste = EXCLUDED.per_capita_mess_waste,
                per_capita_mess_waste_no_peels = EXCLUDED.per_capita_mess_waste_no_peels,
                breakfast_student_waste = EXCLUDED.breakfast_student_waste,
                breakfast_counter_waste = EXCLUDED.breakfast_counter_waste,
                breakfast_vegetable_peels = EXCLUDED.breakfast_vegetable_peels,
                lunch_student_waste = EXCLUDED.lunch_student_waste,
                lunch_counter_waste = EXCLUDED.lunch_counter_waste,
                lunch_vegetable_peels = EXCLUDED.lunch_vegetable_peels,
                snacks_student_waste = EXCLUDED.snacks_student_waste,
                snacks_counter_waste = EXCLUDED.snacks_counter_waste,
                snacks_vegetable_peels = EXCLUDED.snacks_vegetable_peels,
                dinner_student_waste = EXCLUDED.dinner_student_waste,
                dinner_counter_waste = EXCLUDED.dinner_counter_waste,
                dinner_vegetable_peels = EXCLUDED.dinner_vegetable_peels,
                mess_dry_waste = EXCLUDED.mess_dry_waste
        """, (
            data.get("submission_date"), data.get("hostel"),
            total_students, 
            data.get("breakfast_student_waste", 0), data.get("breakfast_counter_waste", 0), data.get("breakfast_vegetable_peels", 0),
            data.get("lunch_student_waste", 0), data.get("lunch_counter_waste", 0), data.get("lunch_vegetable_peels", 0),
            data.get("snacks_student_waste", 0), data.get("snacks_counter_waste", 0), data.get("snacks_vegetable_peels", 0),
            data.get("dinner_student_waste", 0), data.get("dinner_counter_waste", 0), data.get("dinner_vegetable_peels", 0),
            total_mess_waste, total_mess_waste_no_peels, per_capita_mess_waste, per_capita_mess_waste_no_peels,
            data.get("mess_dry_waste", 0)
        ))
        
        conn.commit()
        
    except Exception as e:
        st.error(f"Error adding to master file: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def add_to_master_file_hostel(data):
    """Add verified hostel waste data to master file"""
    conn = get_db_connection()
    if not conn:
        return
    
    try:
        cursor = conn.cursor()
        
        total_hostel_waste = (
            data.get("dry_waste", 0) + data.get("wet_waste", 0) + 
            data.get("e_waste", 0) + data.get("biomedical_waste", 0) + 
            data.get("hazardous_waste", 0)
        )
        
        # Insert or update master data
        cursor.execute("""
            INSERT INTO master_waste_data 
            (date, hostel, total_hostel_waste, dry_waste, wet_waste, e_waste, 
             biomedical_waste, hazardous_waste)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (date, hostel) 
            DO UPDATE SET 
                total_hostel_waste = EXCLUDED.total_hostel_waste,
                dry_waste = EXCLUDED.dry_waste,
                wet_waste = EXCLUDED.wet_waste,
                e_waste = EXCLUDED.e_waste,
                biomedical_waste = EXCLUDED.biomedical_waste,
                hazardous_waste = EXCLUDED.hazardous_waste
        """, (
            data.get("submission_date"), data.get("hostel"),
            total_hostel_waste, data.get("dry_waste", 0), data.get("wet_waste", 0),
            data.get("e_waste", 0), data.get("biomedical_waste", 0), data.get("hazardous_waste", 0)
        ))
        
        conn.commit()
        
    except Exception as e:
        st.error(f"Error adding to master file: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# Dashboard functions
def apply_period_filter(dataframe, period):
    if dataframe.empty or period == "all_time":
        return dataframe
    
    try:
        if 'date' not in dataframe.columns:
            return dataframe
            
        today = pd.to_datetime(datetime.now().date())
        if period == "week":
            start_date = today - pd.Timedelta(days=7)
        elif period == "month":
            start_date = today - pd.Timedelta(days=30)
        elif period == "year":
            start_date = today - pd.Timedelta(days=365)
        else:
            return dataframe
        
        return dataframe[dataframe["date"] >= start_date]
    except Exception:
        return dataframe

def calculate_kpis(dataframe, period_filter="all_time"):
    if dataframe.empty:
        return {
            "total_waste_all_time": 0,
            "total_mess_waste_all_time": 0,
            "per_capita_mess_waste_all_time": 0,
            "per_capita_mess_waste_no_peels_all_time": 0,
            "total_waste_today": 0,
            "total_mess_waste_today": 0,
            "per_capita_mess_waste_today": 0,
            "per_capita_mess_waste_no_peels_today": 0
        }
    
    try:
        filtered_df = apply_period_filter(dataframe, period_filter)
        if filtered_df.empty:
            return {
                "total_waste_all_time": 0,
                "total_mess_waste_all_time": 0,
                "per_capita_mess_waste_all_time": 0,
                "per_capita_mess_waste_no_peels_all_time": 0,
                "total_waste_today": 0,
                "total_mess_waste_today": 0,
                "per_capita_mess_waste_today": 0,
                "per_capita_mess_waste_no_peels_today": 0
            }
        
        today = pd.to_datetime(datetime.now().date())
        today_data = dataframe[dataframe["date"] == today] if 'date' in dataframe.columns else pd.DataFrame()
        
        # Calculate metrics
        total_mess_waste_period = filtered_df["total_mess_waste"].sum() if "total_mess_waste" in filtered_df.columns else 0
        total_hostel_waste_period = filtered_df["total_hostel_waste"].sum() if "total_hostel_waste" in filtered_df.columns else 0
        total_waste_period = total_mess_waste_period + total_hostel_waste_period
        
        total_students = filtered_df["total_students"].sum() if "total_students" in filtered_df.columns else 0
        per_capita_mess_waste_period = total_mess_waste_period / total_students if total_students > 0 else 0
        
        total_mess_waste_no_peels_period = filtered_df["total_mess_waste_no_peels"].sum() if "total_mess_waste_no_peels" in filtered_df.columns else 0
        per_capita_mess_waste_no_peels_period = total_mess_waste_no_peels_period / total_students if total_students > 0 else 0
        
        # Today's metrics
        total_mess_waste_today = today_data["total_mess_waste"].sum() if not today_data.empty and "total_mess_waste" in today_data.columns else 0
        total_hostel_waste_today = today_data["total_hostel_waste"].sum() if not today_data.empty and "total_hostel_waste" in today_data.columns else 0
        total_waste_today = total_mess_waste_today + total_hostel_waste_today
        
        students_today = today_data["total_students"].sum() if not today_data.empty and "total_students" in today_data.columns else 0
        per_capita_mess_waste_today = total_mess_waste_today / students_today if students_today > 0 else 0
        
        total_mess_waste_no_peels_today = today_data["total_mess_waste_no_peels"].sum() if not today_data.empty and "total_mess_waste_no_peels" in today_data.columns else 0
        per_capita_mess_waste_no_peels_today = total_mess_waste_no_peels_today / students_today if students_today > 0 else 0
        
        return {
            "total_waste_all_time": total_waste_period,
            "total_mess_waste_all_time": total_mess_waste_period,
            "per_capita_mess_waste_all_time": per_capita_mess_waste_period,
            "per_capita_mess_waste_no_peels_all_time": per_capita_mess_waste_no_peels_period,
            "total_waste_today": total_waste_today,
            "total_mess_waste_today": total_mess_waste_today,
            "per_capita_mess_waste_today": per_capita_mess_waste_today,
            "per_capita_mess_waste_no_peels_today": per_capita_mess_waste_no_peels_today
        }
    except Exception as e:
        st.error(f"Error calculating KPIs: {str(e)}")
        return {
            "total_waste_all_time": 0,
            "total_mess_waste_all_time": 0,
            "per_capita_mess_waste_all_time": 0,
            "per_capita_mess_waste_no_peels_all_time": 0,
            "total_waste_today": 0,
            "total_mess_waste_today": 0,
            "per_capita_mess_waste_today": 0,
            "per_capita_mess_waste_no_peels_today": 0
        }

def show_dashboard_content(df, title_prefix=""):
    """Show dashboard content with KPIs and charts"""
    if df.empty:
        st.warning("⚠️ No data available for dashboard.")
        st.info("💡 To resolve this issue:")
        st.write("1. Submit some waste data first")
        st.write("2. Make sure data has been verified by PHO")
        st.write("3. Check database connection")
        return
    
    try:
        # Filter options
        st.subheader("🔍 Filter Options")
        col1, col2 = st.columns(2)
        with col1:
            hostels = ["All Hostels"] + get_dynamic_hostels()
            selected_hostel = st.selectbox("Select Hostel", hostels, key=f"{title_prefix}_hostel_filter")
        with col2:
            period_options = ["All Time", "Year", "Month", "Week"]
            selected_period = st.selectbox("Select Time Period", period_options, key=f"{title_prefix}_period_filter")
        
        # Convert to internal format
        period_mapping = {
            "All Time": "all_time",
            "Year": "year", 
            "Month": "month",
            "Week": "week"
        }
        period_filter = period_mapping[selected_period]
        
        # Apply hostel filter FIRST
        if selected_hostel != "All Hostels":
            filtered_df = df[df["hostel"] == selected_hostel] if "hostel" in df.columns else df
            dashboard_title = f"{title_prefix}Dashboard - Hostel {selected_hostel.upper()} ({selected_period})"
        else:
            filtered_df = df
            dashboard_title = f"{title_prefix}Dashboard - All Hostels Combined ({selected_period})"
        
        # Apply time period filter to the already hostel-filtered data
        filtered_df = apply_period_filter(filtered_df, period_filter)
        
        st.markdown(f"### {dashboard_title}")
        st.markdown("---")
        
        # Calculate KPIs on filtered data
        kpis = calculate_kpis(filtered_df, "all_time")
        
        # Display KPIs
        st.subheader("📊 Key Performance Indicators")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                f"🗑️ Total Waste ({selected_period})",
                f"{kpis['total_waste_all_time']:.1f} kg",
                help=f"Total waste generated in selected {selected_period.lower()}"
            )
        with col2:
            st.metric(
                f"🍽️ Total Mess Waste ({selected_period})",
                f"{kpis['total_mess_waste_all_time']:.1f} kg",
                help=f"Total mess waste in selected {selected_period.lower()}"
            )
        with col3:
            st.metric(
                f"👥 Per Capita Mess Waste ({selected_period})",
                f"{kpis['per_capita_mess_waste_all_time']:.3f} kg",
                help=f"Per capita mess waste in {selected_period.lower()}"
            )
        with col4:
            st.metric(
                f"👥 Per Capita (No Peels) ({selected_period})",
                f"{kpis['per_capita_mess_waste_no_peels_all_time']:.3f} kg",
                help=f"Per capita mess waste excluding vegetable peels in {selected_period.lower()}"
            )
        
        # Today's metrics
        col5, col6, col7, col8 = st.columns(4)
        with col5:
            st.metric(
                "🗑️ Total Waste (Today)",
                f"{kpis['total_waste_today']:.1f} kg",
                help="Total waste generated today"
            )
        with col6:
            st.metric(
                "🍽️ Total Mess Waste (Today)",
                f"{kpis['total_mess_waste_today']:.1f} kg",
                help="Total mess waste generated today"
            )
        with col7:
            st.metric(
                "👥 Per Capita Mess Waste (Today)",
                f"{kpis['per_capita_mess_waste_today']:.3f} kg",
                help="Per capita mess waste today"
            )
        with col8:
            st.metric(
                "👥 Per Capita (No Peels) (Today)",
                f"{kpis['per_capita_mess_waste_no_peels_today']:.3f} kg",
                help="Per capita mess waste excluding vegetable peels today"
            )
        
        st.markdown("---")
        
        # Charts section
        st.subheader("📈 Charts and Analytics")
        
        if not filtered_df.empty:
            # Chart selection
            chart_col1, chart_col2 = st.columns(2)
            
            with chart_col1:
                chart_type = st.selectbox(
                    "Select Chart Type for Line Chart",
                    ["Mess Waste", "Hostel Waste", "Per Capita Mess Waste"],
                    key=f"{title_prefix}_chart_type"
                )
            
            # Ensure data is sorted by date before plotting
            chart_df = filtered_df.copy()
            chart_df = chart_df.sort_values('date')
            
            # Create charts based on selected metric
            if chart_type == "Mess Waste" and "total_mess_waste" in chart_df.columns:
                chart_data = chart_df.dropna(subset=['total_mess_waste'])
                
                if not chart_data.empty:
                    fig_line = px.line(
                        chart_data, 
                        x='date', 
                        y='total_mess_waste',
                        color='hostel',
                        title=f'Mess Waste Trend Over Time - {selected_hostel} ({selected_period})',
                        labels={'total_mess_waste': 'Mess Waste (kg)', 'date': 'Date'},
                        markers=True
                    )
                    fig_line.update_layout(
                        xaxis_title="Date",
                        yaxis_title="Mess Waste (kg)",
                        hovermode='x unified'
                    )
                    st.plotly_chart(fig_line, use_container_width=True)
                else:
                    st.info("No mess waste data available for the selected filters.")
                    
            elif chart_type == "Hostel Waste" and "total_hostel_waste" in chart_df.columns:
                chart_data = chart_df.dropna(subset=['total_hostel_waste'])
                
                if not chart_data.empty:
                    fig_line = px.line(
                        chart_data, 
                        x='date', 
                        y='total_hostel_waste',
                        color='hostel',
                        title=f'Hostel Waste Trend Over Time - {selected_hostel} ({selected_period})',
                        labels={'total_hostel_waste': 'Hostel Waste (kg)', 'date': 'Date'},
                        markers=True
                    )
                    fig_line.update_layout(
                        xaxis_title="Date",
                        yaxis_title="Hostel Waste (kg)",
                        hovermode='x unified'
                    )
                    st.plotly_chart(fig_line, use_container_width=True)
                else:
                    st.info("No hostel waste data available for the selected filters.")
                    
            elif chart_type == "Per Capita Mess Waste" and "per_capita_mess_waste" in chart_df.columns:
                chart_data = chart_df.dropna(subset=['per_capita_mess_waste'])
                
                if not chart_data.empty:
                    fig_line = px.line(
                        chart_data, 
                        x='date', 
                        y='per_capita_mess_waste',
                        color='hostel',
                        title=f'Per Capita Mess Waste Trend Over Time - {selected_hostel} ({selected_period})',
                        labels={'per_capita_mess_waste': 'Per Capita Mess Waste (kg)', 'date': 'Date'},
                        markers=True
                    )
                    fig_line.update_layout(
                        xaxis_title="Date",
                        yaxis_title="Per Capita Mess Waste (kg)",
                        hovermode='x unified'
                    )
                    st.plotly_chart(fig_line, use_container_width=True)
                else:
                    st.info("No per capita mess waste data available for the selected filters.")
            else:
                st.info(f"No data available for {chart_type} chart in the selected filters.")
            
            # Additional charts and statistics
            col1, col2 = st.columns(2)
            
            with col1:
                # UPDATED: Donut chart for mess waste categories (student waste, counter waste, vegetable peels)
                if "total_mess_waste" in filtered_df.columns:
                    # Calculate totals for mess waste categories from FILTERED data
                    student_waste_cols = ['breakfast_student_waste', 'lunch_student_waste', 'snacks_student_waste', 'dinner_student_waste']
                    counter_waste_cols = ['breakfast_counter_waste', 'lunch_counter_waste', 'snacks_counter_waste', 'dinner_counter_waste']
                    vegetable_peels_cols = ['breakfast_veg_peels', 'lunch_veg_peels', 'snacks_vegetable_peels', 'dinner_vegetable_peels']
                    
                    total_students_waste = sum(filtered_df[col].sum() for col in student_waste_cols if col in filtered_df.columns)
                    total_counter_waste = sum(filtered_df[col].sum() for col in counter_waste_cols if col in filtered_df.columns)
                    total_vegetable_peels = sum(filtered_df[col].sum() for col in vegetable_peels_cols if col in filtered_df.columns)
                    
                    if total_students_waste > 0 or total_counter_waste > 0 or total_vegetable_peels > 0:
                        mess_category_data = pd.DataFrame({
                            'Category': ["Students' Waste", 'Counter Waste', 'Vegetable Peels'],
                            'Amount': [total_students_waste, total_counter_waste, total_vegetable_peels]
                        })
                        
                        # Filter out zero values
                        mess_category_data = mess_category_data[mess_category_data['Amount'] > 0]
                        
                        if not mess_category_data.empty:
                            fig_donut = px.pie(
                                mess_category_data,
                                values='Amount',
                                names='Category',
                                title=f'Mess Waste Categories - {selected_hostel} ({selected_period})',
                                hole=0.4  # Makes it a donut chart
                            )
                            st.plotly_chart(fig_donut, use_container_width=True)
                        else:
                            st.info("No mess waste category data available for the selected filters.")
                    else:
                        st.info("No mess waste category data available for the selected filters.")
                else:
                    st.info("No mess waste data available for the selected filters.")
            
            with col2:
                # Summary statistics
                st.markdown("### 📊 Summary Statistics")
                st.markdown(f"**Filter Applied:** {selected_hostel} | {selected_period}")
                
                if "total_mess_waste" in filtered_df.columns:
                    st.write(f"**Mess Waste Statistics:**")
                    st.write(f"- Average Daily: {filtered_df['total_mess_waste'].mean():.2f} kg")
                    st.write(f"- Maximum Daily: {filtered_df['total_mess_waste'].max():.2f} kg")
                    st.write(f"- Minimum Daily: {filtered_df['total_mess_waste'].min():.2f} kg")
                    st.write(f"- Total Records: {len(filtered_df)}")
                    if 'total_students' in filtered_df.columns:
                        st.write(f"- Total Students Served: {filtered_df['total_students'].sum():,}")
                
                if "total_hostel_waste" in filtered_df.columns:
                    st.write(f"**Hostel Waste Statistics:**")
                    st.write(f"- Average Daily: {filtered_df['total_hostel_waste'].mean():.2f} kg")
                    st.write(f"- Maximum Daily: {filtered_df['total_hostel_waste'].max():.2f} kg")
                    st.write(f"- Minimum Daily: {filtered_df['total_hostel_waste'].min():.2f} kg")
                
                # Show date range of filtered data
                if 'date' in filtered_df.columns and not filtered_df.empty:
                    date_range_start = filtered_df['date'].min().strftime('%Y-%m-%d')
                    date_range_end = filtered_df['date'].max().strftime('%Y-%m-%d')
                    st.write(f"**Date Range:** {date_range_start} to {date_range_end}")
        else:
            st.warning("No data available for charts with the selected filters.")
            
    except Exception as e:
        st.error(f"Error displaying dashboard: {str(e)}")
        st.info("Please check your data format and try again.")

# -----------------------------------------------------------------------------
# SUPABASE STORAGE
# -----------------------------------------------------------------------------
def get_supabase_storage_usage(bucket_name):
    """Get storage usage from Supabase bucket"""
    try:
        supabase = get_supabase_client()
        if not supabase:
            return 0, []
        
        # List all files in bucket
        files = supabase.storage.from_(bucket_name).list()
        
        if hasattr(files, 'error') and files.error:
            st.error(f"Error accessing bucket: {files.error}")
            return 0, []
        
        total_size = 0
        file_list = []
        
        for file in files:
            if isinstance(file, dict):
                size = file.get('metadata', {}).get('size', 0) or 0
                total_size += size
                file_list.append({
                    'name': file.get('name', ''),
                    'size': size,
                    'created': file.get('created_at', ''),
                    'updated': file.get('updated_at', '')
                })
        
        return total_size, file_list
        
    except Exception as e:
        st.error(f"Error getting storage usage: {e}")
        return 0, []
    
def download_supabase_images(bucket_name):
    """Download all images from Supabase bucket as ZIP"""
    try:
        supabase = get_supabase_client()
        if not supabase:
            return None
        
        import zipfile
        import io
        import requests
        
        # Create ZIP file in memory
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Get all files in bucket
            files = supabase.storage.from_(bucket_name).list()
            
            if hasattr(files, 'error') and files.error:
                st.error(f"Error accessing bucket: {files.error}")
                return None
            
            for file in files:
                if isinstance(file, dict):
                    file_name = file.get('name', '')
                    if file_name:
                        # Get public URL
                        public_url = supabase.storage.from_(bucket_name).get_public_url(file_name)
                        
                        # Download file content
                        response = requests.get(public_url)
                        if response.status_code == 200:
                            zip_file.writestr(file_name, response.content)
        
        zip_buffer.seek(0)
        return zip_buffer.getvalue()
        
    except Exception as e:
        st.error(f"Error creating ZIP file: {e}")
        return None

def delete_supabase_images(bucket_name, file_names=None):
    """Delete images from Supabase bucket"""
    try:
        supabase = get_supabase_client()
        if not supabase:
            return False
        
        if file_names is None:
            # Delete all files
            files = supabase.storage.from_(bucket_name).list()
            if hasattr(files, 'error') and files.error:
                st.error(f"Error accessing bucket: {files.error}")
                return False
            
            file_names = [file.get('name', '') for file in files if isinstance(file, dict) and file.get('name')]
        
        if not file_names:
            st.info("No files to delete")
            return True
        
        # Delete files
        result = supabase.storage.from_(bucket_name).remove(file_names)
        
        if hasattr(result, 'error') and result.error:
            st.error(f"Error deleting files: {result.error}")
            return False
        
        return True
        
    except Exception as e:
        st.error(f"Error deleting files: {e}")
        return False



# -----------------------------------------------------------------------------
# 🔑 LOGIN FORM
# -----------------------------------------------------------------------------
def show_login_form():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🌱 Sustainability Data Portal")
        st.subheader("Login")
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Login", use_container_width=True):
                conn = get_db_connection()
                if not conn:
                    st.error("Cannot connect to DB.")
                    return
                cur = conn.cursor()
                cur.execute("SELECT username, name, password_hash, role FROM users WHERE username=%s", (username,))
                user = cur.fetchone()
                cur.close()
                conn.close()
                if user and bcrypt.checkpw(password.encode('utf-8'), user[2].encode('utf-8')):
                    st.session_state["authentication_status"] = True
                    st.session_state["username"] = user[0]
                    st.session_state["name"] = user[1]
                    st.session_state["role"] = user[3]
                    st.success("Login successful!")
                    st.rerun()
                else:
                    st.error("Incorrect username or password")

# -----------------------------------------------------------------------------
# 🗑️ WASTE COLLECTOR FORM - UPDATED: Auto-hostel selection and image clearing
# -----------------------------------------------------------------------------
def show_pho_supervisor_form(username: str):
    
    # UPDATED: Get hostel from username
    user_hostel = get_hostel_from_username(username)

    st.header(f'Hostel {user_hostel}')
    st.header("🗑️ Waste Collection Interface")
    
    tab1, tab2, tab3 = st.tabs(["🍽️ Mess Waste Data", "🏠 Hostel Waste Data", "📋 My Submissions"])
    
    with tab1:
        st.subheader("📝 Daily Mess Waste Submission (All 4 Meals)")
        
        # Auto-save indicator
        if st.session_state.get('mess_form_data'):
            st.info("💾 Form data auto-saved")
        
        # Load saved form data
        saved_data = load_form_data('mess_form_data', {
            'submission_date': date.today(),
            'hostel': user_hostel if user_hostel else '2',
            'breakfast_students': 0,
            'breakfast_student_waste': 0.0,
            'breakfast_counter_waste': 0.0,
            'breakfast_vegetable_peels': 0.0,
            'lunch_students': 0,
            'lunch_student_waste': 0.0,
            'lunch_counter_waste': 0.0,
            'lunch_vegetable_peels': 0.0,
            'snacks_students': 0,
            'snacks_student_waste': 0.0,
            'snacks_counter_waste': 0.0,
            'snacks_vegetable_peels': 0.0,
            'dinner_students': 0,
            'dinner_student_waste': 0.0,
            'dinner_counter_waste': 0.0,
            'dinner_vegetable_peels': 0.0,
            'mess_dry_waste': 0.0,
            'remarks': ''
        })
        
        col1, col2 = st.columns(2)
        with col1:
            submission_date = st.date_input(
                "📅 Submission Date",
                value=saved_data.get('submission_date', date.today()),
                key="mess_submission_date"
            )
        
        st.markdown("---")
        
        # Breakfast Section
        st.markdown("### 🌅 Breakfast")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            breakfast_students = st.number_input(
                "👥 Students Count",
                min_value=0,
                step=1,
                value=saved_data.get('breakfast_students', 0),
                key="breakfast_students"
            )
        with col2:
            breakfast_student_waste = st.number_input(
                "🍽️ Students' Waste (kg)",
                min_value=0.0,
                step=0.1,
                value=saved_data.get('breakfast_student_waste', 0.0),
                key="breakfast_student_waste"
            )
        with col3:
            breakfast_counter_waste = st.number_input(
                "🍲 Counter Waste (kg)",
                min_value=0.0,
                step=0.1,
                value=saved_data.get('breakfast_counter_waste', 0.0),
                key="breakfast_counter_waste"
            )
        with col4:
            breakfast_vegetable_peels = st.number_input(
                "🥬 Vegetable Peels (kg)",
                min_value=0.0,
                step=0.1,
                value=saved_data.get('breakfast_vegetable_peels', 0.0),
                key="breakfast_vegetable_peels"
            )
        
        # Lunch Section
        st.markdown("### 🌞 Lunch")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            lunch_students = st.number_input(
                "👥 Students Count",
                min_value=0,
                step=1,
                value=saved_data.get('lunch_students', 0),
                key="lunch_students"
            )
        with col2:
            lunch_student_waste = st.number_input(
                "🍽️ Students' Waste (kg)",
                min_value=0.0,
                step=0.1,
                value=saved_data.get('lunch_student_waste', 0.0),
                key="lunch_student_waste"
            )
        with col3:
            lunch_counter_waste = st.number_input(
                "🍲 Counter Waste (kg)",
                min_value=0.0,
                step=0.1,
                value=saved_data.get('lunch_counter_waste', 0.0),
                key="lunch_counter_waste"
            )
        with col4:
            lunch_vegetable_peels = st.number_input(
                "🥬 Vegetable Peels (kg)",
                min_value=0.0,
                step=0.1,
                value=saved_data.get('lunch_vegetable_peels', 0.0),
                key="lunch_vegetable_peels"
            )
        
        # Snacks Section
        st.markdown("### 🍪 Snacks")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            snacks_students = st.number_input(
                "👥 Students Count",
                min_value=0,
                step=1,
                value=saved_data.get('snacks_students', 0),
                key="snacks_students"
            )
        with col2:
            snacks_student_waste = st.number_input(
                "🍽️ Students' Waste (kg)",
                min_value=0.0,
                step=0.1,
                value=saved_data.get('snacks_student_waste', 0.0),
                key="snacks_student_waste"
            )
        with col3:
            snacks_counter_waste = st.number_input(
                "🍲 Counter Waste (kg)",
                min_value=0.0,
                step=0.1,
                value=saved_data.get('snacks_counter_waste', 0.0),
                key="snacks_counter_waste"
            )
        with col4:
            snacks_vegetable_peels = st.number_input(
                "🥬 Vegetable Peels (kg)",
                min_value=0.0,
                step=0.1,
                value=saved_data.get('snacks_vegetable_peels', 0.0),
                key="snacks_vegetable_peels"
            )
        
        # Dinner Section
        st.markdown("### 🌙 Dinner")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            dinner_students = st.number_input(
                "👥 Students Count",
                min_value=0,
                step=1,
                value=saved_data.get('dinner_students', 0),
                key="dinner_students"
            )
        with col2:
            dinner_student_waste = st.number_input(
                "🍽️ Students' Waste (kg)",
                min_value=0.0,
                step=0.1,
                value=saved_data.get('dinner_student_waste', 0.0),
                key="dinner_student_waste"
            )
        with col3:
            dinner_counter_waste = st.number_input(
                "🍲 Counter Waste (kg)",
                min_value=0.0,
                step=0.1,
                value=saved_data.get('dinner_counter_waste', 0.0),
                key="dinner_counter_waste"
            )
        with col4:
            dinner_vegetable_peels = st.number_input(
                "🥬 Vegetable Peels (kg)",
                min_value=0.0,
                step=0.1,
                value=saved_data.get('dinner_vegetable_peels', 0.0),
                key="dinner_vegetable_peels"
            )
        
        # NEW: Mess Dry Waste Section
        st.markdown("### 🗑️ Additional Mess Waste")
        col1, col2 = st.columns(2)
        with col1:
            mess_dry_waste = st.number_input(
                "🗑️ Mess Dry Waste (kg)",
                min_value=0.0,
                step=0.1,
                value=saved_data.get('mess_dry_waste', 0.0),
                key="mess_dry_waste",
                help="Additional dry waste generated in mess operations"
            )
        
        # NEW: Image Upload Section
        st.markdown("### 📸 Upload Images")
        st.markdown("*Upload photos of waste collection for verification*")
        
        uploaded_files = st.file_uploader(
            "Choose image files",
            type=['png', 'jpg', 'jpeg'],
            accept_multiple_files=True,
            key="mess_waste_images",
            help="Upload photos showing the waste collection"
        )
        
        # Display uploaded images preview
        if uploaded_files:
            st.markdown("**Image Preview:**")
            cols = st.columns(min(len(uploaded_files), 3))  # Show max 3 images per row
            for idx, uploaded_file in enumerate(uploaded_files):
                with cols[idx % 3]:
                    st.image(uploaded_file, caption=uploaded_file.name, width=200)
                    st.write(f"Size: {uploaded_file.size} bytes")
        
        # Auto-save form data (UPDATED: Include mess dry waste)
        current_form_data = {
            'submission_date': submission_date,
            'hostel': user_hostel,
            'breakfast_students': breakfast_students,
            'breakfast_student_waste': breakfast_student_waste,
            'breakfast_counter_waste': breakfast_counter_waste,
            'breakfast_vegetable_peels': breakfast_vegetable_peels,
            'lunch_students': lunch_students,
            'lunch_student_waste': lunch_student_waste,
            'lunch_counter_waste': lunch_counter_waste,
            'lunch_vegetable_peels': lunch_vegetable_peels,
            'snacks_students': snacks_students,
            'snacks_student_waste': snacks_student_waste,
            'snacks_counter_waste': snacks_counter_waste,
            'snacks_vegetable_peels': snacks_vegetable_peels,
            'dinner_students': dinner_students,
            'dinner_student_waste': dinner_student_waste,
            'dinner_counter_waste': dinner_counter_waste,
            'dinner_vegetable_peels': dinner_vegetable_peels,
            'mess_dry_waste': mess_dry_waste
        }
        save_form_data('mess_form_data', current_form_data)
        
        # Real-time calculations (UPDATED: Include mess dry waste)
        total_students = breakfast_students + lunch_students + snacks_students + dinner_students
        total_mess_waste = (breakfast_student_waste + breakfast_counter_waste + breakfast_vegetable_peels +
                           lunch_student_waste + lunch_counter_waste + lunch_vegetable_peels +
                           snacks_student_waste + snacks_counter_waste + snacks_vegetable_peels +
                           dinner_student_waste + dinner_counter_waste + dinner_vegetable_peels +
                           mess_dry_waste)
        
        # Display metrics (UPDATED: Include mess dry waste)
        st.markdown("---")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("👥 Total Students", total_students)
        with col2:
            st.metric("🍽️ Total Mess Waste", f"{total_mess_waste:.1f} kg")
        with col3:
            st.metric("🗑️ Mess Dry Waste", f"{mess_dry_waste:.1f} kg")
        
        remarks = st.text_area(
            "📝 Remarks (optional)",
            value=saved_data.get('remarks', ''),
            placeholder="Any additional notes about today's mess waste...",
            key="mess_remarks"
        )
        
        # UPDATED: Submit button with image handling and clearing
        if st.button("✅ Submit Mess Waste Data", type="primary", use_container_width=True):
            data = {
                "submission_date": submission_date.strftime("%Y-%m-%d"),
                "hostel": user_hostel,
                "collection_time": datetime.now().strftime("%H:%M:%S"),
                "breakfast_students": breakfast_students,
                "breakfast_student_waste": breakfast_student_waste,
                "breakfast_counter_waste": breakfast_counter_waste,
                "breakfast_vegetable_peels": breakfast_vegetable_peels,
                "lunch_students": lunch_students,
                "lunch_student_waste": lunch_student_waste,
                "lunch_counter_waste": lunch_counter_waste,
                "lunch_vegetable_peels": lunch_vegetable_peels,
                "snacks_students": snacks_students,
                "snacks_student_waste": snacks_student_waste,
                "snacks_counter_waste": snacks_counter_waste,
                "snacks_vegetable_peels": snacks_vegetable_peels,
                "dinner_students": dinner_students,
                "dinner_student_waste": dinner_student_waste,
                "dinner_counter_waste": dinner_counter_waste,
                "dinner_vegetable_peels": dinner_vegetable_peels,
                "mess_dry_waste": mess_dry_waste,
                "total_students": total_students,
                "total_mess_waste": total_mess_waste,
                "remarks": remarks
            }
            
            if save_mess_waste_data_with_images(username, data, uploaded_files):
                st.success("✅ Mess waste data submitted successfully!")
                if uploaded_files:
                    st.success(f"📸 {len(uploaded_files)} images uploaded successfully!")
                clear_form_data('mess_form_data')  # Clear saved form data
                time.sleep(2)
                st.rerun()
            else:
                st.error("❌ Failed to submit data. Please try again.")
    
    with tab2:
        st.subheader("📝 Hostel Waste Collection")
        
        # Auto-save indicator
        if st.session_state.get('waste_form_data'):
            st.info("💾 Form data auto-saved")
        
        # Load saved form data
        saved_data = load_form_data('waste_form_data', {
            'submission_date': date.today(),
            'hostel': user_hostel if user_hostel else '2',
            'dry_waste': 0.0,
            'wet_waste': 0.0,
            'e_waste': 0.0,
            'biomedical_waste': 0.0,
            'hazardous_waste': 0.0,
            'remarks': ''
        })
        
        col1, col2 = st.columns(2)
        with col1:
            submission_date = st.date_input(
                "📅 Collection Date",
                value=saved_data.get('submission_date', date.today()),
                key="waste_submission_date"
            )
            
            dry_waste = st.number_input(
                "🗑️ Dry Waste (kg)",
                min_value=0.0,
                step=0.1,
                value=saved_data.get('dry_waste', 0.0),
                key="waste_dry_waste"
            )
            wet_waste = st.number_input(
                "💧 Wet Waste (kg)",
                min_value=0.0,
                step=0.1,
                value=saved_data.get('wet_waste', 0.0),
                key="waste_wet_waste"
            )
        
        with col2:
            e_waste = st.number_input(
                "⚡ E-Waste (kg)",
                min_value=0.0,
                step=0.1,
                value=saved_data.get('e_waste', 0.0),
                key="waste_e_waste"
            )
            biomedical_waste = st.number_input(
                "🏥 Biomedical Waste (kg)",
                min_value=0.0,
                step=0.1,
                value=saved_data.get('biomedical_waste', 0.0),
                key="waste_biomedical_waste"
            )
        
            hazardous_waste = st.number_input(
                "☢️ Hazardous Waste (kg)",
                min_value=0.0,
                step=0.1,
                value=saved_data.get('hazardous_waste', 0.0),
                key="waste_hazardous_waste"
            )
        
        # NEW: Image Upload for Hostel Waste
        st.markdown("### 📸 Upload Images")
        st.markdown("*Upload photos of hostel waste collection for verification*")
        
        hostel_uploaded_files = st.file_uploader(
            "Choose image files",
            type=['png', 'jpg', 'jpeg'],
            accept_multiple_files=True,
            key="hostel_waste_images",
            help="Upload photos showing the hostel waste collection"
        )
        
        # Display uploaded images preview
        if hostel_uploaded_files:
            st.markdown("**Image Preview:**")
            cols = st.columns(min(len(hostel_uploaded_files), 3))
            for idx, uploaded_file in enumerate(hostel_uploaded_files):
                with cols[idx % 3]:
                    st.image(uploaded_file, caption=uploaded_file.name, width=200)
                    st.write(f"Size: {uploaded_file.size} bytes")
        
        # Auto-save form data
        current_form_data = {
            'submission_date': submission_date,
            'hostel': user_hostel,
            'dry_waste': dry_waste,
            'wet_waste': wet_waste,
            'e_waste': e_waste,
            'biomedical_waste': biomedical_waste,
            'hazardous_waste': hazardous_waste
        }
        save_form_data('waste_form_data', current_form_data)
        
        # Real-time calculations
        total_waste = dry_waste + wet_waste + e_waste + biomedical_waste + hazardous_waste
        
        # Display total
        st.markdown("---")
        st.metric("🗑️ Total Hostel Waste", f"{total_waste:.1f} kg")
        
        remarks = st.text_area(
            "📝 Remarks (optional)",
            value=saved_data.get('remarks', ''),
            placeholder="Any additional notes about hostel waste collection...",
            key="waste_remarks"
        )
        
        # UPDATED: Submit button with image handling and clearing
        if st.button("✅ Submit Hostel Waste Data", type="primary", use_container_width=True):
            data = {
                "submission_date": submission_date.strftime("%Y-%m-%d"),
                "hostel": user_hostel,
                "collection_time": datetime.now().strftime("%H:%M:%S"),
                "dry_waste": dry_waste,
                "wet_waste": wet_waste,
                "e_waste": e_waste,
                "biomedical_waste": biomedical_waste,
                "hazardous_waste": hazardous_waste,
                "remarks": remarks
            }
            
            if save_hostel_waste_data_with_images(username, data, hostel_uploaded_files):
                st.success("✅ Hostel waste data submitted successfully!")
                if hostel_uploaded_files:
                    st.success(f"📸 {len(hostel_uploaded_files)} images uploaded successfully!")
                clear_form_data('waste_form_data')  # Clear saved form data
                time.sleep(2)
                st.rerun()
            else:
                st.error("❌ Failed to submit data. Please try again.")

    
    with tab3:
        st.subheader("📋 My Submissions")
        
        # Load collector's data from database
        conn = get_db_connection()
        if conn:
            try:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                
                # Get verified submissions
                cursor.execute("""
                    SELECT 'mess_waste' as type, submission_date as date, hostel, total_mess_waste as total_waste, status, verified_at
                    FROM mess_waste_submissions 
                    WHERE submitted_by = %s AND status = 'verified'
                    UNION ALL
                    SELECT 'hostel_waste' as type, submission_date as date, hostel, (dry_waste + wet_waste + e_waste + biomedical_waste + hazardous_waste) as total_waste, status, verified_at
                    FROM hostel_waste_submissions 
                    WHERE submitted_by = %s AND status = 'verified'
                    ORDER BY date DESC
                """, (username, username))
                verified_data = cursor.fetchall()
                
                # Get pending submissions
                cursor.execute("""
                    SELECT 'mess_waste' as type, submission_date as date, hostel, total_mess_waste as total_waste, status, submitted_at
                    FROM mess_waste_submissions 
                    WHERE submitted_by = %s AND status = 'pending'
                    UNION ALL
                    SELECT 'hostel_waste' as type, submission_date as date, hostel, (dry_waste + wet_waste + e_waste + biomedical_waste + hazardous_waste) as total_waste, status, submitted_at
                    FROM hostel_waste_submissions 
                    WHERE submitted_by = %s AND status = 'pending'
                    ORDER BY date DESC
                """, (username, username))
                pending_data = cursor.fetchall()
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("### ✅ Verified Submissions")
                    if verified_data:
                        verified_df = pd.DataFrame([dict(row) for row in verified_data])
                        st.dataframe(verified_df, use_container_width=True)
                        
                        # Download verified data
                        csv = verified_df.to_csv(index=False)
                        st.download_button(
                            label="📥 Download Verified Data",
                            data=csv,
                            file_name=f"verified_data_{username}_{datetime.now().strftime('%Y%m%d')}.csv",
                            mime="text/csv"
                        )
                    else:
                        st.info("No verified submissions found.")
                
                with col2:
                    st.markdown("### ⏳ Pending Submissions")
                    if pending_data:
                        pending_df = pd.DataFrame([dict(row) for row in pending_data])
                        st.dataframe(pending_df, use_container_width=True)
                        
                        # Download pending data
                        csv = pending_df.to_csv(index=False)
                        st.download_button(
                            label="📥 Download Pending Data",
                            data=csv,
                            file_name=f"pending_data_{username}_{datetime.now().strftime('%Y%m%d')}.csv",
                            mime="text/csv"
                        )
                    else:
                        st.info("No pending submissions found.")
                        
            except Exception as e:
                st.error(f"Error loading submissions: {e}")
            finally:
                if cursor:
                    cursor.close()
                if conn:
                    conn.close()


def update_submission_with_edits(submission_id, submission_type, edited_data, pho_username):
    """Update submission with edited data and mark as verified"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        timestamp = datetime.now()
        
        if submission_type == 'mess_waste':
            # Update mess waste submission with edited data
            cursor.execute("""
                UPDATE mess_waste_submissions 
                SET breakfast_students = %s, breakfast_student_waste = %s, breakfast_counter_waste = %s, breakfast_vegetable_peels = %s,
                    lunch_students = %s, lunch_student_waste = %s, lunch_counter_waste = %s, lunch_vegetable_peels = %s,
                    snacks_students = %s, snacks_student_waste = %s, snacks_counter_waste = %s, snacks_vegetable_peels = %s,
                    dinner_students = %s, dinner_student_waste = %s, dinner_counter_waste = %s, dinner_vegetable_peels = %s,
                    mess_dry_waste = %s, total_students = %s, total_mess_waste = %s,
                    status = 'verified', verified_by = %s, verified_at = %s
                WHERE submission_id = %s
            """, (
                edited_data['breakfast_students'], edited_data['breakfast_student_waste'], edited_data['breakfast_counter_waste'], edited_data['breakfast_vegetable_peels'],
                edited_data['lunch_students'], edited_data['lunch_student_waste'], edited_data['lunch_counter_waste'], edited_data['lunch_vegetable_peels'],
                edited_data['snacks_students'], edited_data['snacks_student_waste'], edited_data['snacks_counter_waste'], edited_data['snacks_vegetable_peels'],
                edited_data['dinner_students'], edited_data['dinner_student_waste'], edited_data['dinner_counter_waste'], edited_data['dinner_vegetable_peels'],
                edited_data['mess_dry_waste'], edited_data['total_students'], edited_data['total_mess_waste'],
                pho_username, timestamp, submission_id
            ))
            
        else:
            # Update hostel waste submission with edited data
            cursor.execute("""
                UPDATE hostel_waste_submissions 
                SET dry_waste = %s, wet_waste = %s, e_waste = %s, biomedical_waste = %s, hazardous_waste = %s, total_waste = %s,
                    status = 'verified', verified_by = %s, verified_at = %s
                WHERE submission_id = %s
            """, (
                edited_data['dry_waste'], edited_data['wet_waste'], edited_data['e_waste'],
                edited_data['biomedical_waste'], edited_data['hazardous_waste'], edited_data['total_waste'],
                pho_username, timestamp, submission_id
            ))
        
        conn.commit()
        
        # Clear cache
        load_pending_data_for_pho.clear()
        load_master_data.clear()
        
        return True
        
    except Exception as e:
        st.error(f"Error updating submission: {e}")
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# NEW: PHO Edit Functions
def show_edit_form(record_data, submission_type, pho_username):
    """Show edit form for PHO to modify submissions"""
    st.markdown("### ✏️ Edit Submission")
    
    with st.form("edit_submission_form"):
        if submission_type == 'mess_waste':
            st.markdown("#### Edit Mess Waste Data")
            
            # Create editable fields for mess waste
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**Breakfast**")
                breakfast_students = st.number_input("Students", value=record_data.get('breakfast_students', 0), key="edit_breakfast_students")
                breakfast_student_waste = st.number_input("Student Waste (kg)", value=float(record_data.get('breakfast_student_waste', 0)), step=0.1, key="edit_breakfast_student_waste")
                breakfast_counter_waste = st.number_input("Counter Waste (kg)", value=float(record_data.get('breakfast_counter_waste', 0)), step=0.1, key="edit_breakfast_counter_waste")
                breakfast_vegetable_peels = st.number_input("Vegetable Peels (kg)", value=float(record_data.get('breakfast_vegetable_peels', 0)), step=0.1, key="edit_breakfast_vegetable_peels")
                
                st.markdown("**Lunch**")
                lunch_students = st.number_input("Students", value=record_data.get('lunch_students', 0), key="edit_lunch_students")
                lunch_student_waste = st.number_input("Student Waste (kg)", value=float(record_data.get('lunch_student_waste', 0)), step=0.1, key="edit_lunch_student_waste")
                lunch_counter_waste = st.number_input("Counter Waste (kg)", value=float(record_data.get('lunch_counter_waste', 0)), step=0.1, key="edit_lunch_counter_waste")
                lunch_vegetable_peels = st.number_input("Vegetable Peels (kg)", value=float(record_data.get('lunch_vegetable_peels', 0)), step=0.1, key="edit_lunch_vegetable_peels")
            
            with col2:
                st.markdown("**Snacks**")
                snacks_students = st.number_input("Students", value=record_data.get('snacks_students', 0), key="edit_snacks_students")
                snacks_student_waste = st.number_input("Student Waste (kg)", value=float(record_data.get('snacks_student_waste', 0)), step=0.1, key="edit_snacks_student_waste")
                snacks_counter_waste = st.number_input("Counter Waste (kg)", value=float(record_data.get('snacks_counter_waste', 0)), step=0.1, key="edit_snacks_counter_waste")
                snacks_vegetable_peels = st.number_input("Vegetable Peels (kg)", value=float(record_data.get('snacks_vegetable_peels', 0)), step=0.1, key="edit_snacks_vegetable_peels")
                
                st.markdown("**Dinner**")
                dinner_students = st.number_input("Students", value=record_data.get('dinner_students', 0), key="edit_dinner_students")
                dinner_student_waste = st.number_input("Student Waste (kg)", value=float(record_data.get('dinner_student_waste', 0)), step=0.1, key="edit_dinner_student_waste")
                dinner_counter_waste = st.number_input("Counter Waste (kg)", value=float(record_data.get('dinner_counter_waste', 0)), step=0.1, key="edit_dinner_counter_waste")
                dinner_vegetable_peels = st.number_input("Vegetable Peels (kg)", value=float(record_data.get('dinner_vegetable_peels', 0)), step=0.1, key="edit_dinner_vegetable_peels")
            
            mess_dry_waste = st.number_input("Mess Dry Waste (kg)", value=float(record_data.get('mess_dry_waste', 0)), step=0.1, key="edit_mess_dry_waste")
            
        else:  # hostel_waste
            st.markdown("#### Edit Hostel Waste Data")
            
            col1, col2 = st.columns(2)
            with col1:
                dry_waste = st.number_input("Dry Waste (kg)", value=float(record_data.get('dry_waste', 0)), step=0.1, key="edit_dry_waste")
                wet_waste = st.number_input("Wet Waste (kg)", value=float(record_data.get('wet_waste', 0)), step=0.1, key="edit_wet_waste")
                e_waste = st.number_input("E-Waste (kg)", value=float(record_data.get('e_waste', 0)), step=0.1, key="edit_e_waste")
            with col2:
                biomedical_waste = st.number_input("Biomedical Waste (kg)", value=float(record_data.get('biomedical_waste', 0)), step=0.1, key="edit_biomedical_waste")
                hazardous_waste = st.number_input("Hazardous Waste (kg)", value=float(record_data.get('hazardous_waste', 0)), step=0.1, key="edit_hazardous_waste")
        
        edit_reason = st.text_area("Reason for Edit", placeholder="Explain why this data is being modified...")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.form_submit_button("💾 Save Changes", type="primary"):
                # Prepare edited data
                if submission_type == 'mess_waste':
                    edited_data = {
                        'breakfast_students': breakfast_students,
                        'breakfast_student_waste': breakfast_student_waste,
                        'breakfast_counter_waste': breakfast_counter_waste,
                        'breakfast_vegetable_peels': breakfast_vegetable_peels,
                        'lunch_students': lunch_students,
                        'lunch_student_waste': lunch_student_waste,
                        'lunch_counter_waste': lunch_counter_waste,
                        'lunch_vegetable_peels': lunch_vegetable_peels,
                        'snacks_students': snacks_students,
                        'snacks_student_waste': snacks_student_waste,
                        'snacks_counter_waste': snacks_counter_waste,
                        'snacks_vegetable_peels': snacks_vegetable_peels,
                        'dinner_students': dinner_students,
                        'dinner_student_waste': dinner_student_waste,
                        'dinner_counter_waste': dinner_counter_waste,
                        'dinner_vegetable_peels': dinner_vegetable_peels,
                        'mess_dry_waste': mess_dry_waste,
                        'total_students': breakfast_students + lunch_students + snacks_students + dinner_students,
                        'total_mess_waste': (breakfast_student_waste + breakfast_counter_waste + breakfast_vegetable_peels +
                                           lunch_student_waste + lunch_counter_waste + lunch_vegetable_peels +
                                           snacks_student_waste + snacks_counter_waste + snacks_vegetable_peels +
                                           dinner_student_waste + dinner_counter_waste + dinner_vegetable_peels +
                                           mess_dry_waste)
                    }
                else:
                    edited_data = {
                        'dry_waste': dry_waste,
                        'wet_waste': wet_waste,
                        'e_waste': e_waste,
                        'biomedical_waste': biomedical_waste,
                        'hazardous_waste': hazardous_waste,
                        'total_waste': dry_waste + wet_waste + e_waste + biomedical_waste + hazardous_waste
                    }
                
                # Save edit and approve
                if save_pho_edit(record_data['submission_id'], submission_type, record_data, edited_data, pho_username, edit_reason):
                    if update_submission_with_edits(record_data['submission_id'], submission_type, edited_data, pho_username):
                        st.success("✅ Changes saved and submission approved!")
                        st.session_state['edit_record'] = None
                        st.rerun()
                    else:
                        st.error("❌ Error updating submission")
                else:
                    st.error("❌ Error saving edit")
        
        with col2:
            if st.form_submit_button("❌ Cancel"):
                st.session_state['edit_record'] = None
                st.rerun()



# -----------------------------------------------------------------------------
# ⚕️ PHO DASHBOARD (IMPROVED)
# -----------------------------------------------------------------------------
def show_pho_dashboard(username: str):
    st.header("PHO Dashboard")


    tab1, tab2, tab3, tab4 = st.tabs([
        "🍽️ Mess Waste Verification",
        "🏠 Hostel Waste Verification",
        "✅ Master Data",
        "📊 Dashboard"
    ])

    with tab1:
        st.subheader("🍽️ Mess Waste Data Verification")
        
        # Handle edit/verify states first
        if st.session_state.get('edit_record'):
            show_edit_form(st.session_state['edit_record'], 'mess_waste', username)
            return
        if st.session_state.get('verify_record'):
            record = st.session_state['verify_record']
            approve_submission(record, username)
            st.success("✅ Data verified successfully!")
            st.session_state['verify_record'] = None
            st.session_state['verify_key'] = None
            time.sleep(1)
            st.rerun()
        
        # Load and filter data
        data_by_hostel_date = load_pending_data_for_pho()
        mess_data = {k: v for k, v in data_by_hostel_date.items() if 'mess_waste' in k}
        
        if not mess_data:
            st.info("📜 No pending mess waste verifications at this time.")
            return
        
        # Display mess waste submissions
        for key, records in mess_data.items():
            key_parts = key.rsplit('_', 1)  # Split from right, only once
            hostel_date = key_parts[0]
            waste_type = key_parts[1]
            hostel_date_parts = hostel_date.split('_', 1)
            hostel = hostel_date_parts[0]
            date_str = hostel_date_parts[1]
            
            with st.expander(f"🍽️ Mess Waste - Hostel {hostel} - 📅 {date_str}", expanded=False):
                for idx, rec in enumerate(records):
                    st.markdown("#### Submission")
                    
                    # Display meal-wise data in 4 columns
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.write("**🌅 Breakfast**")
                        st.write(f"Students: {rec.get('breakfast_students', 0)}")
                        st.write(f"Student Waste: {rec.get('breakfast_student_waste', 0)} kg")
                        st.write(f"Counter Waste: {rec.get('breakfast_counter_waste', 0)} kg")
                        st.write(f"Vegetable Peels: {rec.get('breakfast_vegetable_peels', 0)} kg")
                    
                    with col2:
                        st.write("**🍽️ Lunch**")
                        st.write(f"Students: {rec.get('lunch_students', 0)}")
                        st.write(f"Student Waste: {rec.get('lunch_student_waste', 0)} kg")
                        st.write(f"Counter Waste: {rec.get('lunch_counter_waste', 0)} kg")
                        st.write(f"Vegetable Peels: {rec.get('lunch_vegetable_peels', 0)} kg")
                    
                    with col3:
                        st.write("**🍪 Snacks**")
                        st.write(f"Students: {rec.get('snacks_students', 0)}")
                        st.write(f"Student Waste: {rec.get('snacks_student_waste', 0)} kg")
                        st.write(f"Counter Waste: {rec.get('snacks_counter_waste', 0)} kg")
                        st.write(f"Vegetable Peels: {rec.get('snacks_vegetable_peels', 0)} kg")
                    
                    with col4:
                        st.write("**🌙 Dinner**")
                        st.write(f"Students: {rec.get('dinner_students', 0)}")
                        st.write(f"Student Waste: {rec.get('dinner_student_waste', 0)} kg")
                        st.write(f"Counter Waste: {rec.get('dinner_counter_waste', 0)} kg")
                        st.write(f"Vegetable Peels: {rec.get('dinner_vegetable_peels', 0)} kg")
                    
                    # Totals
                    st.markdown("### 📊 Totals")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Total Students", rec.get('total_students', 0))
                    with col2:
                        st.metric("Total Mess Waste", f"{rec.get('total_mess_waste', 0)} kg")
                    with col3:
                        st.metric("Mess Dry Waste", f"{rec.get('mess_dry_waste', 0)} kg")
                    
                    st.write(f"**Remarks:** {rec.get('remarks', 'N/A')}")
                    
                    display_submission_images(rec['submission_id'], 'mess_waste')
                    
                    st.write(f"**Submitted by:** {rec.get('submitted_by', 'N/A')}")
                    st.write(f"**Submitted at:** {rec.get('submitted_at', 'N/A')}")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("✅ Verify Submission", key=f"verify_mess_{hostel}_{date_str}_{rec['submission_id']}", type="primary"):
                            st.session_state['verify_record'] = rec
                            st.session_state['verify_key'] = (hostel, date_str, 'mess_waste', rec['submission_id'])
                            st.rerun()
                    with col2:
                        if st.button("✏️ Edit & Verify", key=f"edit_mess_{hostel}_{date_str}_{rec['submission_id']}"):
                            st.session_state['edit_record'] = rec
                            st.rerun()
                    
                    if idx < len(records) - 1:
                        st.markdown("---")



    with tab2:
        st.subheader("🏠 Hostel Waste Data Verification")
        
        # Handle edit/verify states first
        if st.session_state.get('edit_record'):
            show_edit_form(st.session_state['edit_record'], 'hostel_waste', username)
            return
        if st.session_state.get('verify_record'):
            if isinstance(st.session_state['verify_record'], list):
                approve_all_collections(st.session_state['verify_record'], username)
                st.success("✅ All collections verified successfully!")
            else:
                approve_submission(st.session_state['verify_record'], username)
                st.success("✅ Data verified successfully!")
            st.session_state['verify_record'] = None
            st.session_state['verify_key'] = None
            time.sleep(1)
            st.rerun()
        
        # Load and filter data
        data_by_hostel_date = load_pending_data_for_pho()
        hostel_data = {k: v for k, v in data_by_hostel_date.items() if 'hostel_waste' in k}
        
        if not hostel_data:
            st.info("📜 No pending hostel waste verifications at this time.")
            return
        
        # Display hostel waste submissions
        for key, records in hostel_data.items():
            key_parts = key.rsplit('_', 1)  # Split from right, only once
            hostel_date = key_parts[0]
            waste_type = key_parts[1]
            hostel_date_parts = hostel_date.split('_', 1)
            hostel = hostel_date_parts[0]
            date_str = hostel_date_parts[1]
            
            with st.expander(f"🏠 Hostel Waste - Hostel {hostel} - 📅 {date_str}", expanded=False):
                for idx, rec in enumerate(records):
                    st.markdown("#### Submission")
                    
                    # Display hostel waste specific data in 2 columns
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write(f"**Dry Waste:** {rec.get('dry_waste', 0)} kg")
                        st.write(f"**Wet Waste:** {rec.get('wet_waste', 0)} kg")
                        st.write(f"**E-Waste:** {rec.get('e_waste', 0)} kg")
                    
                    with col2:
                        st.write(f"**Biomedical Waste:** {rec.get('biomedical_waste', 0)} kg")
                        st.write(f"**Hazardous Waste:** {rec.get('hazardous_waste', 0)} kg")
                        st.write(f"**Total Waste:** {rec.get('total_waste', 0)} kg")
                    
                    st.write(f"**Remarks:** {rec.get('remarks', 'N/A')}")
                    
                    display_submission_images(rec['submission_id'], 'hostel_waste')
                    
                    st.write(f"**Submitted by:** {rec.get('submitted_by', 'N/A')}")
                    st.write(f"**Submitted at:** {rec.get('submitted_at', 'N/A')}")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("✅ Verify Submission", key=f"verify_hostel_{hostel}_{date_str}_{rec['submission_id']}", type="primary"):
                            st.session_state['verify_record'] = rec
                            st.session_state['verify_key'] = (hostel, date_str, 'hostel_waste', rec['submission_id'])
                            st.rerun()
                    with col2:
                        if st.button("✏️ Edit & Verify", key=f"edit_hostel_{hostel}_{date_str}_{rec['submission_id']}"):
                            st.session_state['edit_record'] = rec
                            st.rerun()
                    
                    if idx < len(records) - 1:
                        st.markdown("---")



    with tab3:
        st.subheader("📋 Master Data")
        engine = get_sqlalchemy_engine()
        if engine:
            try:
                hostels = ["All"] + get_dynamic_hostels()
                selected_hostel = st.selectbox("Filter by Hostel", hostels, key="pho_master_hostel_tab")
                query = "SELECT * FROM master_waste_data WHERE hostel = %(hostel)s" if selected_hostel != "All" else "SELECT * FROM master_waste_data"
                params = {'hostel': selected_hostel} if selected_hostel != "All" else {}
                master_df = pd.read_sql(query, engine, params=params)
                if not master_df.empty:
                    st.dataframe(master_df, use_container_width=True)
                    csv = master_df.to_csv(index=False)
                    st.download_button(
                        label="📥 Download Master Data",
                        data=csv,
                        file_name=f"pho_master_data_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv"
                    )
                else:
                    st.info("No master data found for the selected filters.")
            except Exception as e:
                st.error(f"Error loading master data: {e}")
            finally:
                engine.dispose()

    with tab4:
        st.subheader("📊 PHO Dashboard")
        df = load_master_data()
        show_dashboard_content(df, "PHO_")



def show_waste_details_view(username: str):
    """Show detailed view of individual waste collections"""
    records = st.session_state['show_waste_details']
    hostel, date_str = st.session_state['waste_details_key']
    
    st.subheader(f"🏠 Hostel {hostel} - 📅 {date_str} - Waste Collection Details")
    
    if st.button("⬅️ Back to Summary", key="back_to_summary"):
        st.session_state['show_waste_details'] = None
        st.session_state['waste_details_key'] = None
        st.rerun()
    
    st.markdown("---")
    
    for idx, rec in enumerate(records, start=1):
        st.markdown(f"### Collection {idx}")
        
        # Hostel waste data display
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Dry Waste:** {rec.get('dry_waste', 0)} kg")
            st.write(f"**Wet Waste:** {rec.get('wet_waste', 0)} kg")
            st.write(f"**E-Waste:** {rec.get('e_waste', 0)} kg")
        with col2:
            st.write(f"**Biomedical Waste:** {rec.get('biomedical_waste', 0)} kg")
            st.write(f"**Hazardous Waste:** {rec.get('hazardous_waste', 0)} kg")
            st.write(f"**Total Waste:** {rec.get('total_waste', 0)} kg")
        
        if rec.get('remarks'):
            st.write(f"**Remarks:** {rec.get('remarks', '')}")
        
        # Display images if available
        display_submission_images(rec['submission_id'], 'hostel_waste')
        
        st.write(f"**Submitted by:** {rec.get('submitted_by', 'N/A')}")
        st.write(f"**Submitted at:** {rec.get('submitted_at', 'N/A')}")
        
        # Verify button for individual collections
        if st.button(f"✅ Verify Collection {idx}", key=f"verify_detail_{hostel}_{date_str}_{idx}", type="primary"):
            st.session_state['verify_record'] = rec
            st.session_state['verify_key'] = (hostel, date_str, 'hostel_waste', idx)
            st.session_state['show_waste_details'] = None
            st.session_state['waste_details_key'] = None
            st.rerun()
        
        st.markdown("---")

# -----------------------------------------------------------------------------
# 👤 ADMIN DASHBOARD (IMPROVED)
# -----------------------------------------------------------------------------
def show_admin_dashboard(username: str):
    st.header("👤 Administrator Dashboard")
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Dashboard", "👥 User Management", "📋 Waste Data", "✏️ PHO Edits", "🗄️ Data Storage"
    ])

    with tab1:
        st.subheader("📊 System Dashboard")
        df = load_master_data()
        show_dashboard_content(df, "Admin_")

    with tab2:
        st.subheader("User Management")
        st.markdown("### ➕ Add New User")
        with st.form("add_user_form"):
            col1, col2 = st.columns(2)
            with col1:
                new_username = st.text_input("Username")
                new_name = st.text_input("Full Name")
            with col2:
                new_role = st.selectbox("Role", ["pho_supervisor", "pho"])
                new_password = st.text_input("Password", type="password")
            if st.form_submit_button("Add User"):
                if new_username and new_name and new_password:
                    if new_role == "pho" and not new_username.startswith("pho_supervisor_"):
                        formatted_username = f"pho_supervisor_{new_username}"
                    else:
                        formatted_username = new_username
                    if add_user(formatted_username, new_name, new_password, new_role):
                        st.success(f"✅ User {formatted_username} added successfully! New hostel '{get_hostel_from_username(formatted_username)}' is now active everywhere.")
                        st.rerun()
                    else:
                        st.error("❌ Failed to add user")
                else:
                    st.error("❌ Please fill all fields")
        st.markdown("---")
        users = get_all_users()
        if users:
            users_df = pd.DataFrame(users)
            st.dataframe(users_df, use_container_width=True)
            st.markdown("### 🗑️ Delete User")
            user_to_delete = st.selectbox("Select user to delete", [u["username"] for u in users])
            @st.dialog("Confirm User Deletion")
            def confirm_delete_user(user_to_delete):
                st.warning(f"Are you sure you want to delete user '{user_to_delete}'? This cannot be undone.")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Confirm Delete", type="primary"):
                        if delete_user(user_to_delete):
                            st.success(f"✅ User {user_to_delete} deleted successfully!")
                            st.rerun()
                        else:
                            st.error("❌ Failed to delete user")
                with col2:
                    if st.button("Cancel"):
                        st.rerun()

            if st.button("Delete User", type="secondary"):
                if user_to_delete != "admin":
                    confirm_delete_user(user_to_delete)
                else:
                    st.error("❌ Cannot delete admin user")

        else:
            st.info("No users found")

    with tab3:
        st.subheader("📊 Waste Data Overview")
        df = load_master_data()
        if not df.empty:
            col1, col2, col3 = st.columns(3)
            hostels = ["All"] + get_dynamic_hostels()
            selected_hostel = st.selectbox("Filter by Hostel", hostels, key="admin_waste_hostel")
            date_range = st.date_input("Filter by Date Range", [df["date"].min(), df["date"].max()], key="admin_waste_date")
            filtered_df = df.copy()
            if selected_hostel != "All":
                filtered_df = filtered_df[filtered_df["hostel"] == selected_hostel]
            if len(date_range) == 2:
                filtered_df = filtered_df[
                    (pd.to_datetime(filtered_df["date"]) >= pd.to_datetime(date_range[0])) &
                    (pd.to_datetime(filtered_df["date"]) <= pd.to_datetime(date_range[1]))
                ]

            st.dataframe(filtered_df, use_container_width=True)
            csv = filtered_df.to_csv(index=False)
            st.download_button(
                label="📥 Download Waste Data",
                data=csv,
                file_name=f"admin_waste_data_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
            st.markdown("### 📈 Data Summary")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Records", len(filtered_df))
            with col2:
                total_mess = filtered_df["total_mess_waste"].sum() if "total_mess_waste" in filtered_df.columns else 0
                st.metric("Total Mess Waste", f"{total_mess:.1f} kg")
            with col3:
                total_hostel = filtered_df["total_hostel_waste"].sum() if "total_hostel_waste" in filtered_df.columns else 0
                st.metric("Total Hostel Waste", f"{total_hostel:.1f} kg")
        else:
            st.info("No waste data available.")

    with tab4:
        st.subheader("📝 PHO Edit History")
        
        # Load PHO edits data
        edits_df = get_pho_edits_data()
        
        if not edits_df.empty:
            # Summary metrics
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Total Edits", len(edits_df))
            
            with col2:
                mess_edits = len(edits_df[edits_df['submission_type'] == 'mess_waste'])
                st.metric("Mess Waste Edits", mess_edits)
            
            with col3:
                hostel_edits = len(edits_df[edits_df['submission_type'] == 'hostel_waste'])
                st.metric("Hostel Waste Edits", hostel_edits)
            
            with col4:
                unique_editors = edits_df['edited_by'].nunique()
                st.metric("Active Editors", unique_editors)
            
            st.markdown("---")
            
            # Filters
            col1, col2, col3 = st.columns(3)
            
            with col1:
                submission_type_filter = st.selectbox(
                    "Filter by Type",
                    ["All", "mess_waste", "hostel_waste"],
                    key="edit_type_filter"
                )
            
            with col2:
                hostel_filter = st.selectbox(
                    "Filter by Hostel",
                    ["All"] + sorted(edits_df['hostel'].dropna().unique().tolist()),
                    key="edit_hostel_filter"
                )
            
            with col3:
                editor_filter = st.selectbox(
                    "Filter by Editor",
                    ["All"] + sorted(edits_df['edited_by'].unique().tolist()),
                    key="edit_editor_filter"
                )
            
            # Apply filters
            filtered_df = edits_df.copy()
            
            if submission_type_filter != "All":
                filtered_df = filtered_df[filtered_df['submission_type'] == submission_type_filter]
            
            if hostel_filter != "All":
                filtered_df = filtered_df[filtered_df['hostel'] == hostel_filter]
            
            if editor_filter != "All":
                filtered_df = filtered_df[filtered_df['edited_by'] == editor_filter]
            
            st.markdown(f"**Showing {len(filtered_df)} of {len(edits_df)} edits**")
            
            if not filtered_df.empty:
                # Display edits with comparison
                for _, edit_record in filtered_df.iterrows():
                    # Edit header
                    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                    
                    with col1:
                        st.write(f"**{edit_record['submission_type'].replace('_', ' ').title()}** - Submission #{edit_record['submission_id']}")
                    
                    with col2:
                        st.write(f"**Hostel:** {edit_record['hostel']}")
                    
                    with col3:
                        st.write(f"**Date:** {edit_record['submission_date']}")
                    
                    with col4:
                        st.write(f"**Edited:** {edit_record['edited_at'].strftime('%Y-%m-%d %H:%M')}")
                    
                    # Show detailed comparison
                    show_edit_comparison(edit_record)
                    
                    st.markdown("---")
            else:
                st.info("No edits found matching the selected filters.")
            
            # Export functionality
            st.markdown("### 📥 Export Edit History")
            
            if st.button("Download Edit History CSV", use_container_width=True):
                # Prepare data for export
                export_df = filtered_df.copy()
                
                # Flatten JSON data for CSV export
                export_rows = []
                for _, row in export_df.iterrows():
                    try:
                        original = json.loads(row['original_data'])
                        edited = json.loads(row['edited_data'])
                        
                        # Find changes
                        changes = []
                        for key, value in edited.items():
                            if value != original.get(key):
                                changes.append(f"{key}: {original.get(key)} → {value}")
                        
                        export_row = {
                            'Edit ID': row['edit_id'],
                            'Submission Type': row['submission_type'],
                            'Submission ID': row['submission_id'],
                            'Hostel': row['hostel'],
                            'Submission Date': row['submission_date'],
                            'Edited By': row['edited_by'],
                            'Edited At': row['edited_at'],
                            'Reason': row['reason'] or 'No reason provided',
                            'Changes Made': '; '.join(changes) if changes else 'No changes detected'
                        }
                        export_rows.append(export_row)
                        
                    except Exception as e:
                        st.error(f"Error processing edit {row['edit_id']}: {e}")
                
                if export_rows:
                    export_df_final = pd.DataFrame(export_rows)
                    csv = export_df_final.to_csv(index=False)
                    
                    st.download_button(
                        label="💾 Download CSV",
                        data=csv,
                        file_name=f"pho_edit_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
        else:
            st.info("📝 No PHO edits found in the system.")
            st.write("PHO edits will appear here when PHO officers modify submitted data.")
            
            # Show example of what edits look like
            with st.expander("ℹ️ About PHO Edits"):
                st.write("""
                **PHO Edit Tracking includes:**
                - Original submitted data
                - Modified data after PHO review
                - Timestamp and editor information
                - Reason for modification
                - Side-by-side comparison view
                - Export functionality for audit trails
                """)


    with tab5:
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 🍽️ Mess Images Storage")
            
            # Get storage info
            mess_size, mess_files = get_supabase_storage_usage('mess-images')
            mess_size_mb = mess_size / 1024 / 1024
            
            st.metric("Storage Used", f"{mess_size_mb:.2f} MB")
            st.metric("Total Files", len(mess_files))
            
            # Show recent files
            if mess_files:
                st.write("**Recent Files:**")
                recent_files = sorted(mess_files, key=lambda x: x.get('created', ''), reverse=True)[:5]
                for file in recent_files:
                    st.write(f"📸 {file['name']} ({file['size']/1024:.1f} KB)")
            
            # Download button
            if st.button("📥 Download All Mess Images", use_container_width=True):
                with st.spinner("Creating ZIP file..."):
                    zip_data = download_supabase_images('mess-images')
                    if zip_data:
                        st.download_button(
                            label="💾 Download ZIP File",
                            data=zip_data,
                            file_name=f"mess_images_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                            mime="application/zip",
                            use_container_width=True
                        )
            
            # Delete button
            if st.button("🗑️ Delete All Mess Images", type="secondary", use_container_width=True):
                if st.checkbox("⚠️ I understand this will permanently delete all mess images", key="delete_mess_confirm"):
                    if st.button("🗑️ Confirm Delete All", type="secondary", key="confirm_delete_mess"):
                        with st.spinner("Deleting images..."):
                            if delete_supabase_images('mess-images'):
                                st.success("✅ All mess images deleted successfully!")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error("❌ Failed to delete images")
        
        with col2:
            st.markdown("### 🏠 Hostel Images Storage")
            
            # Get storage info
            hostel_size, hostel_files = get_supabase_storage_usage('hostel-images')
            hostel_size_mb = hostel_size / 1024 / 1024
            
            st.metric("Storage Used", f"{hostel_size_mb:.2f} MB")
            st.metric("Total Files", len(hostel_files))
            
            # Show recent files
            if hostel_files:
                st.write("**Recent Files:**")
                recent_files = sorted(hostel_files, key=lambda x: x.get('created', ''), reverse=True)[:5]
                for file in recent_files:
                    st.write(f"📸 {file['name']} ({file['size']/1024:.1f} KB)")
            
            # Download button
            if st.button("📥 Download All Hostel Images", use_container_width=True):
                with st.spinner("Creating ZIP file..."):
                    zip_data = download_supabase_images('hostel-images')
                    if zip_data:
                        st.download_button(
                            label="💾 Download ZIP File",
                            data=zip_data,
                            file_name=f"hostel_images_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                            mime="application/zip",
                            use_container_width=True
                        )
            
            # Delete button
            if st.button("🗑️ Delete All Hostel Images", type="secondary", use_container_width=True):
                if st.checkbox("⚠️ I understand this will permanently delete all hostel images", key="delete_hostel_confirm"):
                    if st.button("🗑️ Confirm Delete All", type="secondary", key="confirm_delete_hostel"):
                        with st.spinner("Deleting images..."):
                            if delete_supabase_images('hostel-images'):
                                st.success("✅ All hostel images deleted successfully!")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error("❌ Failed to delete images")
        
        # Overall storage summary
        st.markdown("---")
        st.markdown("### 📊 Total Storage Summary")
        total_size_mb = mess_size_mb + hostel_size_mb
        total_files = len(mess_files) + len(hostel_files)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Storage", f"{total_size_mb:.2f} MB")
        with col2:
            st.metric("Total Files", total_files)
        with col3:
            supabase_url = os.getenv("SUPABASE_URL", "").replace("https://", "").split(".")[0]
            if st.button("🔗 Open Supabase Dashboard"):
                st.write(f"Go to: https://supabase.com/dashboard/project/{supabase_url}/storage/buckets")

# -----------------------------------------------------------------------------
# 🏠 MAIN APPLICATION
# -----------------------------------------------------------------------------
def main():
    init_session_state()
    if not ensure_data_structure():
        st.error("❌ Failed to initialize database. Please check your PostgreSQL connection.")
        st.info("💡 Make sure PostgreSQL is running and the database 'waste_management' exists.")
        st.stop()
    check_session_validity()
    if not st.session_state.get("authentication_status"):
        show_login_form()
        return
    with st.sidebar:
        st.markdown(f"### 👋 Welcome, {st.session_state.name}")
        role_names = {
            "admin": "Administrator",
            "pho_supervisor": "PHO Supervisor", 
            "pho": "PHO"
        }
        st.markdown(f"**Role:** {role_names.get(st.session_state.role, st.session_state.role)}")
        if st.session_state.role == "pho_supervisor":
            user_hostel = get_hostel_from_username(st.session_state.username)
            if user_hostel:
                st.markdown(f"**Assigned Hostel:** {user_hostel}")
        st.markdown("---")
        if st.button("🚪 Logout", use_container_width=True):
            clear_session_state()
            st.rerun()
    if st.session_state.role == "admin":
        show_admin_dashboard(st.session_state.username)
    elif st.session_state.role == "pho_supervisor":
        show_pho_supervisor_form(st.session_state.username)
    elif st.session_state.role == "pho":
        show_pho_dashboard(st.session_state.username)
    else:
        st.error("❌ Invalid role")

if __name__ == "__main__":
    main()
