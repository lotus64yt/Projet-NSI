import asyncio
import websockets
import pygame
import threading
import socket
import json
import math
from pygame import gfxdraw as gfx

PORT = 8765
WIDTH, HEIGHT = 800, 600

positions = {}
pseudos = {}
player_id = None
player_name = ""

running = True
is_host = False

# ========== SERVER ==========
clients = {}
server_started = False

async def server_handler(ws):
    client_id = None
    try:
        async for msg in ws:
            data = json.loads(msg)
            if data["type"] == "move":
                if client_id is None:
                    client_id = data["id"]
                    clients[client_id] = ws
                    positions[client_id] = [data["x"], data["y"]]
                    pseudos[client_id] = data.get("name", "Inconnu")
                else:
                    positions[client_id] = [data["x"], data["y"]]

    finally:
        if client_id:
            del clients[client_id]
            del positions[client_id]
            del pseudos[client_id]


async def server_broadcast():
    while True:
        if clients:
            update = json.dumps({"type": "update", "players": positions, "names": pseudos})

            await asyncio.gather(*(ws.send(update) for ws in clients.values()))
        await asyncio.sleep(0.03)

def start_server():
    async def run_server():
        async with websockets.serve(server_handler, "0.0.0.0", PORT):
            print(f"Serveur WebSocket démarré sur le port {PORT}")
            await server_broadcast()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_server())
    except Exception as e:
        print(f"Erreur serveur : {e}")

# ========== CLIENT ==========
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        IP = s.getsockname()[0]
    except:
        IP = "127.0.0.1"
    finally:
        s.close()
    return IP

def scan_rooms():
    """ Scanne le sous-réseau pour trouver des hôtes sur le port spécifié.
        Renvoie une liste d'adresses IP valides.
        Si aucune room n'est trouvée sur le réseau, retourne 'localhost' (et '127.0.0.1'). """
    found_rooms = []
    try:
        ws = websockets.sync.client.connect(f"ws://localhost:{PORT}")
        ws.close()
        found_rooms.append("localhost")
    except Exception:
        pass

    local_ip = get_local_ip()
    ip_parts = local_ip.split(".")
    base_ip = ".".join(ip_parts[:3]) + "."
    for i in range(1, 255):
        test_ip = base_ip + str(i)
        if test_ip in found_rooms:
            continue
        try:
            ws = websockets.sync.client.connect(f"ws://{test_ip}:{PORT}")
            ws.close()
            found_rooms.append(test_ip)
        except Exception:
            continue

    if not found_rooms:
        found_rooms.append("localhost")
        if "127.0.0.1" not in found_rooms:
            found_rooms.append("127.0.0.1")
    return found_rooms

