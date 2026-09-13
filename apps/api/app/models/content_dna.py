"""Content DNA Models and Validation Contracts.

Enforces deep brand and strategic identity definition before any generation takes place:
- Topic & Target Audience
- Brand Archetype & Voice Tone
- Visual Aesthetic & Style
- Hook Philosophy & CTA Strategy
- Banned Buzzwords & Negative Constraints
- Diverse Batch Variation Generator contracts
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class BrandArchetype(str, Enum):
    EDUCATIONAL_AUTHORITY = "educational_authority"
    CONTRARIAN_PROVOCATEUR = "contrarian_provocateur"
    TACTICAL_BUILDER = "tactical_builder"
    ENTERTAINER_STORYTELLER = "entertainer_storyteller"
    MINIMALIST_EXPLAINER = "minimalist_explainer"


class VoiceTone(str, Enum):
    CONCISE_PUNCHY = "concise_punchy"
    AUTHORITATIVE_ACADEMIC = "authoritative_academic"
    CONVERSATIONAL_WITTY = "conversational_witty"
    URGENT_DIRECT = "urgent_direct"
    CONTEMPLATIVE_DEEP = "contemplative_deep"


class VisualAesthetic(str, Enum):
    DARK_TECH_CINEMATIC = "dark_tech_cinematic"
    WARM_MINIMALIST = "warm_minimalist"
    BOLD_NEON_POP = "bold_neon_pop"
    DOCUMENTARY_RAW = "documentary_raw"
    CLEAN_ENTERPRISE = "clean_enterprise"


class HookPhilosophy(str, Enum):
    CONTRARIAN_MYTHBUSTER = "contrarian_mythbuster"
    QUESTION_INTERRUPT = "question_interrupt"
    SHOCKING_STATISTIC = "shocking_statistic"
    IN_MEDIAS_RES_STORY = "in_medias_res_story"
    PREDICTIVE_WARNING = "predictive_warning"
    FRAMEWORK_PLAYBOOK = "framework_playbook"


class ContentDNA(BaseModel):
    """The canonical strategic DNA defining a brand or content campaign."""
    topic: str
    target_audience: str = "Developers & tech founders"
    brand_archetype: BrandArchetype = BrandArchetype.EDUCATIONAL_AUTHORITY
    voice_tone: VoiceTone = VoiceTone.CONCISE_PUNCHY
    visual_aesthetic: VisualAesthetic = VisualAesthetic.DARK_TECH_CINEMATIC
    hook_philosophy: HookPhilosophy = HookPhilosophy.CONTRARIAN_MYTHBUSTER
    cta_strategy: str = "Follow for practical, production-ready AI workflows"
    core_thesis: Optional[str] = None
    negative_rules: List[str] = Field(
        default_factory=lambda: [
            "No superficial buzzwords (e.g. 'game changer', 'revolutionary', 'unleash')",
            "No generic introductory greetings ('Hey guys, welcome back')",
            "Avoid generic AI stock imagery; focus on realistic UI, hardware, architecture diagrams",
        ]
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DNAVariation(BaseModel):
    """A distinct angle/variation derived from the Content DNA for batch expansion."""
    index: int
    title: str
    angle_type: str
    hook_text: str
    target_angle: str
    differentiator: str
    avoid_overlap_with: List[str] = Field(default_factory=list)
    recommended_template: str = "fast_news_explainer"


class BatchDNAPlan(BaseModel):
    """Output of the DNA Engine expanding 1 DNA profile into N diverse variations."""
    dna: ContentDNA
    variations: List[DNAVariation]
    total_count: int
