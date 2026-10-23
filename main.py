
import pygame
import socket
import json
import threading

# Configuración
WIDTH, HEIGHT = 1280, 720
FPS, PORT = 60, 5555
SERVER_IP = "172.17.38.165"

WHITE = (240, 240, 240)
CYAN = (0, 220, 255)
PINK = (255, 70, 150)
BG = (15, 18, 35)

BAR_W, BAR_H = 18, 130
BALL_RADIUS = 12


# Cliente de red
class NetworkClient:
    def __init__(self, ip):
        self.ip = ip
        self.socket = None
        self.running = False
        self.player = 1
        self.lock = threading.Lock()

        self.state = {
            "p1": HEIGHT // 2,
            "p2": HEIGHT // 2,
            "ball_x": WIDTH // 2,
            "ball_y": HEIGHT // 2,
            "score1": 0,
            "score2": 0,
            "paused": False,
            "game_over": False,
            "winner": "",
            "ready": False
        }

    def connect(self):
        self.socket = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM
        )
        self.socket.connect((self.ip, PORT))
        self.running = True

        threading.Thread(
            target=self.receive,
            daemon=True
        ).start()

    def send(self, data):
        if self.running:
            try:
                self.socket.sendall(
                    (json.dumps(data) + "\n").encode()
                )
            except OSError:
                self.running = False

    def send_input(self, up, down, pause, reset):
        self.send({
            "type": "input",
            "up": up,
            "down": down,
            "pause": pause,
            "reset": reset
        })

    def receive(self):
        buffer = ""

        try:
            while self.running:
                data = self.socket.recv(4096)

                if not data:
                    break

                buffer += data.decode("utf-8")

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)

                    try:
                        message = json.loads(line)

                        if message.get("type") == "welcome":
                            self.player = message.get("player", 1)

                        elif message.get("type") == "state":
                            with self.lock:
                                self.state.update(message)

                        elif message.get("type") == "error":
                            print(
                                "Error del servidor:",
                                message.get("message", "Error desconocido")
                            )

                    except json.JSONDecodeError:
                        continue

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

            try:
                self.socket.close()
            except OSError:
                pass


# Juego
class NeonPong:
    def __init__(self, server_ip=SERVER_IP):
        pygame.init()

        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Neon Pong Multijugador")
        self.clock = pygame.time.Clock()
        self.running = True

        # CORRECCIÓN: utilizar la IP recibida
        self.network = NetworkClient(server_ip)

        self.title_font = pygame.font.SysFont("arial", 40, bold=True)
        self.score_font = pygame.font.SysFont("arial", 60, bold=True)
        self.text_font = pygame.font.SysFont("arial", 22)
        self.small_font = pygame.font.SysFont("arial", 18)

    def events(self):
        pause = reset = False

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False

                elif event.key == pygame.K_SPACE:
                    pause = True

                elif event.key == pygame.K_r:
                    reset = True

        keys = pygame.key.get_pressed()

        if self.network.player == 1:
            up = keys[pygame.K_w]
            down = keys[pygame.K_s]
        else:
            up = keys[pygame.K_UP]
            down = keys[pygame.K_DOWN]

        return bool(up), bool(down), pause, reset

    def text(self, message, font, color, x, y):
        image = font.render(str(message), True, color)
        self.screen.blit(
            image,
            image.get_rect(center=(x, y))
        )

    def draw(self, state):
        screen = self.screen
        screen.fill(BG)

        # Línea central
        pygame.draw.line(
            screen,
            WHITE,
            (WIDTH // 2, 100),
            (WIDTH // 2, HEIGHT - 60),
            2
        )

        # Marcador
        self.text(
            state["score1"],
            self.score_font,
            CYAN,
            WIDTH // 2 - 100,
            100
        )

        self.text(
            state["score2"],
            self.score_font,
            PINK,
            WIDTH // 2 + 100,
            100
        )

        # Paletas
        pygame.draw.rect(
            screen,
            CYAN,
            (42, int(state["p1"]), BAR_W, BAR_H)
        )

        pygame.draw.rect(
            screen,
            PINK,
            (
                WIDTH - 42 - BAR_W,
                int(state["p2"]),
                BAR_W,
                BAR_H
            )
        )

        # Pelota
        if not state["game_over"]:
            pygame.draw.circle(
                screen,
                WHITE,
                (
                    int(state["ball_x"]),
                    int(state["ball_y"])
                ),
                BALL_RADIUS
            )

        # Controles
        controls = (
            "W / S"
            if self.network.player == 1
            else "FLECHAS"
        )

        color = CYAN if self.network.player == 1 else PINK

        self.text(
            f"Mover: {controls}",
            self.small_font,
            color,
            WIDTH // 2,
            HEIGHT - 30
        )

        self.text(
            "ESPACIO: Pausa | R: Reiniciar | ESC: Salir",
            self.small_font,
            WHITE,
            WIDTH // 2,
            HEIGHT - 65
        )

        # Estado del juego
        message = subtitle = ""

        if not self.network.running:
            message = "CONEXION PERDIDA"

        elif not state["ready"]:
            message = "ESPERANDO JUGADOR"
            subtitle = f"Jugador {self.network.player}"

        elif state["game_over"]:
            message = f"GANADOR: {state['winner']}"
            subtitle = (
                f"{state['score1']} - {state['score2']} | R: Reiniciar"
            )

        elif state["paused"]:
            message = "JUEGO PAUSADO"
            subtitle = "ESPACIO para continuar"

        if message:
            self.text(
                message,
                self.title_font,
                WHITE,
                WIDTH // 2,
                HEIGHT // 2 - 20
            )

        if subtitle:
            self.text(
                subtitle,
                self.text_font,
                WHITE,
                WIDTH // 2,
                HEIGHT // 2 + 30
            )

        pygame.display.flip()

    def run(self):
        try:
            self.network.connect()

            while self.running:
                self.clock.tick(FPS)

                up, down, pause, reset = self.events()

                self.network.send_input(
                    up,
                    down,
                    pause,
                    reset
                )

                self.draw(self.network.get_state())

        except OSError as error:
            print("Error de conexión:", error)

        finally:
            self.network.close()
            pygame.quit()


if __name__ == "__main__":
    print(f"Neon Pong | Conectando a {SERVER_IP}:{PORT}")
    NeonPong().run()