async def client_loop(uri):
    global positions
    try:
        async with websockets.connect(uri) as ws:
            async def recv():
                while running:
                    try:
                        data = await ws.recv()
                        msg = json.loads(data)
                        print(f"Message reçu : {msg}")
                        if msg["type"] == "update":
                            positions.clear()
                            positions.update(msg["players"])
                            pseudos.clear()
                            pseudos.update(msg.get("names", {}))

                    except websockets.ConnectionClosed:
                        break

            recv_task = asyncio.create_task(recv())

            while running:
                if player_id in positions:
                    x, y = positions[player_id]
                    await ws.send(json.dumps({"type": "move", "id": player_id, "x": x, "y": y, "name": player_name}))

                await asyncio.sleep(0.03)

            await recv_task
    except websockets.ConnectionClosedError as e:
        print(f"Connection closed: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

def launch_client(ip):
    asyncio.run(client_loop(f"ws://{ip}:{PORT}"))

# ========== PYGAME ==========
def main():
    global player_id, running, is_host, positions, player_name

    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.Clock()
    font = pygame.font.SysFont(None, 50)
    small_font = pygame.font.SysFont(None, 30)

    scanning = False
    found_rooms = []
    scan_done = False

    def draw_button(text, x, y, w=300, h=80):
        rect = pygame.Rect(x, y, w, h)
        gfx.box(screen, rect,(50, 50, 200))
        txt = font.render(text, True, (255, 255, 255))
        screen.blit(txt, (x + 20, y + 20))
        return rect

    def spinner(surface, center, angle):
        radius = 30
        end_x = center[0] + radius * math.cos(angle)
        end_y = center[1] + radius * math.sin(angle)
        gfx.aacircle(surface, center[0], center[1], radius, (200, 200, 200))
        gfx.line(surface, center[0], center[1], int(end_x), int(end_y), (255, 255, 255))

    def start_scan():
        nonlocal scanning, found_rooms, scan_done
        scanning = True
        scan_done = False

        def scan_thread():
            nonlocal found_rooms, scanning, scan_done
            found_rooms = scan_rooms()
            scanning = False
            scan_done = True

        threading.Thread(target=scan_thread, daemon=True).start()

    menu = True
    
    input_active = True
    input_box = pygame.Rect(200, 250, 400, 60)
    color_inactive = pygame.Color('lightskyblue3')
    color_active = pygame.Color('dodgerblue2')
    input_color = color_inactive
    input_text = ""
    input_done = False

    while not input_done:
        screen.fill((30, 30, 30))
        title = font.render("Entrez votre pseudo :", True, (255, 255, 255))
        screen.blit(title, (WIDTH//2 - title.get_width()//2, 180))
        txt_surface = font.render(input_text, True, (255, 255, 255))
        width = max(400, txt_surface.get_width()+10)
        input_box.w = width
        screen.blit(txt_surface, (input_box.x+5, input_box.y+10))
        pygame.draw.rect(screen, input_color, input_box, 2)
        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.MOUSEBUTTONDOWN:
                if input_box.collidepoint(event.pos):
                    input_active = not input_active
                else:
                    input_active = False
                input_color = color_active if input_active else color_inactive
            if event.type == pygame.KEYDOWN:
                if input_active:
                    if event.key == pygame.K_RETURN:
                        if input_text.strip():
                            player_name = input_text.strip()
                            input_done = True
                    elif event.key == pygame.K_BACKSPACE:
                        input_text = input_text[:-1]
                    else:
                        if len(input_text) < 20:
                            input_text += event.unicode

    
    while menu:
        screen.fill((30, 30, 30))
        host_btn = draw_button("Héberger une partie", 250, 180)
        join_btn = draw_button("Chercher une partie", 250, 300)
        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.MOUSEBUTTONDOWN:
                if host_btn.collidepoint(event.pos):
                    is_host = True
                    menu = False
                if join_btn.collidepoint(event.pos):
                    menu = False
        clock.tick(60)

    player_id = str(id(screen))
    positions[player_id] = [100, 100]

    if is_host:
        threading.Thread(target=start_server, daemon=True).start()
        ip = "localhost"
    else:
        start_scan()
        selected_room = None
        spinner_angle = 0
        room_menu = True
        while room_menu:
            screen.fill((40, 40, 40))
            if scanning:
                spinner_angle += 0.1
                spinner(screen, (WIDTH // 2, HEIGHT // 2 - 50), spinner_angle)
                loading_text = font.render("Recherche en cours...", True, (255, 255, 255))
                screen.blit(loading_text, (WIDTH // 2 - loading_text.get_width() // 2, HEIGHT // 2 + 10))
            elif scan_done:
                if found_rooms:
                    title = font.render("Rooms disponibles", True, (255, 255, 255))
                    screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 50))
                    room_rects = []
                    for idx, ip_addr in enumerate(found_rooms):
                        rect = draw_button(ip_addr, 250, 150 + idx * 100, w=300, h=60)
                        room_rects.append((rect, ip_addr))
                    info = small_font.render("Cliquez sur une room pour rejoindre", True, (200,200,200))
                    screen.blit(info, (WIDTH // 2 - info.get_width() // 2, HEIGHT - 50))
                else:
                    no_room_text = font.render("Aucune room trouvée", True, (255, 0, 0))
                    screen.blit(no_room_text, (WIDTH // 2 - no_room_text.get_width() // 2, HEIGHT // 2 - 20))
            pygame.display.flip()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
                if event.type == pygame.MOUSEBUTTONDOWN and scan_done and found_rooms:
                    for rect, ip_addr in room_rects:
                        if rect.collidepoint(event.pos):
                            selected_room = ip_addr
                            room_menu = False
            clock.tick(60)
        if not selected_room:
            print("Aucun hôte sélectionné.")
            return
        ip = selected_room

    threading.Thread(target=launch_client, args=(ip,), daemon=True).start()

    while running:
        screen.fill((20, 20, 20))
        keys = pygame.key.get_pressed()
        x, y = positions.get(player_id, [100, 100])
        if keys[pygame.K_LEFT]:
            x -= 5
        if keys[pygame.K_RIGHT]:
            x += 5
        if keys[pygame.K_UP]:
            y -= 5
        if keys[pygame.K_DOWN]:
            y += 5
        positions[player_id] = [x, y]

        for pid, (px, py) in positions.items():
            color = (0, 255, 0, 255) if pid == player_id else (255, 0, 0, 255)
            gfx.box(screen, pygame.Rect(px, py, 30, 30), color)
            name = pseudos.get(pid, "???")
            name_surf = small_font.render(name, True, (255, 255, 255))
            screen.blit(name_surf, (px, py - 25))

        pygame.display.flip()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
        clock.tick(60)

    pygame.quit()

if __name__ == "__main__":
    main()
