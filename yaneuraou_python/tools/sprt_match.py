import argparse
import math
import os
import random
import sys

try:
    import yaml
except ImportError:
    yaml = None

from engine_invoker import (
    GameResult,
    create_option,
    load_book_positions,
    resolve_engine_binary_and_eval,
    vs_match,
)


def elo_to_score(elo):
    return 1.0 / (1.0 + 10.0 ** (-elo / 400.0))


def log_prob_term(count, prob):
    if count == 0:
        return 0.0
    if prob <= 0.0:
        return float("-inf")
    return count * math.log(prob)


def ternary_search_max(objective, left, right, iterations=80):
    if right <= left:
        return left, objective(left)
    for _ in range(iterations):
        m1 = left + (right - left) / 3.0
        m2 = right - (right - left) / 3.0
        if objective(m1) < objective(m2):
            left = m1
        else:
            right = m2
    point = (left + right) / 2.0
    return point, objective(point)


def constrained_trinomial_log_likelihood(wins, draws, losses, score):
    draw_upper = min(2.0 * score, 2.0 * (1.0 - score))
    if draw_upper < 0.0:
        return float("-inf"), 0.0, 0.0, 0.0

    def objective(draw_prob):
        win_prob = score - 0.5 * draw_prob
        loss_prob = 1.0 - score - 0.5 * draw_prob
        return (
            log_prob_term(wins, win_prob)
            + log_prob_term(draws, draw_prob)
            + log_prob_term(losses, loss_prob)
        )

    best_draw, best_ll = ternary_search_max(objective, 0.0, draw_upper)
    candidates = [0.0, draw_upper, best_draw]
    for candidate in candidates:
        ll = objective(candidate)
        if ll > best_ll:
            best_ll = ll
            best_draw = candidate

    win_prob = score - 0.5 * best_draw
    loss_prob = 1.0 - score - 0.5 * best_draw
    return best_ll, win_prob, best_draw, loss_prob


def pentanomial_probabilities(score, draw_prob):
    win_prob = score - 0.5 * draw_prob
    loss_prob = 1.0 - score - 0.5 * draw_prob
    probs = (
        loss_prob * loss_prob,
        2.0 * loss_prob * draw_prob,
        draw_prob * draw_prob + 2.0 * win_prob * loss_prob,
        2.0 * win_prob * draw_prob,
        win_prob * win_prob,
    )
    return probs, win_prob, loss_prob


def constrained_pentanomial_log_likelihood(pair_counts, score):
    draw_upper = min(2.0 * score, 2.0 * (1.0 - score))
    if draw_upper < 0.0:
        return float("-inf"), (0.0, 0.0, 0.0, 0.0, 0.0), 0.0, 0.0, 0.0

    def objective(draw_prob):
        probs, _win_prob, _loss_prob = pentanomial_probabilities(score, draw_prob)
        total = 0.0
        for count, prob in zip(pair_counts, probs):
            total += log_prob_term(count, prob)
        return total

    best_draw, best_ll = ternary_search_max(objective, 0.0, draw_upper)
    candidates = [0.0, draw_upper, best_draw]
    for candidate in candidates:
        ll = objective(candidate)
        if ll > best_ll:
            best_ll = ll
            best_draw = candidate

    probs, win_prob, loss_prob = pentanomial_probabilities(score, best_draw)
    return best_ll, probs, win_prob, best_draw, loss_prob


