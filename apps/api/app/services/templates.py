from typing import Dict, Any, List
from pydantic import BaseModel

class VideoTemplate(BaseModel):
    id: str
    name: str
    description: str
    default_duration: int
    aspect_ratio: str
    transition_style: str
    font_style: str
    structure: List[str]

TEMPLATES: Dict[str, VideoTemplate] = {
    "Educational": VideoTemplate(
        id="TEMPLATE_02_EDUCATIONAL",
        name="Educational Explainer",
        description="Clean, high-information layout with bold headlines and structured key points.",
        default_duration=45,
        aspect_ratio="9:16",
        transition_style="fade",
        font_style="Inter",
        structure=["Hook Question", "Core Concept 1", "Core Concept 2", "Summary", "CTA"]
    ),
    "Storytelling": VideoTemplate(
        id="TEMPLATE_03_STORYTELLING",
        name="Storytelling & Narrative",
        description="Cinematic pace with emotional hook, narrative build-up, and memorable climax.",
        default_duration=50,
        aspect_ratio="9:16",
        transition_style="slide",
        font_style="Montserrat",
        structure=["Intriguing Hook", "Inciting Incident", "Rising Action", "Climax", "Takeaway"]
    ),
    "Top10": VideoTemplate(
        id="TEMPLATE_05_TOP10",
        name="Top List Countdown",
        description="Fast-paced countdown template with numerical badges and high-energy transitions.",
        default_duration=30,
        aspect_ratio="9:16",
        transition_style="wipe",
        font_style="Impact",
        structure=["Hook", "Item 3", "Item 2", "Item 1", "CTA"]
    )
}

def get_template(template_name: str) -> VideoTemplate:
    return TEMPLATES.get(template_name, TEMPLATES["Educational"])
