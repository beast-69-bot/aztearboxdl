import time


last_update_time = {}


def get_progress_bar(current: int, total: int) -> str:
    """Returns a visual ASCII progress bar."""
    percentage = current * 100 / total
    filled = int(percentage / 5)
    bar = "█" * filled + "░" * (20 - filled)
    return f"[{bar}] {percentage:.1f}%"


def format_bytes(size: float) -> str:
    """Converts bytes to human-readable format."""
    if not size:
        return "0 B"
    power = 1024
    n = 0
    labels = {0: "B", 1: "KB", 2: "MB", 3: "GB", 4: "TB"}
    while size > power:
        size /= power
        n += 1
    return f"{size:.2f} {labels[n]}"


async def progress_callback(current, total, message, action: str, filename: str, start_time: float):
    """
    Updates the Telegram message with a live progress bar.
    Rate-limited to once every 3 seconds to avoid FloodWait.
    """
    msg_id = message.id
    now = time.time()

    if msg_id in last_update_time and (now - last_update_time[msg_id]) < 3.0:
        if current != total:
            return

    last_update_time[msg_id] = now

    elapsed = now - start_time or 0.1
    speed = current / elapsed
    eta = int((total - current) / speed) if speed else 0

    text = (
        f"⏳ **{action}...**\n"
        f"📁 `{filename}`\n\n"
        f"{get_progress_bar(current, total)}\n"
        f"🚀 **Speed:** {format_bytes(speed)}/s\n"
        f"📦 **Size:** {format_bytes(current)} / {format_bytes(total)}\n"
        f"⏱ **ETA:** {eta}s"
    )

    try:
        await message.edit_text(text)
    except Exception:
        pass
