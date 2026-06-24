#!/usr/bin/env python3
"""
Bilibili 音频爬虫 - 为 HeartGuard 下载歌曲
用法:
  1. 批量下载预设歌曲:   python bilibili_music_crawler.py
  2. 下载单个 BV 号:     python bilibili_music_crawler.py BV1xx411c7mD 歌名
  3. 搜索并下载:          python bilibili_music_crawler.py --search "海阔天空 beyond"
"""

import requests
import re
import os
import sys
import json
import time
import hashlib
import subprocess
from urllib.parse import quote_plus

# ===== 配置 =====
MUSIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "music")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com",
}

# ===== 预设歌曲列表 (BV号 -> 歌曲名) =====
# 可自行补充 BV 号
SONG_LIST = {
    # 心率良好(放松)
    "海阔天空":         "BV1Gs41147oW",   # Beyond 海阔天空
    "起风了":           "BV1dW411h7xw",   # 买辣椒也用券 起风了
    "晴天":             "BV1Gs41147oW",   # 周杰伦 晴天 (需确认)
    "小幸运":           "BV1Hs411z7ZJ",   # 田馥甄 小幸运
    "平凡之路":         "BV1ax411U7aL",   # 朴树 平凡之路
    # 心率偏高(专注)
    "蓝莲花":           "BV1px411P7T5",   # 许巍 蓝莲花
    "夜空中最亮的星":   "BV1Z4411x7SW",   # 逃跑计划
    "追梦赤子心":       "BV1ax411U7aL",   # GALA
    "怒放的生命":       "BV1px411P7T5",   # 汪峰
    "曾经的你":         "BV1px411P7T5",   # 许巍
    # 心率偏低(治愈)
    "南山南":           "BV1Gs41147oW",   # 马頔
    "安河桥":           "BV1Gs41147oW",   # 宋冬野
    "成都":             "BV1bx411c7u7",   # 赵雷
    "七月上":           "BV1Gs41147oW",   # Jam
    # 情绪危机(活力)
    "隐形的翅膀":       "BV1Gs41147oW",   # 张韶涵
    "勇敢一点":         "BV1bx411c7u7",   # 赵雷
}

# ===== WBI 签名 (B站新API需要) =====
def get_wbi_keys(session):
    """获取 WBI 签名所需的 img_key 和 sub_key"""
    try:
        resp = session.get(
            "https://api.bilibili.com/x/web-interface/nav",
            headers=HEADERS,
            timeout=10
        )
        data = resp.json().get("data", {})
        img_url = data.get("wbi_img", {}).get("img_url", "")
        sub_url = data.get("wbi_img", {}).get("sub_url", "")
        img_key = img_url.rsplit("/", 1)[-1].split(".")[0]
        sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0]
        return img_key, sub_key
    except Exception as e:
        print(f"  [!] 获取 WBI keys 失败: {e}")
        return "", ""

def get_mixin_key(orig: str) -> str:
    """WBI mixin key 算法"""
    mixin_key_enc_tab = [
        46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
        27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
        37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
        22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52
    ]
    return "".join(orig[i] for i in mixin_key_enc_tab)[:32]

def wbi_sign(params: dict, img_key: str, sub_key: str) -> dict:
    """对参数进行 WBI 签名"""
    if not img_key or not sub_key:
        return params
    mixin_key = get_mixin_key(img_key + sub_key)
    curr_time = round(time.time())
    params["wts"] = curr_time
    # 按 key 排序
    query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    w_rid = hashlib.md5((query + mixin_key).encode()).hexdigest()
    params["w_rid"] = w_rid
    return params

