"""Unit and integration tests for Phase 4: Studio UX & A/B Experimentation Loop."""

import pytest
import uuid
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.api.v1.experiments import (
    MetricGoal,
    ExperimentStatus,
    VariantMetrics,
)
from app.services.editorial_memory import EditorialMemoryService


@pytest.mark.asyncio
async def test_ab_experiment_lifecycle_and_winner_determination():
    """Verify complete A/B experiment flow: creation -> metric ingestion -> winner identification."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create experiment
        create_payload = {
            "name": "Hook Test: Curiosity vs Shock",
            "hypothesis": "Contrarian shock hook achieves higher 3-sec retention than curiosity question",
            "content_id_a": str(uuid.uuid4()),
            "content_id_b": str(uuid.uuid4()),
            "primary_metric": "retention_3s",
        }
        res = await client.post("/api/v1/experiments/", json=create_payload)
        assert res.status_code == 200
        data = res.json()
        exp_id = data["id"]
        assert data["status"] == ExperimentStatus.ACTIVE.value
        assert data["name"] == create_payload["name"]

        # 2. Ingest real-world metrics (Variant A gets 78% 3s retention, Variant B gets 52%)
        metrics_payload = {
            "experiment_id": exp_id,
            "variant_a_metrics": {
                "content_id": create_payload["content_id_a"],
                "views": 15000,
                "retention_3s_pct": 78.0,
                "completion_pct": 42.0,
                "ctr_pct": 8.5,
                "shares": 120,
                "saves": 340,
            },
            "variant_b_metrics": {
                "content_id": create_payload["content_id_b"],
                "views": 14200,
                "retention_3s_pct": 52.0,
                "completion_pct": 28.0,
                "ctr_pct": 6.1,
                "shares": 45,
                "saves": 110,
            },
        }
        res_metrics = await client.post(f"/api/v1/experiments/{exp_id}/metrics", json=metrics_payload)
        assert res_metrics.status_code == 200
        concluded = res_metrics.json()

        # 3. Verify winner determination and lift percent
        assert concluded["status"] == ExperimentStatus.CONCLUDED.value
        assert concluded["winner_content_id"] == create_payload["content_id_a"]
        assert concluded["lift_percent"] == 50.0
        assert "Variant A outperformed Variant B" in concluded["strategic_takeaway"]

        # 4. Verify strategic feedback was recorded in editorial memory
        memory = EditorialMemoryService.get_instance()
        guidelines = memory.get_editorial_guidelines()
        assert "LEARNED CREATOR EDITORIAL TASTE GUIDELINES" in guidelines
