import discord
from discord.ext import commands
import asyncio
import yt_dlp as youtube_dl
import os
from keep_alive import keep_alive

# === KONFIGURASI ===
PREFIX = "!"  # bisa diganti sesuai keinginan
TOKEN = os.getenv("TOKEN")  # token diambil dari environment variable

# === SETUP BOT ===
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# === OPSI YT-DLP ===
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': False,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',  # bind ke ipv4
    'force-ipv4': True,
    'cachedir': False,
    'extract_flat': False,
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if 'entries' in data:  # playlist
            data = data['entries'][0]
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

# === VARIABEL GLOBAL UNTUK QUEUE ===
queues = {}
now_playing = {}

def get_queue(ctx):
    if ctx.guild.id not in queues:
        queues[ctx.guild.id] = asyncio.Queue()
    return queues[ctx.guild.id]

async def play_next(ctx):
    queue = get_queue(ctx)
    if queue.empty():
        now_playing[ctx.guild.id] = None
        await ctx.send("Queue kosong, meninggalkan voice channel.")
        await ctx.voice_client.disconnect()
        return
    url = await queue.get()
    await play_song(ctx, url)

async def play_song(ctx, url):
    voice = ctx.voice_client
    if voice is None:
        return
    try:
        async with ctx.typing():
            player = await YTDLSource.from_url(url, loop=bot.loop, stream=True)
            voice.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop))
            now_playing[ctx.guild.id] = player
            await ctx.send(f"🎶 Sedang diputar: **{player.title}**")
    except Exception as e:
        await ctx.send(f"Terjadi kesalahan: {e}")
        await play_next(ctx)

# === EVENT ===
@bot.event
async def on_ready():
    print(f'{bot.user} telah online!')
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name=f"{PREFIX}play"))

# === COMMANDS ===
@bot.command(name='join')
async def join(ctx):
    """Bot join ke voice channel"""
    if ctx.author.voice is None:
        await ctx.send("Kamu harus berada di voice channel dulu.")
        return
    channel = ctx.author.voice.channel
    if ctx.voice_client is not None:
        await ctx.voice_client.move_to(channel)
    else:
        await channel.connect()
    await ctx.send(f"Bergabung ke {channel.name}")

@bot.command(name='play')
async def play(ctx, *, query):
    """Putar musik dari YouTube/Spotify/link/search"""
    if ctx.voice_client is None:
        await ctx.invoke(join)
    if ctx.voice_client is None:
        return
    # Jika bukan URL, jadikan pencarian
    if not query.startswith(('http://', 'https://')):
        query = f"ytsearch:{query}"
    queue = get_queue(ctx)
    await queue.put(query)
    await ctx.send(f"Ditambahkan ke antrian: {query}")
    if not ctx.voice_client.is_playing():
        await play_next(ctx)

@bot.command(name='skip')
async def skip(ctx):
    """Lewati lagu saat ini"""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭️ Lagu dilewati.")
    else:
        await ctx.send("Tidak ada lagu yang diputar.")

@bot.command(name='stop')
async def stop(ctx):
    """Hentikan musik dan bersihkan antrian"""
    if ctx.voice_client:
        queues[ctx.guild.id] = asyncio.Queue()
        ctx.voice_client.stop()
        await ctx.voice_client.disconnect()
        await ctx.send("⏹️ Musik dihentikan, antrian dibersihkan.")

@bot.command(name='pause')
async def pause(ctx):
    """Jeda musik"""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ Musik dijeda.")
    else:
        await ctx.send("Tidak ada musik yang diputar.")

@bot.command(name='resume')
async def resume(ctx):
    """Lanjutkan musik yang dijeda"""
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ Musik dilanjutkan.")
    else:
        await ctx.send("Tidak ada musik yang dijeda.")

@bot.command(name='volume')
async def volume(ctx, volume: int):
    """Atur volume (0-200)"""
    if ctx.voice_client is None:
        await ctx.send("Bot tidak sedang di voice channel.")
        return
    if not 0 <= volume <= 200:
        await ctx.send("Volume harus antara 0 dan 200.")
        return
    if ctx.voice_client.source:
        ctx.voice_client.source.volume = volume / 100
    await ctx.send(f"🔊 Volume diatur ke {volume}%")

@bot.command(name='queue')
async def queue(ctx):
    """Tampilkan antrian lagu"""
    q = get_queue(ctx)
    if q.empty():
        await ctx.send("Antrian kosong.")
    else:
        items = list(q._queue)
        desc = "\n".join([f"{i+1}. {item}" for i, item in enumerate(items[:10])])
        await ctx.send(f"**Antrian ({len(items)} lagu):**\n{desc}")

@bot.command(name='nowplaying', aliases=['np'])
async def nowplaying(ctx):
    """Tampilkan lagu yang sedang diputar"""
    if ctx.guild.id in now_playing and now_playing[ctx.guild.id] is not None:
        player = now_playing[ctx.guild.id]
        await ctx.send(f"🎵 Sedang diputar: **{player.title}**")
    else:
        await ctx.send("Tidak ada lagu yang diputar.")

@bot.command(name='disconnect', aliases=['dc'])
async def disconnect(ctx):
    """Keluar dari voice channel"""
    if ctx.voice_client:
        queues[ctx.guild.id] = asyncio.Queue()
        await ctx.voice_client.disconnect()
        await ctx.send("👋 Sampai jumpa!")

# === JALANKAN BOT ===
if __name__ == "__main__":
    if TOKEN is None:
        print("Error: TOKEN environment variable belum diatur.")
    else:
        keep_alive()
        bot.run(TOKEN)
