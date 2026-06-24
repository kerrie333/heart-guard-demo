#!/bin/bash
# HeartGuard 批量下载 B 站音乐
# 使用 yt-dlp + Safari cookies 下载
set -e

MUSIC_DIR="/Users/kerriewang/WorkBuddy/2026-06-19-10-16-44/heart-guard-demo/music"
mkdir -p "$MUSIC_DIR"

# 歌曲列表: "歌曲名|搜索关键词"
SONGS=(
  "起风了|起风了 买辣椒也用券"
  "晴天|周杰伦 晴天"
  "小幸运|田馥甄 小幸运"
  "平凡之路|朴树 平凡之路"
  "蓝莲花|许巍 蓝莲花"
  "夜空中最亮的星|逃跑计划 夜空中最亮的星"
  "追梦赤子心|GALA 追梦赤子心"
  "怒放的生命|汪峰 怒放的生命"
  "曾经的你|许巍 曾经的你"
  "南山南|马頔 南山南"
  "安河桥|宋冬野 安河桥"
  "成都|赵雷 成都"
  "七月上|Jam 七月上"
  "隐形的翅膀|张韶涵 隐形的翅膀"
  "勇敢一点|赵雷 勇敢一点"
)

TOTAL=${#SONGS[@]}
COUNT=0
SUCCESS=0
FAILED=0

for entry in "${SONGS[@]}"; do
  COUNT=$((COUNT + 1))
  SONG_NAME="${entry%%|*}"
  SEARCH_KEY="${entry##*|}"
  MP3_PATH="$MUSIC_DIR/${SONG_NAME}.mp3"

  echo ""
  echo "[$COUNT/$TOTAL] $SONG_NAME (搜索: $SEARCH_KEY)"

  # 跳过已存在
  if [ -f "$MP3_PATH" ]; then
    echo "  已存在, 跳过"
    SUCCESS=$((SUCCESS + 1))
    continue
  fi

  # 用 yt-dlp 搜索下载
  yt-dlp \
    -f "bestaudio" \
    -x --audio-format mp3 --audio-quality 5 \
    -o "$MUSIC_DIR/${SONG_NAME}.%(ext)s" \
    --no-playlist \
    --cookies-from-browser safari \
    "bilisearch:${SEARCH_KEY}" \
    2>&1 | tail -5

  if [ -f "$MP3_PATH" ]; then
    SIZE=$(du -h "$MP3_PATH" | cut -f1)
    echo "  ✓ 完成 ($SIZE)"
    SUCCESS=$((SUCCESS + 1))
  else
    echo "  ✗ 失败"
    FAILED=$((FAILED + 1))
  fi

  # 礼貌延迟
  sleep 2
done

echo ""
echo "========================================"
echo "完成! 成功 $SUCCESS, 失败 $FAILED"
echo "文件目录: $MUSIC_DIR"
echo "========================================"
ls -lh "$MUSIC_DIR/"
