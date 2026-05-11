# Database Configuration
import os

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "network_slicing_5g")

# Database config dict for mysql.connector
DB_CONFIG = {
    "host": DB_HOST,
    "port": DB_PORT,
    "user": DB_USER,
    "password": DB_PASSWORD,
    "database": DB_NAME,
}

# App / legacy env (Docker Compose may still set FLASK_*; ignored by FastAPI services)
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
FLASK_ENV = os.getenv("FLASK_ENV", "production")
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"

# MS2 — Keras .h5 autoencoder + joblib IF/scaler/features (see ml/inference.py)
AUTOENCODER_PATH = os.getenv("AUTOENCODER_PATH", "./ml/autoencoder.h5")
SCALER_PATH = os.getenv("SCALER_PATH", "./ml/scaler.pkl")
ENCODER_PATH = os.getenv("ENCODER_PATH", "./ml/features.pkl")
ISO_FOREST_PATH = os.getenv("ISO_FOREST_PATH", "./ml/iso_forest.pkl")

# Alert Configuration
ALERT_EMAIL = os.getenv("ALERT_EMAIL", "")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")


# Service URLs (for inter-service communication)
MS1_URL = os.getenv("MS1_URL", "http://localhost:5001")
MS2_URL = os.getenv("MS2_URL", "http://localhost:5000")
MS3_URL = os.getenv("MS3_URL", "http://localhost:5003")
MS5_URL = os.getenv("MS5_URL", "http://localhost:5005")

# API Settings
API_VERSION = "v1"
JSONIFY_PRETTYPRINT_REGULAR = False if FLASK_ENV == "production" else True

# Database connection pool settings
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", 10))
DB_POOL_NAME = os.getenv("DB_POOL_NAME", "network_slicing_pool")
