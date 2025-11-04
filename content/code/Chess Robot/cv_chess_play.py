
import cv2
import json
import numpy as np
import chess
import chess.engine
import chess.svg
from PIL import Image
import io
import random
import os
import sys
import cairosvg
import time
from run_robot import move_piece  # pastikan bisa diimport di direktori yang sama

# === CONFIG ===
CALIB_JSON = "sqdict.json"
ENGINE_PATH = r"stockfish-windows-x86-64-avx2.exe"
MOVE_THRESHOLD = 30
MIN_CONTOUR_AREA = 250
CAM_INDEX = 0
BOARD_ORIENTATION = "TOP"  # "TOP", "BOTTOM", "SIDE_L", "SIDE_R"

DEBUG_MODE = False  # Tekan 'd' untuk toggle ON/OFF

# === ENGINE ===
if not os.path.exists(ENGINE_PATH):
    print(f"[ERROR] File engine tidak ditemukan: {ENGINE_PATH}")
    sys.exit(1)

engine = chess.engine.SimpleEngine.popen_uci(ENGINE_PATH)
print(f"[INFO] Stockfish dijalankan dari {ENGINE_PATH}")

# === LOAD JSON ===
if not os.path.exists(CALIB_JSON):
    print(f"[ERROR] File kalibrasi tidak ditemukan: {CALIB_JSON}")
    engine.quit()
    sys.exit(1)

with open(CALIB_JSON, "r") as f:
    sq_points = json.load(f)
print(f"[INFO] Memuat {len(sq_points)} kotak dari {CALIB_JSON}")

# === ORIENTATION ===
files = 'abcdefgh'
ranks = '12345678'

def remap_square(square_name: str) -> str:
    f = square_name[0]
    r = square_name[1]
    fi = files.index(f)
    ri = ranks.index(r)
    if BOARD_ORIENTATION == "TOP":
        return square_name
    elif BOARD_ORIENTATION == "BOTTOM":
        return f"{files[7 - fi]}{ranks[7 - ri]}"
    elif BOARD_ORIENTATION == "SIDE_L":
        return f"{files[ri]}{ranks[7 - fi]}"
    elif BOARD_ORIENTATION == "SIDE_R":
        return f"{files[7 - ri]}{ranks[fi]}"
    else:
        return square_name

# === HELPERS ===
def poly_center(pts):
    a = np.array(pts, np.int32)
    M = cv2.moments(a)
    if M["m00"] == 0:
        return int(a[:, 0].mean()), int(a[:, 1].mean())
    return int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])

def find_square(x, y):
    """Return square name if point (x,y) is inside the polygon for that square."""
    pt = (float(x), float(y))
    for sq, pts in sq_points.items():
        poly = np.array(pts, np.int32)
        # pointPolygonTest >= 0 berarti di dalam atau di tepi polygon
        if cv2.pointPolygonTest(poly, pt, False) >= 0:
            return sq
    return None

def overlay_poly(frame, poly_pts, color, alpha=0.45):
    overlay = frame.copy()
    pts = np.array(poly_pts, np.int32)
    cv2.fillPoly(overlay, [pts], color)
    return cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)

def draw_board_labels(base_frame):
    overlay = base_frame.copy()
    font = cv2.FONT_HERSHEY_SIMPLEX
    for sq, pts in sq_points.items():
        p = np.array(pts, np.int32)
        cv2.polylines(overlay, [p], True, (255, 255, 255), 1)
        if sq == "a1":
            cx, cy = poly_center(pts)
            mapped = remap_square(sq)
            cv2.putText(overlay, mapped, (cx - 12, cy + 5), font, 0.45, (0, 255, 255), 1, cv2.LINE_AA)
    return overlay

