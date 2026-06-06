from flask import Flask, render_template, request, jsonify, send_file
import sqlite3
import datetime
import random
import io
import json as json_lib
import urllib.request
import urllib.parse

from dotenv import load_dotenv
import os
import google.genai as genai

app = Flask(__name__)

# ===== Gemini API =====
load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


# ===== Database =====
def init_db():
    conn = sqlite3.connect("diary.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS diary(
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            user TEXT,
            ai   TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_diary(
            date    TEXT PRIMARY KEY,
            summary TEXT,
            title   TEXT,
            emotion TEXT
        )
    """)
    # カラム追加（既存DBへの対応）
    try:
        c.execute("ALTER TABLE daily_diary ADD COLUMN title TEXT")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE daily_diary ADD COLUMN emotion TEXT")
    except Exception:
        pass
    c.execute("""
        CREATE TABLE IF NOT EXISTS home_insight(
            date    TEXT PRIMARY KEY,
            insight TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_dictionary(
            id      INTEGER PRIMARY KEY CHECK (id = 1),
            updated TEXT,
            data    TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS emotion_scores(
            date   TEXT PRIMARY KEY,
            energy INTEGER
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS life_themes(
            id      INTEGER PRIMARY KEY CHECK (id = 1),
            updated TEXT,
            data    TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_moods(
            date TEXT PRIMARY KEY,
            mood INTEGER,
            time TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS weekly_report(
            id      INTEGER PRIMARY KEY CHECK (id = 1),
            updated TEXT,
            data    TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS self_model(
            id      INTEGER PRIMARY KEY CHECK (id = 1),
            updated TEXT,
            data    TEXT
        )
    """)
    conn.commit()
    conn.close()


init_db()


# ===== AI Diary Summary =====
def generate_diary_entry(date: str, conversations: list) -> dict | None:
    """会話記録から日記（タイトル・感情タグ・本文）を生成する"""
    conv_text = '\n'.join(
        [f"私：{c['user']}\nAI：{c['ai']}" for c in conversations]
    )
    prompt = f"""
以下は{date}の会話記録です。この会話をもとに日記エントリを作成してください。

出力はJSON形式で、以下の3つのキーのみ含めてください：
- "title": その日を一言で表す詩的なタイトル（10〜20字、鍵括弧なし）
- "emotion": 感情・状況タグを2〜3個（例: "夜 / 対人 / 少し疲労" のようなスラッシュ区切り）
- "body": 本人が書いたような日記本文（80〜120字。「AIと話した」などの表現は使わない）

会話記録：
{conv_text}

JSONのみ出力し、説明文は不要です。
"""
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite", contents=prompt
        )
        text = response.text.strip()
        # コードブロック除去
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json_lib.loads(text.strip())
    except Exception as e:
        print(f"Diary entry error: {e}")
        return None


def get_diary_entry(conn, day: str) -> dict:
    """日記エントリ取得。今日は再生成、過去はキャッシュ優先"""
    today = datetime.date.today().isoformat()
    c = conn.cursor()

    if day != today:
        c.execute("SELECT summary, title, emotion FROM daily_diary WHERE date=?", (day,))
        row = c.fetchone()
        if row and row[0]:
            return {"body": row[0], "title": row[1] or "", "emotion": row[2] or ""}

    c.execute(
        "SELECT user, ai FROM diary WHERE substr(date,1,10)=? ORDER BY date ASC", (day,)
    )
    convs = [{"user": r[0], "ai": r[1]} for r in c.fetchall()]
    entry = generate_diary_entry(day, convs)
    if entry:
        c.execute(
            "INSERT OR REPLACE INTO daily_diary(date, summary, title, emotion) VALUES(?,?,?,?)",
            (day, entry.get("body", ""), entry.get("title", ""), entry.get("emotion", ""))
        )
        conn.commit()
        return entry
    return {"body": "（日記を生成できませんでした）", "title": "", "emotion": ""}


def _parse_json_response(text: str):
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    return json_lib.loads(text.strip())


def generate_recent_you(conversations: list) -> dict | None:
    """直近の会話から「最近のあなた」を段落形式で生成"""
    if not conversations:
        return None
    conv_text = '\n'.join([f"私：{c['user']}" for c in conversations[-20:]])
    prompt = f"""
以下はユーザーの最近の会話の断片です。
深夜ラジオのパーソナリティが静かに観察するように、この人の最近の状態を分析してください。

JSONで以下の3キーを出力：
- "intro": 全体的な傾向を表す1文（30〜50字。「最近は〜」で始める。断言しない）
- "highlights": 感情を強く動かしているもの3項目（各6〜12字のリスト）
- "closing": 課題や内側にある葛藤を表す1文（25〜45字。「一方で〜」で始める）

口調は詩的に、分析っぽくならないように。JSONのみ出力。

会話の断片：
{conv_text}
"""
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite", contents=prompt
        )
        return _parse_json_response(response.text)
    except Exception as e:
        print(f"Recent you error: {e}")
        return None


def get_recent_you(conn) -> dict:
    """今日の「最近のあなた」を取得（日次キャッシュ）"""
    today = datetime.date.today().isoformat()
    c = conn.cursor()
    c.execute("SELECT insight FROM home_insight WHERE date=?", (today,))
    row = c.fetchone()
    if row and row[0]:
        try:
            data = json_lib.loads(row[0])
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    since = (datetime.date.today() - datetime.timedelta(days=14)).isoformat()
    c.execute(
        "SELECT user, ai FROM diary WHERE substr(date,1,10)>=? ORDER BY date DESC LIMIT 30",
        (since,)
    )
    convs = [{"user": r[0], "ai": r[1]} for r in c.fetchall()]
    result = generate_recent_you(convs)
    if result:
        c.execute(
            "INSERT OR REPLACE INTO home_insight(date, insight) VALUES(?,?)",
            (today, json_lib.dumps(result, ensure_ascii=False))
        )
        conn.commit()
    return result or {}


def generate_emotion_scores(days_data: list) -> list | None:
    """各日の会話からエネルギースコア(0-100)を一括生成"""
    lines = []
    for d in days_data:
        msgs = ' / '.join(d['msgs'][:5])
        lines.append(f"{d['date']}: {msgs}")
    prompt = f"""
以下の各日の発言断片から、感情エネルギースコア（0〜100の整数）を推定してください。
（100=非常に活気、50=普通、0=非常に疲弊・落ち込み）

JSONの配列のみ出力。形式: [{{"date":"YYYY-MM-DD","energy":整数}}, ...]

{chr(10).join(lines)}
"""
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite", contents=prompt
        )
        result = _parse_json_response(response.text)
        return result if isinstance(result, list) else None
    except Exception as e:
        print(f"Emotion scores error: {e}")
        return None


def get_emotion_trend(conn) -> list:
    """過去7日のエネルギー推移を返す（日次キャッシュ）"""
    today = datetime.date.today()
    days = [(today - datetime.timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    c = conn.cursor()

    result = {}
    missing = []
    for day in days:
        if day == today.isoformat():
            missing.append(day)
        else:
            c.execute("SELECT energy FROM emotion_scores WHERE date=?", (day,))
            row = c.fetchone()
            if row:
                result[day] = row[0]
            else:
                missing.append(day)

    if missing:
        days_data = []
        for day in missing:
            c.execute(
                "SELECT user FROM diary WHERE substr(date,1,10)=? ORDER BY date ASC",
                (day,)
            )
            msgs = [r[0] for r in c.fetchall()]
            if msgs:
                days_data.append({"date": day, "msgs": msgs})

        if days_data:
            scores = generate_emotion_scores(days_data)
            if scores:
                for s in scores:
                    result[s["date"]] = s["energy"]
                    if s["date"] != today.isoformat():
                        c.execute(
                            "INSERT OR REPLACE INTO emotion_scores(date,energy) VALUES(?,?)",
                            (s["date"], s["energy"])
                        )
                conn.commit()

    return [{"date": d, "energy": result.get(d)} for d in days]


def generate_life_themes(conversations: list) -> list | None:
    """会話履歴から今月の人生テーマを抽出"""
    if not conversations:
        return None
    conv_text = '\n'.join([f"私：{c['user']}" for c in conversations[-40:]])
    prompt = f"""
以下の会話から、この人が最近向き合っている人生テーマを3〜4個抽出してください。

JSONの配列のみ出力（例: ["本気になれる場所探し", "人とのつながり", "エネルギー回復"]）
- 各10〜20字
- 具体的で、その人特有のテーマに
- 「〜探し」「〜との向き合い」「〜を求める旅」など動的なニュアンスで

{conv_text}
"""
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite", contents=prompt
        )
        result = _parse_json_response(response.text)
        return result if isinstance(result, list) else None
    except Exception as e:
        print(f"Life themes error: {e}")
        return None


def get_life_themes(conn) -> list:
    """今月の人生テーマを取得（7日キャッシュ）"""
    c = conn.cursor()
    c.execute("SELECT updated, data FROM life_themes WHERE id=1")
    row = c.fetchone()
    if row and row[0]:
        try:
            updated = datetime.date.fromisoformat(row[0])
            if (datetime.date.today() - updated).days < 7:
                return json_lib.loads(row[1])
        except Exception:
            pass

    since = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
    c.execute(
        "SELECT user, ai FROM diary WHERE substr(date,1,10)>=? ORDER BY date DESC LIMIT 60",
        (since,)
    )
    convs = [{"user": r[0], "ai": r[1]} for r in c.fetchall()]
    themes = generate_life_themes(convs)
    if themes:
        c.execute(
            "INSERT OR REPLACE INTO life_themes(id, updated, data) VALUES(1,?,?)",
            (datetime.date.today().isoformat(), json_lib.dumps(themes, ensure_ascii=False))
        )
        conn.commit()
    return themes or []


def generate_user_dictionary(conversations: list) -> dict | None:
    """会話履歴から「あなた辞典」を生成"""
    if not conversations:
        return None
    conv_text = '\n'.join([f"私：{c['user']}" for c in conversations[-60:]])
    prompt = f"""
以下はユーザーの会話の断片です。
この人の輪郭を「あなた辞典」としてまとめてください。

JSONで以下の4キーを出力：
- "likes": 好きなもの・こと（3〜5項目のリスト、各8〜15字）
- "dislikes": 苦手なもの・こと（2〜4項目のリスト、各8〜15字）
- "energy": 元気になる条件（2〜4項目のリスト、各8〜15字）
- "pattern": 思考のくせ（2〜4項目のリスト、各8〜18字）

断定しすぎず、観察的に。「〜かも」「〜みたい」のニュアンスで。
JSONのみ出力。

会話の断片：
{conv_text}
"""
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite", contents=prompt
        )
        return _parse_json_response(response.text)
    except Exception as e:
        print(f"User dictionary error: {e}")
        return None


def get_user_dictionary(conn) -> dict | None:
    """あなた辞典を取得（7日キャッシュ）"""
    c = conn.cursor()
    c.execute("SELECT updated, data FROM user_dictionary WHERE id=1")
    row = c.fetchone()
    if row and row[0]:
        updated = datetime.date.fromisoformat(row[0])
        if (datetime.date.today() - updated).days < 7:
            try:
                return json_lib.loads(row[1])
            except Exception:
                pass

    c.execute("SELECT user, ai FROM diary ORDER BY date DESC LIMIT 80")
    convs = [{"user": r[0], "ai": r[1]} for r in c.fetchall()]
    dictionary = generate_user_dictionary(convs)
    if dictionary:
        c.execute(
            "INSERT OR REPLACE INTO user_dictionary(id, updated, data) VALUES(1,?,?)",
            (datetime.date.today().isoformat(), json_lib.dumps(dictionary, ensure_ascii=False))
        )
        conn.commit()
    return dictionary


# ===== AI Reply =====
def generate_ai_reply(user_text):
    prompt = f"""
あなたは深夜ラジオのパーソナリティのような存在です。
静かに話を聞き、相手の言葉の奥にあるものを拾い上げる。
押しつけず、でも確かに"そこにいる"感じ。

【話し方】
- 落ち着いた、少し詩的なトーン
- 短く、でも余韻がある言葉を選ぶ
- 「〜だね」「〜かな」「〜だと思う」など柔らかい語尾
- たまに少し哲学的な視点を一言だけ添える

【構成】
- 相手の言葉をそっと受け止める（1文）
- その人の内側にあるものに光を当てる視点か問い（1〜2文）
- 合計2〜3文。絶対に長くしない

【禁止】
- 「AI：」などのラベル
- 「頑張って」「大丈夫」などの空虚な励まし
- 説教・アドバイス・解決策の押しつけ
- 明るすぎる・軽すぎる反応

深夜3時に、誰かがそっと話しかけてくれた——そんな感覚で返してください。

相手の言葉：{user_text}
"""
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite", contents=prompt
        )
        return response.text
    except Exception as e:
        print(f"API Error: {e}")
        return "ごめんね、ちょっと今考え事をしちゃって頭が追いつかないんだ。少し時間をおいてから、また話しかけてくれるかな？"


# ===== VOICEVOX 互換 TTS =====
# 試みるエンジンのポート一覧（順番に試す）
# 50021: VOICEVOX / 10101: AivisSpeech / 50031: COEIROINK
TTS_PORTS = [50021, 10101, 50031]

# スピーカー名から性別を推定
FEMALE_KEYWORDS = [
    'めたん', 'ずんだ', 'つむぎ', 'はう', 'リツ', 'ひまり', 'もち子',
    'WhiteCUL', '小夜', 'SAYO', 'アンヌ', '夜街', '旅人', '小晴',
    'なみき', 'ちび式', 'トワ', '琴詠', 'あみ', '式', '女', '姫',
]
MALE_KEYWORDS = [
    '武宏', '虎太郎', '龍星', '後鬼', '剣崎', '雄', '司朗', '男',
    'マシン', 'ロボ', '勇雄', 'テスト',
]


def guess_gender(name: str) -> str:
    for kw in FEMALE_KEYWORDS:
        if kw in name:
            return 'women'
    for kw in MALE_KEYWORDS:
        if kw in name:
            return 'men'
    return 'women'  # デフォルトは女性


def fetch_speakers_from_port(port: int) -> list:
    """指定ポートからスピーカー一覧を取得"""
    try:
        req = urllib.request.Request(f"http://localhost:{port}/speakers")
        with urllib.request.urlopen(req, timeout=2) as resp:
            speakers = json_lib.loads(resp.read())
        result = []
        for s in speakers:
            gender = guess_gender(s.get("name", ""))
            for style in s.get("styles", []):
                result.append({
                    "value":  f"{port}:{style['id']}",   # "ポート:ID"
                    "name":   f"{s['name']}（{style['name']}）",
                    "gender": gender,
                })
        return result
    except Exception:
        return []


def synthesize(port: int, speaker_id: int, text: str) -> bytes | None:
    """指定ポート・スピーカーで音声合成して WAV bytes を返す"""
    try:
        # ① audio_query
        params = urllib.parse.urlencode({"text": text, "speaker": speaker_id})
        req = urllib.request.Request(
            f"http://localhost:{port}/audio_query?{params}", method="POST"
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            query = json_lib.loads(resp.read())

        # 速度・間を調整
        query["speedScale"]        = 1.1
        query["prePhonemeLength"]  = 0.05
        query["postPhonemeLength"] = 0.05

        # ② synthesis
        body    = json_lib.dumps(query).encode()
        params2 = urllib.parse.urlencode({"speaker": speaker_id})
        req2 = urllib.request.Request(
            f"http://localhost:{port}/synthesis?{params2}",
            data=body, method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req2, timeout=15) as resp2:
            return resp2.read()
    except Exception:
        return None


# ===== Save Diary =====
def save_diary(user, ai):
    conn = sqlite3.connect("diary.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO diary(date, user, ai) VALUES(?, ?, ?)",
        (datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), user, ai),
    )
    conn.commit()
    conn.close()


# ===== Get Recent =====
def get_recent():
    conn = sqlite3.connect("diary.db")
    c = conn.cursor()
    c.execute("SELECT date, user FROM diary ORDER BY date DESC LIMIT 10")
    data = c.fetchall()
    conn.close()
    return data


# ===== Random Past =====
def get_random_past():
    conn = sqlite3.connect("diary.db")
    c = conn.cursor()
    c.execute("SELECT date, user FROM diary")
    data = c.fetchall()
    conn.close()
    return random.choice(data) if data else None


# ===== Daily Prompts =====
DAILY_PROMPTS = [
    "最近、自分に正直でいられていますか？",
    "今日、何かに感動しましたか？",
    "今の自分を、一言で表すとしたら？",
    "最近、心が軽くなった瞬間はありましたか？",
    "今、一番「重い」と感じていることは何ですか？",
    "最近、誰かに素直な気持ちを伝えられましたか？",
    "今、何に対して「もやもや」していますか？",
    "最近、自分を責めすぎていませんか？",
    "最近、誰かと本当に通じ合えた気がしましたか？",
    "今、誰に会いたいですか？",
    "最近、誰かのことを心配していますか？",
    "関係を深めたい人が、今いますか？",
    "最近、「一人でいたい」と「誰かといたい」、どちらが強いですか？",
    "今、何に向けてエネルギーを使っていますか？",
    "最近、「これは意味があることだ」と感じた瞬間はありましたか？",
    "今の自分は、どこに向かっていますか？",
    "最近、本気になれていますか？",
    "今日の体は、何点ですか？",
    "最近、よく眠れていますか？",
    "元気が出るのは、どんな時ですか？",
    "最近、身体を動かしましたか？",
    "最近、「幸せだな」と感じた瞬間はありましたか？",
    "今、何があれば満足できると思いますか？",
    "自分にとって「豊かさ」とはどんな状態ですか？",
    "最近、小さなことで喜べましたか？",
    "今、何がいちばん「消耗」していますか？",
    "最近、本当の意味でリフレッシュできましたか？",
    "1年後、どんな自分でいたいですか？",
    "最近、新しい何かに挑戦しましたか？",
    "最近、自分の変化に気づきましたか？",
    "今日、何かを避けていませんか？",
    "今の自分が、一番「怖い」と思っていることは何ですか？",
    "最近、誰かに頼れましたか？",
    "今日、自分に優しくできましたか？",
    "最近、何かに没頭できましたか？",
    "今の自分に足りていないものは何ですか？",
    "最近、笑いましたか？どんな時に？",
    "今の自分の「ペース」はどうですか？",
    "最近、誰かに感謝を伝えましたか？",
    "今、何かに夢中になっていますか？",
    "最近、「ちゃんと生きてる」と感じた瞬間はありましたか？",
    "今日、どんな色の一日でしたか？",
    "最近、自分の「好き」を大切にできましたか？",
    "今、心の中で何かが変わり始めていますか？",
    "最近、静かな時間を持てましたか？",
    "最近、自分の価値観に従って選択できましたか？",
    "最近、何かをあきらめましたか？それはどんな気持ちでしたか？",
    "今の自分が、もっと増やしたいものは何ですか？",
    "最近、時間を忘れるほど集中しましたか？",
    "今日、何が「いい一日だった」と思えるポイントになりそうですか？",
    "最近、誰かの言葉が心に残りましたか？",
    "今の自分に、最も必要なものは何ですか？",
    "最近、自分のことを後回しにしていませんか？",
    "今日、何かひとつだけ手放すとしたら何ですか？",
    "最近、「これが自分だ」と感じた瞬間はありましたか？",
    "今、誰かに謝りたいことはありますか？",
    "最近、未来が少し楽しみになる瞬間はありましたか？",
    "今日、どんな自分でいたいですか？",
    "最近、自分の「弱さ」を認められましたか？",
    "今、一番「大切にしたいもの」は何ですか？",
]


def get_daily_prompt() -> str:
    idx = datetime.date.today().timetuple().tm_yday % len(DAILY_PROMPTS)
    return DAILY_PROMPTS[idx]


# ===== Weekly Report =====
def generate_weekly_report(conn) -> str | None:
    since = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    c = conn.cursor()
    c.execute(
        "SELECT user, date FROM diary WHERE substr(date,1,10)>=? ORDER BY date ASC",
        (since,)
    )
    convs = c.fetchall()
    if not convs:
        return None

    c.execute("SELECT date, mood FROM daily_moods WHERE date>=? ORDER BY date ASC", (since,))
    moods = c.fetchall()

    conv_text  = '\n'.join([f"[{r[1][:10]}] {r[0]}" for r in convs[-20:]])
    mood_text  = '\n'.join([f"{r[0]}: 気分{r[1]}/5" for r in moods]) if moods else "記録なし"

    prompt = f"""
以下は過去7日間の会話と気分の記録です。
深夜ラジオのパーソナリティが1週間を静かに振り返るように、100〜180字で書いてください。

【スタイル】
- 「先週は〜」で始める
- 詩的で余韻がある
- 気分の変化・傾向・気づきを自然に盛り込む
- 最後は「あなた」への語りかけで締める
- 文章のみ、ラベル不要

会話記録:
{conv_text}

気分記録:
{mood_text}
"""
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite", contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        print(f"Weekly report error: {e}")
        return None


def get_weekly_report(conn) -> str:
    today = datetime.date.today().isoformat()
    c = conn.cursor()
    c.execute("SELECT updated, data FROM weekly_report WHERE id=1")
    row = c.fetchone()
    if row and row[0] == today:
        return row[1]
    report = generate_weekly_report(conn)
    if report:
        c.execute(
            "INSERT OR REPLACE INTO weekly_report(id, updated, data) VALUES(1,?,?)",
            (today, report)
        )
        conn.commit()
    return report or ""


# ===== Pages =====
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/mypage")
def mypage():
    return render_template("mypage.html")

@app.route("/diary")
def diary():
    return render_template("diary.html")

@app.route("/analysis")
def analysis():
    return render_template("analysis.html")

@app.route("/self")
def self_page():
    return render_template("self.html")


# ===== API =====
@app.route("/api/talk", methods=["POST"])
def talk():
    """テキスト返答のみ（速度優先 — 音声は /api/tts に分離）"""
    req_data = request.json
    if not req_data or "text" not in req_data:
        return jsonify({"reply": "うまく声が聞き取れなかったみたい。もう一度話しかけてみてね！"})

    user_text = req_data["text"]
    if not user_text.strip():
        return jsonify({"reply": "何かお話ししてくれるのを待っているよ！"})

    ai_text = generate_ai_reply(user_text)
    save_diary(user_text, ai_text)

    return jsonify({"reply": ai_text})   # テキストだけ即返す


@app.route("/api/tts", methods=["POST"])
def tts():
    """音声合成（VOICEVOX 互換エンジンを使用）"""
    req_data = request.json
    if not req_data or "text" not in req_data:
        return jsonify({"use_browser": True})

    text       = req_data["text"]
    voice_val  = req_data.get("voice", "50021:8")   # "port:id"

    try:
        port_str, id_str = str(voice_val).split(":")
        port       = int(port_str)
        speaker_id = int(id_str)
    except Exception:
        port, speaker_id = 50021, 8

    wav = synthesize(port, speaker_id, text)
    if wav:
        return send_file(io.BytesIO(wav), mimetype="audio/wav")

    return jsonify({"use_browser": True})


@app.route("/api/tts_speakers")
def tts_speakers():
    """全エンジンのスピーカー一覧を返す"""
    result = []
    for port in TTS_PORTS:
        result.extend(fetch_speakers_from_port(port))
    return jsonify(result)


@app.route("/api/recent")
def recent():
    return jsonify(get_recent())


@app.route("/api/random")
def random_entry():
    return jsonify(get_random_past())


@app.route("/api/diary/daily")
def diary_daily():
    """日ごとにまとめた日記を返す（AIサマリー付き）"""
    conn = sqlite3.connect("diary.db")
    c = conn.cursor()
    c.execute("""
        SELECT substr(date, 1, 10) as day, count(*) as cnt
        FROM diary
        GROUP BY day
        ORDER BY day DESC
    """)
    rows = c.fetchall()
    result = []
    for day, cnt in rows:
        entry = get_diary_entry(conn, day)
        result.append({"date": day, "count": cnt, **entry})
    conn.close()
    return jsonify(result)


@app.route("/api/diary/random_day")
def diary_random_day():
    """ランダムな1日分の日記を返す（AIサマリー付き）"""
    conn = sqlite3.connect("diary.db")
    c = conn.cursor()
    c.execute("""
        SELECT substr(date, 1, 10) as day, count(*) as cnt
        FROM diary
        GROUP BY day
        ORDER BY RANDOM()
        LIMIT 1
    """)
    row = c.fetchone()
    if not row:
        conn.close()
        return jsonify(None)
    day, cnt = row
    entry = get_diary_entry(conn, day)
    conn.close()
    return jsonify({"date": day, "count": cnt, **entry})


@app.route("/api/recent_you")
def recent_you():
    """今日の「最近のあなた」を返す"""
    conn = sqlite3.connect("diary.db")
    data = get_recent_you(conn)
    conn.close()
    return jsonify(data)


@app.route("/api/emotion_trend")
def emotion_trend():
    """過去7日のエネルギー推移を返す"""
    conn = sqlite3.connect("diary.db")
    trend = get_emotion_trend(conn)
    conn.close()
    return jsonify(trend)


@app.route("/api/life_themes")
def life_themes():
    """今月の人生テーマを返す"""
    conn = sqlite3.connect("diary.db")
    themes = get_life_themes(conn)
    conn.close()
    return jsonify(themes)


@app.route("/api/user_dictionary")
def user_dictionary_api():
    """あなた辞典を返す"""
    conn = sqlite3.connect("diary.db")
    dictionary = get_user_dictionary(conn)
    conn.close()
    return jsonify(dictionary or {})


def generate_self_model(conversations: list) -> dict | None:
    """会話履歴からユーザーの人格モデルを生成"""
    if len(conversations) < 5:
        return None
    conv_text = '\n'.join([f"私：{c['user']}" for c in conversations[-50:]])
    prompt = f"""
以下はユーザーの会話記録です。
この人物の人格・思考パターン・価値観・言葉遣いを分析してください。

JSONで以下の4キーを出力：
- "intro": この人物の一人称での自己紹介（80〜120字。「私は〜」で始まる。断定しすぎない）
- "voice": 話し方・表現の特徴（3項目のリスト、各8〜14字）
- "values": 大切にしていること（3項目のリスト、各6〜12字）
- "shadow": 心に抱えていること・葛藤（2項目のリスト、各6〜12字）

観察的に、詩的に。断言しすぎない。JSONのみ出力。

会話記録：
{conv_text}
"""
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite", contents=prompt
        )
        return _parse_json_response(response.text)
    except Exception as e:
        print(f"Self model error: {e}")
        return None


def get_self_model(conn) -> dict | None:
    """自己モデルを取得（7日キャッシュ）"""
    c = conn.cursor()
    c.execute("SELECT updated, data FROM self_model WHERE id=1")
    row = c.fetchone()
    if row and row[0]:
        try:
            updated = datetime.date.fromisoformat(row[0])
            if (datetime.date.today() - updated).days < 7:
                return json_lib.loads(row[1])
        except Exception:
            pass
    c.execute("SELECT user, ai FROM diary ORDER BY date DESC LIMIT 80")
    convs = [{"user": r[0], "ai": r[1]} for r in c.fetchall()]
    model = generate_self_model(convs)
    if model:
        c.execute(
            "INSERT OR REPLACE INTO self_model(id, updated, data) VALUES(1,?,?)",
            (datetime.date.today().isoformat(), json_lib.dumps(model, ensure_ascii=False))
        )
        conn.commit()
    return model


@app.route("/api/streak")
def streak():
    """連続記録日数を返す"""
    conn = sqlite3.connect("diary.db")
    c = conn.cursor()
    c.execute("SELECT DISTINCT substr(date,1,10) as day FROM diary ORDER BY day DESC")
    days = [r[0] for r in c.fetchall()]
    conn.close()
    if not days:
        return jsonify({"streak": 0})
    count = 0
    today = datetime.date.today()
    for i in range(len(days)):
        if days[i] == (today - datetime.timedelta(days=i)).isoformat():
            count += 1
        else:
            break
    return jsonify({"streak": count})


@app.route("/api/heatmap")
def heatmap():
    """曜日×時間帯の感情ヒートマップデータを返す"""
    conn = sqlite3.connect("diary.db")
    c = conn.cursor()

    c.execute("SELECT date FROM diary ORDER BY date ASC")
    entries = [r[0] for r in c.fetchall()]

    c.execute("SELECT date, energy FROM emotion_scores")
    scores = {r[0]: r[1] for r in c.fetchall()}

    c.execute("SELECT date, mood FROM daily_moods")
    moods = {r[0]: r[1] * 20 for r in c.fetchall()}  # 1-5 → 20-100

    conn.close()

    data = {}
    for date_str in entries:
        try:
            dt = datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M")
        except Exception:
            continue

        wd   = dt.weekday()        # 0=月, 6=日
        hour = dt.hour
        slot = (0 if 6  <= hour < 12 else
                1 if 12 <= hour < 18 else
                2 if 18 <= hour < 22 else 3)

        date_key = date_str[:10]
        energy   = scores.get(date_key) or moods.get(date_key)
        if energy is not None:
            key = f"{wd},{slot}"
            data.setdefault(key, []).append(energy)

    averaged = {k: round(sum(v) / len(v)) for k, v in data.items()}
    return jsonify({
        "data":     averaged,
        "weekdays": ["月", "火", "水", "木", "金", "土", "日"],
        "slots":    ["朝", "昼", "夕", "夜"],
    })


@app.route("/api/week_ago")
def week_ago():
    """7日前の今日の最初の発言を返す"""
    target = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    conn = sqlite3.connect("diary.db")
    c = conn.cursor()
    c.execute(
        "SELECT user, date FROM diary WHERE substr(date,1,10)=? ORDER BY date ASC LIMIT 1",
        (target,)
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return jsonify(None)
    return jsonify({"text": row[0], "date": row[1]})


@app.route("/api/daily_prompt")
def daily_prompt():
    return jsonify({"question": get_daily_prompt()})


@app.route("/api/mood", methods=["POST"])
def record_mood():
    data = request.json or {}
    mood = int(data.get("mood", 3))
    if not 1 <= mood <= 5:
        return jsonify({"ok": False})
    conn = sqlite3.connect("diary.db")
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO daily_moods(date, mood, time) VALUES(?,?,?)",
        (datetime.date.today().isoformat(), mood,
         datetime.datetime.now().strftime("%H:%M"))
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/self_model")
def self_model_api():
    conn = sqlite3.connect("diary.db")
    model = get_self_model(conn)
    conn.close()
    return jsonify(model or {})


@app.route("/api/talk_as_me", methods=["POST"])
def talk_as_me():
    """自分モデルとして返答する"""
    req_data = request.json or {}
    user_text = req_data.get("text", "")
    if not user_text.strip():
        return jsonify({"reply": "何か聞いてみて。"})

    conn = sqlite3.connect("diary.db")
    model = get_self_model(conn)
    c = conn.cursor()
    c.execute("SELECT user FROM diary ORDER BY date DESC LIMIT 8")
    recent = [r[0] for r in c.fetchall()]
    conn.close()

    if not model:
        return jsonify({"reply": "まだ自分モデルを作るデータが足りないみたい。もう少し話しかけてみて。"})

    recent_text = '\n'.join([f"私：{r}" for r in recent])
    prompt = f"""
あなたは以下のプロフィールを持つ人物です。
この人物の一人称の視点から、自然に短く返答してください。

【プロフィール】
{model.get('intro', '')}
話し方の特徴：{' / '.join(model.get('voice', []))}
大切にしていること：{' / '.join(model.get('values', []))}

【最近の発言例】
{recent_text}

【ルール】
- この人物らしい語り口で
- 2〜3文以内
- 自分の内側から答える感じで
- AIっぽくならない

相手の言葉：{user_text}
"""
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite", contents=prompt
        )
        reply = response.text.strip()
        save_diary(user_text, reply)
        return jsonify({"reply": reply})
    except Exception as e:
        print(f"Talk as me error: {e}")
        return jsonify({"reply": "うまく言葉が出てこなかった。もう一度聞いて。"})


@app.route("/api/weekly_report")
def weekly_report_api():
    conn = sqlite3.connect("diary.db")
    report = get_weekly_report(conn)
    conn.close()
    return jsonify({"report": report})


# ===== Run =====
if __name__ == "__main__":
    app.run(debug=True)