class TrinomialSprtTracker:
    def __init__(self, elo0, elo1, alpha, beta, min_games, report_every):
        if elo1 <= elo0:
            raise ValueError("elo1 must be greater than elo0 for SPRT.")
        if not (0.0 < alpha < 1.0 and 0.0 < beta < 1.0):
            raise ValueError("alpha and beta must be in (0, 1).")
        if min_games < 1:
            raise ValueError("min_games must be >= 1.")
        if report_every < 1:
            raise ValueError("report_every must be >= 1.")
        self.mu0 = elo_to_score(elo0)
        self.mu1 = elo_to_score(elo1)
        self.upper = math.log((1.0 - beta) / alpha)
        self.lower = math.log(beta / (1.0 - alpha))
        self.min_games = min_games
        self.report_every = report_every
        self.games = 0
        self.wins = 0
        self.draws = 0
        self.losses = 0
        self.llr = 0.0
        self.decision = None
        self.h0_probs = (self.mu0, 0.0, 1.0 - self.mu0)
        self.h1_probs = (self.mu1, 0.0, 1.0 - self.mu1)

    def update(self, game_info):
        result = game_info["result"]
        if result == GameResult.P1_WIN:
            self.wins += 1
        elif result == GameResult.DRAW:
            self.draws += 1
        elif result == GameResult.P2_WIN:
            self.losses += 1
        else:
            raise ValueError(f"Unsupported game result: {result}")
        self.games += 1

        h0_ll, h0_w, h0_d, h0_l = constrained_trinomial_log_likelihood(self.wins, self.draws, self.losses, self.mu0)
        h1_ll, h1_w, h1_d, h1_l = constrained_trinomial_log_likelihood(self.wins, self.draws, self.losses, self.mu1)
        self.h0_probs = (h0_w, h0_d, h0_l)
        self.h1_probs = (h1_w, h1_d, h1_l)
        self.llr = h1_ll - h0_ll

        if self.games >= self.min_games:
            if self.llr >= self.upper:
                self.decision = "accept_h1"
            elif self.llr <= self.lower:
                self.decision = "accept_h0"
        return True

    @property
    def score_rate(self):
        if self.games == 0:
            return 0.0
        return (self.wins + 0.5 * self.draws) / self.games

    @property
    def draw_rate(self):
        if self.games == 0:
            return 0.0
        return self.draws / self.games

    @property
    def estimated_elo(self):
        score = min(max(self.score_rate, 1e-9), 1.0 - 1e-9)
        return 400.0 * math.log10(score / (1.0 - score))

    def should_stop(self):
        return self.decision is not None

    def should_report(self):
        return self.games == 1 or self.games % self.report_every == 0 or self.should_stop()

    def summary_line(self):
        return (
            f"games={self.games} "
            f"W/D/L={self.wins}/{self.draws}/{self.losses} "
            f"score={self.score_rate:.4f} "
            f"draw={self.draw_rate:.4f} "
            f"elo={self.estimated_elo:.2f} "
            f"llr={self.llr:.4f} "
            f"[{self.lower:.4f}, {self.upper:.4f}]"
        )

    def model_line(self):
        h0_w, h0_d, h0_l = self.h0_probs
        h1_w, h1_d, h1_l = self.h1_probs
        return (
            f"H0(w/d/l)=({h0_w:.4f}/{h0_d:.4f}/{h0_l:.4f}) "
            f"H1(w/d/l)=({h1_w:.4f}/{h1_d:.4f}/{h1_l:.4f})"
        )


