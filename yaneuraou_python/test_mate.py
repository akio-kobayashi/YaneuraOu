import sys
import os

# Add the project root to the Python path to allow importing 'python_yaneuraou'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from yaneuraou_python import core as yaneuraou_engine
except ImportError as e:
    print(f"Error: Could not import the wrapper module: {e}")
    print("Please make sure you have built the wrapper by running 'build.sh' in the 'python_yaneuraou' directory.")
    sys.exit(1)

def test_mate_problem():
    """
    Tests a known mate problem.
    """
    print("--- Testing 3-ply mate problem (Koufu problem) ---")

    # 有名な3手詰め「香歩問題」
    # 正解手順: ▲2一香成
    sfen = "l6nl/5+P1gk/p1p1p3p/1p2p2b1/9/1P2P2P1/P1P1P1P1P/1KGSG4/L7+R b - p 1"
    
    print(f"SFEN: {sfen}")

    # 詰み探索の実行 (ノード数上限を多めに設定)
    is_mate, pv = yaneuraou_engine.solve_mate(sfen, nodes_limit=5_000_000)

    print(f"Result: is_mate={is_mate}, pv={pv}")

    # 結果の検証
    assert is_mate is True, "is_mate should be True"
    assert len(pv) >= 3, "PV length should be at least 3" # Mate in 3
    assert pv[0] == "2a1a+", "First move should be 2a1a+"

    print("✅ Test passed!")


def test_no_mate_problem():
    """
    Tests a position that is not a mate.
    """
    print("\n--- Testing non-mate position (initial position) ---")
    
    # 初期局面 (詰みではない)
    sfen = "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - 1"
    
    print(f"SFEN: {sfen}")

    # 詰み探索の実行 (ノード数は少なめで良い)
    is_mate, pv = yaneuraou_engine.solve_mate(sfen, nodes_limit=100_000)

    print(f"Result: is_mate={is_mate}, pv={pv}")

    # 結果の検証 (不詰が証明されるはず)
    assert is_mate is False, "is_mate should be False"
    assert len(pv) == 0, "PV should be empty"

    print("✅ Test passed!")


if __name__ == "__main__":
    print("--- Initializing YaneuraOu engine ---")
    yaneuraou_engine.init()
    print("Initialization complete.")
    
    test_mate_problem()
    test_no_mate_problem()

    print("\nAll tests completed successfully!")
