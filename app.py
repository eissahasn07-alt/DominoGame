
# -*- coding: utf-8 -*-
# app.py - الدومينو الفارسي الموسع (جاهز للنشر)

from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit, join_room
import random
import uuid
import os

# ============================================================
# 1. إعدادات التطبيق الأساسية
# ============================================================
app = Flask(__name__)
app.config['SECRET_KEY'] = 'domino-secret-2024'
socketio = SocketIO(app, cors_allowed_origins="*")

# ============================================================
# 2. قاموس الأرقام الفارسية (قلب المشروع)
# ============================================================
FARSI_DICT = {
    0: "صِفر", 1: "يَك", 2: "دو", 3: "سِه", 4: "جَهَار", 5: "بَنْج",
    6: "شِيش", 7: "هَفْت", 8: "هَشْت", 9: "نُه", 10: "دَه",
    11: "يازْدَه", 12: "دَوازْدَه", 13: "سيزْدَه", 14: "جَهَارْدَه", 15: "پانزْدَه",
    16: "شانزْدَه", 17: "هَفْدَه", 18: "هَشْدَه", 19: "نوزْدَه", 20: "بيست",
    30: "سي", 40: "جِهِل", 50: "پَنْجاه", 60: "شَصْت", 70: "هَفْتاد",
    80: "هَشْتاد", 90: "نَوَد", 100: "صَد", 200: "دِويست", 300: "سيصَد",
    400: "جَهَارصَد", 500: "پانصَد", 600: "شِيشصَد", 700: "هَفْتصَد",
    800: "هَشْتصَد", 900: "نُهصَد", 1000: "هِزار"
}

