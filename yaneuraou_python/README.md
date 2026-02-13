# YaneuraOu Python Wrapper

やねうら王の高性能な指し手生成および詰み探索機能を Python から利用するためのライブラリです。`pybind11` を使用して C++ 実装を直接呼び出しているため、非常に高速に動作します。

## 主な機能

-   **合法手生成**: 指定した SFEN 局面からすべての合法手を生成し、移動元・移動先・移動後の SFEN などの詳細情報を取得。
-   **詰み探索**: やねうら王の df-pn ソルバーを使用して、指定した局面の詰みを判定および詰み手順（PV）を取得。
-   **高速動作**: やねうら王の C++ コアロジックを直接呼び出し。

## インストール方法

このライブラリをビルドするには、C++ コンパイラと CMake がインストールされている必要があります。
親ディレクトリの `source` フォルダにあるソースファイルを参照してビルドされます。

```bash
git clone https://github.com/akio-kobayashi/YaneuraOu.git
cd YaneuraOu/yaneuraou_python
pip install .
```

## 使い方

### 初期化と合法手生成

```python
from yaneuraou_python import core

# エンジンの初期化 (テーブルの作成など)
core.init()

# 平手のSFEN
sfen = "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - 1"

# 合法手情報の取得
moves_info = core.get_legal_moves_info(sfen)

for info in moves_info:
    print(f"Move: {info['usi']}, From: {info['from']}, To: {info['to']}")
    print(f"  SFEN after move: {info['sfen']}")
```

### 詰み探索

```python
from yaneuraou_python import core

core.init()

# 詰みのある局面のSFEN
mate_sfen = "9/9/9/9/9/9/9/9/k8/R8 b - 1"
# solve_mate(sfen, nodes_limit)
# nodes_limit: 探索ノード数制限 (デフォルト 1,000,000)
is_mate, pv = core.solve_mate(mate_sfen, nodes_limit=1000000)

if is_mate is True:
    print(f"詰みを発見しました! 手順: {' '.join(pv)}")
elif is_mate is False:
    print("不詰が証明されました。")
else:
    print("制限時間/ノード数内に詰みを発見できませんでした。")
```

## ライセンス

このプロジェクトは、やねうら王本体と同様に **GNU General Public License v3.0 (GPLv3)** の下でライセンスされています。

## 謝辞

このラッパーは、[やねうら王](https://github.com/yaneurao/YaneuraOu) の開発チームによる素晴らしい成果を利用しています。
