import asyncio
import os
from app.db.database import engine, Base, AsyncSessionLocal
from app.db.models import Content as DBContent
from app.workflows.content_pipeline import ContentPipeline
from app.workflows.workflow_state import WorkflowState

async def run_llama_test():
    print("🚀 Initializing DB tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        print("📝 Creating test Content entry...")
        content = DBContent(
            title="Why AI Automation is Changing Content Creation",
            content_type="Shorts",
            platform="Shorts",
            status="idea"
        )
        db.add(content)
        await db.commit()
        await db.refresh(content)
        content_id = content.id
        print(f"✅ Content created with ID: {content_id}")

        pipeline = ContentPipeline()
        print("🦙 Running ContentPipeline using Llama 3 (llama3:latest)...")
        
        model_overrides = {
            "research": "llama3:latest",
            "script": "llama3:latest",
            "scene": "llama3:latest"
        }
        
        ctx = await pipeline.run(content_id, db, model_overrides=model_overrides)
        
        print("\n================ PIPELINE RESULTS ================")
        print(f"Final State: {ctx.current_state}")
        if ctx.research:
            print(f"\n🔬 [Research Summary]: {ctx.research.summary[:150]}...")
            print(f"   Hooks count: {len(ctx.research.hooks)}")
        if ctx.script:
            print(f"\n📜 [Script Hook]: {ctx.script.hook}")
            print(f"   [Script Body]: {ctx.script.body[:150]}...")
            print(f"   Estimated Duration: {ctx.script.estimated_duration}s")
        if ctx.scene_plan:
            print(f"\n🎬 [Scenes Planned]: {len(ctx.scene_plan.scenes)} scenes")
            for sc in ctx.scene_plan.scenes:
                print(f"   Scene {sc.scene_number} ({sc.duration}s): {sc.narration[:60]}...")
        if ctx.quality_result:
            print(f"\n⭐ [Quality Score]: {ctx.quality_result.overall_score}/100 (Passed: {ctx.quality_result.passed})")
            print(f"   Feedback: {ctx.quality_result.feedback}")
        if ctx.final_video_path:
            print(f"\n🎥 [Final Video Generated]: {ctx.final_video_path}")
            print(f"   File size: {os.path.getsize(ctx.final_video_path)} bytes")

if __name__ == "__main__":
    asyncio.run(run_llama_test())
