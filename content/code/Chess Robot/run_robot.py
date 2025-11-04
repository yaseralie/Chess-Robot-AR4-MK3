import serial
import time

# ===============================
# KONFIGURASI SERIAL
# ===============================
ROBOT_PORT = "COM16"      # ganti sesuai port robot
GRIPPER_PORT = "COM17"    # ganti sesuai port gripper
BAUDRATE = 9600

robot = serial.Serial(ROBOT_PORT, BAUDRATE, timeout=0.5)
gripper = serial.Serial(GRIPPER_PORT, BAUDRATE, timeout=0.5)

# ===============================
# POSISI REFERENSI
# ===============================
A1 = (500.000, -95.000)
H1 = (500.000, 95.000)
A8 = (300.000, -85.000)
H8 = (295.000, 105.000)

TEMP_CMD = "MJX286.878Y200.064Z433.700Rz0.018Ry180.000Rx0.016J70.00J80.00J90.00Sp40Ac15Dc15Rm80WFLm000000"
HOME_CMD = "MJX286.878Y0.064Z433.700Rz0.018Ry180.000Rx0.016J70.00J80.00J90.00Sp40Ac15Dc15Rm80WFLm000000"
BOX_CMD  = "MJX331.169Y-178.241Z240.000Rz0.077Ry180.000Rx0.069J70.00J80.00J90.00Sp40Ac15Dc15Rm80WFLm000000"

# ===============================
# FUNGSI PEMBANTU
# ===============================

def wait_robot_response(max_wait=20):
    """Menunggu sampai robot mengirim respon (apapun isinya)."""
    start = time.time()
    buffer = ""
    while True:
        if robot.in_waiting:
            data = robot.read(robot.in_waiting).decode(errors='ignore')
            buffer += data
            if buffer.strip() != "":
                break
        if time.time() - start > max_wait:
            print("   ⚠️ Timeout: tidak ada respon dari robot (lanjut)...")
            break
        time.sleep(0.05)
    dur = time.time() - start
    print(f"   ↳ Respon diterima ({dur:.2f} detik)")
    return dur


def wait_gripper_response():
    """Gripper tidak kirim respon, tunggu singkat saja"""
    time.sleep(0.3)


def square_to_coord(square):
    """Mengubah notasi seperti 'e2' menjadi koordinat X,Y berdasarkan A1,H1,A8,H8"""
    file = square[0].lower()
    rank = int(square[1])

    fx = (ord(file) - ord('a')) / (ord('h') - ord('a'))
    fy = (rank - 1) / (8 - 1)

    x1 = A1[0] + (A8[0] - A1[0]) * fy
    x2 = H1[0] + (H8[0] - H1[0]) * fy
    y1 = A1[1] + (A8[1] - A1[1]) * fy
    y2 = H1[1] + (H8[1] - H1[1]) * fy

    X = x1 + (x2 - x1) * fx
    Y = y1 + (y2 - y1) * fx
    return (X, Y, rank)   # ✅ tambahkan rank supaya bisa tahu ketinggian z


def send_robot(cmd, note=""):
    print(f"> {note} ...")
    start = time.time()
    robot.write((cmd + "\n").encode())
    wait_robot_response()
    total = time.time() - start
    print(f"   ✓ {note} selesai ({total:.2f} detik)")


def move_robot(x, y, z=240, sp=30, note="Move"):
    cmd = f"MJX{x:.3f}Y{y:.3f}Z{z:.3f}Rz0.024Ry174.670Rx0.016J70.00J80.00J90.00Sp{sp}Ac15Dc15Rm80WFLm000000"
    send_robot(cmd, note)


def move_temp():
    send_robot(TEMP_CMD, "Move TEMP")


def move_home():
    send_robot(HOME_CMD, "Move HOME")


def move_box():
    send_robot(BOX_CMD, "Move BOX")


def gripper_open():
    print("> Gripper OPEN")
    gripper.write(b"SV0P35\n")
    wait_gripper_response()
    print("   ✓ Gripper OPEN selesai")


def gripper_close():
    print("> Gripper CLOSE")
    gripper.write(b"SV0P0\n")
    wait_gripper_response()
    print("   ✓ Gripper CLOSE selesai")


# ===============================
# GERAKAN UTAMA
# ===============================
last_end = None  # simpan posisi terakhir robot (misal 'e4')

