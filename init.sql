-- Initialize 5G Network Slicing Database Schema
-- Run this script when MySQL container starts

CREATE DATABASE IF NOT EXISTS network_slicing_5g;
USE network_slicing_5g;

-- QoS Predictions table
CREATE TABLE IF NOT EXISTS qos_predictions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    slice_id VARCHAR(50) NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    time INT,
    plr FLOAT,
    delay Float,
    lte5g_cat INT,
    qos_score FLOAT,
    p_sla_met FLOAT,
    qos_risk_score FLOAT,
    risk_tier VARCHAR(20),
    congestion_level VARCHAR(20),
    sla_respected BOOLEAN
);

-- Anomaly Detection table
CREATE TABLE IF NOT EXISTS anomaly_detections (
    id INT AUTO_INCREMENT PRIMARY KEY,
    slice_id VARCHAR(50) NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_anomaly BOOLEAN,
    score FLOAT,
    confidence FLOAT,
    method VARCHAR(50),
    features JSON
);

-- Model Performance Metrics table
CREATE TABLE IF NOT EXISTS model_metrics (
    id INT AUTO_INCREMENT PRIMARY KEY,
    model_name VARCHAR(100) NOT NULL,
    model_version VARCHAR(50),
    accuracy FLOAT,
    `precision` FLOAT,
    recall FLOAT,
    f1_score FLOAT,
    roc_auc FLOAT,
    log_loss FLOAT,
    training_time FLOAT,
    training_date DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Alerts table
CREATE TABLE IF NOT EXISTS alerts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    alert_type VARCHAR(50),
    severity VARCHAR(20),
    message TEXT,
    slice_id VARCHAR(50),
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    acknowledged BOOLEAN DEFAULT FALSE
);

-- System Logs table
CREATE TABLE IF NOT EXISTS system_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    service VARCHAR(50),
    level VARCHAR(20),
    message TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Pressure band overrides (merged in congestion_engine when CONGESTION_THRESHOLDS_FROM_DB=true)
CREATE TABLE IF NOT EXISTS operator_thresholds (
    profile_key VARCHAR(32) PRIMARY KEY,
    pressure_low_max FLOAT NOT NULL,
    pressure_medium_max FLOAT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Create users for service access
CREATE USER IF NOT EXISTS 'network_user'@'%' IDENTIFIED BY 'network_pass';
GRANT ALL PRIVILEGES ON network_slicing_5g.* TO 'network_user'@'%';
FLUSH PRIVILEGES;
