import cv2
import numpy as np
import json
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--rotate", type=int, default=0,
                    choices=[0, 90, 180, 270],
                    help="Rotasi orientasi papan terhadap kamera (CW). "
                         "Misal kamera dari kanan = 90, dari belakang = 180, dari kiri = 270.")
args = parser.parse_args()
CAM_ROT = args.rotate

points = []

def mouse_click(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        if len(points) < 4:
            points.append((x, y))
            print(f"[INFO] Titik {len(points)}: {x}, {y}")
        else:
            print("[INFO] Sudah 4 titik. Tekan 'r' untuk reset atau 's' untuk simpan.")

def remap_index(r_disp, c_disp, cam_rot):
    """Remap index (baris, kolom) dari tampilan kamera ke notasi papan standar."""
    if cam_rot == 0:
        r_std, c_std = r_disp, c_disp
    elif cam_rot == 90:
        r_std, c_std = c_disp, 7 - r_disp
    elif cam_rot == 180:
        r_std, c_std = 7 - r_disp, 7 - c_disp
    elif cam_rot == 270:
        r_std, c_std = 7 - c_disp, r_disp
    else:
        r_std, c_std = r_disp, c_disp
    return r_std, c_std

# === Buka kamera ===
cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
if not cap.isOpened():
    print("❌ Kamera tidak bisa dibuka.")
    exit()

cv2.namedWindow("Kalibrasi Papan")
cv2.setMouseCallback("Kalibrasi Papan", mouse_click)

print("📸 Instruksi:")
print(" 1️⃣ Arahkan kamera ke posisi yang AKAN digunakan (misal dari samping).")
print(" 2️⃣ Klik 4 titik sudut papan (urut: kiri-atas, kanan-atas, kanan-bawah, kiri-bawah).")
print(" 3️⃣ Tekan 'r' untuk reset, 's' untuk simpan hasil sqdict.json, 'q' untuk keluar.")
print(f"[INFO] Rotasi papan relatif ke kamera: {CAM_ROT}° (CW)\n")

while True:
    ret, frame = cap.read()
    if not ret:
        continue

    vis = frame.copy()

    # Gambar titik klik
    for idx, p in enumerate(points):
        cv2.circle(vis, p, 6, (0, 0, 255), -1)
        cv2.putText(vis, str(idx+1), (p[0]+8, p[1]-8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)

    if len(points) == 4:
        # Gambar kotak & grid
        pts = np.array(points, dtype=np.int32)
        cv2.polylines(vis, [pts], True, (255,255,255), 2)

        src = np.array([[0,0],[8,0],[8,8],[0,8]], dtype=np.float32)
        dst = np.array(points, dtype=np.float32)
        H = cv2.getPerspectiveTransform(src, dst)

        src_grid = np.array([[[x,y] for x in range(9)] for y in range(9)], dtype=np.float32)
        dst_grid = cv2.perspectiveTransform(src_grid.reshape(-1,1,2), H).reshape(9,9,2)

        # Gambar grid
        for r in range(9):
            cv2.polylines(vis, [dst_grid[r,:,:].astype(int)], False, (180,180,180), 1)
        for c in range(9):
            cv2.polylines(vis, [dst_grid[:,c,:].astype(int)], False, (180,180,180), 1)

        # === Tampilkan label notasi papan standar ===
        files = 'abcdefgh'
        ranks = '87654321'
        font = cv2.FONT_HERSHEY_SIMPLEX

        for r in range(8):
            for c in range(8):
                r_std, c_std = remap_index(r, c, CAM_ROT)
                file_letter = files[c_std]
                rank_char = ranks[r_std]
                label = f"{file_letter}{rank_char}"

                center = dst_grid[r, c] + (dst_grid[r+1, c+1] - dst_grid[r, c]) / 2
                cx, cy = int(center[0]), int(center[1])
                cv2.putText(vis, label, (cx-12, cy+5), font, 0.5, (0,255,255), 1, cv2.LINE_AA)

    cv2.imshow("Kalibrasi Papan", vis)
    key = cv2.waitKey(1) & 0xFF

    if key == ord('q'):
        print("Keluar tanpa menyimpan.")
        break
    elif key == ord('r'):
        points = []
        print("[INFO] Reset titik.")
    elif key == ord('s'):
        if len(points) != 4:
            print("[WARN] Harus klik 4 titik dulu sebelum menyimpan.")
            continue

        src = np.array([[0,0],[8,0],[8,8],[0,8]], dtype=np.float32)
        dst = np.array(points, dtype=np.float32)
        H = cv2.getPerspectiveTransform(src, dst)

        src_grid = np.array([[[x,y] for x in range(9)] for y in range(9)], dtype=np.float32)
        dst_grid = cv2.perspectiveTransform(src_grid.reshape(-1,1,2), H).reshape(9,9,2)

        displayed_squares = {}
        for r in range(8):
            for c in range(8):
                tl = dst_grid[r, c].tolist()
                tr = dst_grid[r, c+1].tolist()
                br = dst_grid[r+1, c+1].tolist()
                bl = dst_grid[r+1, c].tolist()
                displayed_squares[(r,c)] = [tl,tr,br,bl]

        # Remap orientasi papan ke notasi standar
        files = 'abcdefgh'
        ranks = '87654321'
        squares_std = {}
        for (r_disp, c_disp), poly in displayed_squares.items():
            r_std, c_std = remap_index(r_disp, c_disp, CAM_ROT)
            file_letter = files[c_std]
            rank_char = ranks[r_std]
            squares_std[f"{file_letter}{rank_char}"] = poly

        with open('sqdict.json', 'w') as f:
            json.dump(squares_std, f, indent=2)
        print(f"[✅] sqdict.json disimpan dengan rotasi orientasi {CAM_ROT}° (notasi sudah disesuaikan).")
        break

cap.release()
cv2.destroyAllWindows()
