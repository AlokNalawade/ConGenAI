"""A/B Experimentation & Empirical Analytics Feedback API.

Enables creators to run controlled creative experiments:
- Video A (Hook A, Thumbnail A) vs Video B (Hook B, Thumbnail B)
- Real-world retention metric ingestion (3-second view rate, completion rate, CTR, shares)
- Automatic winner determination and strategic feedback loop to the DNA Engine
"""

import uuid
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.services.editorial_memory import EditorialMemoryService

router = APIRouter()


class MetricGoal(str, Enum):
    RETENTION_3S = "retention_3s"
    COMPLETION_RATE = "completion_rate"
    CTR = "ctr"
    SHARES = "shares"


class ExperimentStatus(str, Enum):
    ACTIVE = "active"
    CONCLUDED = "concluded"


class VariantMetrics(BaseModel):
    content_id: str
    views: int = 0
    retention_3s_pct: float = 0.0
    completion_pct: float = 0.0
    ctr_pct: float = 0.0
    shares: int = 0
    saves: int = 0


class ExperimentCreate(BaseModel):
    name: str
    hypothesis: str
    content_id_a: str
    content_id_b: str
    primary_metric: MetricGoal = MetricGoal.RETENTION_3S


class ExperimentResult(BaseModel):
    id: str
    name: str
    hypothesis: str
    status: ExperimentStatus
    primary_metric: MetricGoal
    variant_a: VariantMetrics
    variant_b: VariantMetrics
    winner_content_id: Optional[str] = None
    lift_percent: Optional[float] = None
    strategic_takeaway: Optional[str] = None


# In-memory store for experiments & metrics (with fallback support)
_EXPERIMENTS_STORE: Dict[str, ExperimentResult] = {}


@router.post("/", response_model=ExperimentResult)
async def create_experiment(body: ExperimentCreate):
    """Register a new A/B creative experiment."""
    exp_id = f"exp_{uuid.uuid4().hex[:8]}"
    exp = ExperimentResult(
        id=exp_id,
        name=body.name,
        hypothesis=body.hypothesis,
        status=ExperimentStatus.ACTIVE,
        primary_metric=body.primary_metric,
        variant_a=VariantMetrics(content_id=body.content_id_a),
        variant_b=VariantMetrics(content_id=body.content_id_b),
    )
    _EXPERIMENTS_STORE[exp_id] = exp
    return exp


@router.get("/{experiment_id}", response_model=ExperimentResult)
async def get_experiment(experiment_id: str):
    """Retrieve experiment status and metric comparison."""
    if experiment_id not in _EXPERIMENTS_STORE:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return _EXPERIMENTS_STORE[experiment_id]


@router.post("/{experiment_id}/metrics", response_model=ExperimentResult)
async def ingest_experiment_metrics(
    experiment_id: str,
    variant_a_metrics: VariantMetrics,
    variant_b_metrics: VariantMetrics,
):
    """Ingest empirical social media performance metrics and determine winner."""
    if experiment_id not in _EXPERIMENTS_STORE:
        raise HTTPException(status_code=404, detail="Experiment not found")
    
    exp = _EXPERIMENTS_STORE[experiment_id]
    exp.variant_a = variant_a_metrics
    exp.variant_b = variant_b_metrics

    # Winner determination based on primary metric
    metric_key = exp.primary_metric.value
    score_a = getattr(variant_a_metrics, f"{metric_key}_pct", None) or getattr(variant_a_metrics, metric_key, 0.0)
    score_b = getattr(variant_b_metrics, f"{metric_key}_pct", None) or getattr(variant_b_metrics, metric_key, 0.0)

    if score_a > score_b:
        exp.winner_content_id = variant_a_metrics.content_id
        lift = ((score_a - score_b) / max(score_b, 0.01)) * 100.0
        exp.lift_percent = round(lift, 1)
        exp.strategic_takeaway = f"Variant A outperformed Variant B by {exp.lift_percent}% on {exp.primary_metric.value}."
    elif score_b > score_a:
        exp.winner_content_id = variant_b_metrics.content_id
        lift = ((score_b - score_a) / max(score_a, 0.01)) * 100.0
        exp.lift_percent = round(lift, 1)
        exp.strategic_takeaway = f"Variant B outperformed Variant A by {exp.lift_percent}% on {exp.primary_metric.value}."
    else:
        exp.winner_content_id = None
        exp.lift_percent = 0.0
        exp.strategic_takeaway = "Metrics tied between both variants."

    exp.status = ExperimentStatus.CONCLUDED

    # Feed winning takeaway into editorial memory
    memory = EditorialMemoryService.get_instance()
    memory.record_hook_correction(
        original_hook=f"Hypothesis: {exp.hypothesis}",
        user_hook=f"Winner: {exp.strategic_takeaway}",
    )

    return exp
