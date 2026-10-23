import socket, threading, json, time, random, math

HOST, PORT, FPS = "0.0.0.0", 5555, 60
WIDTH, HEIGHT = 1280, 720
BW, BH, BS = 18, 130, 460
BR, INITIAL, MAX_SPEED = 12, 360, 850
ACCEL, WIN, PLAYERS = 1.10, 5, 2
KEYS = ("up", "down", "pause", "reset")

class Paddle:
    def __init__(self, x):
        self.x, self.width, self.height = x, BW, BH
        self.reset()

    def reset(self):
        self.y = HEIGHT / 2 - BH / 2

    def move(self, up, down, dt):
        self.y = max(0, min(HEIGHT - BH,
            self.y + (bool(down) - bool(up)) * BS * dt))


class Ball:
    def __init__(self):
        self.radius = BR
        self.reset()

    def reset(self, direction=None):
        angle = random.uniform(-.55, .55)
        speed = INITIAL / math.sqrt(1 + angle ** 2)
        self.x, self.y = WIDTH / 2, HEIGHT / 2
        self.vx = (direction or random.choice((-1, 1))) * speed
        self.vy = angle * speed

    def move(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        if self.y - BR <= 0:
            self.y, self.vy = BR, abs(self.vy)
        elif self.y + BR >= HEIGHT:
            self.y, self.vy = HEIGHT - BR, -abs(self.vy)

    def bounce(self, offset, direction):
        self.vy += offset * 160
        length = math.hypot(self.vx, self.vy)
        speed = min(length * ACCEL, MAX_SPEED)
        if length:
            self.vx = direction * speed * abs(self.vx) / length
            self.vy *= speed / length

class Game:
    def __init__(self):
        self.p1, self.p2, self.ball = Paddle(42), Paddle(WIDTH - 60), Ball()
        self.score1 = self.score2 = 0
        self.paused = self.game_over = self.ready = False
        self.winner = ""

    def reset(self):
        self.score1 = self.score2 = 0
        self.paused = self.game_over = False
        self.winner = ""
        self.p1.reset()
        self.p2.reset()
        self.ball.reset()

    def update(self, inputs, players, dt):
        self.ready = players == PLAYERS
        if not self.ready:
            return
        a, b = inputs[1], inputs[2]
        if a["reset"]:
            self.reset()
            return
        if a["pause"]:
            self.paused = not self.paused
        if self.paused or self.game_over:
            return
        self.p1.move(a["up"], a["down"], dt)
        self.p2.move(b["up"], b["down"], dt)
        self.ball.move(dt)
        self.collisions()
        ball = self.ball
        if ball.x + BR < 0:
            self.score2 += 1
            ball.reset(1)
        elif ball.x - BR > WIDTH:
            self.score1 += 1
            ball.reset(-1)
        if self.score1 >= WIN or self.score2 >= WIN:
            self.game_over = True
            self.winner = "PLAYER 1" if self.score1 >= WIN else "PLAYER 2"

    def collisions(self):
        b = self.ball
        for p, d in ((self.p1, 1), (self.p2, -1)):
            if (b.vx * d < 0 and b.x - BR <= p.x + BW
                    and b.x + BR >= p.x and b.y + BR >= p.y
                    and b.y - BR <= p.y + BH):
                b.x = p.x + BW + BR if d == 1 else p.x - BR
                b.vx = abs(b.vx) * d
                b.bounce((b.y - p.y - BH / 2) / (BH / 2), d)

    def get_state(self):
        b = self.ball
        return dict(type="state", p1=self.p1.y, p2=self.p2.y,
            ball_x=b.x, ball_y=b.y, score1=self.score1,
            score2=self.score2, paused=self.paused,
            game_over=self.game_over, winner=self.winner,
            ready=self.ready, vx=b.vx, vy=b.vy)


class GameServer:
    def __init__(self):
        self.game, self.clients = Game(), {}
        self.inputs = {p: dict.fromkeys(KEYS, False) for p in (1, 2)}
        self.lock, self.running = threading.Lock(), threading.Event()
        self.running.set()

    @staticmethod
    def send(conn, msg):
        conn.sendall((json.dumps(msg, separators=(",", ":")) + "\n").encode())

    def disconnect(self, p, conn):
        with self.lock:
            if self.clients.get(p) is not conn:
                return
            del self.clients[p]
            self.inputs[p] = dict.fromkeys(KEYS, False)
            self.game.ready = False
        conn.close()
        print(f"Jugador {p} desconectado")

    def handle(self, conn, p):
        buf = ""
        try:
            while self.running.is_set():
                data = conn.recv(4096)
                if not data:
                    break
                buf += data.decode()
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    try:
                        msg = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(msg, dict) and msg.get("type") == "input":
                        with self.lock:
                            if self.clients.get(p) is not conn:
                                return
                            self.inputs[p] = {k: bool(msg.get(k, False)) for k in KEYS}
        except (OSError, UnicodeDecodeError):
            pass
        finally:
            self.disconnect(p, conn)

    def accept(self):
        while self.running.is_set():
            try:
                conn, addr = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with self.lock:
                p = next((n for n in (1, 2) if n not in self.clients), None)
                if p:
                    self.clients[p] = conn
                    self.inputs[p] = dict.fromkeys(KEYS, False)
                    self.game.ready = len(self.clients) == PLAYERS
            if p is None:
                try:
                    self.send(conn, dict(type="error", message="La partida está llena."))
                except OSError:
                    pass
                conn.close()
                continue
            try:
                self.send(conn, dict(type="welcome", player=p))
            except OSError:
                self.disconnect(p, conn)
                continue
            print(f"Jugador {p} conectado desde {addr}")
            threading.Thread(target=self.handle, args=(conn, p), daemon=True).start()

    def start(self):
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((HOST, PORT))
        self.sock.listen(PLAYERS)
        self.sock.settimeout(1)
        print(f"Servidor Pong activo en {PORT}. Esperando jugadores...")
        threading.Thread(target=self.accept, daemon=True).start()
        previous = time.monotonic()
        try:
            while self.running.is_set():
                now = time.monotonic()
                dt, previous = min(now - previous, .03), now
                with self.lock:
                    self.game.update(self.inputs, len(self.clients), dt)
                    state, clients = self.game.get_state(), list(self.clients.items())
                for p, conn in clients:
                    try:
                        self.send(conn, state)
                    except OSError:
                        self.disconnect(p, conn)
                time.sleep(1 / FPS)
        except KeyboardInterrupt:
            print("\nCerrando servidor...")
        finally:
            self.running.clear()
            self.sock.close()
            for conn in list(self.clients.values()):
                try:
                    conn.shutdown(socket.SHUT_RDWR)
                    conn.close()
                except OSError:
                    pass
            print("Servidor cerrado correctamente.")


if __name__ == "__main__":
    GameServer().start()
