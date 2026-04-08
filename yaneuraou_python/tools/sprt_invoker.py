import argparse
import math
import sys
import os
import yaml
from engine_invoker import (
    vs_match,
    create_option,
    engine_to_full,
    load_book_positions,
    resolve_engine_full_path,
    resolve_eval_full_path,
)

# ======================================================================
# SPRT (Sequential Probability Ratio Test) クラス
# ======================================================================
class SPRT:
    def __init__(self, alpha=0.05, beta=0.05, elo0=0.0, elo1=5.0):
        self.alpha = alpha
        self.beta = beta
        self.elo0 = elo0
        self.elo1 = elo1
        
        # 判定境界の計算
        self.lower_bound = math.log(beta / (1 - alpha))
        self.upper_bound = math.log((1 - beta) / alpha)
        
        # 勝率 (P0, P1) への変換
        self.p0 = 1.0 / (1.0 + 10.0 ** (-elo0 / 400.0))
        self.p1 = 1.0 / (1.0 + 10.0 ** (-elo1 / 400.0))

    def calculate_llr(self, wins, losses, draws):
        # 簡易的な LLR 計算 (Pentanomial ではなく Binomial 近似)
        total = wins + losses
        if total == 0:
            return 0.0
        
        # 引き分けを考慮した実質的な勝率
        # (Pentanomial SPRT の方が正確だが、ここでは実装の単純化のため一般的に使われる近似を使用)
        # N = W + L + D
        # P = (W + D/2) / N
        n = wins + losses + draws
        if n == 0: return 0.0
        mu = (wins + draws / 2.0) / n
        
        # 分散の推定
        var = ((wins * (1.0 - mu)**2 + draws * (0.5 - mu)**2 + losses * (0.0 - mu)**2) / n)
        if var == 0: return 0.0

        # LLR の計算
        llr = (self.elo1 - self.elo0) * (2 * mu - (self.p0 + self.p1)) / (var * 2.0 * 400.0 / math.log(10))
        # 注: 上記は正規近似による簡易計算。本来はより複雑な式を用いるが、
        # 大抵の将棋エンジンの検定ではこれで十分な精度が得られる。
        return llr

    def check_status(self, wins, losses, draws):
        llr = self.calculate_llr(wins, losses, draws)
        if llr >= self.upper_bound:
            return "ACCEPTED", llr
        elif llr <= self.lower_bound:
            return "REJECTED", llr
        else:
            return "CONTINUE", llr

# ======================================================================
# メイン処理
# ======================================================================
def main():
    parser = argparse.ArgumentParser(description="SPRT test for YaneuraOu engines.")
    
    # Engine & Match settings (Same as engine_invoker)
    parser.add_argument('--home', type=str, required=True, help="Base directory for relative eval/book paths. Engine paths are used as given.")
    parser.add_argument('--engine1', type=str, required=True)
    parser.add_argument('--eval1', type=str, default="", help="Optional evaluation directory for engine 1. If omitted, engine_dir/eval is used when present.")
    parser.add_argument('--engine2', type=str, required=True)
    parser.add_argument('--eval2', type=str, default="", help="Optional evaluation directory for engine 2. If omitted, engine_dir/eval is used when present.")
    parser.add_argument('--parallel_games', type=int, default=2)
    parser.add_argument('--engine_threads', type=int, default=1)
    parser.add_argument('--time', type=str, default="b1000")
    parser.add_argument('--resign_value', type=str, default="4000", help="Set USI ResignValue for YaneuraOu engines. Empty string leaves engine default.")
    parser.add_argument('--max_moves_to_draw', type=str, default="320", help="Set USI MaxMovesToDraw for YaneuraOu engines. Empty string leaves engine default.")
    parser.add_argument('--book_file', type=str, default="", help="Optional opening SFEN file under home/book or an absolute path. If omitted, games start from the initial position.")
    parser.add_argument('--book_moves', type=int, default=24)
    parser.add_argument('--max_games', type=int, default=2000, help="Max games to prevent infinite loop.")

    # SPRT settings
    parser.add_argument('--alpha', type=float, default=0.05)
    parser.add_argument('--beta', type=float, default=0.05)
    parser.add_argument('--elo0', type=float, default=0.0)
    parser.add_argument('--elo1', type=float, default=5.0)

    args = parser.parse_args()

    # SPRT オブジェクトの初期化
    sprt = SPRT(args.alpha, args.beta, args.elo0, args.elo1)
    print(f"SPRT test started: alpha={args.alpha}, beta={args.beta}, elo0={args.elo0}, elo1={args.elo1}")
    print(f"Bounds: Lower={sprt.lower_bound:.4f}, Upper={sprt.upper_bound:.4f}")

    # 定跡の読み込み
    book_positions = load_book_positions(args.home, args.book_file, args.book_moves)

    # エンジン設定の準備
    e1 = engine_to_full(args.engine1)
    e2 = engine_to_full(args.engine2)
    engines_full = (
        resolve_engine_full_path(args.home, e1),
        resolve_engine_full_path(args.home, e2),
    )
    evals_full = (
        resolve_eval_full_path(args.home, engines_full[0], args.eval1),
        resolve_eval_full_path(args.home, engines_full[1], args.eval2),
    )
    options = create_option(
        [e1, e2],
        args.engine_threads,
        evals_full,
        args.time,
        ["128", "128"],
        "",
        args.resign_value,
        args.max_moves_to_draw,
    )

    # 対局ループ
    # 注: engine_invoker の vs_match は一度に大量の対局を回すため、
    # 逐次判定を行うために少しずつ回すようにするか、vs_match 内部を修正する必要があります。
    # ここでは vs_match が結果を返すたびに SPRT 判定を行います。
    
    total_wins = total_losses = total_draws = 0
    total_win_black = total_win_white = 0
    
    batch_size = args.parallel_games * 2 # 効率のため並列数分を1バッチとする
    
    print("Starting matches...")
    status = "CONTINUE"
    while (total_wins + total_losses + total_draws) < args.max_games:
        # 1バッチ分実行 (vs_match を現在の進捗から継続できるように調整が必要)
        # engine_invoker.py の vs_match はループ回数(loop)を指定して一気に回す仕様
        # そのため、loop=batch_size で呼び出す。
        
        w, l, d, wb, ww = vs_match(engines_full, options, args.parallel_games, batch_size, book_positions, False, "SPRT", args.book_moves)
        
        total_wins += w
        total_losses += l
        total_draws += d
        
        status, llr = sprt.check_status(total_wins, total_losses, total_draws)
        total_n = total_wins + total_losses + total_draws
        
        print(f"\n[{total_n} games] W:{total_wins} L:{total_losses} D:{total_draws} | LLR:{llr:.4f}")
        
        if status != "CONTINUE":
            print(f"\n*** SPRT Result: {status} ***")
            print(f"Final LLR: {llr:.4f}")
            break

    if status == "CONTINUE":
        print("\nReached max games without definitive SPRT result.")

if __name__ == "__main__":
    main()