# ===== 搜索歌曲 =====
def search_song(session, keyword):
    """在 B 站搜索歌曲，返回第一个结果的 BV 号和标题"""
    print(f"  搜索: {keyword}")
    try:
        img_key, sub_key = get_wbi_keys(session)
        params = {
            "search_type": "video",
            "keyword": keyword,
            "page": 1,
            "page_size": 5,
        }
        params = wbi_sign(params, img_key, sub_key)
        resp = session.get(
            "https://api.bilibili.com/x/wbi/search/type",
            params=params,
            headers=HEADERS,
            timeout=15
        )
        data = resp.json()
        results = data.get("data", {}).get("result", [])
        if results:
            first = results[0]
            bvid = first.get("bvid", "")
            title = first.get("title", "")
            # 清理标题中的 HTML 标签
            title = re.sub(r'<[^>]+>', '', title)
            print(f"  找到: {title} ({bvid})")
            return bvid, title
        else:
            print(f"  [!] 未找到搜索结果")
            return None, None
    except Exception as e:
        print(f"  [!] 搜索失败: {e}")
        return None, None

# ===== 获取音频流 URL =====
def get_audio_url(session, bvid):
    """通过 BV 号获取视频的音频流 URL (DASH 格式)"""
    try:
        # 先获取 cid
        resp = session.get(
            f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}",
            headers=HEADERS,
            timeout=10
        )
        data = resp.json().get("data", {})
        cid = data.get("cid")
        aid = data.get("aid")
        title = data.get("title", "")
        duration = data.get("duration", 0)

        if not cid:
            print(f"  [!] 无法获取 cid, bvid={bvid}")
            return None, None

        # 获取 DASH 格式播放地址
        resp = session.get(
            f"https://api.bilibili.com/x/player/playurl",
            params={
                "bvid": bvid,
                "cid": cid,
                "qn": 16,        # 最低画质即可, 只要音频
                "fnval": 16,     # DASH 格式
                "fnver": 0,
                "fourk": 0,
            },
            headers=HEADERS,
            timeout=15
        )
        data = resp.json().get("data", {})
        dash = data.get("dash", {})
        audio_list = dash.get("audio", [])

        if not audio_list:
            print(f"  [!] 未找到音频流 (可能不是DASH格式或需要登录)")
            return None, None

        # 选最高音质的音频
        audio_list.sort(key=lambda x: x.get("bandwidth", 0), reverse=True)
        audio_url = audio_list[0].get("baseUrl") or audio_list[0].get("base_url")

        print(f"  音频流: {audio_url[:80]}...")
        return audio_url, title

    except Exception as e:
        print(f"  [!] 获取音频URL失败: {e}")
        return None, None

# ===== 下载并转 MP3 =====
def download_and_convert(session, audio_url, song_name, output_dir):
    """下载音频流并用 ffmpeg 转 MP3"""
    os.makedirs(output_dir, exist_ok=True)
    safe_name = re.sub(r'[/\\:*?"<>|]', '_', song_name)
    mp3_path = os.path.join(output_dir, f"{safe_name}.mp3")
    tmp_path = os.path.join(output_dir, f"{safe_name}_tmp.m4a")

    # 如果已存在则跳过
    if os.path.exists(mp3_path):
        print(f"  文件已存在, 跳过: {mp3_path}")
        return mp3_path

    print(f"  下载中...")
    try:
        resp = session.get(audio_url, headers={
            **HEADERS,
            "Referer": "https://www.bilibili.com",
        }, stream=True, timeout=60)
        resp.raise_for_status()

        with open(tmp_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        file_size = os.path.getsize(tmp_path)
        print(f"  下载完成: {file_size / 1024 / 1024:.1f} MB")

        # 用 ffmpeg 转 MP3
        print(f"  转换 MP3...")
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", tmp_path, "-codec:a", "libmp3lame",
             "-qscale:a", "2", mp3_path],
            capture_output=True, text=True, timeout=120
        )

        if not os.path.exists(mp3_path):
            print(f"  [!] ffmpeg 转换失败: {result.stderr[-200:]}")
            # 如果转换失败, 直接用原文件
            os.rename(tmp_path, mp3_path.replace(".mp3", ".m4a"))
            return None

        os.remove(tmp_path)
        print(f"  ✓ 完成: {mp3_path}")
        return mp3_path

    except Exception as e:
        print(f"  [!] 下载/转换失败: {e}")
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return None

