"""
5G Network Slicing - Test API Endpoints
Run with: pytest test_api.py -v
"""

import json
import os
import time

import pytest
import requests

# Base URLs — depuis l’hôte (ports exposés) ou depuis le service `ci` (noms Docker)
MS1_URL = os.getenv("MS1_URL", "http://localhost:5001")
MS2_URL = os.getenv("MS2_URL", "http://localhost:5000")
MS3_URL = os.getenv("MS3_URL", "http://localhost:5003")
MS5_URL = os.getenv("MS5_URL", "http://localhost:5005")
NGINX_URL = os.getenv("NGINX_URL", "http://localhost").rstrip("/")


# Wait for services to be ready
def wait_for_service(url, max_retries=30):
    """Wait for a service to become available"""
    for i in range(max_retries):
        try:
            response = requests.get(f"{url}/health", timeout=2)
            if response.status_code == 200:
                return True
        except:
            pass
        time.sleep(1)
    return False


@pytest.fixture(scope="module", autouse=True)
def ensure_services():
    """Ensure services are running before tests"""
    services = {"MS1": MS1_URL, "MS2": MS2_URL, "MS3": MS3_URL, "MS5": MS5_URL}

    for name, url in services.items():
        if not wait_for_service(url):
            pytest.skip(f"{name} service not available at {url}")

    print("All services are healthy")
    yield

    # Cleanup (if needed)
    print("Tests completed")


class TestMS1QoSPrediction:
    """Tests for MS1 QoS Prediction Service"""

    def test_health(self):
        """Test MS1 health endpoint"""
        response = requests.get(f"{MS1_URL}/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "MS1-QoS-Prediction"

    def test_predict_qos(self):
        """Test QoS prediction"""
        payload = {
            "slice_id": "test_slice_001",
            "time": 14,
            "plr": 0.001,
            "delay": 100,
            "lte5g_cat": 14,
        }

        response = requests.post(
            f"{MS1_URL}/predict/qos/5g", json=payload, headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "qos_score" in data
        assert "p_sla_met" in data
        assert "qos_risk_score" in data
        assert "risk_tier" in data
        assert "sla_respected" in data
        assert "congestion_level" in data
        assert data["congestion_level"] in ("Low", "Medium", "High")
        assert "congestion_slice_profile" in data
        assert str(data["congestion_slice_profile"]) in ("1", "2", "3")
        assert "pressure_index" in data
        assert 0 <= data["qos_score"] <= 1

    def test_predict_invalid(self):
        """Test QoS prediction with invalid data"""
        payload = {
            "slice_id": "test",
            "time": 14,
            # Missing required fields
        }

        response = requests.post(f"{MS1_URL}/predict/qos/5g", json=payload)
        assert response.status_code == 400

    def test_get_stats(self):
        """Test statistics endpoint"""
        response = requests.get(f"{MS1_URL}/predict/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_predictions" in data
        assert "sla_compliance_rate" in data


class TestMS2AnomalyDetection:
    """Tests for MS2 Anomaly Detection Service"""

    def test_health(self):
        """Test MS2 health endpoint"""
        response = requests.get(f"{MS2_URL}/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "MS2-Anomaly-Detection"

    def test_detect_anomaly(self):
        """Test anomaly detection"""
        payload = {
            "slice_id": "test_slice_001",
            "packet_loss_rate": 0.001,
            "packet_delay": 12.3,
            "lte_5g": 1,
            "gbr": 0,
            "ar_vr_gaming": 0,
            "healthcare": 0,
            "industry_4_0": 0,
            "iot_devices": 1,
            "public_safety": 0,
            "smart_city_home": 0,
            "smart_transportation": 0,
            "smartphone": 0,
        }

        response = requests.post(f"{MS2_URL}/api/anomaly/detect", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "is_anomaly" in data["data"]
        assert "score" in data["data"]
        assert "confidence" in data["data"]

    def test_get_stats(self):
        """Test anomaly statistics"""
        response = requests.get(f"{MS2_URL}/api/anomaly/stats?days=7")
        assert response.status_code == 200


class TestMS3Dashboard:
    """Tests for MS3 Dashboard Service"""

    def test_health(self):
        """Test MS3 health endpoint"""
        response = requests.get(f"{MS3_URL}/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "MS3-Dashboard"

    def test_dashboard_data(self):
        """Test dashboard data aggregation"""
        response = requests.get(f"{MS3_URL}/api/dashboard-data")
        assert response.status_code == 200
        data = response.json()
        assert "summary" in data
        assert "predictions" in data
        assert "anomalies" in data
        assert "alerts" in data


class TestMS5ModelManagement:
    """Tests for MS5 Model Management Service"""

    def test_health(self):
        """Test MS5 health endpoint"""
        response = requests.get(f"{MS5_URL}/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "MS5-Model-Management"

    def test_list_models(self):
        """Test model listing (DB registry + on-disk artifacts)"""
        response = requests.get(f"{MS5_URL}/models")
        assert response.status_code == 200
        data = response.json()
        assert "models" in data
        assert "artifacts" in data
        assert isinstance(data["artifacts"], list)
        assert "metadata_bundle" in data

    def test_register_model(self):
        """Test model registration"""
        payload = {
            "model_name": "test_xgboost_v1",
            "model_version": "1.0.0",
            "accuracy": 0.912,
            "precision": 0.89,
            "recall": 0.94,
            "f1_score": 0.91,
            "roc_auc": 0.9542,
            "log_loss": 0.2847,
            "training_time": 2.3,
        }

        response = requests.post(f"{MS5_URL}/models/register", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "model_id" in data


class TestNginxProxy:
    """Tests for Nginx reverse proxy"""

    def test_root_endpoint(self):
        """Test Nginx root endpoint"""
        response = requests.get(f"{NGINX_URL}/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_health_via_nginx(self):
        """Test health check through Nginx"""
        response = requests.get(f"{NGINX_URL}/health")
        assert response.status_code == 200
