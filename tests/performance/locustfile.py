from locust import HttpUser, task, between

class AEOSUser(HttpUser):
    wait_time = between(1, 5)

    @task(3)
    def view_dashboard_incidents(self):
        self.client.get("/api/v1/incidents?limit=20&offset=0")

    @task(2)
    def view_escalations(self):
        self.client.get("/api/v1/escalations/pending")

    @task(1)
    def view_policies(self):
        self.client.get("/api/v1/policies")

    @task(1)
    def ingest_incident(self):
        # Simulate simple text ingestion
        payload = {"format": "text", "metadata": '{"source": "locust_load_test"}'}
        files = {"file": ("test.txt", b"Load test simulated incident", "text/plain")}
        self.client.post("/api/v1/incidents/ingest", data=payload, files=files)
