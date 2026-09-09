import os
import uuid
import shutil
import ffmpeg
import imageio_ffmpeg

class VideoService:
    def __init__(self):
        self.output_dir = os.path.join("data", "assets", "videos")
        os.makedirs(self.output_dir, exist_ok=True)
        self.ffmpeg_cmd = shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()

    def create_scene_video(self, image_path: str, audio_path: str, text: str = None, duration: float = None) -> str:
        filename = f"scene_{uuid.uuid4()}.mp4"
        filepath = os.path.join(self.output_dir, filename)
        
        try:
            # Simple combination of image and audio using ffmpeg-python
            input_image = ffmpeg.input(image_path, loop=1)
            input_audio = ffmpeg.input(audio_path)
            
            output_kwargs = {
                'vcodec': 'libx264',
                'acodec': 'aac',
                'ar': '44100',
                'ac': 2,
                'r': 25,
                'af': 'volume=1.5',
                'pix_fmt': 'yuv420p',
                'vf': 'scale=1080:1920,format=yuv420p'
            }
            if duration and float(duration) > 0:
                output_kwargs['t'] = float(duration)
            else:
                output_kwargs['shortest'] = None
            
            stream = ffmpeg.output(
                input_image.video,
                input_audio.audio,
                filepath,
                **output_kwargs
            )
            ffmpeg.run(stream, cmd=self.ffmpeg_cmd, overwrite_output=True, capture_stdout=True, capture_stderr=True)
            
            return filepath
        except ffmpeg.Error as e:
            err_msg = e.stderr.decode('utf8') if e.stderr else str(e)
            print('stdout:', e.stdout.decode('utf8') if e.stdout else '')
            print('stderr:', err_msg)
            raise RuntimeError(f"FFmpeg render error: {err_msg}") from e

    def concatenate_videos(self, video_paths: list[str]) -> str:
        if not video_paths:
            raise ValueError("No video paths provided")
            
        filename = f"final_{uuid.uuid4()}.mp4"
        filepath = os.path.join(self.output_dir, filename)
        
        try:
            # Write files to a text file for ffmpeg concat demuxer
            list_file_path = os.path.join(self.output_dir, f"list_{uuid.uuid4()}.txt")
            with open(list_file_path, 'w') as f:
                for path in video_paths:
                    # ffmpeg requires absolute paths or relative to the list file
                    abs_path = os.path.abspath(path)
                    f.write(f"file '{abs_path}'\n")
            
            stream = ffmpeg.input(list_file_path, format='concat', safe=0)
            stream = ffmpeg.output(stream, filepath, c='copy')
            ffmpeg.run(stream, cmd=self.ffmpeg_cmd, overwrite_output=True, capture_stdout=True, capture_stderr=True)
            
            # Cleanup
            if os.path.exists(list_file_path):
                os.remove(list_file_path)
            
            return filepath
        except ffmpeg.Error as e:
            err_msg = e.stderr.decode('utf8') if e.stderr else str(e)
            print('stdout:', e.stdout.decode('utf8') if e.stdout else '')
            print('stderr:', err_msg)
            raise RuntimeError(f"FFmpeg concat error: {err_msg}") from e