def number_to_farsi(n):
    """تحويل أي رقم إلى اسمه الفارسي"""
    if n in FARSI_DICT:
        return FARSI_DICT[n]
    if 20 < n < 100:
        tens = (n // 10) * 10
        ones = n % 10
        return f"{FARSI_DICT[tens]} و {FARSI_DICT[ones]}" if ones else FARSI_DICT[tens]
    return str(n)

# ============================================================
# 3. تعريف قطع الدومينو الموسعة (55 قطعة)
# ============================================================
def generate_pieces():
    """توليد جميع القطع من 0-0 إلى 9-9"""
    pieces = []
    for i in range(10):
        for j in range(i, 10):
            pieces.append((i, j))
    return pieces

def get_piece_name(piece):
    """الحصول على الاسم الفارسي للقطعة"""
    a, b = piece
    if a == b:
        names = {0:"خالي", 1:"يَك دوبارة", 2:"دوبارة", 3:"دوسِه", 4:"دورجي", 
                 5:"دوبَنْج", 6:"هيبيك", 7:"دوهَفْت", 8:"دوهَشْت", 9:"دونُه"}
        return names.get(a, f"{number_to_farsi(a)} دوبل")
    return f"{number_to_farsi(a)} و {number_to_farsi(b)}"

# ============================================================
# 4. فئة إدارة اللعبة (Game Engine)
# ============================================================
class DominoGame:
    def __init__(self, room_id, players):
        self.room = room_id
        self.players = players
        self.scores = {p: 0 for p in players}
        self.hands = {p: [] for p in players}
        self.board = []
        self.boneyard = []
        self.current_player = None
        self.started = False
        self.ended = False
        self.passed = set()

    def start(self):
        """توزيع القطع وبدء اللعب"""
        pieces = generate_pieces()
        random.shuffle(pieces)
        per_player = 7 if len(self.players) <= 3 else 5
        
        for i, p in enumerate(self.players):
            self.hands[p] = pieces[i*per_player:(i+1)*per_player]
        
        self.boneyard = pieces[len(self.players)*per_player:]
        
        # من يبدأ؟ من معه أعلى دش
        high = -1
        starter = self.players[0]
        for p in self.players:
            for piece in self.hands[p]:
                if piece[0] == piece[1] and piece[0] > high:
                    high = piece[0]
                    starter = p
        self.current_player = starter
        self.started = True
        return self.get_state()

    def can_play(self, piece):
        """هل يمكن لعب هذه القطعة؟"""
        if not self.board: return True
        left, right = self.board[0][0], self.board[-1][1]
        return piece[0] in (left, right) or piece[1] in (left, right)

    def play(self, player, piece_str):
        """تنفيذ نقلة"""
        piece = tuple(map(int, piece_str.split('-')))
        if piece not in self.hands[player] or not self.can_play(piece):
            return False
        
        self.hands[player].remove(piece)
        if not self.board:
            self.board.append(piece)
        else:
            # محاولة اللعب على اليمين أولاً
            if piece[0] == self.board[-1][1]:
                self.board.append(piece)
            elif piece[1] == self.board[-1][1]:
                self.board.append((piece[1], piece[0]))
            elif piece[1] == self.board[0][0]:
                self.board.insert(0, piece)
            elif piece[0] == self.board[0][0]:
                self.board.insert(0, (piece[1], piece[0]))
        
        self.passed.clear()
        
        # فوز اللاعب
        if not self.hands[player]:
            self.end_round(player)
            return "win"
        
        self.next_turn()
        return True

    def draw(self, player):
        """سحب من البنك"""
        if self.boneyard:
            piece = self.boneyard.pop()
            self.hands[player].append(piece)
            return piece
        self.passed.add(player)
        self.next_turn()
        return None

    def pass_turn(self, player):
        """تمرير الدور"""
        self.passed.add(player)
        self.next_turn()
        # انسداد
        if len(self.passed) >= len(self.players):
            self.end_round(None)

    def next_turn(self):
        """الدور التالي"""
        idx = self.players.index(self.current_player)
        for _ in range(len(self.players)):
            idx = (idx + 1) % len(self.players)
            if self.players[idx] not in self.passed:
                self.current_player = self.players[idx]
                return

    def end_round(self, winner):
        """نهاية الجولة وتوزيع النقاط"""
        points = {p: sum(sum(t) for t in self.hands[p]) for p in self.players}
        if winner:
            self.scores[winner] += sum(points.values())
        else:
            # انسداد: الأقل نقاطاً يفوز
            min_pts = min(points.values())
            for p, pts in points.items():
                if pts == min_pts:
                    self.scores[p] += sum(points.values()) - min_pts
        self.ended = True

    def get_state(self):
        """حالة اللعبة الحالية للواجهة"""
        return {
            "players": self.players,
            "scores": self.scores,
            "current": self.current_player,
            "board": [f"{p[0]}-{p[1]}" for p in self.board],
            "boneyard": len(self.boneyard),
            "hands": {p: [f"{c[0]}-{c[1]}" for c in self.hands[p]] for p in self.players},
            "detailed": {p: [{"str": f"{c[0]}-{c[1]}", "name": get_piece_name(c), "val": c[0]+c[1]} for c in self.hands[p]] for p in self.players},
            "started": self.started,
            "ended": self.ended
        }

# ============================================================
# 5. تخزين الغرف (في الذاكرة)
# ============================================================
rooms = {}

# ============================================================
# 6. مسارات التطبيق (Routes)
# ============================================================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/create', methods=['POST'])
def create():
    room_id = str(uuid.uuid4())[:6]
    rooms[room_id] = {'players': [], 'game': None}
    return jsonify({'room': room_id})

# ============================================================
# 7. أحداث Socket.IO (اللعب الحي)
# ============================================================
@socketio.on('join')
def on_join(data):
    room = data['room']
    name = data['name']
    join_room(room)
    
    if room in rooms:
        if name not in rooms[room]['players']:
            rooms[room]['players'].append(name)
        emit('joined', {'players': rooms[room]['players']}, room=room)

@socketio.on('start')
def on_start(data):
    room = data['room']
    if room in rooms and len(rooms[room]['players']) >= 2:
        game = DominoGame(room, rooms[room]['players'])
        rooms[room]['game'] = game
        emit('state', game.start(), room=room)

@socketio.on('play')
def on_play(data):
    room = data['room']
    game = rooms[room]['game']
    if game and game.current_player == data['player']:
        result = game.play(data['player'], data['piece'])
        if result:
            emit('state', game.get_state(), room=room)
            if result == "win":
                emit('round_end', {'winner': data['player'], 'scores': game.scores}, room=room)

@socketio.on('draw')
def on_draw(data):
    room = data['room']
    game = rooms[room]['game']
    if game and game.current_player == data['player']:
        piece = game.draw(data['player'])
        emit('state', game.get_state(), room=room)
        if piece:
            emit('drawn', {'player': data['player'], 'piece': f"{piece[0]}-{piece[1]}", 'name': get_piece_name(piece)}, room=room)

@socketio.on('pass')
def on_pass(data):
    room = data['room']
    game = rooms[room]['game']
    if game and game.current_player == data['player']:
        game.pass_turn(data['player'])
        emit('state', game.get_state(), room=room)

# ============================================================
# 8. نقطة التشغيل
# ============================================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