class PentanomialSprtTracker:
    def __init__(self, elo0, elo1, alpha, beta, min_pairs, report_every):
        if elo1 <= elo0:
            raise ValueError("elo1 must be greater than elo0 for SPRT.")
        if not (0.0 < alpha < 1.0 and 0.0 < beta < 1.0):
            raise ValueError("alpha and beta must be in (0, 1).")
        if min_pairs < 1:
            raise ValueError("min_pairs must be >= 1.")
        if report_every < 1:
            raise ValueError("report_every must be >= 1.")
        self.mu0 = elo_to_score(elo0)
        self.mu1 = elo_to_score(elo1)
        self.upper = math.log((1.0 - beta) / alpha)
        self.lower = math.log(beta / (1.0 - alpha))
        self.min_pairs = min_pairs
        self.report_every = report_every
        self.games = 0
        self.completed_pairs = 0
        self.incomplete_pairs = {}
        self.pair_counts = [0, 0, 0, 0, 0]
        self.wins = 0
        self.draws = 0
        self.losses = 0
        self.llr = 0.0
        self.decision = None
        self.h0_probs = (self.mu0 * self.mu0, 0.0, 0.0, 0.0, (1.0 - self.mu0) * (1.0 - self.mu0))
        self.h1_probs = self.h0_probs

    def result_to_score(self, result):
        if result == GameResult.P1_WIN:
            return 1.0
        if result == GameResult.DRAW:
            return 0.5
        if result == GameResult.P2_WIN:
            return 0.0
        raise ValueError(f"Unsupported game result: {result}")

    def update(self, game_info):
        result = game_info["result"]
        self.games += 1
        if result == GameResult.P1_WIN:
            self.wins += 1
        elif result == GameResult.DRAW:
            self.draws += 1
        elif result == GameResult.P2_WIN:
            self.losses += 1
        else:
            raise ValueError(f"Unsupported game result: {result}")

        pair_index = game_info["pair_index"]
        bucket = self.incomplete_pairs.setdefault(pair_index, [])
        bucket.append(self.result_to_score(result))
        if len(bucket) < 2:
            return False

        pair_score = bucket[0] + bucket[1]
        category = int(round(pair_score * 2))
        self.pair_counts[category] += 1
        self.completed_pairs += 1
        del self.incomplete_pairs[pair_index]

        h0_ll, h0_probs, _h0_w, _h0_d, _h0_l = constrained_pentanomial_log_likelihood(self.pair_counts, self.mu0)
        h1_ll, h1_probs, _h1_w, _h1_d, _h1_l = constrained_pentanomial_log_likelihood(self.pair_counts, self.mu1)
        self.h0_probs = h0_probs
        self.h1_probs = h1_probs
        self.llr = h1_ll - h0_ll

        if self.completed_pairs >= self.min_pairs:
            if self.llr >= self.upper:
                self.decision = "accept_h1"
            elif self.llr <= self.lower:
                self.decision = "accept_h0"
        return True

    @property
    def score_rate(self):
        if self.completed_pairs == 0:
            return 0.0
        total_pair_score = (
            0.0 * self.pair_counts[0]
            + 0.5 * self.pair_counts[1]
            + 1.0 * self.pair_counts[2]
            + 1.5 * self.pair_counts[3]
            + 2.0 * self.pair_counts[4]
        )
        return total_pair_score / (2.0 * self.completed_pairs)

    @property
    def draw_rate(self):
        if self.games == 0:
            return 0.0
        return self.draws / self.games

    @property
    def estimated_elo(self):
        score = min(max(self.score_rate, 1e-9), 1.0 - 1e-9)
        return 400.0 * math.log10(score / (1.0 - score))

    def should_stop(self):
        return self.decision is not None

    def should_report(self):
        return self.completed_pairs == 1 or self.completed_pairs % self.report_every == 0 or self.should_stop()

    def summary_line(self):
        return (
            f"games={self.games} "
            f"pairs={self.completed_pairs} "
            f"incomplete={len(self.incomplete_pairs)} "
            f"W/D/L={self.wins}/{self.draws}/{self.losses} "
            f"pair_counts(0,0.5,1,1.5,2)={self.pair_counts} "
            f"score={self.score_rate:.4f} "
            f"draw={self.draw_rate:.4f} "
            f"elo={self.estimated_elo:.2f} "
            f"llr={self.llr:.4f} "
            f"[{self.lower:.4f}, {self.upper:.4f}]"
        )

    def model_line(self):
        h0 = "/".join(f"{x:.4f}" for x in self.h0_probs)
        h1 = "/".join(f"{x:.4f}" for x in self.h1_probs)
        return f"H0(pair 0/0.5/1/1.5/2)=({h0}) H1(pair 0/0.5/1/1.5/2)=({h1})"


def load_config(parser, args):
    config = vars(args).copy()
    if args.config:
        if yaml is None:
            print("PyYAML is required when using --config. Please install it with 'pip install pyyaml'")
            sys.exit(1)
        try:
            with open(args.config, "r") as f:
                loaded = yaml.safe_load(f)
            if loaded:
                for key, value in loaded.items():
                    if key in config and config[key] == parser.get_default(key):
                        config[key] = value
        except FileNotFoundError:
            print(f"Warning: Config file not found at {args.config}")
        except Exception as exc:
            print(f"Warning: Error reading config file: {exc}")
    return config


def load_book_sfens(home, book_file_path, book_moves, rand_book):
    book_positions = load_book_positions(home, book_file_path, book_moves)
    if book_file_path and len(book_positions) > 1:
        random.shuffle(book_positions)
    return book_positions


