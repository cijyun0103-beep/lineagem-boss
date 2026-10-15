from datetime import datetime, timedelta
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# 5 隻核心王的重生週期（單位：分鐘）
boss_database = {
    "死亡騎士": {"interval": 240, "respawn_time": None},
    "將軍": {"interval": 360, "respawn_time": None},
    "古代巨人": {"interval": 510, "respawn_time": None},
    "不死鳥": {"interval": 480, "respawn_time": None},
    "克特": {"interval": 600, "respawn_time": None},
}


@app.route("/")
def index():
  return render_template("index.html", bosses=boss_database)


@app.route("/get_bosses")
def get_bosses():
  return jsonify(boss_database)


@app.route("/kill/<boss_name>", methods=["POST"])
def record_kill(boss_name):
  if boss_name in boss_database:
    now = datetime.now()
    interval = boss_database[boss_name]["interval"]
    respawn = now + timedelta(minutes=interval)
    boss_database[boss_name]["respawn_time"] = respawn.strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    return jsonify({"status": "success"})
  return jsonify({"status": "error", "message": "找不到此王"}), 400


@app.route("/manual_kill", methods=["POST"])
def manual_kill():
  data = request.json
  boss_name = data.get("boss_name")
  time_str = data.get("time_str").strip()

  if boss_name not in boss_database:
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

    interval = boss_database[boss_name]["interval"]
    respawn = kill_time + timedelta(minutes=interval)

    boss_database[boss_name]["respawn_time"] = respawn.strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    return jsonify({"status": "success"})
  except ValueError:
    return jsonify({"status": "error", "message": "時間數值無效"}), 400


@app.route("/reset", methods=["POST"])
def reset_all():
  for boss in boss_database:
    boss_database[boss]["respawn_time"] = None
  return jsonify({"status": "success"})


if __name__ == "__main__":
  app.run(debug=True, port=5000)