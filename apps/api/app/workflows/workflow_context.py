from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import uuid
from app.workflows.workflow_state import WorkflowState
from app.models.ai_contracts import ResearchResult, StrategyResult, ScriptResult, ScenePlan, QualityResult

@dataclass
class WorkflowContext:
    content_id: uuid.UUID
    current_state: WorkflowState = WorkflowState.IDEA
    idea_id: Optional[uuid.UUID] = None
    title: str = "Untitled Video"
    topic: str = "General"
    target_audience: str = "General"
    platform: str = "Shorts"
    pipeline_run_id: Optional[uuid.UUID] = None
    model_overrides: Dict[str, str] = field(default_factory=dict)
    strategy_dna: Dict[str, Any] = field(default_factory=dict)
    
    # Execution outputs
    research: Optional[ResearchResult] = None
    strategy: Optional[StrategyResult] = None
    script: Optional[ScriptResult] = None
    scene_plan: Optional[ScenePlan] = None
    scene_assets: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    final_video_path: Optional[str] = None
    final_video_asset_id: Optional[uuid.UUID] = None
    quality_result: Optional[QualityResult] = None
    
    # Audit & Diagnostics
    logs: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    retry_counts: Dict[str, int] = field(default_factory=dict)

    def log(self, message: str):
        self.logs.append(message)

    def add_error(self, step: str, error: str):
        err_msg = f"[{step}] {error}"
        self.errors.append(err_msg)
        self.logs.append(f"ERROR: {err_msg}")