def build_parser():
    parser = argparse.ArgumentParser(
        description="Run USI engine matches with SPRT stopping rules.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument("--config", type=str, help="Path to a YAML configuration file.")
    parser.add_argument("--home", type=str, help="Base directory used to resolve relative engine/book paths.")
    parser.add_argument("--engine1", type=str, help="Path or name of engine 1.")
    parser.add_argument("--eval1", type=str, default="", help="Optional evaluation directory for engine 1.")
    parser.add_argument("--engine2", type=str, help="Path or name of engine 2.")
    parser.add_argument("--eval2", type=str, default="", help="Optional evaluation directory for engine 2.")

    parser.add_argument("--parallel_games", type=int, default=1, help="Number of games to run in parallel.")
    parser.add_argument("--engine_threads", type=int, default=1, help="Number of threads for each engine process.")
    parser.add_argument("--time", type=str, default="b1000", help="Time control settings.")
    parser.add_argument("--hash1", type=str, default="128", help="Hash size for engine 1 (in MB).")
    parser.add_argument("--hash2", type=str, default="128", help="Hash size for engine 2 (in MB).")
    parser.add_argument("--multipv", type=int, default=1, help="Number of candidate lines to request from the engine.")
    parser.add_argument("--book_file", type=str, default="", help="Opening SFEN file under home/book or absolute path.")
    parser.add_argument("--book_moves", type=int, default=24, help="Number of book moves to use.")
    parser.add_argument("--rand_book", action="store_true", help="Shuffle opening book entries.")
    parser.add_argument("--log", action="store_true", help="Enable engine communication logging.")
    parser.add_argument("--param_log_path", type=str, default="", help="Path prefix for engine parameter logs.")
    parser.add_argument("--save_candidates", action="store_true", help="Save MultiPV candidate lists.")
    parser.add_argument("--alt_move_prob", type=float, default=0.0, help="Probability of selecting a close alternative move.")
    parser.add_argument("--alt_move_margin_cp", type=int, default=-1, help="Max centipawn gap for alternative move selection.")
    parser.add_argument("--alt_move_temperature", type=float, default=12.0, help="Sampling temperature for alternative moves.")

    parser.add_argument("--sprt_mode", choices=["pentanomial", "trinomial"], default="pentanomial", help="SPRT model.")
    parser.add_argument("--elo0", type=float, default=0.0, help="Null hypothesis Elo bound.")
    parser.add_argument("--elo1", type=float, default=5.0, help="Alternative hypothesis Elo bound.")
    parser.add_argument("--alpha", type=float, default=0.05, help="Type I error rate.")
    parser.add_argument("--beta", type=float, default=0.05, help="Type II error rate.")
    parser.add_argument("--min_games", type=int, default=20, help="Minimum finished games before allowing trinomial stop.")
    parser.add_argument("--min_pairs", type=int, default=10, help="Minimum finished pairs before allowing pentanomial stop.")
    parser.add_argument("--max_games", type=int, default=2000, help="Hard cap on played games.")
    parser.add_argument("--report_every", type=int, default=20, help="Print progress every N completed games or pairs.")
    return parser


def build_tracker(config):
    if config["sprt_mode"] == "pentanomial":
        return PentanomialSprtTracker(
            elo0=config["elo0"],
            elo1=config["elo1"],
            alpha=config["alpha"],
            beta=config["beta"],
            min_pairs=config["min_pairs"],
            report_every=config["report_every"],
        )
    return TrinomialSprtTracker(
        elo0=config["elo0"],
        elo1=config["elo1"],
        alpha=config["alpha"],
        beta=config["beta"],
        min_games=config["min_games"],
        report_every=config["report_every"],
    )


def main():
    parser = build_parser()
    args = parser.parse_args()
    config = load_config(parser, args)

    required_args = ["home", "engine1", "engine2"]
    for arg in required_args:
        if not config.get(arg):
            print(f"Error: Missing required argument: --{arg}.")
            sys.exit(1)

    tracker = build_tracker(config)
    paired_openings = config["sprt_mode"] == "pentanomial"

    home = config["home"]
    engine1, eval1_dir = resolve_engine_binary_and_eval(home, config["engine1"], config["eval1"])
    engine2, eval2_dir = resolve_engine_binary_and_eval(home, config["engine2"], config["eval2"])
    engines = (engine1, engine2)
    engines_full = engines
    evals_full = (eval1_dir, eval2_dir)
    book_sfens = load_book_sfens(home, config["book_file"], config["book_moves"], config["rand_book"])
    options = create_option(
        engines,
        config["engine_threads"],
        evals_full,
        config["time"],
        [config["hash1"], config["hash2"]],
        config["multipv"],
        config["param_log_path"],
    )
    opt2 = f"T{config['engine_threads']},{config['time']},SPRT"

    print("engine1        :", engine1, "eval =", eval1_dir if eval1_dir else "(engine default)")
    print("engine2        :", engine2, "eval =", eval2_dir if eval2_dir else "(engine default)")
    print("parallel_games :", config["parallel_games"])
    print("max_games      :", config["max_games"])
    print("time           :", config["time"])
    print("book_file      :", config["book_file"] if config["book_file"] else "(initial position)")
    print("sprt_mode      :", config["sprt_mode"])
    print("paired_openings:", paired_openings)
    print("elo0 / elo1    :", config["elo0"], "/", config["elo1"])
    print("alpha / beta   :", config["alpha"], "/", config["beta"])
    print("boundaries     :", tracker.lower, tracker.upper)
    if paired_openings:
        print("sprt model     : pentanomial paired openings, same start position twice with reversed colors")
        print("min_pairs      :", config["min_pairs"])
    else:
        print("sprt model     : trinomial W/D/L with draw-rate MLE under each hypothesis")
        print("min_games      :", config["min_games"])
    sys.stdout.flush()

    def progress_line(game_info):
        result_name = game_info["result"].name
        parts = [
            f"game={game_info['game_index']}",
            f"book={game_info['book_index']}",
            f"moves={game_info['moves']}",
            f"result={result_name}",
            f"term={game_info['termination_reason']}",
        ]
        if paired_openings:
            parts.append(f"pair={game_info['pair_index']}")
            parts.append(f"complete={tracker.completed_pairs}")
        parts.append(f"llr={tracker.llr:.4f}")
        return " ".join(parts)

    def start_line(start_info):
        parts = [
            "start",
            f"thread={start_info['thread_index']}",
            f"book={start_info['book_index']}",
        ]
        if paired_openings:
            parts.append(f"pair={start_info['pair_index']}")
        parts.append(f"stm={'black' if start_info['side_to_move'] == 0 else 'white'}")
        return " ".join(parts)

    def on_start(start_info):
        print(start_line(start_info))
        sys.stdout.flush()

    def move_line(move_info):
        parts = [
            "ply",
            f"thread={move_info['thread_index']}",
            f"book={move_info['book_index']}",
        ]
        if paired_openings:
            parts.append(f"pair={move_info['pair_index']}")
        parts.append(f"ply={move_info['ply']}")
        parts.append(f"side={'black' if move_info['side_to_move'] == 0 else 'white'}")
        parts.append(f"move={move_info['move']}")
        return " ".join(parts)

    def on_move(move_info):
        print(move_line(move_info))
        sys.stdout.flush()

    def on_result(game_info):
        unit_completed = tracker.update(game_info)
        print(progress_line(game_info))
        sys.stdout.flush()
        if unit_completed and tracker.should_report():
            print(tracker.summary_line())
            print(tracker.model_line())
            sys.stdout.flush()

    def should_stop(_win, _lose, _draw):
        return tracker.should_stop()

    w, l, d, _wb, _ww = vs_match(
        engines_full,
        options,
        config["parallel_games"],
        config["max_games"],
        book_sfens,
        config["log"],
        opt2,
        config["book_moves"],
        config["save_candidates"],
        config["alt_move_prob"],
        config["alt_move_margin_cp"],
        config["alt_move_temperature"],
        result_callback=on_result,
        start_callback=on_start,
        move_callback=on_move,
        stop_predicate=should_stop,
        paired_openings=paired_openings,
    )

    print("\nfinal result:")
    print(f"W/D/L={w}/{d}/{l}")
    print(tracker.summary_line())
    print(tracker.model_line())
    if tracker.decision == "accept_h1":
        print(f"decision=accept_h1 engine1 >= elo1 ({config['elo1']})")
    elif tracker.decision == "accept_h0":
        print(f"decision=accept_h0 engine1 <= elo0 ({config['elo0']})")
    else:
        print("decision=inconclusive reached max_games")


if __name__ == "__main__":
    main()
