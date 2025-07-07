import psycopg2
import bcrypt
import random
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database configuration - uses your .env file
DB_CONFIG = dict(
    host=os.getenv("DB_HOST"),
    database=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASS"),
    port=os.getenv("DB_PORT")
)

PHO_SUPERVISORS = [
    ("pho_supervisor_2", "2"),
    ("pho_supervisor_10", "10"),
    ("pho_supervisor_11", "11"),
    ("pho_supervisor_12", "12-13-14"),
    ("pho_supervisor_18", "18"),
]

def random_float(a, b, digits=2):
    return round(random.uniform(a, b), digits)

def random_int(a, b):
    return random.randint(a, b)

def random_time():
    hour = random_int(6, 9)
    minute = random_int(0, 59)
    return f"{hour:02d}:{minute:02d}"

def create_all_tables():
    """Create all tables with correct schema"""
    print("🔧 Creating database tables...")
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Drop existing tables
    tables_to_drop = [
        "pho_edits", "submission_images", "master_waste_data", 
        "mess_waste_submissions", "hostel_waste_submissions", "users"
    ]
    
    for table in tables_to_drop:
        cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
        print(f"  Dropped {table}")

    # Create users table
    cur.execute("""
    CREATE TABLE users (
        username VARCHAR PRIMARY KEY,
        name VARCHAR NOT NULL,
        password_hash VARCHAR NOT NULL,
        role VARCHAR NOT NULL
    );
    """)

    # Create mess waste submissions table
    cur.execute("""
    CREATE TABLE mess_waste_submissions (
        submission_id SERIAL PRIMARY KEY,
        hostel VARCHAR NOT NULL,
        submission_date DATE NOT NULL,
        collection_time TIME NOT NULL,
        breakfast_students INTEGER DEFAULT 0,
        breakfast_student_waste FLOAT DEFAULT 0,
        breakfast_counter_waste FLOAT DEFAULT 0,
        breakfast_vegetable_peels FLOAT DEFAULT 0,
        lunch_students INTEGER DEFAULT 0,
        lunch_student_waste FLOAT DEFAULT 0,
        lunch_counter_waste FLOAT DEFAULT 0,
        lunch_vegetable_peels FLOAT DEFAULT 0,
        snacks_students INTEGER DEFAULT 0,
        snacks_student_waste FLOAT DEFAULT 0,
        snacks_counter_waste FLOAT DEFAULT 0,
        snacks_vegetable_peels FLOAT DEFAULT 0,
        dinner_students INTEGER DEFAULT 0,
        dinner_student_waste FLOAT DEFAULT 0,
        dinner_counter_waste FLOAT DEFAULT 0,
        dinner_vegetable_peels FLOAT DEFAULT 0,
        mess_dry_waste FLOAT DEFAULT 0,
        total_students INTEGER DEFAULT 0,
        total_mess_waste FLOAT DEFAULT 0,
        remarks TEXT,
        status VARCHAR DEFAULT 'pending',
        submitted_by VARCHAR NOT NULL,
        submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        verified_by VARCHAR,
        verified_at TIMESTAMP
    );
    """)

    # Create hostel waste submissions table
    cur.execute("""
    CREATE TABLE hostel_waste_submissions (
        submission_id SERIAL PRIMARY KEY,
        hostel VARCHAR NOT NULL,
        submission_date DATE NOT NULL,
        collection_time TIME NOT NULL,
        dry_waste FLOAT DEFAULT 0,
        wet_waste FLOAT DEFAULT 0,
        e_waste FLOAT DEFAULT 0,
        biomedical_waste FLOAT DEFAULT 0,
        hazardous_waste FLOAT DEFAULT 0,
        total_waste FLOAT DEFAULT 0,
        remarks TEXT,
        status VARCHAR DEFAULT 'pending',
        submitted_by VARCHAR NOT NULL,
        submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        verified_by VARCHAR,
        verified_at TIMESTAMP
    );
    """)

    # Create master waste data table
    cur.execute("""
    CREATE TABLE master_waste_data (
        id SERIAL PRIMARY KEY,
        hostel VARCHAR NOT NULL,
        date DATE NOT NULL,
        breakfast_student_waste FLOAT DEFAULT 0,
        breakfast_counter_waste FLOAT DEFAULT 0,
        breakfast_vegetable_peels FLOAT DEFAULT 0,
        lunch_student_waste FLOAT DEFAULT 0,
        lunch_counter_waste FLOAT DEFAULT 0,
        lunch_vegetable_peels FLOAT DEFAULT 0,
        snacks_student_waste FLOAT DEFAULT 0,
        snacks_counter_waste FLOAT DEFAULT 0,
        snacks_vegetable_peels FLOAT DEFAULT 0,
        dinner_student_waste FLOAT DEFAULT 0,
        dinner_counter_waste FLOAT DEFAULT 0,
        dinner_vegetable_peels FLOAT DEFAULT 0,
        total_students INTEGER DEFAULT 0,
        mess_dry_waste FLOAT DEFAULT 0,
        total_mess_waste FLOAT DEFAULT 0,
        total_mess_waste_no_peels FLOAT DEFAULT 0,
        per_capita_mess_waste FLOAT DEFAULT 0,
        per_capita_mess_waste_no_peels FLOAT DEFAULT 0,
        dry_waste FLOAT DEFAULT 0,
        wet_waste FLOAT DEFAULT 0,
        e_waste FLOAT DEFAULT 0,
        biomedical_waste FLOAT DEFAULT 0,
        hazardous_waste FLOAT DEFAULT 0,
        total_hostel_waste FLOAT DEFAULT 0
    );
    """)

    # Create submission images table
    cur.execute("""
    CREATE TABLE submission_images (
        id SERIAL PRIMARY KEY,
        submission_type VARCHAR NOT NULL,
        submission_id INTEGER NOT NULL,
        image_url TEXT NOT NULL,
        image_filename VARCHAR NOT NULL,
        file_size INTEGER,
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Create pho edits table
    cur.execute("""
    CREATE TABLE pho_edits (
        edit_id SERIAL PRIMARY KEY,
        submission_type VARCHAR NOT NULL,
        submission_id INTEGER NOT NULL,
        original_data JSONB NOT NULL,
        edited_data JSONB NOT NULL,
        edited_by VARCHAR NOT NULL,
        edited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        reason TEXT
    );
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("✅ All tables created successfully")

def create_default_users():
    """Create all default users with hashed passwords"""
    print("👥 Creating default users...")
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    users = [
        ("admin", "Admin User", "adminpass", "admin"),
        ("pho", "PHO", "phopass", "pho"),
        ("pho1", "PHO One", "phopass1", "pho"),
        ("pho_supervisor_2", "PHO Supervisor 2", "phosuppass2", "pho_supervisor"),
        ("pho_supervisor_10", "PHO Supervisor 10", "phosuppass10", "pho_supervisor"),
        ("pho_supervisor_11", "PHO Supervisor 11", "phosuppass11", "pho_supervisor"),
        ("pho_supervisor_12", "PHO Supervisor 12-13-14", "phosuppass12", "pho_supervisor"),
        ("pho_supervisor_18", "PHO Supervisor 18", "phosuppass18", "pho_supervisor"),
    ]

    for username, name, password, role in users:
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        cur.execute(
            "INSERT INTO users (username, name, password_hash, role) VALUES (%s, %s, %s, %s)",
            (username, name, hashed.decode('utf-8'), role)
        )
        print(f"  Created user: {username} ({role})")

    conn.commit()
    cur.close()
    conn.close()
    print("✅ Default users created successfully")

def generate_mess_submissions():
    """Generate 2 months of mess waste submissions"""
    print("🍽️ Generating mess waste submissions...")
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    today = datetime.now().date()
    start_date = today - timedelta(days=59)  # 2 months
    mess_rows = []

    hostel_base_values = {
        "2": {"students": 180},
        "10": {"students": 200},
        "11": {"students": 190},
        "12-13-14": {"students": 450},
        "18": {"students": 210}
    }

    for supervisor, hostel in PHO_SUPERVISORS:
        base_vals = hostel_base_values[hostel]
        print(f"  Generating data for Hostel {hostel}...")
        
        for i in range(60):  # 60 days = 2 months
            day = start_date + timedelta(days=i)

            # Generate consistent student counts with small variation
            total_students = base_vals["students"] + random.randint(-10, 10)
            
            # Distribute students across meals
            breakfast_students = int(total_students * 0.25 + random.randint(-5, 5))
            lunch_students = int(total_students * 0.30 + random.randint(-5, 5))
            snacks_students = int(total_students * 0.20 + random.randint(-3, 3))
            dinner_students = int(total_students * 0.25 + random.randint(-5, 5))

            # Generate consistent waste per student
            waste_per_student = random.uniform(0.08, 0.12)
            
            # Breakfast waste
            breakfast_student_waste = round(breakfast_students * waste_per_student * 0.7, 2)
            breakfast_counter_waste = round(breakfast_students * waste_per_student * 0.2, 2)
            breakfast_vegetable_peels = round(breakfast_students * waste_per_student * 0.1, 2)

            # Lunch waste (higher)
            lunch_waste_per_student = waste_per_student * 1.2
            lunch_student_waste = round(lunch_students * lunch_waste_per_student * 0.6, 2)
            lunch_counter_waste = round(lunch_students * lunch_waste_per_student * 0.25, 2)
            lunch_vegetable_peels = round(lunch_students * lunch_waste_per_student * 0.15, 2)

            # Snacks waste (lower)
            snacks_waste_per_student = waste_per_student * 0.6
            snacks_student_waste = round(snacks_students * snacks_waste_per_student * 0.8, 2)
            snacks_counter_waste = round(snacks_students * snacks_waste_per_student * 0.15, 2)
            snacks_vegetable_peels = round(snacks_students * snacks_waste_per_student * 0.05, 2)

            # Dinner waste
            dinner_waste_per_student = waste_per_student * 1.1
            dinner_student_waste = round(dinner_students * dinner_waste_per_student * 0.65, 2)
            dinner_counter_waste = round(dinner_students * dinner_waste_per_student * 0.25, 2)
            dinner_vegetable_peels = round(dinner_students * dinner_waste_per_student * 0.1, 2)

            # Dry waste
            mess_dry_waste = round(random.uniform(2, 8), 2)
            
            # Calculate total
            total_mess_waste = round(
                breakfast_student_waste + breakfast_counter_waste + breakfast_vegetable_peels +
                lunch_student_waste + lunch_counter_waste + lunch_vegetable_peels +
                snacks_student_waste + snacks_counter_waste + snacks_vegetable_peels +
                dinner_student_waste + dinner_counter_waste + dinner_vegetable_peels +
                mess_dry_waste, 2
            )

            # Status: older entries verified, recent ones pending
            if day < today - timedelta(days=3):
                status = "verified"
                verified_by = "pho"
                verified_at = datetime.now() - timedelta(days=random_int(0, 3))
            else:
                status = "pending"
                verified_by = None
                verified_at = None

            mess_rows.append((
                hostel, day, random_time(),
                breakfast_students, breakfast_student_waste, breakfast_counter_waste, breakfast_vegetable_peels,
                lunch_students, lunch_student_waste, lunch_counter_waste, lunch_vegetable_peels,
                snacks_students, snacks_student_waste, snacks_counter_waste, snacks_vegetable_peels,
                dinner_students, dinner_student_waste, dinner_counter_waste, dinner_vegetable_peels,
                mess_dry_waste, total_students, total_mess_waste,
                "Routine collection", status, supervisor, datetime.now(), verified_by, verified_at
            ))

    # Insert in batches to avoid timeout
    batch_size = 50
    for i in range(0, len(mess_rows), batch_size):
        batch = mess_rows[i:i+batch_size]
        cur.executemany("""
        INSERT INTO mess_waste_submissions (
            hostel, submission_date, collection_time,
            breakfast_students, breakfast_student_waste, breakfast_counter_waste, breakfast_vegetable_peels,
            lunch_students, lunch_student_waste, lunch_counter_waste, lunch_vegetable_peels,
            snacks_students, snacks_student_waste, snacks_counter_waste, snacks_vegetable_peels,
            dinner_students, dinner_student_waste, dinner_counter_waste, dinner_vegetable_peels,
            mess_dry_waste, total_students, total_mess_waste,
            remarks, status, submitted_by, submitted_at, verified_by, verified_at
        ) VALUES (
            %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s, %s, %s
        );
        """, batch)
        conn.commit()
        print(f"  Inserted batch {i//batch_size + 1}/{(len(mess_rows)-1)//batch_size + 1}")

    cur.close()
    conn.close()
    print(f"✅ Generated {len(mess_rows)} mess waste submissions")

def generate_hostel_submissions():
    """Generate 2 months of hostel waste submissions"""
    print("🏠 Generating hostel waste submissions...")
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    today = datetime.now().date()
    start_date = today - timedelta(days=59)
    hostel_rows = []

    hostel_base_values = {
        "2": {"base": 8},
        "10": {"base": 9},
        "11": {"base": 8.5},
        "12-13-14": {"base": 20},
        "18": {"base": 10}
    }

    for supervisor, hostel in PHO_SUPERVISORS:
        base_vals = hostel_base_values[hostel]
        print(f"  Generating data for Hostel {hostel}...")
        
        for i in range(60):
            day = start_date + timedelta(days=i)

            # Generate consistent hostel waste with small variation
            hostel_base = base_vals["base"]
            dry_waste = round(hostel_base * 0.5 + random.uniform(-0.3, 0.3), 2)
            wet_waste = round(hostel_base * 0.3 + random.uniform(-0.2, 0.2), 2)
            e_waste = round(hostel_base * 0.1 + random.uniform(-0.05, 0.05), 2)
            biomedical = round(hostel_base * 0.05 + random.uniform(-0.02, 0.02), 2)
            hazardous = round(hostel_base * 0.05 + random.uniform(-0.02, 0.02), 2)
            total_waste = round(dry_waste + wet_waste + e_waste + biomedical + hazardous, 2)

            # Status: older entries verified, recent ones pending
            if day < today - timedelta(days=3):
                status = "verified"
                verified_by = "pho"
                verified_at = datetime.now() - timedelta(days=random_int(0, 3))
            else:
                status = "pending"
                verified_by = None
                verified_at = None

            hostel_rows.append((
                hostel, day, random_time(),
                dry_waste, wet_waste, e_waste, biomedical, hazardous, total_waste,
                "Routine", status, supervisor, datetime.now(), verified_by, verified_at
            ))

    # Insert in batches
    batch_size = 50
    for i in range(0, len(hostel_rows), batch_size):
        batch = hostel_rows[i:i+batch_size]
        cur.executemany("""
        INSERT INTO hostel_waste_submissions (
            hostel, submission_date, collection_time,
            dry_waste, wet_waste, e_waste, biomedical_waste, hazardous_waste, total_waste,
            remarks, status, submitted_by, submitted_at, verified_by, verified_at
        ) VALUES (
            %s, %s, %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s
        );
        """, batch)
        conn.commit()
        print(f"  Inserted batch {i//batch_size + 1}/{(len(hostel_rows)-1)//batch_size + 1}")

    cur.close()
    conn.close()
    print(f"✅ Generated {len(hostel_rows)} hostel waste submissions")

def generate_master_data():
    """Generate 2 months of master data for dashboard"""
    print("📊 Generating master waste data...")
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    today = datetime.now().date()
    start_date = today - timedelta(days=59)
    master_rows = []

    hostel_base_values = {
        "2": {"students": 180, "mess_base": 25, "hostel_base": 8},
        "10": {"students": 200, "mess_base": 28, "hostel_base": 9},
        "11": {"students": 190, "mess_base": 26, "hostel_base": 8.5},
        "12-13-14": {"students": 450, "mess_base": 65, "hostel_base": 20},
        "18": {"students": 210, "mess_base": 30, "hostel_base": 10}
    }

    for supervisor, hostel in PHO_SUPERVISORS:
        base_vals = hostel_base_values[hostel]
        print(f"  Generating master data for Hostel {hostel}...")
        
        for i in range(60):
            day = start_date + timedelta(days=i)

            # Generate consistent data
            total_students = base_vals["students"] + random.randint(-10, 10)
            waste_per_student = random.uniform(0.08, 0.12)
            
            # Breakfast
            breakfast_students = int(total_students * 0.25)
            breakfast_student_waste = round(breakfast_students * waste_per_student * 0.7, 2)
            breakfast_counter_waste = round(breakfast_students * waste_per_student * 0.2, 2)
            breakfast_vegetable_peels = round(breakfast_students * waste_per_student * 0.1, 2)

            # Lunch
            lunch_students = int(total_students * 0.30)
            lunch_waste_per_student = waste_per_student * 1.2
            lunch_student_waste = round(lunch_students * lunch_waste_per_student * 0.6, 2)
            lunch_counter_waste = round(lunch_students * lunch_waste_per_student * 0.25, 2)
            lunch_vegetable_peels = round(lunch_students * lunch_waste_per_student * 0.15, 2)

            # Snacks
            snacks_students = int(total_students * 0.20)
            snacks_waste_per_student = waste_per_student * 0.6
            snacks_student_waste = round(snacks_students * snacks_waste_per_student * 0.8, 2)
            snacks_counter_waste = round(snacks_students * snacks_waste_per_student * 0.15, 2)
            snacks_vegetable_peels = round(snacks_students * snacks_waste_per_student * 0.05, 2)

            # Dinner
            dinner_students = int(total_students * 0.25)
            dinner_waste_per_student = waste_per_student * 1.1
            dinner_student_waste = round(dinner_students * dinner_waste_per_student * 0.65, 2)
            dinner_counter_waste = round(dinner_students * dinner_waste_per_student * 0.25, 2)
            dinner_vegetable_peels = round(dinner_students * dinner_waste_per_student * 0.1, 2)

            # Mess totals
            mess_dry_waste = round(base_vals["mess_base"] * 0.15 + random.uniform(-0.5, 0.5), 2)
            total_mess_waste = round(
                breakfast_student_waste + breakfast_counter_waste + breakfast_vegetable_peels +
                lunch_student_waste + lunch_counter_waste + lunch_vegetable_peels +
                snacks_student_waste + snacks_counter_waste + snacks_vegetable_peels +
                dinner_student_waste + dinner_counter_waste + dinner_vegetable_peels +
                mess_dry_waste, 2
            )

            # Per capita calculations
            veg_peels_total = breakfast_vegetable_peels + lunch_vegetable_peels + snacks_vegetable_peels + dinner_vegetable_peels
            total_mess_waste_no_peels = round(total_mess_waste - veg_peels_total, 2)
            per_capita_mess_waste = round(total_mess_waste / total_students, 3) if total_students > 0 else 0
            per_capita_mess_waste_no_peels = round(total_mess_waste_no_peels / total_students, 3) if total_students > 0 else 0

            # Hostel waste
            hostel_base = base_vals["hostel_base"]
            dry_waste = round(hostel_base * 0.5 + random.uniform(-0.3, 0.3), 2)
            wet_waste = round(hostel_base * 0.3 + random.uniform(-0.2, 0.2), 2)
            e_waste = round(hostel_base * 0.1 + random.uniform(-0.05, 0.05), 2)
            biomedical = round(hostel_base * 0.05 + random.uniform(-0.02, 0.02), 2)
            hazardous = round(hostel_base * 0.05 + random.uniform(-0.02, 0.02), 2)
            total_hostel_waste = round(dry_waste + wet_waste + e_waste + biomedical + hazardous, 2)

            master_rows.append((
                hostel, day,
                breakfast_student_waste, breakfast_counter_waste, breakfast_vegetable_peels,
                lunch_student_waste, lunch_counter_waste, lunch_vegetable_peels,
                snacks_student_waste, snacks_counter_waste, snacks_vegetable_peels,
                dinner_student_waste, dinner_counter_waste, dinner_vegetable_peels,
                total_students, mess_dry_waste, total_mess_waste, total_mess_waste_no_peels,
                per_capita_mess_waste, per_capita_mess_waste_no_peels,
                dry_waste, wet_waste, e_waste, biomedical, hazardous, total_hostel_waste
            ))

    # Insert in batches
    batch_size = 50
    for i in range(0, len(master_rows), batch_size):
        batch = master_rows[i:i+batch_size]
        cur.executemany("""
        INSERT INTO master_waste_data (
            hostel, date,
            breakfast_student_waste, breakfast_counter_waste, breakfast_vegetable_peels,
            lunch_student_waste, lunch_counter_waste, lunch_vegetable_peels,
            snacks_student_waste, snacks_counter_waste, snacks_vegetable_peels,
            dinner_student_waste, dinner_counter_waste, dinner_vegetable_peels,
            total_students, mess_dry_waste, total_mess_waste, total_mess_waste_no_peels,
            per_capita_mess_waste, per_capita_mess_waste_no_peels,
            dry_waste, wet_waste, e_waste, biomedical_waste, hazardous_waste, total_hostel_waste
        ) VALUES (
            %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s,
            %s, %s, %s, %s, %s, %s
        );
        """, batch)
        conn.commit()
        print(f"  Inserted batch {i//batch_size + 1}/{(len(master_rows)-1)//batch_size + 1}")

    cur.close()
    conn.close()
    print(f"✅ Generated {len(master_rows)} master data entries")

def main():
    """Run complete data generation"""
    print("🚀 Starting complete sample data generation for Supabase...")
    print("=" * 60)
    
    try:
        # Step 1: Create tables
        create_all_tables()
        print()
        
        # Step 2: Create users
        create_default_users()
        print()
        
        # Step 3: Generate mess waste submissions
        generate_mess_submissions()
        print()
        
        # Step 4: Generate hostel waste submissions
        generate_hostel_submissions()
        print()
        
        # Step 5: Generate master data
        generate_master_data()
        print()
        
        print("=" * 60)
        print("✅ Complete sample data generation finished!")
        print("📊 Summary:")
        print("- 8 users created (admin, PHOs, PHO supervisors)")
        print("- 300 mess waste submissions (60 days × 5 hostels)")
        print("- 300 hostel waste submissions (60 days × 5 hostels)")
        print("- 300 master data entries (60 days × 5 hostels)")
        print("- Recent 3 days: pending submissions")
        print("- Older entries: verified submissions")
        print()
        print("🎉 Your Supabase database is now ready for testing!")
        print("🔗 You can now test your app with all functionalities")
        
    except Exception as e:
        print(f"❌ Error during data generation: {e}")
        print("Make sure your .env file has correct Supabase credentials")

if __name__ == "__main__":
    main()
