"""最终视频合成."""
from app.services.dubbing.ffmpeg import compose_video


async def compose_final_video(
    original_video: str,
    dubbing_audio: str,
    out_path: str,
) -> str:
    """用 dubbing_audio 替换 original_video 的音轨，输出 out_path."""
    return await compose_video(original_video, dubbing_audio, out_path)
