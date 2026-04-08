#!/usr/bin/env python3

import argparse
import json
import math
import os
import queue
import random
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import List, Optional

try:
    import yaml
except ImportError:
    yaml = None

try:
    from engine_invoker import (
        load_book_positions,
        parse_usi_score_info,
        resolve_engine_binary_and_eval,
    )
except ImportError:
    from .engine_invoker import (
        load_book_positions,
        parse_usi_score_info,
        resolve_engine_binary_and_eval,
    )


@dataclass
class AnalysisResult:
    bestmove: Optional[str]
    score_type: Optional[str]
    score: Optional[int]
    normalized_score: Optional[int]
    pv: List[str]
    raw_info: Optional[str]


def load_config(parser, args):
    config = vars(args).copy()
    if not args.config:
        return config

    if yaml is None:
        raise RuntimeError("PyYAML is required when using --config.")

    with open(args.config, "r", encoding="utf-8") as f:
        file_config = yaml.safe_load(f) or {}

    for key, value in file_config.items():
        if key in config and config[key] == parser.get_default(key):
            config[key] = value
    return config


class UsiEngine:
    def __init__(self, binary_path, eval_dir, threads, hash_size, multipv, extra_options, startup_timeout, think_timeout):
        self.binary_path = binary_path
        self.eval_dir = eval_dir
        self.threads = threads
        self.hash_size = hash_size
        self.multipv = multipv
        self.extra_options = extra_options or []
        self.startup_timeout = startup_timeout
        self.think_timeout = think_timeout
        self.proc = None
        self.output_queue = queue.Queue()
        self.reader_thread = None

    def start(self):
        working_dir = os.path.dirname(self.binary_path) or None
        self.proc = subprocess.Popen(
            [self.binary_path],
            cwd=working_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            text=True,
            bufsize=1,
        )
        self.reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.reader_thread.start()
        self.send("usi")
        self._read_until("usiok", self.startup_timeout)

        self.send(f"setoption name Threads value {self.threads}")
        self.send(f"setoption name USI_Hash value {self.hash_size}")
        self.send("setoption name BookFile value no_book")
        self.send(f"setoption name MultiPV value {self.multipv}")
        if self.eval_dir:
            self.send(f"setoption name EvalDir value {self.eval_dir}")
        for option_line in self.extra_options:
            self.send(option_line)

        self.send("isready")
        self._read_until("readyok", self.startup_timeout)
        self.send("usinewgame")

    def close(self):
        if not self.proc:
            return
        try:
            self.send("quit")
        except Exception:
            pass
        if self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=3)
            except Exception:
                self.proc.kill()
        self.proc = None
        self.reader_thread = None

    def send(self, line):
        if not self.proc or not self.proc.stdin:
            raise RuntimeError("Engine process is not running.")
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()

    def _reader_loop(self):
        while self.proc and self.proc.stdout:
            line = self.proc.stdout.readline()
            if not line:
                break
            self.output_queue.put(line.rstrip("\n"))

    def _readline(self, timeout_seconds):
        deadline = time.time() + timeout_seconds
        while True:
            if self.proc.poll() is not None:
                raise RuntimeError(f"Engine terminated unexpectedly: {self.binary_path}")
            try:
                return self.output_queue.get(timeout=0.1)
            except queue.Empty:
                pass
            if time.time() >= deadline:
                raise TimeoutError(f"Timed out while waiting for engine output: {self.binary_path}")

    def _read_until(self, token, timeout_seconds):
        while True:
            line = self._readline(timeout_seconds)
            if token in line:
                return line

    def analyze(self, position_command, go_command):
        self.send(position_command)
        self.send(go_command)

        latest = None
        bestmove = None
        while True:
            line = self._readline(self.think_timeout)
            if line.startswith("info ") and " score " in line:
                parsed = parse_usi_score_info(line)
                if parsed and parsed["multipv"] == 1:
                    latest = parsed
            elif line.startswith("bestmove"):
                parts = line.split()
                if len(parts) >= 2:
                    bestmove = parts[1]
                break

        normalized_score = None
        if latest and latest["normalized_score"] not in ("", "?"):
            normalized_score = int(latest["normalized_score"])

        return AnalysisResult(
            bestmove=bestmove,
            score_type=latest["score_type"] if latest else None,
            score=latest["score"] if latest else None,
            normalized_score=normalized_score,
            pv=latest["pv"] if latest else [],
            raw_info=" ".join(
                [
                    latest["score_type"],
                    str(latest["score"]),
                    "pv",
                    *latest["pv"],
                ]
            ) if latest else None,
        )


