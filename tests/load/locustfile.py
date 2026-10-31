from __future__ import annotations

import random

from locust import HttpUser, between, task


class TicketClassificationUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        """Login and get auth token before starting tasks."""
        response = self.client.post(
            "/api/v1/auth/login",
            json={"username": "service", "password": "any"},
        )
        if response.status_code == 200:
            self.token = response.json()["access_token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            self.token = None
            self.headers = {}

    @task(10)
    def classify_single_ticket(self):
        """Classify a single ticket - most common operation."""
        tickets = [
            {
                "subject": "Login issue",
                "body": "Cannot login to my account",
                "customer_id": "cust-001",
            },
            {
                "subject": "Bug report",
                "body": "API returns 500 error on /users endpoint",
                "customer_id": "cust-002",
            },
            {
                "subject": "Billing question",
                "body": "Invoice amount is incorrect",
                "customer_id": "cust-003",
            },
            {
                "subject": "Feature request",
                "body": "Add dark mode support",
                "customer_id": "cust-004",
            },
            {
                "subject": "Security concern",
                "body": "Potential data breach detected",
                "customer_id": "cust-005",
            },
            {
                "subject": "Account access",
                "body": "Need to reset password",
                "customer_id": "cust-006",
            },
            {
                "subject": "Technical issue",
                "body": "Integration with Salesforce failing",
                "customer_id": "cust-007",
            },
            {
                "subject": "General question",
                "body": "What are your business hours?",
                "customer_id": "cust-008",
            },
        ]
        ticket = random.choice(tickets)
        self.client.post(
            "/api/v1/classify",
            json=ticket,
            headers=self.headers,
            name="/api/v1/classify",
        )

    @task(3)
    def classify_batch_tickets(self):
        """Batch classify multiple tickets."""
        batch = {
            "tickets": [
                {
                    "subject": f"Batch ticket {i}",
                    "body": f"Description for batch ticket {i}",
                    "customer_id": f"cust-batch-{i}",
                }
                for i in range(random.randint(5, 20))
            ]
        }
        self.client.post(
            "/api/v1/classify/batch",
            json=batch,
            headers=self.headers,
            name="/api/v1/classify/batch",
        )

    @task(5)
    def health_check(self):
        """Health check endpoint."""
        self.client.get("/api/v1/health/live", name="/api/v1/health/live")
        self.client.get("/api/v1/health/ready", name="/api/v1/health/ready")

    @task(1)
    def metrics_endpoint(self):
        """Prometheus metrics endpoint."""
        self.client.get("/api/v1/metrics", name="/api/v1/metrics")


class TicketClassificationV2User(HttpUser):
    """Load test for v2 API endpoints."""

    wait_time = between(1, 3)

    def on_start(self):
        response = self.client.post(
            "/api/v1/auth/login",
            json={"username": "service", "password": "any"},
        )
        if response.status_code == 200:
            self.token = response.json()["access_token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            self.token = None
            self.headers = {}

    @task(10)
    def classify_single_ticket_v2(self):
        tickets = [
            {
                "subject": "Login issue",
                "body": "Cannot login to my account",
                "customer_id": "cust-001",
                "language": "en",
                "source": "web",
                "urgency": "high",
            },
            {
                "subject": "Bug report",
                "body": "API returns 500 error on /users endpoint",
                "customer_id": "cust-002",
                "language": "en",
                "source": "api",
                "urgency": "critical",
            },
            {
                "subject": "Billing question",
                "body": "Invoice amount is incorrect",
                "customer_id": "cust-003",
                "language": "es",
                "source": "email",
                "urgency": "medium",
            },
        ]
        ticket = random.choice(tickets)
        self.client.post(
            "/api/v2/classify",
            json=ticket,
            headers=self.headers,
            name="/api/v2/classify",
        )

    @task(3)
    def classify_batch_tickets_v2(self):
        batch = {
            "tickets": [
                {
                    "subject": f"Batch ticket {i}",
                    "body": f"Description for batch ticket {i}",
                    "customer_id": f"cust-batch-{i}",
                    "language": "en",
                    "source": "web",
                }
                for i in range(random.randint(5, 20))
            ]
        }
        self.client.post(
            "/api/v2/classify/batch",
            json=batch,
            headers=self.headers,
            name="/api/v2/classify/batch",
        )

    @task(5)
    def health_check_v2(self):
        self.client.get("/api/v2/health/live", name="/api/v2/health/live")
        self.client.get("/api/v2/health/ready", name="/api/v2/health/ready")


class ChaosUser(HttpUser):
    """Chaos engineering tests - simulate failures and edge cases."""

    wait_time = between(0.5, 1.5)

    def on_start(self):
        response = self.client.post(
            "/api/v1/auth/login",
            json={"username": "service", "password": "any"},
        )
        if response.status_code == 200:
            self.token = response.json()["access_token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            self.token = None
            self.headers = {}

    @task(5)
    def invalid_payload(self):
        """Send invalid payloads to test validation."""
        invalid_tickets = [
            {},  # Missing required fields
            {"subject": "", "body": "test"},  # Empty subject
            {"subject": "test"},  # Missing body
            {"subject": "a" * 501, "body": "test"},  # Subject too long
            {"subject": "test", "body": "x" * 10001},  # Body too long
            {"subject": "test", "body": "test", "customer_email": "invalid-email"},  # Invalid email
        ]
        ticket = random.choice(invalid_tickets)
        with self.client.post(
            "/api/v1/classify",
            json=ticket,
            headers=self.headers,
            name="/api/v1/classify (invalid)",
            catch_response=True,
        ) as response:
            if response.status_code in (400, 422):
                response.success()

    @task(2)
    def large_batch(self):
        """Send large batch to test limits."""
        batch = {
            "tickets": [
                {
                    "subject": f"Large batch {i}",
                    "body": f"Description {i}",
                    "customer_id": f"cust-{i}",
                }
                for i in range(100)  # Max batch size
            ]
        }
        self.client.post(
            "/api/v1/classify/batch",
            json=batch,
            headers=self.headers,
            name="/api/v1/classify/batch (large)",
        )

    @task(3)
    def unauthenticated_requests(self):
        """Test unauthenticated access."""
        with self.client.post(
            "/api/v1/classify",
            json={"subject": "test", "body": "test"},
            name="/api/v1/classify (unauth)",
            catch_response=True,
        ) as response:
            if response.status_code == 401:
                response.success()

    @task(1)
    def rate_limit_test(self):
        """Rapid requests to test rate limiting."""
        for _ in range(5):
            with self.client.post(
                "/api/v1/classify",
                json={
                    "subject": "rate limit test",
                    "body": "testing rate limits",
                    "customer_id": "cust-rl",
                },
                headers=self.headers,
                name="/api/v1/classify (rate limit)",
                catch_response=True,
            ) as response:
                if response.status_code in (200, 429):
                    response.success()
