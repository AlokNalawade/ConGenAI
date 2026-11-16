import pytest

from app.movie.genres import get_genre_registry, validate_genres
from app.models.movie_schemas import MovieProjectCreate


def test_genre_registry_has_expected_builtin_profiles():
    registry = get_genre_registry()
    ids = {profile["id"] for profile in registry["profiles"]}
    assert {"science_fiction", "horror", "thriller", "documentary", "animation"} <= ids
    assert registry["allow_hybrid_genres"] is True


def test_genre_validation_supports_hybrid_and_custom_profiles():
    assert validate_genres(["science_fiction", "horror"]) == ["science_fiction", "horror"]
    assert validate_genres(["custom_space_opera"]) == ["custom_space_opera"]


def test_project_defaults_are_safe_and_editable():
    project = MovieProjectCreate(title="Proof of concept")
    assert project.runtime_seconds == 900
    assert project.genre_ids == ["science_fiction"]
    assert project.approval_mode == "manual"
    assert project.auto_publish is False


def test_movie_project_rejects_auto_publish():
    with pytest.raises(ValueError, match="automatic publishing"):
        MovieProjectCreate(title="Unsafe", auto_publish=True)


def test_movie_project_rejects_non_manual_approval():
    with pytest.raises(ValueError, match="manual approval"):
        MovieProjectCreate(title="Unsafe", approval_mode="automatic")
