import pygame, socket, json, threading

WIDTH, HEIGHT, FPS, PORT = 1280, 720, 60, 5555
SERVER_IP = "172.17.38.165"
WHITE, CYAN, PINK, BG = (240,240,240), (0,220,255), (255,70,150), (15,18,35)
BAR_W, BAR_H, BALL_RADIUS = 18, 130, 12


class NetworkClient:
    def __init__(self, ip):
        self.ip, self.socket, self.running, self.player = ip, None, False, 1
        self.lock = threading.Lock()
        self.state = dict(p1=HEIGHT//2, p2=HEIGHT//2, ball_x=WIDTH//2,
            ball_y=HEIGHT//2, score1=0, score2=0, paused=False,
            game_over=False, winner="", ready=False)

    def connect(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((self.ip, PORT))
        self.running = True
        threading.Thread(target=self.receive, daemon=True).start()

    def send(self, data):
        if self.running:
            try:
                self.socket.sendall((json.dumps(data) + "\n").encode())
            except OSError:
                self.running = False

    def send_input(self, up, down, pause, reset):
        self.send(dict(type="input", up=up, down=down, pause=pause, reset=reset))

    def receive(self):
        buffer = ""
        try:
            while self.running:
                data = self.socket.recv(4096)
                if not data:
                    break
                buffer += data.decode()
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    try:
                        msg = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if msg.get("type") == "welcome":
                        self.player = msg.get("player", 1)
                    elif msg.get("type") == "state":
                        with self.lock:
                            self.state.update(msg)
                    elif msg.get("type") == "error":
                        print("Error:", msg.get("message", "Desconocido"))
        except (OSError, UnicodeDecodeError):
            pass
        self.running = False

    def get_state(self):
        with self.lock:
            return self.state.copy()

    def close(self):
        self.running = False
        if self.socket:
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.socket.close()


class NeonPong:
    def __init__(self, server_ip=SERVER_IP):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Neon Pong Multijugador")
        self.clock, self.running = pygame.time.Clock(), True
        self.network = NetworkClient(server_ip)
        self.title = pygame.font.SysFont("arial", 40, bold=True)
        self.score = pygame.font.SysFont("arial", 60, bold=True)
        self.text_font = pygame.font.SysFont("arial", 22)
        self.small = pygame.font.SysFont("arial", 18)

    def events(self):
        pause = reset = False
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                self.running = False
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    self.running = False
                elif e.key == pygame.K_SPACE:
                    pause = True
                elif e.key == pygame.K_r:
                    reset = True
        keys = pygame.key.get_pressed()
        up, down = ((keys[pygame.K_w], keys[pygame.K_s])
                    if self.network.player == 1 else
                    (keys[pygame.K_UP], keys[pygame.K_DOWN]))
        return bool(up), bool(down), pause, reset

    def text(self, msg, font, color, x, y):
        img = font.render(str(msg), True, color)
        self.screen.blit(img, img.get_rect(center=(x, y)))

    def draw(self, s):
        screen = self.screen
        screen.fill(BG)
        pygame.draw.line(screen, WHITE, (WIDTH//2, 100), (WIDTH//2, HEIGHT-60), 2)
        self.text(s["score1"], self.score, CYAN, WIDTH//2-100, 100)
        self.text(s["score2"], self.score, PINK, WIDTH//2+100, 100)
        pygame.draw.rect(screen, CYAN, (42, int(s["p1"]), BAR_W, BAR_H))
        pygame.draw.rect(screen, PINK, (WIDTH-60, int(s["p2"]), BAR_W, BAR_H))
        if not s["game_over"]:
            pygame.draw.circle(screen, WHITE,
                (int(s["ball_x"]), int(s["ball_y"])), BALL_RADIUS)
        p = self.network.player
        self.text("Mover: " + ("W / S" if p == 1 else "FLECHAS"),
                  self.small, CYAN if p == 1 else PINK, WIDTH//2, HEIGHT-30)
        self.text("ESPACIO: Pausa | R: Reiniciar | ESC: Salir",
                  self.small, WHITE, WIDTH//2, HEIGHT-65)
        msg = sub = ""
        if not self.network.running:
            msg = "CONEXION PERDIDA"
        elif not s["ready"]:
            msg, sub = "ESPERANDO JUGADOR", f"Jugador {p}"
        elif s["game_over"]:
            msg, sub = f"GANADOR: {s['winner']}", f"{s['score1']} - {s['score2']} | R: Reiniciar"
        elif s["paused"]:
            msg, sub = "JUEGO PAUSADO", "ESPACIO para continuar"
        if msg:
            self.text(msg, self.title, WHITE, WIDTH//2, HEIGHT//2-20)
        if sub:
            self.text(sub, self.text_font, WHITE, WIDTH//2, HEIGHT//2+30)
        pygame.display.flip()

    def run(self):
        try:
            self.network.connect()
            while self.running:
                self.clock.tick(FPS)
                self.network.send_input(*self.events())
                self.draw(self.network.get_state())
        except OSError as e:
            print("Error de conexión:", e)
        finally:
            self.network.close()
            pygame.quit()


if __name__ == "__main__":
    print(f"Neon Pong | Conectando a {SERVER_IP}:{PORT}")
    NeonPong().run()
