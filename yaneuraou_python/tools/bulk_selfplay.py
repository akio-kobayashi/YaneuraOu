import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
ENGINE_INVOKER = SCRIPT_DIR / "engine_invoker.py"
SELFPLAY_TO_CSA = SCRIPT_DIR / "selfplay_to_csa.py"


def build_time_control(args):
    if args.time:
        return args.time
    if args.nodes is not None:
        return f"n{args.nodes}"
    if args.depth is not None:
        return f"d{args.depth}"
    return f"b{args.byoyomi_ms}"


def build_invoker_command(args, worker_dir: Path):
    cmd = [
        sys.executable,
        str(ENGINE_INVOKER),
        "--home",
        args.home,
        "--engine1",
        args.engine1,
        "--eval1",
        args.eval1,
        "--engine2",
        args.engine2,
        "--eval2",
        args.eval2,
        "--parallel_games",
        str(args.parallel_games),
        "--engine_threads",
        str(args.engine_threads),
        "--loop",
        str(args.games_per_worker),
        "--time",
        build_time_control(args),
        "--hash1",
        str(args.hash1),
        "--hash2",
        str(args.hash2),
        "--multipv",
        str(args.multipv),
    ]

    if args.book_file:
        cmd += ["--book_file", args.book_file, "--book_moves", str(args.book_moves)]
    if args.rand_book:
        cmd.append("--rand_book")
    if args.log:
        cmd.append("--log")
    if args.save_candidates:
        cmd.append("--save_candidates")
    if args.alt_move_prob > 0.0:
        cmd += ["--alt_move_prob", str(args.alt_move_prob)]
    if args.alt_move_margin_cp >= 0:
        cmd += ["--alt_move_margin_cp", str(args.alt_move_margin_cp)]
    if args.alt_move_temperature != 12.0:
        cmd += ["--alt_move_temperature", str(args.alt_move_temperature)]

    return cmd


def find_single_output(worker_dir: Path, suffix: str):
    files = sorted(worker_dir.glob(f"*{suffix}"))
    if not files:
        raise FileNotFoundError(f"No {suffix} file generated in {worker_dir}")
    if len(files) > 1:
        return files[-1]
    return files[0]


