#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <string>
#include <vector>
#include <stdexcept>
#include <iostream>

#include "config.h"
#include "types.h"
#include "bitboard.h"
#include "position.h"
#include "movegen.h"
#include "usi.h"
#include "misc.h"
#include "thread.h"
#include "mate.h"

namespace py = pybind11;
using namespace YaneuraOu;

// --- 初期化 ---
// グローバルなオブジェクトやテーブルを初期化する
// Pythonモジュールがインポートされたときに一度だけ呼び出すべき
void initialize_yaneuraou() {
    static bool initialized = false;
    if (!initialized) {
        Bitboard::init();
        Position::init();
        initialize_usi_option();
        // Mate::init() は USE_MATE_1PLY の中で宣言されている
#if defined(USE_MATE_1PLY)
        Mate::init();
#endif
        initialized = true;
    }
}


// --- ヘルパー関数 ---

std::string square_to_str(Square sq) {
    if (sq == SQ_NB) return "None";
    return YaneuraOu::square_to_string(sq);
}

std::string move_to_usi_str(Move m) {
    if (m == MOVE_NONE) return "none";
    if (m == MOVE_NULL) return "null";
    return YaneuraOu::move_to_usi_string(m);
}

// --- ラッパー関数 ---

py::list get_legal_moves_info(const std::string& sfen_str) {
    py::list results;
    Position pos;
    pos.set(sfen_str);
    
    MoveList<LEGAL_ALL> legal_moves_list(pos);

    for (const Move& move : legal_moves_list) {
        pos.do_move(move);
        std::string after_sfen = pos.sfen();
        pos.undo_move();

        py::dict move_info;
        move_info["from"] = square_to_str(move.from());
        move_info["to"] = square_to_str(move.to());
        move_info["usi"] = move_to_usi_str(move);
        move_info["sfen"] = after_sfen;
        
        results.append(move_info);
    }

    return results;
}

// 詰み探索を実行するラッパー
// 戻り値: (is_mate, pv)
// is_mate: bool | None (詰み:True, 不詰:False, 不明:None)
// pv: list[str] (詰み手順のUSI文字列リスト)
py::tuple solve_mate(const std::string& sfen_str, u64 nodes_limit) {
    // df-pnソルバーのインスタンスを作成
    // ここでは一番シンプルなNode32bitを使用
    Mate::Dfpn::MateDfpnSolver solver(Mate::Dfpn::DfpnSolverType::Node32bit);

    // メモリ確保 (ノード数に応じて)
    // ノードあたり32bitなので、nodes_limit * 4 バイト。少し多めに確保。
    // alloc()はMB単位なので注意。最低でも1MBは確保。
    size_t mem_size_mb = std::max((size_t)1, (size_t)(nodes_limit * 5 / (1024 * 1024)));
    solver.alloc(mem_size_mb);

    // 局面のセット
    Position pos;
    pos.set(sfen_str);

    // 詰み探索の実行
    Move result_move = solver.mate_dfpn(pos, nodes_limit);

    // 結果の判定
    if (result_move == MOVE_NULL) {
        // 不詰が証明された
        return py::make_tuple(false, py::list());
    } else if (result_move == MOVE_NONE) {
        // 制限内に解けなかった (メモリ不足 or ノード数超過)
        return py::make_tuple(py::none(), py::list());
    } else {
        // 詰みを発見
        std::vector<Move> pv_moves = solver.get_pv();
        py::list pv_usi;
        for (const auto& move : pv_moves) {
            pv_usi.append(move_to_usi_str(move));
        }
        return py::make_tuple(true, pv_usi);
    }
}


// --- pybind11モジュール定義 ---

PYBIND11_MODULE(python_yaneuraou_core, m) {
    m.doc() = "pybind11 based Python wrapper for YaneuraOu";

    // --- 初期化 ---
    m.def("init", &initialize_yaneuraou, "Initialize YaneuraOu's global objects.");

    // --- 合法手生成 ---
    m.def("get_legal_moves_info", &get_legal_moves_info,
          "Generates all legal moves for a given SFEN position and returns their details.");

    // --- 詰み探索 ---
    m.def("solve_mate", &solve_mate,
          "Solve mate problem for a given SFEN position.",
          py::arg("sfen"), py::arg("nodes_limit") = 1000000);
}