def move_piece(move_str, capture=False, castle=False):
    global last_end
    start = move_str[:2]
    end = move_str[2:]

    print(f"\n=== Langkah {start} → {end} ===")
    xs, ys, rank_s = square_to_coord(start)
    xe, ye, rank_e = square_to_coord(end)

    # tentukan z turun berdasarkan rank
    z_down_start = 140 if rank_s >= 5 else 150
    z_down_end   = 140 if rank_e >= 5 else 150

    total_start = time.time()
    gripper_open()
    move_temp()

    # === Jika capture ===
    if capture:
        print(f"[CAPTURE] Ambil bidak lawan di {end}")
        move_robot(xe, ye, 240, 30, f"Ke atas posisi lawan {end}")
        move_robot(xe, ye, z_down_end, 8, f"Turun ke bidak lawan (Z={z_down_end})")
        time.sleep(1)
        gripper_close()
        time.sleep(3)
        move_robot(xe, ye, 240, 20, f"Naik dari bidak lawan")
        move_box()
        time.sleep(1)
        gripper_open()
        move_temp()
        print("[INFO] Bidak lawan dibuang ke kotak")

    # Jika castling, kita harus pindahkan king dulu lalu rook
    if castle:
        # --- Move KING (start->end) ---
        print("[CASTLE] Pindahkan KING terlebih dahulu")
        gripper_open()
        move_temp()
        move_robot(xs, ys, 240, 45, f"Ke atas {start} (king)")
        move_robot(xs, ys, z_down_start, 10, f"Turun ke {start} (king)")
        time.sleep(0.6)
        gripper_close()
        time.sleep(0.6)
        move_robot(xs, ys, 240, 20, f"Naik dari {start} (king)")
        move_temp()
        move_robot(xe, ye, 240, 45, f"Ke atas {end} (king)")
        move_robot(xe, ye, z_down_end, 8, f"Turun ke {end} (king)")
        gripper_open()
        move_robot(xe, ye, 240, 20, f"Naik dari {end} (king)")
        move_temp()

        # --- Move ROOK (determine rook start/end from king move) ---
        print("[CASTLE] Sekarang pindahkan ROOK")
        # tentukan rook start & rook end berdasarkan arah castling
        # jika king bergerak ke kanan (g-file) => rook dari h -> f
        ks_file = start[0]
        ke_file = end[0]
        ks_rank = start[1]
        if ord(ke_file) > ord(ks_file):
            # kingside: rook from hX -> fX
            rook_start = f"h{ks_rank}"
            rook_end   = f"f{ks_rank}"
        else:
            # queenside: rook from aX -> dX
            rook_start = f"a{ks_rank}"
            rook_end   = f"d{ks_rank}"

        rx_s, ry_s, rrank_s = square_to_coord(rook_start)
        rx_e, ry_e, rrank_e = square_to_coord(rook_end)
        z_down_rook = 145 if rrank_s >= 5 else 150

        # pindahkan rook/benteng
        gripper_open()
        move_temp()
        move_robot(rx_s, ry_s, 240, 45, f"Ke atas {rook_start} (rook)")
        move_robot(rx_s, ry_s, z_down_rook, 10, f"Turun ke {rook_start} (rook)")
        time.sleep(0.6)
        gripper_close()
        time.sleep(0.6)
        move_robot(rx_s, ry_s, 240, 20, f"Naik dari {rook_start} (rook)")
        move_temp()
        move_robot(rx_e, ry_e, 240, 45, f"Ke atas {rook_end} (rook)")
        move_robot(rx_e, ry_e, z_down_rook, 8, f"Turun ke {rook_end} (rook)")
        gripper_open()
        move_robot(rx_e, ry_e, 240, 20, f"Naik dari {rook_end} (rook)")
        move_temp()

        # selesai castling -> ke HOME dan rapikan gripper
        move_home()
        gripper_close()
        last_end = end
        total_time = time.time() - total_start
        print(f"=== CASTLE selesai dalam {total_time:.2f} detik ===\n")
        return

    # === Ambil bidak sendiri ===
    move_robot(xs, ys, 240, 45, f"Ke atas {start}")
    move_robot(xs, ys, z_down_start, 10, f"Turun ke {start} (Z={z_down_start})")
    time.sleep(1)
    gripper_close()
    time.sleep(3)
    move_robot(xs, ys, 240, 20, f"Naik dari {start}")

    # === Tentukan apakah perlu ke TEMP ===
    same_file = (start[0] == end[0])
    rank_distance = abs(int(start[1]) - int(end[1]))
    file_start = start[0]
    file_end = end[0]

    need_temp = True

    # Jika kolom d/e (berapapun jaraknya) → skip temp
    if file_start in ['d', 'e'] and file_end in ['d', 'e']:
        need_temp = False
    # Jika kolom sama tapi di luar d/e → skip temp jika jarak < 3
    elif same_file and rank_distance < 3:
        need_temp = False

    if need_temp:
        move_temp()
    else:
        print(f"   ↳ Lewati TEMP (gerakan pendek di kolom {start[0].upper()})")

    # === Taruh bidak di petak tujuan ===
    move_robot(xe, ye, 240, 45, f"Ke atas {end}")
    move_robot(xe, ye, z_down_end, 5, f"Turun ke {end} (Z={z_down_end})")
    gripper_open()
    move_robot(xe, ye, 240, 20, f"Naik dari {end}")
    move_home()
    gripper_close()
    last_end = end

    total_time = time.time() - total_start
    print(f"=== Selesai dalam {total_time:.2f} detik ===\n")


# ===============================
# MAIN LOOP
# ===============================
if __name__ == "__main__":
    print("=== Robot Chess Controller ===")
    print("Masukkan langkah (contoh e2e4), atau 'q' untuk keluar.\n")

    while True:
        cmd = input("Langkah: ").strip()
        if cmd.lower() == "q":
            print("Keluar...")
            break
        if len(cmd) == 4:
            move_piece(cmd)
        else:
            print("Format salah, contoh: e2e4")
