import argparse
import json
from pathlib import Path


def load_cshogi():
    try:
        import cshogi
        from cshogi import CSA
        return cshogi, CSA
    except Exception as exc:
        raise SystemExit(
            "cshogi is required to convert self-play output to CSA. "
            "Install it first, for example: "
            "pip install 'git+https://github.com/akio-kobayashi/cshogi.git'"
        ) from exc


def parse_sfen_records(path: Path):
    lines = [line.rstrip("\n") for line in path.read_text(encoding="utf-8").splitlines()]
    if len(lines) % 2 != 0:
        raise ValueError(f"{path} must contain move/eval pairs on alternating lines.")

    records = []
    for i in range(0, len(lines), 2):
        move_line = lines[i].strip()
        eval_line = lines[i + 1].strip()

        if not move_line.startswith("startpos"):
            raise ValueError(f"Unsupported move line: {move_line}")

        parts = move_line.split()
        if parts[:2] == ["startpos", "moves"]:
            moves = parts[2:]
        elif parts == ["startpos"]:
            moves = []
        else:
            raise ValueError(f"Unsupported move line: {move_line}")

        records.append({
            "moves": moves,
            "eval_values": eval_line.split() if eval_line else [],
        })
    return records


def parse_jsonl_records(path: Path | None):
    if path is None:
        return None

    records = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def infer_colors(index: int, record: dict, engine1_name: str, engine2_name: str):
    black_engine = record.get("black_engine")
    white_engine = record.get("white_engine")

    if black_engine not in (1, 2) or white_engine not in (1, 2):
        black_engine = 1 if index % 2 == 0 else 2
        white_engine = 2 if black_engine == 1 else 1

    black_name = record.get("black_engine_name") or (engine1_name if black_engine == 1 else engine2_name)
    white_name = record.get("white_engine_name") or (engine1_name if white_engine == 1 else engine2_name)
    return black_name, white_name


def format_move_comment(eval_value, candidates, selected_move):
    score = eval_value if eval_value not in (None, "") else "0"
    parts = [score]

    if selected_move:
        source = selected_move.get("source")
        selected_multipv = selected_move.get("selected_multipv")
        if source and source != "bestmove":
            parts.append(f"sel={source}")
        if selected_multipv and selected_multipv != 1:
            parts.append(f"sel_multipv={selected_multipv}")

    if candidates:
        encoded = []
        for candidate in candidates:
            pv = candidate.get("pv") or []
            pv_head = pv[0] if pv else "none"
            encoded.append(
                f"{candidate.get('multipv', '?')}:{pv_head}:{candidate.get('score_type', '?')}={candidate.get('score', '?')}"
            )
        if encoded:
            parts.append("cand=" + "|".join(encoded))

    return "** " + " ".join(parts)


def result_to_endgame(result: str, draw_endgame: str):
    if result in ("P1_WIN", "P2_WIN"):
        return "%TORYO"
    if result == "DRAW":
        return draw_endgame
    return "%CHUDAN"


def convert_game(index: int, base_record: dict, json_record: dict, output_dir: Path, draw_endgame: str, engine1_name: str, engine2_name: str):
    cshogi, CSA = load_cshogi()
    board = cshogi.Board()

    moves = base_record["moves"]
    eval_values = json_record.get("eval_values", base_record.get("eval_values", []))
    candidates = json_record.get("candidates", [])
    selected_moves = json_record.get("selected_moves", [])
    result = json_record.get("result", "DRAW")
    termination_reason = json_record.get("termination_reason", "")

    if eval_values and len(eval_values) != len(moves):
        raise ValueError(
            f"Game {index + 1}: move count ({len(moves)}) and eval count ({len(eval_values)}) do not match."
        )
    if candidates and len(candidates) != len(moves):
        raise ValueError(
            f"Game {index + 1}: move count ({len(moves)}) and candidate count ({len(candidates)}) do not match."
        )
    if selected_moves and len(selected_moves) != len(moves):
        raise ValueError(
            f"Game {index + 1}: move count ({len(moves)}) and selected move count ({len(selected_moves)}) do not match."
        )

    black_name, white_name = infer_colors(index, json_record, engine1_name, engine2_name)
    exporter = CSA.Exporter(str(output_dir / f"game_{index + 1:06d}.csa"), encoding="utf-8")

    header_comment = "generated_from:selfplay_to_csa"
    if termination_reason:
        header_comment += f" termination_reason:{termination_reason}"
    exporter.info(names=[black_name, white_name], comment=header_comment)

    for ply, usi_move in enumerate(moves):
        move = board.move_from_usi(usi_move)
        exporter.move(
            move,
            comment=format_move_comment(
                eval_values[ply] if eval_values else None,
                candidates[ply] if candidates else None,
                selected_moves[ply] if selected_moves else None,
            ),
        )
        board.push(move)

    exporter.endgame(result_to_endgame(result, draw_endgame))
    exporter.close()


def main():
    parser = argparse.ArgumentParser(
        description="Convert engine_invoker .sfen/.jsonl self-play output into per-game CSA files."
    )
    parser.add_argument("sfen_file", help="Path to the .sfen file generated by engine_invoker.py.")
    parser.add_argument("--jsonl-file", help="Optional JSONL sidecar generated with --save_candidates.")
    parser.add_argument("--output-dir", required=True, help="Directory where per-game .csa files will be written.")
    parser.add_argument("--engine1-name", default="engine1", help="Fallback display name for engine 1.")
    parser.add_argument("--engine2-name", default="engine2", help="Fallback display name for engine 2.")
    parser.add_argument(
        "--draw-endgame",
        default="%SENNICHITE",
        choices=["%SENNICHITE", "%JISHOGI", "%CHUDAN"],
        help="CSA endgame marker to use when the self-play record result is DRAW.",
    )
    args = parser.parse_args()

    sfen_path = Path(args.sfen_file)
    jsonl_path = Path(args.jsonl_file) if args.jsonl_file else None
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    sfen_records = parse_sfen_records(sfen_path)
    jsonl_records = parse_jsonl_records(jsonl_path)
    if jsonl_records is not None and len(jsonl_records) != len(sfen_records):
        raise SystemExit(
            f"Record count mismatch: {sfen_path} has {len(sfen_records)} records but "
            f"{jsonl_path} has {len(jsonl_records)} records."
        )

    for index, base_record in enumerate(sfen_records):
        json_record = jsonl_records[index] if jsonl_records is not None else {}
        convert_game(
            index,
            base_record,
            json_record,
            output_dir,
            args.draw_endgame,
            args.engine1_name,
            args.engine2_name,
        )

    print(f"Wrote {len(sfen_records)} CSA files to {output_dir}")


if __name__ == "__main__":
    main()