def run_worker(worker_id: int, args, output_root: Path):
    worker_dir = output_root / f"worker_{worker_id:02d}"
    worker_dir.mkdir(parents=True, exist_ok=True)

    cmd = build_invoker_command(args, worker_dir)
    proc = subprocess.run(cmd, cwd=worker_dir, text=True, capture_output=True)

    if proc.returncode != 0:
        raise RuntimeError(
            f"worker {worker_id} failed with exit code {proc.returncode}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )

    sfen_file = find_single_output(worker_dir, ".sfen")
    jsonl_file = worker_dir / (sfen_file.stem + ".jsonl")

    result = {
        "worker_id": worker_id,
        "worker_dir": worker_dir,
        "sfen_file": sfen_file,
        "jsonl_file": jsonl_file if jsonl_file.exists() else None,
        "stdout": proc.stdout,
    }

    if args.convert_csa:
        csa_dir = worker_dir / "csa"
        convert_cmd = [
            sys.executable,
            str(SELFPLAY_TO_CSA),
            str(sfen_file),
            "--output-dir",
            str(csa_dir),
            "--engine1-name",
            args.engine1_name,
            "--engine2-name",
            args.engine2_name,
            "--draw-endgame",
            args.draw_endgame,
        ]
        if jsonl_file.exists():
            convert_cmd += ["--jsonl-file", str(jsonl_file)]

        convert_proc = subprocess.run(convert_cmd, cwd=worker_dir, text=True, capture_output=True)
        if convert_proc.returncode != 0:
            raise RuntimeError(
                f"worker {worker_id} CSA conversion failed with exit code {convert_proc.returncode}\n"
                f"stdout:\n{convert_proc.stdout}\n"
                f"stderr:\n{convert_proc.stderr}"
            )
        result["csa_dir"] = csa_dir
        result["convert_stdout"] = convert_proc.stdout

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Run many engine_invoker self-play jobs and optionally convert the outputs to CSA."
    )
    parser.add_argument("--home", required=True, help="Home directory containing exe/eval/book.")
    parser.add_argument("--engine1", required=True, help="Engine 1 name or path under home/exe.")
    parser.add_argument("--eval1", required=True, help="Engine 1 eval name under home/eval.")
    parser.add_argument("--engine2", required=True, help="Engine 2 name or path under home/exe.")
    parser.add_argument("--eval2", required=True, help="Engine 2 eval name under home/eval.")
    parser.add_argument("--output-root", required=True, help="Root directory for worker outputs.")
    parser.add_argument("--workers", type=int, default=1, help="Number of concurrent engine_invoker jobs.")
    parser.add_argument("--games-per-worker", type=int, default=1000, help="Total games per worker process.")
    parser.add_argument("--parallel-games", type=int, default=1, help="parallel_games passed to engine_invoker.py.")
    parser.add_argument("--engine-threads", type=int, default=1, help="Threads per engine process.")
    parser.add_argument("--hash1", type=int, default=128, help="Hash MB for engine1.")
    parser.add_argument("--hash2", type=int, default=128, help="Hash MB for engine2.")
    parser.add_argument("--multipv", type=int, default=1, help="MultiPV passed to engine_invoker.py.")
    parser.add_argument("--time", default="", help="Raw engine_invoker --time string. Overrides depth/byoyomi/nodes.")
    parser.add_argument("--depth", type=int, default=None, help="Use fixed-depth self-play via dN.")
    parser.add_argument("--byoyomi-ms", type=int, default=100, help="Use byoyomi self-play via bN when --time/--depth/--nodes are omitted.")
    parser.add_argument("--nodes", type=int, default=None, help="Use fixed-node self-play via nN.")
    parser.add_argument("--book-file", default="", help="Opening book SFEN file.")
    parser.add_argument("--book-moves", type=int, default=24, help="Book moves to follow.")
    parser.add_argument("--rand-book", action="store_true", help="Shuffle opening book entries.")
    parser.add_argument("--log", action="store_true", help="Enable engine_invoker logging.")
    parser.add_argument("--save-candidates", action="store_true", help="Keep MultiPV JSONL sidecars.")
    parser.add_argument("--alt-move-prob", type=float, default=0.0, help="Alternative move sampling probability.")
    parser.add_argument("--alt-move-margin-cp", type=int, default=-1, help="Alternative move centipawn margin.")
    parser.add_argument("--alt-move-temperature", type=float, default=12.0, help="Alternative move sampling temperature.")
    parser.add_argument("--convert-csa", action="store_true", help="Convert each worker output into CSA files after self-play.")
    parser.add_argument("--engine1-name", default="engine1", help="CSA fallback engine1 name.")
    parser.add_argument("--engine2-name", default="engine2", help="CSA fallback engine2 name.")
    parser.add_argument("--draw-endgame", default="%SENNICHITE", choices=["%SENNICHITE", "%JISHOGI", "%CHUDAN"])
    args = parser.parse_args()

    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    print(f"output_root      : {output_root}")
    print(f"workers          : {args.workers}")
    print(f"games_per_worker : {args.games_per_worker}")
    print(f"parallel_games   : {args.parallel_games}")
    print(f"engine_threads   : {args.engine_threads}")
    print(f"time_control     : {build_time_control(args)}")
    print(f"convert_csa      : {args.convert_csa}")
    sys.stdout.flush()

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(run_worker, worker_id, args, output_root) for worker_id in range(args.workers)]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(f"worker {result['worker_id']} done: {result['sfen_file'].name}")
            if result.get("csa_dir"):
                print(f"worker {result['worker_id']} csa: {result['csa_dir']}")
            sys.stdout.flush()

    print(f"completed workers: {len(results)}")


if __name__ == "__main__":
    main()