def parse_setoption_values(values):
    options = []
    for value in values:
        if not value:
            continue
        if value.startswith("setoption "):
            options.append(value)
        else:
            options.append(f"setoption name {value}")
    return options


def safe_mean(values):
    if not values:
        return float("nan")
    return sum(values) / len(values)


def format_score(score_type, score, normalized_score):
    if score_type is None or score is None:
        return "-"
    if score_type == "cp":
        return f"cp {score} ({normalized_score})"
    return f"{score_type} {score} ({normalized_score})"


def select_positions(positions, skip, limit, sample_seed):
    if skip:
        positions = positions[skip:]
    if limit > 0 and len(positions) > limit:
        rng = random.Random(sample_seed)
        positions = rng.sample(positions, limit)
    return positions


def main():
    parser = argparse.ArgumentParser(
        description="Compare per-position evaluation scores between two USI engines.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--config", type=str, default="", help="Optional YAML config file.")
    parser.add_argument("--home", type=str, required=False, default=".", help="Base directory used to resolve relative engine and position paths.")
    parser.add_argument("--engine1", type=str, required=False, default="", help="Path or name of engine 1.")
    parser.add_argument("--eval1", type=str, default="", help="Optional evaluation directory for engine 1.")
    parser.add_argument("--engine2", type=str, required=False, default="", help="Path or name of engine 2.")
    parser.add_argument("--eval2", type=str, default="", help="Optional evaluation directory for engine 2.")
    parser.add_argument("--positions", type=str, required=False, default="", help="SFEN/startpos file to evaluate, one position per line.")
    parser.add_argument("--book_moves", type=int, default=24, help="Number of moves to keep when reading startpos records.")
    parser.add_argument("--go", type=str, default="go depth 8", help="USI go command used for each position.")
    parser.add_argument("--engine_threads", type=int, default=1, help="Threads value sent to each engine.")
    parser.add_argument("--hash1", type=int, default=128, help="USI_Hash for engine 1.")
    parser.add_argument("--hash2", type=int, default=128, help="USI_Hash for engine 2.")
    parser.add_argument("--multipv", type=int, default=1, help="MultiPV value sent to each engine.")
    parser.add_argument("--setoption1", action="append", default=[], help="Additional setoption payload for engine 1. Example: 'MinimumThinkingTime value 0'")
    parser.add_argument("--setoption2", action="append", default=[], help="Additional setoption payload for engine 2. Example: 'MinimumThinkingTime value 0'")
    parser.add_argument("--limit", type=int, default=0, help="Maximum number of positions to evaluate after random sampling. 0 means all.")
    parser.add_argument("--skip", type=int, default=0, help="Number of initial positions to skip.")
    parser.add_argument("--sample_seed", type=int, default=42, help="Random seed used when sampling positions for --limit.")
    parser.add_argument("--output", type=str, default="", help="Optional JSONL output path.")
    parser.add_argument("--startup_timeout", type=float, default=30.0, help="Timeout in seconds for USI startup and readyok.")
    parser.add_argument("--think_timeout", type=float, default=120.0, help="Timeout in seconds for each position analysis.")
    args = parser.parse_args()

    config = load_config(parser, args)
    required_args = ["engine1", "engine2", "positions"]
    for key in required_args:
        if not config.get(key):
            print(f"Error: Missing required argument --{key}", file=sys.stderr)
            sys.exit(1)

    home = os.path.abspath(config["home"])
    binary1, eval_dir1 = resolve_engine_binary_and_eval(home, config["engine1"], config["eval1"])
    binary2, eval_dir2 = resolve_engine_binary_and_eval(home, config["engine2"], config["eval2"])
    positions = load_book_positions(home, config["positions"], config["book_moves"])
    positions = select_positions(
        positions,
        config["skip"],
        config["limit"],
        config["sample_seed"],
    )
    if not positions:
        print("Error: No positions to evaluate after applying skip/limit.", file=sys.stderr)
        sys.exit(1)

    engine1 = UsiEngine(
        binary_path=binary1,
        eval_dir=eval_dir1,
        threads=config["engine_threads"],
        hash_size=config["hash1"],
        multipv=config["multipv"],
        extra_options=parse_setoption_values(config["setoption1"]),
        startup_timeout=config["startup_timeout"],
        think_timeout=config["think_timeout"],
    )
    engine2 = UsiEngine(
        binary_path=binary2,
        eval_dir=eval_dir2,
        threads=config["engine_threads"],
        hash_size=config["hash2"],
        multipv=config["multipv"],
        extra_options=parse_setoption_values(config["setoption2"]),
        startup_timeout=config["startup_timeout"],
        think_timeout=config["think_timeout"],
    )

    deltas = []
    abs_deltas = []
    bestmove_matches = 0
    output_file = None

    try:
        engine1.start()
        engine2.start()

        if config["output"]:
            output_path = os.path.abspath(config["output"])
            output_file = open(output_path, "w", encoding="utf-8")

        for index, position in enumerate(positions, start=1):
            result1 = engine1.analyze(position["position_command"], config["go"])
            result2 = engine2.analyze(position["position_command"], config["go"])

            delta = None
            if result1.normalized_score is not None and result2.normalized_score is not None:
                delta = result1.normalized_score - result2.normalized_score
                deltas.append(delta)
                abs_deltas.append(abs(delta))

            bestmove_match = result1.bestmove == result2.bestmove and result1.bestmove is not None
            if bestmove_match:
                bestmove_matches += 1

            record = {
                "index": index,
                "record_line": position["record_line"],
                "engine1": {
                    "bestmove": result1.bestmove,
                    "score_type": result1.score_type,
                    "score": result1.score,
                    "normalized_score": result1.normalized_score,
                    "pv": result1.pv,
                },
                "engine2": {
                    "bestmove": result2.bestmove,
                    "score_type": result2.score_type,
                    "score": result2.score,
                    "normalized_score": result2.normalized_score,
                    "pv": result2.pv,
                },
                "delta": delta,
                "bestmove_match": bestmove_match,
            }

            if output_file:
                output_file.write(json.dumps(record, ensure_ascii=False) + "\n")

            delta_text = str(delta) if delta is not None else "-"
            print(
                f"[{index}/{len(positions)}] "
                f"delta={delta_text:>6} "
                f"bm_match={'Y' if bestmove_match else 'N'} "
                f"e1={format_score(result1.score_type, result1.score, result1.normalized_score)} "
                f"e2={format_score(result2.score_type, result2.score, result2.normalized_score)}"
            )

    finally:
        if output_file:
            output_file.close()
        engine1.close()
        engine2.close()

    comparable = len(deltas)
    print()
    print("Summary")
    print(f"positions          : {len(positions)}")
    print(f"sample_seed        : {config['sample_seed']}")
    print(f"comparable_scores  : {comparable}")
    print(f"avg_delta          : {safe_mean(deltas):.2f}" if comparable else "avg_delta          : -")
    print(f"avg_abs_delta      : {safe_mean(abs_deltas):.2f}" if comparable else "avg_abs_delta      : -")
    print(f"rms_delta          : {math.sqrt(safe_mean([x * x for x in deltas])):.2f}" if comparable else "rms_delta          : -")
    print(f"bestmove_match_rate: {bestmove_matches / len(positions):.4f}")
    if config["output"]:
        print(f"output             : {os.path.abspath(config['output'])}")


if __name__ == "__main__":
    main()