def pick_top_two_contours_by_square(contours, mask_board):
    # Kontur -> (square, contour, area, cx, cy)
    items = []
    for c in contours:
        area = cv2.contourArea(c)
        if area <= MIN_CONTOUR_AREA:
            continue

        x, y, w, h = cv2.boundingRect(c)
        M = cv2.moments(c)

        # Bias: gunakan center-top dari bounding box (bagian atas bidak) — 30..40% dari tinggi
        top_center_y = int(y + 0.35 * h)
        bbox_center_x = int(x + w // 2)

        if M["m00"] != 0:
            cx_m = int(M["m10"] / M["m00"])
            cy_m = int(M["m01"] / M["m00"])
            # gunakan centroid untuk X (lebih stabil horizontal), dan gunakan top_center_y untuk Y
            cx = cx_m
            cy = top_center_y
        else:
            cx = bbox_center_x
            cy = top_center_y

        sq = find_square(cx, cy)
        if sq:
            items.append((sq, c, area, cx, cy))

    # group by square, keep largest contour per square
    by_sq = {}
    for sq, c, area, cx, cy in items:
        if sq not in by_sq or area > by_sq[sq][0]:
            by_sq[sq] = (area, c, cx, cy)

    # sort squares by area desc, return up to 2 contours (contour objects)
    sorted_sq = sorted(by_sq.items(), key=lambda kv: kv[1][0], reverse=True)
    contours_out = []
    for sq, (area, c, cx, cy) in sorted_sq[:2]:
        contours_out.append((c, cx, cy))  # return tuple (contour, cx, cy)
    return contours_out

def show_board(board, last_move=None):
    svg = chess.svg.board(board=board, lastmove=last_move, coordinates=True, size=700)
    png_data = cairosvg.svg2png(bytestring=svg.encode('utf-8'))
    img = Image.open(io.BytesIO(png_data))
    img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    cv2.imshow("Board State", img_cv)
    cv2.waitKey(1)

def draw_contours_debug(frame, contours):
    dbg = frame.copy()
    for i, c in enumerate(contours):
        area = cv2.contourArea(c)
        x, y, w, h = cv2.boundingRect(c)
        M = cv2.moments(c)
        if M["m00"] != 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
        else:
            cx, cy = x + w // 2, y + h // 2

        cv2.rectangle(dbg, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.circle(dbg, (cx, cy), 3, (0, 0, 255), -1)
        cv2.putText(dbg, f"A:{int(area)}", (x, y - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    return dbg

# === CAMERA ===
cap = cv2.VideoCapture(CAM_INDEX, cv2.CAP_DSHOW)
if not cap.isOpened():
    print("[ERROR] Kamera tidak bisa dibuka.")
    engine.quit()
    sys.exit(1)

board = chess.Board()
ref_frame = None
last_move = None
comp_turn = False
move_history = []

print("[INFO] Tekan 'r' dua kali untuk langkah, 'u'=undo, 'U'=undo 2 langkah, 'd'=toggle debug, 'q'=keluar.")
show_board(board)

try:
    while not board.is_game_over():
        ret, frame_raw = cap.read()
        if not ret:
            continue

        display = draw_board_labels(frame_raw.copy())
        cv2.imshow("Chess Tracker", display)
        key = cv2.waitKey(1) & 0xFF

        # === Toggle debug mode ===
        if key == ord('d'):
            DEBUG_MODE = not DEBUG_MODE
            state = "ON" if DEBUG_MODE else "OFF"
            print(f"[INFO] Debug mode: {state}")
            if not DEBUG_MODE:
                try:
                    if cv2.getWindowProperty("Diff", cv2.WND_PROP_VISIBLE) >= 0:
                        cv2.destroyWindow("Diff")
                except cv2.error:
                    pass

                try:
                    if cv2.getWindowProperty("Contours", cv2.WND_PROP_VISIBLE) >= 0:
                        cv2.destroyWindow("Contours")
                except cv2.error:
                    pass

        # === Rekam langkah pemain (dua kali tekan 'r') ===
        if key == ord('r'):
            if ref_frame is None:
                ref_frame = frame_raw.copy()
                print("[DEBUG] Frame awal disimpan.")
            else:
                print("[DEBUG] Frame akhir direkam, memproses...")
                # versi lebih universal (untuk putih gading dan hitam/coklat)
                g1 = 0.5 * ref_frame[:, :, 2] + 0.4 * ref_frame[:, :, 1] + 0.1 * ref_frame[:, :, 0]
                g2 = 0.5 * frame_raw[:, :, 2] + 0.4 * frame_raw[:, :, 1] + 0.1 * frame_raw[:, :, 0]
                g1 = g1.astype(np.uint8)
                g2 = g2.astype(np.uint8)

                g1 = cv2.GaussianBlur(g1, (5, 5), 0)
                g2 = cv2.GaussianBlur(g2, (5, 5), 0)
                diff = cv2.absdiff(g1, g2)
                diff = cv2.GaussianBlur(diff, (3,3), 0)
                diff = cv2.convertScaleAbs(diff, alpha=1.3, beta=0)  # memperkuat kontras perbedaan
                _, diff_thresh = cv2.threshold(diff, MOVE_THRESHOLD, 255, cv2.THRESH_BINARY)
                diff_m = cv2.dilate(diff_thresh, None, iterations=4)
                diff_m = cv2.erode(diff_m, None, iterations=2)

                # === Batasi area deteksi hanya pada papan catur ===
                mask_board = np.zeros_like(diff_m)
                for pts in sq_points.values():
                    cv2.fillPoly(mask_board, [np.array(pts, np.int32)], 255)
                diff_m = cv2.bitwise_and(diff_m, mask_board)

                if DEBUG_MODE:
                    cv2.imshow("Diff", diff_m)

                kernel = np.ones((3, 3), np.uint8)
                diff_m = cv2.morphologyEx(diff_m, cv2.MORPH_OPEN, kernel)
                diff_m = cv2.morphologyEx(diff_m, cv2.MORPH_CLOSE, kernel)

                contours, _ = cv2.findContours(diff_m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                # ambil kandidat dari kontur (kontur, dan bounding)
                contours_filtered = [c for c in contours if cv2.contourArea(c) > MIN_CONTOUR_AREA]

                # helper: buat daftar kandidat kotak (square) untuk sebuah kontur
                def candidates_for_contour(c):
                    x, y, w, h = cv2.boundingRect(c)
                    M = cv2.moments(c)
                    if M["m00"] != 0:
                        cx_m = int(M["m10"] / M["m00"])
                        cy_m = int(M["m01"] / M["m00"])
                    else:
                        cx_m = x + w//2
                        cy_m = y + h//2

                    # coba beberapa vertical bias dan sedikit horizontal jitter
                    y_factors = [0.20, 0.30, 0.40]   # 20%..40% dari atas bounding box
                    x_jitters = [0, -6, 6]           # geser kiri/kanan kecil
                    cands = []
                    for yf in y_factors:
                        cy_try = int(y + yf * h)
                        for xj in x_jitters:
                            cx_try = cx_m + xj
                            sq_try = find_square(cx_try, cy_try)
                            if sq_try:
                                cands.append((sq_try, cx_try, cy_try))
                    # dedup while keeping order
                    seen = set()
                    out = []
                    for s in cands:
                        if s[0] not in seen:
                            seen.add(s[0]); out.append(s)
                    return out

                # build candidate lists for each detected contour
                contour_cand_lists = [(c, candidates_for_contour(c)) for c in contours_filtered]

                # if no contours -> skip
                detected = set()
                chosen_mapping = []  # will store chosen (sq, cx, cy)

                # snapshot board before move
                prev_board = board.copy()

                # if we have two or more contours, try combinations (prefer 2 largest)
                if len(contour_cand_lists) >= 2:
                    # sort contours by contour area descending and keep top 2
                    contour_cand_lists = sorted(contour_cand_lists,
                                                key=lambda it: cv2.contourArea(it[0]),
                                                reverse=True)[:2]

                    (c0, list0), (c1, list1) = contour_cand_lists

                    found = False
                    # try all combinations of candidate squares for the two contours
                    for s0, cx0, cy0 in list0:
                        for s1, cx1, cy1 in list1:
                            # two possible orderings: s0->s1 or s1->s0
                            try_moves = [(s0, s1), (s1, s0)]
                            for fr, to in try_moves:
                                try:
                                    mv = chess.Move.from_uci(fr + to)
                                except Exception:
                                    continue
                                # check legality on prev_board snapshot
                                if mv in prev_board.legal_moves:
                                    # accept this mapping
                                    detected = {fr, to}
                                    chosen_mapping = [(fr, cx0, cy0) if fr==s0 else (fr, cx1, cy1),
                                                      (to, cx1, cy1) if to==s1 else (to, cx0, cy0)]
                                    found = True
                                    break
                            if found:
                                break
                        if found:
                            break

                    # fallback: if not found any legal move using candidates, use previous simple logic:
                    if not found:
                        # default: map using the first candidate of each contour (if exists)
                        if list0 and list1:
                            s0 = list0[0][0]
                            s1 = list1[0][0]
                            detected = {s0, s1}
                            chosen_mapping = [(s0, list0[0][1], list0[0][2]), (s1, list1[0][1], list1[0][2])]

                elif len(contour_cand_lists) == 1:
                    # only one contour (likely capture or single detection) -> take best candidate
                    c0, list0 = contour_cand_lists[0]
                    if list0:
                        # choose first that matches any legal move destination
                        # prefer candidate that matches legal moves' destination
                        dest_chosen = None
                        for sq_try, cx_try, cy_try in list0:
                            # is there a legal move ending at sq_try?
                            candidates = [m for m in prev_board.legal_moves if m.uci()[2:] == sq_try]
                            if candidates:
                                dest_chosen = (sq_try, cx_try, cy_try)
                                break
                        if dest_chosen:
                            detected = {dest_chosen[0]}
                            chosen_mapping = [dest_chosen]
                        else:
                            detected = {list0[0][0]}
                            chosen_mapping = [list0[0]]

                else:
                    detected = set()

                # debug print chosen candidates
                if DEBUG_MODE:
                    print(f"[DEBUG] Contour candidate lists lengths: {[len(l) for _,l in contour_cand_lists]}")
                    print(f"[DEBUG] Chosen mapping: {chosen_mapping}")
                    print(f"[DEBUG] Kotak terdeteksi: {detected}")

                # visual debug: tunjukkan kotak dan titik yang dipilih
                if DEBUG_MODE and chosen_mapping:
                    dbg = frame_raw.copy()
                    for sq, cx, cy in chosen_mapping:
                        # draw square polygon and center used
                        poly = np.array(sq_points[sq], np.int32)
                        cv2.polylines(dbg, [poly], True, (0,255,0), 2)
                        cv2.circle(dbg, (int(cx), int(cy)), 4, (0,0,255), -1)
                        cv2.putText(dbg, sq, (int(cx)+6, int(cy)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 1)
                    cv2.imshow("Contours", dbg)

                print(f"[DEBUG] Kotak terdeteksi: {detected}")

                # === interpretasi langkah ===
                from_sq, to_sq = None, None
                if len(detected) == 2:
                    a, b = list(detected)

                    # Gunakan snapshot board sebelumnya untuk deteksi lebih akurat
                    # (salin state sebelum langkah)
                    prev_board = board.copy()

                    piece_a = prev_board.piece_at(chess.parse_square(a))
                    piece_b = prev_board.piece_at(chess.parse_square(b))

                    # Jika hanya satu yang punya bidak di posisi awal -> itu from_sq
                    if piece_a and not piece_b:
                        from_sq, to_sq = a, b
                    elif piece_b and not piece_a:
                        from_sq, to_sq = b, a
                    else:
                        # Jika keduanya kosong atau keduanya terisi (sulit), gunakan heuristik arah rank
                        def rank_idx(s): return int(s[1])
                        if board.turn == chess.WHITE:
                            from_sq, to_sq = sorted([a, b], key=rank_idx)
                        else:
                            from_sq, to_sq = sorted([a, b], key=rank_idx, reverse=True)

                elif len(detected) == 1:
                    # hanya satu kotak berubah — coba cara lebih andal untuk cari from_sq
                    to_sq = list(detected)[0]
                    prev_board = board.copy()  # snapshot posisi sebelum langkah
                    piece_now = board.piece_at(chess.parse_square(to_sq))

                    # 1) Jika kotak sekarang terisi, coba cari legal move yang berakhir di sini
                    if piece_now:
                        # filter kandidat yang asalnya memang punya piece pada prev_board
                        candidates = [m for m in board.legal_moves if m.uci()[2:] == to_sq]
                        chosen = None
                        for m in candidates:
                            src = m.uci()[:2]
                            if prev_board.piece_at(chess.parse_square(src)):
                                chosen = m
                                break
                        # jika tidak ketemu yang asalnya terisi, fallback ke first candidate
                        if not chosen and candidates:
                            chosen = candidates[0]
                        if chosen:
                            from_sq = chosen.uci()[:2]
                            to_sq = chosen.uci()[2:]
                    else:
                        # 2) kalau kotak akhir kosong -> kemungkinan bidak pindah dari kotak sekeliling
                        file = to_sq[0]
                        rank = int(to_sq[1])
                        fi = files.index(file)

                        # buat urutan pencarian yang prioritas: vertikal (sesuai giliran), horizontal, diagonal, 2-langkah
                        search_offsets = []

                        if board.turn == chess.WHITE:
                            # prefer datang dari bawah (rank-1), lalu left/right, lalu diagonals, then two-step from rank-2
                            search_offsets += [(0, -1), (-1, 0), (1, 0), (-1, -1), (1, -1), (0, -2)]
                        else:
                            # black moves downward in rank numbers (from higher rank to lower)
                            search_offsets += [(0, 1), (-1, 0), (1, 0), (-1, 1), (1, 1), (0, 2)]

                        # ensure we also consider all orthogonals/diagonals if needed
                        search_offsets += [(-1, 1), (1, 1), (-1, -1), (1, -1)]

                        found = False
                        for df, dr in search_offsets:
                            f_idx = fi + df
                            r_idx = rank + dr
                            if 0 <= f_idx < 8 and 1 <= r_idx <= 8:
                                adj = f"{files[f_idx]}{r_idx}"
                                if prev_board.piece_at(chess.parse_square(adj)):
                                    # verify move adj -> to_sq is legal
                                    try_mv = chess.Move.from_uci(adj + to_sq)
                                    if try_mv in board.legal_moves:
                                        from_sq = adj
                                        found = True
                                        break
                        # 3) jika belum juga ketemu, fallback: cari *any* neighbor yang punya piece (tanpa cek legal)
                        if not found:
                            for df in (-1, 0, 1):
                                for dr in (-1, 0, 1):
                                    if df == 0 and dr == 0:
                                        continue
                                    f_idx = fi + df
                                    r_idx = rank + dr
                                    if 0 <= f_idx < 8 and 1 <= r_idx <= 8:
                                        adj = f"{files[f_idx]}{r_idx}"
                                        if prev_board.piece_at(chess.parse_square(adj)):
                                            # jika move adj->to_sq legal gunakan, kalau tidak, tetap simpan adj sebagai last-resort
                                            try_mv = None
                                            try:
                                                try_mv = chess.Move.from_uci(adj + to_sq)
                                            except Exception:
                                                try_mv = None
                                            if try_mv and try_mv in board.legal_moves:
                                                from_sq = adj
                                                found = True
                                                break
                                            if not from_sq:
                                                from_sq = adj
                                if found:
                                    break
                        # jika masih None, from_sq tetap None dan akan dianggap invalid

                else:
                    print("[WARN] Deteksi tidak valid.")

                # === eksekusi langkah ===
                if from_sq and to_sq:
                    move = from_sq + to_sq
                    try:
                        mv = chess.Move.from_uci(move)
                        if mv in board.legal_moves:
                            board.push(mv)
                            move_history.append(mv)
                            last_move = mv
                            print(f"[YOU] Kamu main: {move}")
                            show_board(board, last_move)

                            # === HIGHLIGHT langkah pemain (FROM hijau, TO merah) ===
                            try:
                                frame_high = overlay_poly(frame_raw.copy(), sq_points[from_sq], (0, 255, 0), 0.5)
                                frame_high = overlay_poly(frame_high, sq_points[to_sq], (0, 0, 255), 0.5)
                                frame_high = draw_board_labels(frame_high)
                                cv2.imshow("Chess Tracker", frame_high)
                                cv2.waitKey(700)  # tampilkan sebentar
                            except Exception as e:
                                # jangan crash kalau key tidak ada di sq_points (safety)
                                if DEBUG_MODE:
                                    print(f"[DEBUG] Gagal highlight pemain: {e}")

                            comp_turn = True
                        else:
                            print(f"[!] Invalid move: {move}")
                    except Exception as e:
                        print(f"[!] Error interpretasi langkah: {e}")

                ref_frame = None

        # === Undo 1 langkah ===
        if key == ord('u'):
            if move_history:
                mv = move_history.pop()
                board.pop()
                print(f"[UNDO] Menghapus langkah terakhir: {mv}")
                show_board(board)
            else:
                print("[INFO] Tidak ada langkah untuk di-undo.")

        # === Undo 2 langkah ===
        if key == ord('U'):
            if len(move_history) >= 2:
                mv2 = move_history.pop()
                mv1 = move_history.pop()
                board.pop()
                board.pop()
                print(f"[UNDO] Menghapus 2 langkah terakhir: {mv1}, {mv2}")
                show_board(board)
            else:
                print("[INFO] Tidak cukup langkah untuk undo 2 kali.")

        # === COMPUTER TURN ===
        if comp_turn:
            result = engine.play(board, chess.engine.Limit(time=random.uniform(0.4, 0.9)))
            mv = result.move

            # === FOR ROBOT MOVEMENT ===
            move_str = mv.uci()            # Contoh: 'e2e4' atau 'd5e6'
            # deteksi capture & castling SEBELUM push
            is_capture = board.is_capture(mv)
            # deteksi castling: jika piece di from_square adalah raja dan bergeser 2 file
            piece_from = board.piece_at(mv.from_square)
            is_castle = False
            if piece_from and piece_from.piece_type == chess.KING:
                file_diff = abs((mv.to_square % 8) - (mv.from_square % 8))
                if file_diff == 2:
                    is_castle = True

            board.push(mv)
            move_history.append(mv)
            last_move = mv
            print(f"[AI] Komputer main: {move_str} (capture={is_capture}, castle={is_castle})")
            show_board(board, last_move)

            # === HIGHLIGHT langkah AI (FROM kuning, TO oranye) ===
            try:
                move_str = mv.uci()
                frame_ai = overlay_poly(frame_raw.copy(), sq_points[move_str[:2]], (0, 255, 255), 0.45)  # kuning
                frame_ai = overlay_poly(frame_ai, sq_points[move_str[2:]], (0, 165, 255), 0.45)  # oranye-ish
                frame_ai = draw_board_labels(frame_ai)
                cv2.imshow("Chess Tracker", frame_ai)
                cv2.waitKey(900)

                # panggil run_robot.move_piece dengan flag capture & castle
                move_piece(move_str, capture=is_capture, castle=is_castle)

            except Exception as e:
                if DEBUG_MODE:
                    print(f"[DEBUG] Gagal highlight AI: {e}")

            comp_turn = False

        if key == ord('q'):
            print("[INFO] Keluar.")
            break

    print("[INFO] Permainan selesai.")
finally:
    cap.release()
    cv2.destroyAllWindows()
    engine.quit()
