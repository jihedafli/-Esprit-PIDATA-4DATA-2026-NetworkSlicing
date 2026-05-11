#!/usr/bin/env python3
"""
Database initialization script for local development
Run with: python init_db.py
"""

import mysql.connector
from mysql.connector import Error
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def init_database():
    """Initialize the database schema and sample data"""
    try:
        # Read schema
        with open("init.sql", "r") as f:
            schema = f.read()

        # Connect to MySQL
        conn = mysql.connector.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", 3306)),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", ""),
        )

        cursor = conn.cursor()

        # Execute schema
        for statement in schema.split(";"):
            if statement.strip():
                cursor.execute(statement)

        conn.commit()
        cursor.close()
        conn.close()

        print("✓ Database initialized successfully")
        print("  Database: network_slicing_5g")
        print("  User: network_user / network_pass")

    except Error as e:
        print(f"✗ Database initialization failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    print("Initializing 5G Network Slicing Database...")
    init_database()
