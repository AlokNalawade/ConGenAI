from app.visual.continuity import (
    CharacterAnchor, EnvironmentAnchor, SceneContinuity,
    VisualBible, VisualContinuityEngine,
)


def test_visual_bible_renders_persistent_identity_and_location():
    bible = VisualBible(
        style="photoreal historical cinema",
        characters=[CharacterAnchor(
            "CHAR_01", "middle-aged warrior, angular face, dark eyes",
            "indigo cotton tunic", ["same facial scar", "same braided hair"]
        )],
        environments=[EnvironmentAnchor(
            "LOC_01", "stone courtyard with a central well",
            "overcast late afternoon", ["well remains centre frame", "north gate behind"]
        )],
        prop_anchors=["bronze sword stays in the character's right hand"],
    )
    rendered = bible.render()
    assert "CHAR_01" in rendered
    assert "same facial scar" in rendered
    assert "LOC_01" in rendered
    assert "well remains centre frame" in rendered
    assert "right hand" in rendered


def test_scene_prompts_carry_physics_camera_and_previous_state():
    engine = VisualContinuityEngine(VisualBible(style="naturalistic cinema"))
    previous = SceneContinuity(
        scene_number=1, action_state="the warrior begins walking toward the north gate"
    )
    prompt = engine.build_prompt("Warrior crosses the courtyard", 2, previous_scene=previous)
    assert "begins walking toward the north gate" in prompt
    assert "gravity" in prompt
    assert "motivated camera movement" in prompt
    assert "same face" in prompt


def test_mismatched_scene_state_is_rejected():
    engine = VisualContinuityEngine()
    state = SceneContinuity(scene_number=3)
    try:
        engine.build_prompt("A shot", 2, current_scene=state)
    except ValueError as exc:
        assert "must match" in str(exc)
    else:
        raise AssertionError("Expected mismatched scene state to fail")
