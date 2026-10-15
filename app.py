from datetime import datetime, timedelta
import threading
import time
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify, render_template, request
import requests
from supabase import create_client

app = Flask(__name__)

# Supabase 資料庫連線設定
SUPABASE_URL = "https://pauozfhclllxbidtxhxj.supabase.co"
SUPABASE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBhdW96ZmhjbGxseGJpZHR4aHhqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTIwNjA0NTcsImV4cCI6MjEwNzYzNjQ1N30."
    "3Xe6aGM8GcRezamqm8hpQjbI_ej5OEl4FsIFZTRIrww"
)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 請填入你的 Discord Webhook 網址
DISCORD_WEBHOOK_URL = "你的_DISCORD_WEBHOOK_URL"

# 5 隻核心王的預設間隔（分鐘）
boss_intervals = {
    "死亡騎士": 240,
    "將軍": 360,
    "古代巨人": 510,
    "不死鳥": 480,
    "克特": 600,
}

# 記錄哪些王已經發送過 1 分鐘提醒，避免重複洗頻
notified_bosses = set()


def send_discord_message(content):
  if not DISCORD_WEBHOOK_URL or DISCORD_WEBHOOK_URL == "你的_DISCORD_WEBHOOK_URL":
    return
  try:
    requests.post(DISCORD_WEBHOOK_URL, json={"content": content})
  except Exception as e:
    print(f"Discord 發送失敗: {e}")


def get_boss_database():
  response = supabase.table("bosses").select("*").execute()
  data = {}
  db_rows = response.data if response.data else []
  existing_names = {row["name"] for row in db_rows}

  for boss, interval in boss_intervals.items():
    respawn_time = None
    for row in db_rows:
      if row["name"] == boss:
        respawn_time = row["respawn_time"]
        break

    if boss not in existing_names:
      supabase.table("bosses").insert(
          {"name": boss, "respawn_time": None}
      ).execute()

    data[boss] = {"interval": interval, "respawn_time": respawn_time}
  return data


@app.route("/")
def index():
  boss_database = get_boss_database()
  return render_template("index.html", bosses=boss_database)


@app.route("/get_bosses")
def get_bosses():
  return jsonify(get_boss_database())


@app.route("/kill/<boss_name>", methods=["POST"])
def record_kill(boss_name):
  if boss_name in boss_intervals:
    now = datetime.now()
    interval = boss_intervals[boss_name]
    respawn = now + timedelta(minutes=interval)
    respawn_str = respawn.strftime("%Y-%m-%d %H:%M:%S")

    # 更新雲端資料庫
    supabase.table("bosses").update({"respawn_time": respawn_str}).eq(
        "name", boss_name
    ).execute()

    # 移除舊的提醒紀錄，讓下次倒數 1 分鐘能正常觸發
    if boss_name in notified_bosses:
      notified_bosses.remove(boss_name)

    # 發送 Discord 擊殺通知
    msg = (
        f"⚔️ **【王表通知】** `{boss_name}` 已被擊殺！\n⏳ 預計重生時間："
        f" `{respawn_str}`"
    )
    send_discord_message(msg)

    return jsonify({"status": "success"})
  return jsonify({"status": "error", "message": "找不到此王"}), 400


@app.route("/manual_kill", methods=["POST"])
def manual_kill():
  data = request.json
  boss_name = data.get("boss_name")
  time_str = data.get("time_str", "").strip()

  if boss_name not in boss_intervals:
    return jsonify({"status": "error", "message": "找不到此王"}), 400

  now = datetime.now()
  try:
    if len(time_str) == 4:
      hour = int(time_str[0:2])
      minute = int(time_str[2:4])
      kill_time = now.replace(
          hour=hour, minute=minute, second=0, microsecond=0
      )
    elif len(time_str) == 6:
      hour = int(time_str[0:2])
      minute = int(time_str[2:4])
      second = int(time_str[4:6])
      kill_time = now.replace(
          hour=hour, minute=minute, second=second, microsecond=0
      )
    else:
      return jsonify({"status": "error", "message": "時間格式錯誤"}), 400

    interval = boss_intervals[boss_name]
    respawn = kill_time + timedelta(minutes=interval)
    respawn_str = respawn.strftime("%Y-%m-%d %H:%M:%S")

    supabase.table("bosses").update({"respawn_time": respawn_str}).eq(
        "name", boss_name
    ).execute()

    if boss_name in notified_bosses:
      notified_bosses.remove(boss_name)

    msg = (
        f"⚔️ **【王表手動補登】** `{boss_name}`\n⏳ 預計重生時間："
        f" `{respawn_str}`"
    )
    send_discord_message(msg)

    return jsonify({"status": "success"})
  except ValueError:
    return jsonify({"status": "error", "message": "時間數值無效"}), 400


@app.route("/reset", methods=["POST"])
def reset_all():
  for boss in boss_intervals:
    supabase.table("bosses").update({"respawn_time": None}).eq(
        "name", boss
    ).execute()
  notified_bosses.clear()
  send_discord_message("🔄 **【王表通知】** 所有王表時間已重置！")
  return jsonify({"status": "success"})


# 背景定時檢查：每分鐘執行一次，檢查是否剩餘 1 分鐘
def check_boss_timers():
  try:
    response = supabase.table("bosses").select("*").execute()
    rows = response.data if response.data else []
    now = datetime.now()

    for row in rows:
      boss_name = row["name"]
      respawn_str = row["respawn_time"]
      if not respawn_str:
        continue

      respawn_time = datetime.strptime(respawn_str, "%Y-%m-%d %H:%M:%S")
      diff_seconds = (respawn_time - now).total_seconds()

      # 當剩餘時間在 50 秒到 70 秒之間（即倒數 1 分鐘左右），且還沒發送過通知
      if 50 <= diff_seconds <= 70:
        if boss_name not in notified_bosses:
          notified_bosses.add(boss_name)
          # 發送 Discord 訊息，開頭加上 TTS 語音朗讀提示
          tts_msg = (
              f"📢 **【注意】** 警告！精銳首領 **{boss_name}** 將在 1 分鐘後重生！"
              f" (預定時間: {respawn_str})"
          )
          send_discord_message(tts_msg)
  except Exception as e:
    print(f"定時檢查錯誤: {e}")


# 啟動背景排程器
scheduler = BackgroundScheduler()
scheduler.add_job(
    func=check_boss_timers, trigger="interval", seconds=30
)  # 每 30 秒檢查一次
scheduler.start()


if __name__ == "__main__":
  app.run(debug=True, port=5000)