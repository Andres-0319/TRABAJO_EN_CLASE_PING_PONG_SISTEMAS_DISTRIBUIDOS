import traceback
from main import NeonPong

SERVER_IP_DEFAULT = "172.17.38.165"


def main():
    print("===================================")
    print("       NEON PONG CLIENT")
    print("        MULTIJUGADOR LAN")
    print("===================================")
    print(f"IP predeterminada: {SERVER_IP_DEFAULT}")

    ip = input("IP del servidor (ENTER para usar la predeterminada): ").strip()

    try:
        print("\nCargando juego...")
        NeonPong(ip or SERVER_IP_DEFAULT).run()
    except KeyboardInterrupt:
        print("\nCliente cerrado.")
    except Exception as error:
        print(f"\nError al iniciar el juego: {error}")
        traceback.print_exc()
    finally:
        try:
            input("\nPulsa ENTER para cerrar esta ventana...")
        except EOFError:
            pass


if __name__ == "__main__":
    main()