# ===== 用 yt-dlp 作为备选方案 =====
def download_with_ytdlp(bvid, song_name, output_dir):
    """使用 yt-dlp 下载音频 (备选方案)"""
    os.makedirs(output_dir, exist_ok=True)
    safe_name = re.sub(r'[/\\:*?"<>|]', '_', song_name)
    output_template = os.path.join(output_dir, f"{safe_name}.%(ext)s")
    url = f"https://www.bilibili.com/video/{bvid}"

    print(f"  使用 yt-dlp 下载: {url}")
    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "-f", "bestaudio",
                "-x", "--audio-format", "mp3",
                "--audio-quality", "0",
                "-o", output_template,
                "--no-playlist",
                url
            ],
            capture_output=True, text=True, timeout=180
        )

        mp3_path = os.path.join(output_dir, f"{safe_name}.mp3")
        if os.path.exists(mp3_path):
            print(f"  ✓ yt-dlp 完成: {mp3_path}")
            return mp3_path
        else:
            print(f"  [!] yt-dlp 输出: {result.stdout[-300:]}")
            print(f"  [!] yt-dlp 错误: {result.stderr[-300:]}")
            return None
    except Exception as e:
        print(f"  [!] yt-dlp 失败: {e}")
        return None

# ===== 主流程 =====
def main():
    os.makedirs(MUSIC_DIR, exist_ok=True)
    session = requests.Session()

    # 模式 1: 搜索下载
    if len(sys.argv) >= 2 and sys.argv[1] == "--search":
        keyword = " ".join(sys.argv[2:])
        bvid, title = search_song(session, keyword)
        if bvid:
            audio_url, _ = get_audio_url(session, bvid)
            if audio_url:
                download_and_convert(session, audio_url, keyword, MUSIC_DIR)
            else:
                print("  API 方式失败, 尝试 yt-dlp...")
                download_with_ytdlp(bvid, keyword, MUSIC_DIR)
        return

    # 模式 2: 指定 BV 号
    if len(sys.argv) >= 3 and not sys.argv[1].startswith("--"):
        bvid = sys.argv[1]
        song_name = sys.argv[2]
        audio_url, _ = get_audio_url(session, bvid)
        if audio_url:
            download_and_convert(session, audio_url, song_name, MUSIC_DIR)
        else:
            print("  API 方式失败, 尝试 yt-dlp...")
            download_with_ytdlp(bvid, song_name, MUSIC_DIR)
        return

    # 模式 3: 批量下载预设列表
    print("=" * 50)
    print("HeartGuard Bilibili 音乐爬虫")
    print(f"目标目录: {MUSIC_DIR}")
    print(f"预设歌曲: {len(SONG_LIST)} 首")
    print("=" * 50)

    success = 0
    failed = 0

    for song_name, bvid in SONG_LIST.items():
        print(f"\n--- [{success + failed + 1}/{len(SONG_LIST)}] {song_name} ---")

        # 检查是否已下载
        safe_name = re.sub(r'[/\\:*?"<>|]', '_', song_name)
        mp3_path = os.path.join(MUSIC_DIR, f"{safe_name}.mp3")
        if os.path.exists(mp3_path):
            print(f"  已存在, 跳过")
            success += 1
            continue

        # 方案 A: API + ffmpeg
        audio_url, _ = get_audio_url(session, bvid)
        if audio_url:
            result = download_and_convert(session, audio_url, song_name, MUSIC_DIR)
            if result:
                success += 1
                continue

        # 方案 B: yt-dlp 备选
        print("  切换到 yt-dlp...")
        result = download_with_ytdlp(bvid, song_name, MUSIC_DIR)
        if result:
            success += 1
        else:
            failed += 1
            print(f"  ✗ {song_name} 下载失败")

        # 礼貌延迟
        time.sleep(1)

    print(f"\n{'=' * 50}")
    print(f"完成! 成功 {success} 首, 失败 {failed} 首")
    print(f"文件目录: {MUSIC_DIR}")
    print(f"{'=' * 50}")

if __name__ == "__main__":
    main()
