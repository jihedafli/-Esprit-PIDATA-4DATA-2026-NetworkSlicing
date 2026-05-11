"""
Database models for 5G Network Slicing
"""

import os
import mysql.connector
from datetime import datetime
from mysql.connector import Error

# DB_CONFIG for BaseModel
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "network_slicing_5g"),
}


class BaseModel:
    """Base model with common database operations"""

    @staticmethod
    def execute_query(query, params=None, fetchone=False, commit=False):
        """Execute a database query"""
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor(dictionary=True)
            cursor.execute(query, params or ())

            if commit:
                conn.commit()
                result = cursor.lastrowid
            else:
                result = cursor.fetchone() if fetchone else cursor.fetchall()

            cursor.close()
            conn.close()
            return result

        except Error as e:
            print(f"Database error: {e}")
            return None


class QoSPrediction(BaseModel):
    """Model for QoS predictions"""

    @staticmethod
    def create(data):
        """Insert a new QoS prediction"""
        query = """
            INSERT INTO qos_predictions
            (slice_id, time, plr, delay, lte5g_cat, qos_score, p_sla_met,
             qos_risk_score, risk_tier, congestion_level, sla_respected)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        return BaseModel.execute_query(
            query,
            (
                data["slice_id"],
                data.get("time"),
                data.get("plr"),
                data.get("delay"),
                data.get("lte5g_cat"),
                data["qos_score"],
                data["p_sla_met"],
                data["qos_risk_score"],
                data["risk_tier"],
                data["congestion_level"],
                data["sla_respected"],
            ),
            commit=True,
        )

    @staticmethod
    def get_recent(limit=100):
        """Get recent predictions"""
        query = """
            SELECT * FROM qos_predictions
            ORDER BY timestamp DESC
            LIMIT %s
        """
        return BaseModel.execute_query(query, (limit,))

    @staticmethod
    def get_statistics():
        """Get prediction statistics"""
        query = """
            SELECT
                COUNT(*) as total,
                AVG(qos_score) as avg_qos_score,
                AVG(qos_risk_score) as avg_risk_score,
                SUM(CASE WHEN sla_respected = TRUE THEN 1 ELSE 0 END) as sla_compliant,
                SUM(CASE WHEN risk_tier = 'High' THEN 1 ELSE 0 END) as high_risk_count
            FROM qos_predictions
        """
        return BaseModel.execute_query(query, fetchone=True)


class AnomalyDetection(BaseModel):
    """Model for anomaly detections"""

    @staticmethod
    def create(data):
        """Insert a new anomaly detection record"""
        query = """
            INSERT INTO anomaly_detections
            (slice_id, is_anomaly, score, confidence, method, features)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        return BaseModel.execute_query(
            query,
            (
                data["slice_id"],
                data["is_anomaly"],
                data["score"],
                data["confidence"],
                data.get("method", "IsolationForest"),
                str(data.get("features", {})),
            ),
            commit=True,
        )

    @staticmethod
    def get_recent(days=7, limit=100):
        """Get recent anomaly detections"""
        query = """
            SELECT * FROM anomaly_detections
            WHERE timestamp >= DATE_SUB(NOW(), INTERVAL %s DAY)
            ORDER BY timestamp DESC
            LIMIT %s
        """
        return BaseModel.execute_query(query, (days, limit))


class ModelMetrics(BaseModel):
    """Model for tracking model performance metrics"""

    @staticmethod
    def create(data):
        """Insert model metrics"""
        query = """
            INSERT INTO model_metrics
            (model_name, model_version, accuracy, precision, recall, f1_score, roc_auc, log_loss, training_time)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        return BaseModel.execute_query(
            query,
            (
                data["model_name"],
                data.get("model_version", "v1.0"),
                data.get("accuracy"),
                data.get("precision"),
                data.get("recall"),
                data.get("f1_score"),
                data.get("roc_auc"),
                data.get("log_loss"),
                data.get("training_time"),
            ),
            commit=True,
        )

    @staticmethod
    def get_latest(model_name=None):
        """Get latest model metrics"""
        if model_name:
            query = """
                SELECT * FROM model_metrics
                WHERE model_name = %s
                ORDER BY training_date DESC
                LIMIT 1
            """
            return BaseModel.execute_query(query, (model_name,), fetchone=True)
        else:
            query = "SELECT * FROM model_metrics ORDER BY training_date DESC LIMIT 10"
            return BaseModel.execute_query(query)


class Alert(BaseModel):
    """Model for system alerts"""

    @staticmethod
    def create(alert_type, severity, message, slice_id=None):
        """Create a new alert"""
        query = """
            INSERT INTO alerts (alert_type, severity, message, slice_id)
            VALUES (%s, %s, %s, %s)
        """
        return BaseModel.execute_query(
            query, (alert_type, severity, message, slice_id), commit=True
        )

    @staticmethod
    def get_unacknowledged():
        """Get unacknowledged alerts"""
        query = "SELECT * FROM alerts WHERE acknowledged = FALSE ORDER BY timestamp DESC"
        return BaseModel.execute_query(query)

    @staticmethod
    def acknowledge(alert_id):
        """Acknowledge an alert"""
        query = "UPDATE alerts SET acknowledged = TRUE WHERE id = %s"
        return BaseModel.execute_query(query, (alert_id,), commit=True)
