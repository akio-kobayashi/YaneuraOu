cmake_minimum_required(VERSION 3.15...3.27) # CMakeの最小バージョンと推奨バージョン

project(yaneuraou_python LANGUAGES CXX) # プロジェクト名と使用言語を指定

# pybind11を検出
find_package(pybind11 CONFIG REQUIRED)

# Pythonラッパーのモジュール名を定義
set(MODULE_NAME yaneuraou_python.core)

# YaneuraOuのソースディレクトリのパスを設定 (親ディレクトリにあるsourceを指す)
# これはyaneuraou_python_wrapper/CMakeLists.txtから見て '../source' となる
set(YANEURAOU_SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../source")

# YaneuraOuの合法手生成に必要なC++ソースファイルとヘッダファイル
# 必要に応じてここに追加・修正してください
set(YANEURAOU_CORE_SOURCES
    ${YANEURAOU_SOURCE_DIR}/bitboard.cpp
    ${YANEURAOU_SOURCE_DIR}/position.cpp
    ${YANEURAOU_SOURCE_DIR}/movegen.cpp
    ${YANEURAOU_SOURCE_DIR}/types.cpp
    ${YANEURAOU_SOURCE_DIR}/thread.cpp
    ${YANEURAOU_SOURCE_DIR}/misc.cpp
    ${YANEURAOU_SOURCE_DIR}/tt.cpp
    # 評価関数ファイルもPositionで参照されているので追加
    ${YANEURAOU_SOURCE_DIR}/eval/evaluate.cpp
    ${YANEURAOU_SOURCE_DIR}/eval/evaluate_bona_piece.cpp
    # 詰み探索のために追加
    ${YANEURAOU_SOURCE_DIR}/mate/mate.cpp
    ${YANEURAOU_SOURCE_DIR}/mate/mate_solver.cpp
    ${YANEURAOU_SOURCE_DIR}/mate/mate1ply_without_effect.cpp
    ${YANEURAOU_SOURCE_DIR}/mate/mate1ply_with_effect.cpp
    ${YANEURAOU_SOURCE_DIR}/search.cpp
    ${YANEURAOU_SOURCE_DIR}/movepick.cpp
    ${YANEURAOU_SOURCE_DIR}/score.cpp # search.cppが依存
)

# ヘッダファイルのインクルードパス
include_directories(
    ${YANEURAOU_SOURCE_DIR}
    ${YANEURAOU_SOURCE_DIR}/eval
    ${YANEURAOU_SOURCE_DIR}/mate # 詰み探索のために追加
    ${pybind11_INCLUDE_DIRS}
)

# ラッパーのメインC++ソースファイル
set(WRAPPER_SOURCES
    src/yaneuraou_wrapper/wrapper.cpp
)

# Python拡張モジュールをビルドする
pybind11_add_module(${MODULE_NAME} SHARED
    ${YANEURAOU_CORE_SOURCES}
    ${WRAPPER_SOURCES}
)

# 詰み探索エンジンを有効にするためのマクロを定義
target_compile_definitions(${MODULE_NAME} PRIVATE YANEURAOU_MATE_ENGINE)

# モジュールにリンクするライブラリ (例えば数学関数など)
target_link_libraries(${MODULE_NAME} PRIVATE pybind11::embed)