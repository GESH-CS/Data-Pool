# 🌱 Waste Management System

A comprehensive Streamlit web application for managing hostel and mess waste data with real-time analytics, image uploads, and approval workflows. Built with Supabase backend for scalable data management.

![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)
![Supabase](https://img.shields.io/badge/Supabase-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white)

## 🚀 Features

### 🔐 Authentication & User Management
- **Role-based access control** (Admin, PHO, PHO Supervisors)
- **Secure password hashing** with bcrypt
- **Session management** with automatic timeout
- **User creation and management** interface

### 📊 Data Collection & Management
- **Mess waste tracking** with detailed meal-wise breakdown
- **Hostel waste management** across multiple categories
- **Real-time data validation** and calculations
- **Form auto-save** functionality to prevent data loss

### 📸 Image Management
- **Supabase storage integration** for image uploads
- **Multiple image support** per submission
- **Automatic image compression** and optimization
- **Secure image viewing** in verification interface

### ✅ Approval Workflow
- **PHO verification system** for data quality control
- **Edit tracking** with full audit trail
- **Approval status management** (pending/verified/rejected)
- **Notification system** for status updates

### 📈 Analytics & Reporting
- **Interactive dashboards** with Plotly charts
- **Real-time KPI calculations** and metrics
- **Time-series analysis** with filtering options
- **Per-capita waste analysis** and trends
- **Export functionality** for reports and data

### 🎨 User Experience
- **Responsive design** optimized for mobile and desktop
- **Sustainability-themed UI** with green color scheme
- **Intuitive navigation** with role-based menus
- **Real-time feedback** and status indicators

## 🏗️ Architecture

```
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ Streamlit │ │ Supabase │ │ PostgreSQL │
│ Frontend │◄──►│ Backend │◄──►│ Database │
│ │ │ │ │ │
└─────────────────┘ └─────────────────┘ └─────────────────┘
│ │ │
│ │ │
▼ ▼ ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ User Auth │ │ File Storage │ │ Data Analytics │
│ & Sessions │ │ & Images │ │ & Reports │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

## 🛠️ Tech Stack

- **Frontend**: Streamlit 1.28+
- **Backend**: Supabase (PostgreSQL + Storage)
- **Authentication**: bcrypt password hashing
- **Charts**: Plotly for interactive visualizations
- **Database**: PostgreSQL with real-time capabilities
- **Storage**: Supabase Storage for image management
- **Deployment**: Render.com compatible

## 📋 Prerequisites

- Python 3.8 or higher
- Supabase account and project
- Git (for cloning)

## 🚀 Quick Start

### 1. Clone the Repository
```
git clone https://github.com/yourusername/waste-management-app.git
cd Data-Pool
```
### 2. Install Dependencies
```
pip install -r requirements.txt
```
### 3. Set Up Environment Variables
Create a `.env` file in the root directory:
```
Supabase Database Configuration
DB_HOST=aws-0-ap-south-1.pooler.supabase.com
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres.your_project_id
DB_PASS=your_database_password

Supabase API Configuration
SUPABASE_URL=https://your_project_id.supabase.co
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_KEY=your_service_key
```
### 4. Set Up Supabase Database
Run the database setup script to create tables and sample data:
```
python sample_data_setup.py
```

**⚠️ Warning**: This script will drop existing tables. Only run on a fresh database.

### 5. Create Supabase Storage Buckets
In your Supabase dashboard, create these public buckets:
- `mess-images`
- `hostel-images`

### 6. Run the Application
```
streamlit run app.py
```

The app will be available at `http://localhost:8501`

## 👥 Default Login Credentials

| Role | Username | Password | Access Level |
|------|----------|----------|--------------|
| **Admin** | `admin` | `adminpass` | Full system access, user management |
| **PHO** | `pho` | `phopass` | Data verification, approval, analytics |
| **PHO Supervisor** | `pho_supervisor_2` | `phosuppass2` | Data submission for Hostel 2 |
| **PHO Supervisor** | `pho_supervisor_10` | `phosuppass10` | Data submission for Hostel 10 |
| **PHO Supervisor** | `pho_supervisor_11` | `phosuppass11` | Data submission for Hostel 11 |
| **PHO Supervisor** | `pho_supervisor_12` | `phosuppass12` | Data submission for Hostel 12-13-14 |
| **PHO Supervisor** | `pho_supervisor_18` | `phosuppass18` | Data submission for Hostel 18 |

## 📱 User Roles & Permissions

### 🔧 Admin
- **User Management**: Create, edit, delete users
- **System Overview**: Access to all data and analytics
- **Data Management**: Export, backup, and storage management
- **Edit Tracking**: View all PHO edits and audit trails
- **System Configuration**: Manage app settings

### 👨‍⚕️ PHO (Public Health Officer)
- **Data Verification**: Review and approve submissions
- **Analytics Dashboard**: View trends and KPIs
- **Data Editing**: Modify submissions with audit trail
- **Report Generation**: Export verified data
- **Quality Control**: Reject invalid submissions

### 👥 PHO Supervisor
- **Data Submission**: Submit mess and hostel waste data
- **Image Upload**: Attach photos to submissions
- **Form Management**: Save and edit draft submissions
- **Status Tracking**: View submission approval status
- **Hostel-Specific**: Access only assigned hostel data

## 📊 Database Schema

### Core Tables
- **users**: User authentication and roles
- **mess_waste_submissions**: Detailed mess waste data
- **hostel_waste_submissions**: Hostel waste categories
- **master_waste_data**: Aggregated data for analytics
- **submission_images**: Image metadata and URLs
- **pho_edits**: Edit tracking and audit trail

### Key Relationships
```
users ──┐
├── mess_waste_submissions
├── hostel_waste_submissions
└── pho_edits

mess_waste_submissions ──┐
├── submission_images
└── master_waste_data

hostel_waste_submissions ──┐
├── submission_images
└── master_waste_data
```

## 🚀 Deployment

### Deploy to Render
1. **Connect GitHub**: Link your repository to Render
2. **Set Environment Variables**: Add all variables from `.env`
3. **Configure Build**: Use `pip install -r requirements.txt`
4. **Set Start Command**: `streamlit run app.py --server.port $PORT`

### Deploy to Streamlit Community Cloud
1. **Connect Repository**: Link GitHub repo to Streamlit Cloud
2. **Add Secrets**: Copy `.env` contents to Streamlit secrets
3. **Deploy**: Automatic deployment from main branch

## 📈 Sample Data

The application includes 2 months of realistic sample data:
- **300 mess waste submissions** (60 days × 5 hostels)
- **300 hostel waste submissions** (60 days × 5 hostels)
- **Realistic waste patterns** with seasonal variations
- **Mixed approval status** (recent pending, older approved)
- **Sample images** and edit history

## 🔧 Configuration

### Streamlit Configuration
The app includes optimized settings in `.streamlit/config.toml`:
- **Mobile-responsive** sidebar behavior
- **Sustainability theme** with green color scheme
- **Large file uploads** (200MB limit)
- **Performance optimizations**

### Environment Variables
| Variable | Description | Example |
|----------|-------------|---------|
| `DB_HOST` | Supabase database host | `aws-0-ap-south-1.pooler.supabase.com` |
| `DB_USER` | Database username | `postgres.your_project_id` |
| `DB_PASS` | Database password | `your_secure_password` |
| `SUPABASE_URL` | Supabase project URL | `https://your_project_id.supabase.co` |
| `SUPABASE_ANON_KEY` | Public API key | `eyJhbGciOiJIUzI1NiIsInR5cCI6...` |

---

<<<<<<< HEAD
*This application helps to track and reduce waste through data-driven insights and streamlined workflows.*
=======
*This application helps to track and reduce waste through data-driven insights and streamlined workflows.*

>>>>>>> 3fe28e03ff6a483f632950cb2b61a8b287f563fb
