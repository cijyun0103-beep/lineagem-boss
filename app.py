from datetime import datetime, timedelta
from flask import Flask, jsonify, render_template, request
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

# 5 隻核心王的預設間隔（分鐘）
boss_intervals = {
    "死亡騎士": 240,
    "將軍": 360,
    "古代巨人": 510,
    "不死鳥": 480,
    "克特": 600,
}


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

    supabase.table("bosses").update({"respawn_time": respawn_str}).eq(
        "name", boss_name
    ).execute()
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
    ), execute()
    return jsonify({"status": "success"})
  except ValueError:
    return jsonify({"status": "error", "message": "時間數值無效"}), 400


@app.route("/reset", methods=["POST"])
def reset_all():
  for boss in boss_intervals:
    supabase.table("bosses").update({"respawn_time": None}).eq(
        "name", boss
    ).execute()
  return jsonify({"status": "success"})


if __name__ == "__main__":
  app.run(debug=True, port=5000)