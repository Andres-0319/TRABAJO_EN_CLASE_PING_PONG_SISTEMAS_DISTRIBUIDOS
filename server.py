import socket
import threading
import json
import time
import random
import math

# Configuración
HOST, PORT = "0.0.0.0", 5555
WIDTH, HEIGHT = 1280, 720
BAR_W, BAR_H, BAR_SPEED = 18, 130, 460
BALL_RADIUS = 12
INITIAL_SPEED, MAX_SPEED = 360, 850
ACCELERATION = 1.10
WIN_SCORE, FPS, MAX_PLAYERS = 5, 60, 2


# Paleta
class Paddle:
    def __init__(self, x):
        self.x = x
        self.width, self.height = BAR_W, BAR_H
        self.reset()

    def reset(self):
        self.y = HEIGHT // 2 - self.height // 2

    def move(self, up, down, dt):
        self.y += (bool(down) - bool(up)) * BAR_SPEED * dt
        self.y = max(0, min(HEIGHT - self.height, self.y))


# Pelota
class Ball:
    def __init__(self):
        self.reset()

    def reset(self, direction=None):
        direction = direction or random.choice([-1, 1])
        angle = random.uniform(-0.55, 0.55)
        speed = INITIAL_SPEED / math.sqrt(1 + angle ** 2)

        self.radius = BALL_RADIUS
        self.x, self.y = WIDTH / 2, HEIGHT / 2
        self.vx, self.vy = direction * speed, angle * speed

    def move(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt

        if self.y - self.radius <= 0:
            self.y = self.radius
            self.vy = abs(self.vy)
        elif self.y + self.radius >= HEIGHT:
            self.y = HEIGHT - self.radius
            self.vy = -abs(self.vy)

    def bounce(self, offset, direction):
        self.vy += offset * 160
        speed = min(math.hypot(self.vx, self.vy) * ACCELERATION, MAX_SPEED)
        length = math.hypot(self.vx, self.vy)

        if length:
            self.vx = direction * speed * abs(self.vx) / length
            self.vy *= speed / length


# Juego
class Game:
    def __init__(self):
        self.paddle1 = Paddle(42)
        self.paddle2 = Paddle(WIDTH - 42 - BAR_W)
        self.ball = Ball()
        self.score1 = self.score2 = 0
        self.paused = self.game_over = self.ready = False
        self.winner = ""

    def reset(self):
        self.score1 = self.score2 = 0
        self.paused = self.game_over = False
        self.winner = ""
        self.paddle1.reset()
        self.paddle2.reset()
        self.ball.reset()

    def update(self, inputs, players, dt):
        self.ready = players == MAX_PLAYERS
        if not self.ready:
            return

        p1, p2 = inputs[1], inputs[2]

        if p1["reset"]:
            self.reset()
            return

        if p1["pause"]:
            self.paused = not self.paused

        if self.paused or self.game_over:
            return

        self.paddle1.move(p1["up"], p1["down"], dt)
        self.paddle2.move(p2["up"], p2["down"], dt)
        self.ball.move(dt)
        self.collisions()
        self.check_score()

        if self.score1 >= WIN_SCORE:
            self.game_over, self.winner = True, "PLAYER 1"
        elif self.score2 >= WIN_SCORE:
            self.game_over, self.winner = True, "PLAYER 2"

    def collisions(self):
        ball = self.ball

        for paddle, direction in (
            (self.paddle1, 1),
            (self.paddle2, -1)
        ):
            if (ball.vx * direction < 0 and
                ball.x - ball.radius <= paddle.x + paddle.width and
                ball.x + ball.radius >= paddle.x and
                ball.y + ball.radius >= paddle.y and
                ball.y - ball.radius <= paddle.y + paddle.height):

                ball.x = (
                    paddle.x + paddle.width + ball.radius
                    if direction == 1
                    else paddle.x - ball.radius
                )
                ball.vx = abs(ball.vx) * direction

                offset = (
                    ball.y - (paddle.y + paddle.height / 2)
                ) / (paddle.height / 2)

                ball.bounce(offset, direction)

    def check_score(self):
        ball = self.ball

        if ball.x + ball.radius < 0:
            self.score2 += 1
            ball.reset(1)
        elif ball.x - ball.radius > WIDTH:
            self.score1 += 1
            ball.reset(-1)

    def get_state(self):
        return {
            "type": "state",
            "p1": self.paddle1.y,
            "p2": self.paddle2.y,
            "ball_x": self.ball.x,
            "ball_y": self.ball.y,
            "score1": self.score1,
            "score2": self.score2,
            "paused": self.paused,
            "game_over": self.game_over,
            "winner": self.winner,
            "ready": self.ready,
            "vx": self.ball.vx,
            "vy": self.ball.vy
        }


# Servidor
class GameServer:
    def __init__(self, host=HOST, port=PORT):
        self.host, self.port = host, port
        self.game = Game()
        self.clients = {}
        self.inputs = {1: self.empty_input(), 2: self.empty_input()}
        self.lock = threading.Lock()
        self.running = threading.Event()
        self.running.set()
        self.server_socket = None

    @staticmethod
    def empty_input():
        return {"up": False, "down": False, "pause": False, "reset": False}

    @staticmethod
    def send(conn, message):
        data = json.dumps(message, separators=(",", ":")) + "\n"
        conn.sendall(data.encode("utf-8"))

    def accept_clients(self):
        while self.running.is_set():
            try:
                conn, address = self.server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            with self.lock:
                player = next((p for p in (1, 2) if p not in self.clients), None)

            if player is None:
                try:
                    self.send(conn, {"type": "error", "message": "La partida está llena."})
                except OSError:
                    pass
                conn.close()
                continue

            try:
                self.send(conn, {"type": "welcome", "player": player})
            except OSError:
                conn.close()
                continue

            with self.lock:
                self.clients[player] = conn
                self.inputs[player] = self.empty_input()
                self.game.ready = len(self.clients) == MAX_PLAYERS

            print(f"Jugador {player} conectado desde {address}")

            threading.Thread(
                target=self.handle_client,
                args=(conn, player),
                daemon=True
            ).start()

    def handle_client(self, conn, player):
        buffer = ""

        try:
            while self.running.is_set():
                data = conn.recv(4096)
                if not data:
                    break

                buffer += data.decode("utf-8")

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)

                    try:
                        message = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if not isinstance(message, dict) or message.get("type") != "input":
                        continue

                    with self.lock:
                        if self.clients.get(player) is not conn:
                            return

                        self.inputs[player] = {
                            key: bool(message.get(key, False))
                            for key in ("up", "down", "pause", "reset")
                        }

        except (OSError, UnicodeDecodeError):
            pass
        finally:
            self.disconnect(player, conn)

    def disconnect(self, player, conn):
        with self.lock:
            if self.clients.get(player) is not conn:
                return

            del self.clients[player]
            self.inputs[player] = self.empty_input()
            self.game.ready = len(self.clients) == MAX_PLAYERS

        try:
            conn.close()
        except OSError:
            pass

        print(f"Jugador {player} desconectado")

    def broadcast(self):
        with self.lock:
            state = self.game.get_state()
            clients = list(self.clients.items())

        for player, conn in clients:
            try:
                self.send(conn, state)
            except OSError:
                self.disconnect(player, conn)

    def game_loop(self):
        previous = time.monotonic()

        while self.running.is_set():
            now = time.monotonic()
            dt = min(now - previous, 0.03)
            previous = now

            with self.lock:
                self.game.update(self.inputs, len(self.clients), dt)

            self.broadcast()
            time.sleep(1 / FPS)

    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(MAX_PLAYERS)
        self.server_socket.settimeout(1)

        print(f"Servidor Pong activo en el puerto {self.port}")
        print("Esperando jugadores...")

        threading.Thread(target=self.accept_clients, daemon=True).start()

        try:
            self.game_loop()
        except KeyboardInterrupt:
            print("\nCerrando servidor...")
        finally:
            self.stop()

    def stop(self):
        self.running.clear()

        if self.server_socket:
            try:
                self.server_socket.close()
            except OSError:
                pass

        with self.lock:
            clients = list(self.clients.values())
            self.clients.clear()

        for conn in clients:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                conn.close()
            except OSError:
                pass

        print("Servidor cerrado correctamente.")


if __name__ == "__main__":
    GameServer().start()
