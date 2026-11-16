import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.movie_models import MovieProject, MovieScene, MovieShot
from app.models.movie_schemas import (
    MovieProjectCreate, MovieProjectRead, MovieProjectUpdate,
    MovieSceneCreate, MovieShotCreate,
)
from app.movie.genres import validate_genres, get_genre_registry


router = APIRouter()


@router.get("/genres")
async def list_movie_genres():
    registry = get_genre_registry()
    return {
        "version": registry.get("version", 1),
        "allow_custom_genres": registry.get("allow_custom_genres", False),
        "allow_hybrid_genres": registry.get("allow_hybrid_genres", False),
        "profiles": registry.get("profiles", []),
    }


@router.post("/projects", response_model=MovieProjectRead, status_code=201)
async def create_movie_project(payload: MovieProjectCreate, db: AsyncSession = Depends(get_db)):
    try:
        genres = validate_genres(payload.genre_ids)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    values = payload.model_dump()
    values["genre_ids"] = genres
    values["auto_publish"] = False
    values["approval_mode"] = "manual"
    project = MovieProject(**values)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("/projects", response_model=list[MovieProjectRead])
async def list_movie_projects(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MovieProject).order_by(MovieProject.created_at.desc()).offset(skip).limit(limit)
    )
    return result.scalars().all()


@router.get("/projects/{project_id}", response_model=MovieProjectRead)
async def get_movie_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    project = await db.get(MovieProject, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Movie project not found")
    return project


@router.patch("/projects/{project_id}", response_model=MovieProjectRead)
async def update_movie_project(
    project_id: uuid.UUID,
    payload: MovieProjectUpdate,
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(MovieProject, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Movie project not found")
    changes = payload.model_dump(exclude_unset=True)
    if "genre_ids" in changes and changes["genre_ids"] is not None:
        try:
            changes["genre_ids"] = validate_genres(changes["genre_ids"])
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    for key, value in changes.items():
        setattr(project, key, value)
    await db.commit()
    await db.refresh(project)
    return project


@router.post("/projects/{project_id}/scenes", status_code=201)
async def create_movie_scene(
    project_id: uuid.UUID,
    payload: MovieSceneCreate,
    db: AsyncSession = Depends(get_db),
):
    if await db.get(MovieProject, project_id) is None:
        raise HTTPException(status_code=404, detail="Movie project not found")
    scene = MovieScene(project_id=project_id, **payload.model_dump())
    db.add(scene)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Scene number already exists in this project") from exc
    await db.refresh(scene)
    return scene


@router.get("/projects/{project_id}/scenes")
async def list_movie_scenes(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    if await db.get(MovieProject, project_id) is None:
        raise HTTPException(status_code=404, detail="Movie project not found")
    result = await db.execute(
        select(MovieScene).where(MovieScene.project_id == project_id).order_by(MovieScene.scene_number)
    )
    return result.scalars().all()


@router.post("/scenes/{scene_id}/shots", status_code=201)
async def create_movie_shot(
    scene_id: uuid.UUID,
    payload: MovieShotCreate,
    db: AsyncSession = Depends(get_db),
):
    scene = await db.get(MovieScene, scene_id)
    if scene is None:
        raise HTTPException(status_code=404, detail="Movie scene not found")
    shot = MovieShot(
        project_id=scene.project_id,
        scene_id=scene.id,
        **payload.model_dump(),
    )
    db.add(shot)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Shot number already exists in this scene") from exc
    await db.refresh(shot)
    return shot


@router.get("/projects/{project_id}/shots")
async def list_movie_shots(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    if await db.get(MovieProject, project_id) is None:
        raise HTTPException(status_code=404, detail="Movie project not found")
    result = await db.execute(
        select(MovieShot).where(MovieShot.project_id == project_id).order_by(MovieShot.scene_id, MovieShot.shot_number)
    )
    return result.scalars().all()
