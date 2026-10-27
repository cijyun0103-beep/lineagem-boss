from datetime import datetime, timedelta, timezone
from flask import Flask, jsonify, render_template, request
from flask_apscheduler import APScheduler
import requests
from supabase import create_client

app = Flask(__name__)


# 定義 Flask-APScheduler 的設定
class Config:
  JOBS = [{
      "id": "background_check",
      "func": "__main__:background_check_timers",
      "trigger": "interval",
      "seconds": 10,
  }]

  SCHEDULER_API_ENABLED = True


app.config.from_object(Config)

# 定義台灣時區 (UTC+8)
TW_TZ = timezone(timedelta(hours=8))

# Supabase 資料庫連線設定
SUPABASE_URL = "https://pauozfhclllxbidtxhxj.supabase.co"
SUPABASE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBhdW96ZmhjbGxseGJpZHR4aHhqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTIwNjA0NTcsImV4cCI6MjEwNzYzNjQ1N30."
    "3Xe6aGM8GcRezamqm8hpQjbI_ej5OEl4FsIFZTRIrww"
)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 你的 Discord Webhook 網址
DISCORD_WEBHOOK_URL = (
    "https://discord.com/api/webhooks/1558663969709883452/"
    "32kLWSD9jjvl-_ZTiUFfeosOoUE0lJJ5LRKeTVKXwP4Qyf-uqsWYlxzB5WnAlP3Z-fyK"
)

# 嚴格對應標準王名稱
boss_intervals = {
    "死亡騎士": 240,
    "將軍": 360,
    "古代巨人": 510,
    "不死鳥": 480,
    "克特": 600,
}


def send_discord_message(content, tts=False):
  if not DISCORD_WEBHOOK_URL:
    return
  try:
    requests.post(
        DISCORD_WEBHOOK_URL, json={"content": content, "tts": tts}
    )
  except Exception as e:
    print(f"Discord 發送失敗: {e}")


# 背景自動檢查核心邏輯
def background_check_timers():
  with app.app_context():
    try:
      response = supabase.table("bosses").select("*").execute()
      db_rows = response.data if response.data else []
      now = datetime.now(TW_TZ).replace(tzinfo=None)

      for row in db_rows:
        boss_name = row["name"]
        respawn_str = row["respawn_time"]
        is_notified = row.get("notified", False) or False
        interval = boss_intervals.get(boss_name, 0)

        if not respawn_str:
          continue

        respawn_time = datetime.strptime(respawn_str, "%Y-%m-%d %H:%M:%S")

        # 自動滾動時間處理
        if respawn_time <= now:
          missed_count = row.get("missed_count", 0) or 0
          while respawn_time <= now:
            respawn_time += timedelta(minutes=interval)
            missed_count += 1
            is_notified = False

          supabase.table("bosses").update({
              "respawn_time": respawn_time.strftime("%Y-%m-%d %H:%M:%S"),
              "missed_count": missed_count,
              "notified": is_notified,
          }).eq("name", boss_name).execute()
          continue

        diff_seconds = (respawn_time - now).total_seconds()

        # 當距離重生時間落在 50 秒到 75 秒之間
        if 50 <= diff_seconds <= 75:
          if not is_notified:
            update_res = (
                supabase.table("bosses")
                .update({"notified": True})
                .eq("name", boss_name)
                .eq("notified", False)
                .execute()
            )

            if update_res.data:
              tts_msg = f"{boss_name}預計一分鐘後重生!"
              send_discord_message(tts_msg, tts=True)
              print(f"成功發送通知: {tts_msg}")

        elif diff_seconds < -30 or diff_seconds > 120:
          if is_notified:
            supabase.table("bosses").update({"notified": False}).eq(
                "name", boss_name
            ).execute()

    except Exception as e:
      print(f"背景定時檢查錯誤: {e}")


def get_boss_database():
  response = supabase.table("bosses").select("*").execute()
  data = {}
  db_rows = response.data if response.data else []
  existing_names = {row["name"] for row in db_rows}

  for boss, interval in boss_intervals.items():
    respawn_time_str = None
    missed_count = 0

    for row in db_rows:
      if row["name"] == boss:
        respawn_time_str = row["respawn_time"]
        missed_count = row.get("missed_count", 0) or 0
        break

    if boss not in existing_names:
      supabase.table("bosses").insert({
          "name": boss,
          "respawn_time": None,
          "missed_count": 0,
          "notified": False,
      }).execute()

    data[boss] = {
        "interval": interval,
        "respawn_time": respawn_time_str,
        "missed_count": missed_count,
    }

  return data


@app.route("/")
def index():
  boss_database = get_boss_database()
  return render_template("index.html", bosses=boss_database, version="v2.10")


@app.route("/get_bosses")
def get_bosses():
  return jsonify(get_boss_database())


@app.route("/kill/<boss_name>", methods=["POST"])
def record_kill(boss_name):
  if boss_name in boss_intervals:
    now = datetime.now(TW_TZ).replace(tzinfo=None)
    kill_time_str = now.strftime("%H:%M:%S")
    interval = boss_intervals[boss_name]
    respawn = now + timedelta(minutes=interval)
    respawn_str = respawn.strftime("%H:%M:%S")
    respawn_db_str = respawn.strftime("%Y-%m-%d %H:%M:%S")

    supabase.table("bosses").update({
        "respawn_time": respawn_db_str,
        "missed_count": 0,
        "notified": False,
    }).eq("name", boss_name).execute()

    msg = (
        f"⚔️ **{boss_name}** 已於 `{kill_time_str}` 擊殺，預計於"
        f" `{respawn_str}` 重生！"
    )
    send_discord_message(msg, tts=False)

    return jsonify({"status": "success"})
  return jsonify({"status": "error", "message": "找不到此王"}), 400


@app.route("/manual_kill", methods=["POST"])
def manual_kill():
  data = request.json
  boss_name = data.get("boss_name")
  time_str = data.get("time_str", "").strip()

  if boss_name not in boss_intervals:
    return jsonify({"status": "error", "message": "找不到此王"}), 400

  # 新增：如果輸入 -1 則直接重置該王
  if time_str == "-1":
    supabase.table("bosses").update({
        "respawn_time": None,
        "missed_count": 0,
        "notified": False,
    }).eq("name", boss_name).execute()

    msg = f"🔄 **{boss_name}** 已透過手動輸入 `-1` 進行重置！"
    send_discord_message(msg, tts=False)
    return jsonify({"status": "success"})

  now = datetime.now(TW_TZ).replace(tzinfo=None)
  try:
    if len(time_str) == 4:
      hour = int(time_str[0:2])
      minute = int(time_str[2:4])
      second = 0
    elif len(time_str) == 6:
      hour = int(time_str[0:2])
      minute = int(time_str[2:4])
      second = int(time_str[4:6])
    else:
      return jsonify({"status": "error", "message": "時間格式錯誤"}), 400

    kill_time = now.replace(
        hour=hour, minute=minute, second=second, microsecond=0
    )
    if kill_time > now:
      kill_time = kill_time - timedelta(days=1)

    kill_time_str = kill_time.strftime("%H:%M:%S")
    interval = boss_intervals[boss_name]
    respawn = kill_time + timedelta(minutes=interval)
    respawn_str = respawn.strftime("%H:%M:%S")
    respawn_db_str = respawn.strftime("%Y-%m-%d %H:%M:%S")

    supabase.table("bosses").update({
        "respawn_time": respawn_db_str,
        "missed_count": 0,
        "notified": False,
    }).eq("name", boss_name).execute()

    msg = (
        f"✍️ **{boss_name}** (手動補登) 已於 `{kill_time_str}` 擊殺，預計於"
        f" `{respawn_str}` 重生！"
    )
    send_discord_message(msg, tts=False)

    return jsonify({"status": "success"})
  except ValueError:
    return jsonify({"status": "error", "message": "時間數值無效"}), 400


@app.route("/reset", methods=["POST"])
def reset_all():
  for boss in boss_intervals:
    supabase.table("bosses").update({
        "respawn_time": None,
        "missed_count": 0,
        "notified": False,
    }).eq("name", boss).execute()
  send_discord_message("🔄 **【王表通知】** 所有王表時間已重置！", tts=False)
  return jsonify({"status": "success"})


if __name__ == "__main__":
  scheduler = APScheduler()
  scheduler.init_app(app)
  scheduler.start()
  app.run(debug=True, port=5000, use_reloader=False)