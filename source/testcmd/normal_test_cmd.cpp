#include "../config.h"

#if defined(ENABLE_TEST_CMD)

// ----------------------------------
//      通常のtestコマンド
// ----------------------------------

#include <fstream>
#include <sstream>
#include "../position.h"
#include "../usi.h"
#include "../thread.h"
#include "../search.h"
#include "../movegen.h"
#include "../learn/learn.h"

#if defined(EVAL_LEARN)
#include "../eval/evaluate_common.h"
#endif

namespace YaneuraOu {
namespace {

	std::string csv_quote(std::string s)
	{
		size_t pos = 0;
		while ((pos = s.find('"', pos)) != std::string::npos)
		{
			s.insert(pos, 1, '"');
			pos += 2;
		}
		return "\"" + s + "\"";
	}

	// "test genmoves" : 指し手生成テストコマンド
	// positionコマンドで設定されている現在の局面から。
	void gen_moves(IEngine& engine, std::istringstream& is)
	{
		auto& pos = engine.get_position();

		// 試行回数
		int64_t loop = 30000000;

		std::string token;
		while (is >> token)
		{
			if (token == "loop")
				is >> loop;
		}

		//	pos.set("l6nl/5+P1gk/2np1S3/p1p4Pp/3P2Sp1/1PPb2P1P/P5GS1/R8/LN4bKL w GR5pnsg 1");

		auto start = now();
		std::cout << "Generate Moves Test : " << std::endl
				  << "  loop = " << loop << std::endl;

		for (int i = 0; i < loop; ++i)
		{
			if (pos.checkers())
				MoveList<EVASIONS> ml(pos);
			else
				MoveList<NON_EVASIONS> ml(pos);
		}

		auto end = now();

		std::cout << "..done." << std::endl;

		// 局面と生成された指し手を出力しておく。
		std::cout << pos;

		if (pos.checkers())
			for (auto m : MoveList<EVASIONS>(pos))
				std::cout << Move(m) << ' ';
		else
			for (auto m : MoveList<NON_EVASIONS>(pos))
				std::cout << Move(m) << ' ';

		std::cout << std::endl << (1000 * loop / (end - start)) << " times per second." << std::endl;
	}

	// "test autoplay" : 自己対局用テストコマンド
	//   ASSERT_LV 5
	//   とかにしてビルドして、このコマンドで連続自己対局をすると探索や指し手生成にバグがあれば
	//	 何らか引っかかることが多いので開発の時に便利。
	//   goコマンド相当の処理で対局させているので通常の探索部であればどの探索部に対しても機能する。

	void auto_play(IEngine& engine, std::istringstream& is)
	{
		auto& options = engine.get_options();
		auto& threads = engine.get_threads();

		Position pos;

		// 対局回数
		uint64_t loop = 50000; // default 5万回

		// 詳細の出力を行うのか(対局棋譜など)
		bool verbose = false;

		// 1手の思考長さ[ms]
		int movetime = 500;    // default 500ms

		// 1手のnodes limit
		s64 nodes_limit = 0;
		
		std::string token;
		while (is >> token)
		{
			if (token == "loop")
				is >> loop;
			else if (token == "verbose")
				verbose = true;
			else if (token == "movetime")
				is >> movetime;
			else if (token == "nodes")
				is >> nodes_limit;
		}

		std::cout   << "Auto Play test : " << std::endl
					<< "  loop     = " << loop << std::endl
					<< "  movetime = " << movetime << std::endl
					<< "  verbose  = " << verbose << std::endl
					<< "  nodes    = " << nodes_limit << std::endl
			;

		const int MAX_PLY = 256; // 256手までテスト

		auto start = now();

		// 読み筋の出力の抑制
		//global_options.silent = true;
		// TODO : あとで調整する。

		//lm.movetime = movetime; // これで時間固定の思考となる。
		// →　毎回同じ指し手になると嫌だから、自分で乱数を加えてばらつかせる

		// ふかうら王の場合、root mate searchが回っていると探索を打ち切らないので、ここで
		// 同じ思考時間になってしまう可能性がある。
		if (options.count("RootMateSearchNodesLimit"))
			options.set_option_if_exists("RootMateSearchNodesLimit",std::to_string(100)); // 100ノードに減らしておく。

		//if (Options.count("DNN_Batch_Size1"))
		//	Options["DNN_Batch_Size1"] = std::to_string(32); // これも減らしておかないとbatchsizeまでで時間がきてしまう。
		// →　このタイミングでやるとmodelのrebuildが起きるのか…。

		// isreadyが呼び出されたものとする。
		engine.isready();

		// 思考時間のランダム化のための乱数
		PRNG prng;

		for (uint64_t i = 0; i < loop ; ++i)
		{
			// 局面を遡るためのStateInfoのlist。
			StateListPtr states(new StateList(1));
			pos.set_hirate(&states->back());

			if (verbose)
				std::cout << "position startpos moves";

			char result = ' ';
			Color mateScoreColor = (Color)-1;

			for (int ply = 0;; ++ply)
			{
				if (!(ply < MAX_PLY))
				{
					result = 'M'; // MaxMoves
					break;
				}

				// 詰まされているかのチェック
				if (pos.is_mated())
				{
					result = (pos.side_to_move() == BLACK) ? 'W' : 'B'; // 勝ったほうのプレイヤーを出力
					break;
				}

				// 千日手のチェック
				auto rep = pos.is_repetition(16);
				if (rep == REPETITION_DRAW)
				{
					result = '.'; // 引き分け
					break;
				}

#if defined(USE_ENTERING_KING_WIN)
				// MateEngineなど宣言勝ちをサポートしていないエンジンもある…。
				
				// 宣言勝ちのチェック
				if (pos.DeclarationWin())
				{
					result = (pos.side_to_move() == BLACK) ? 'b' : 'w'; // 勝ったほうのプレイヤーを小文字で出力
					break;
				}
#endif

				// Stockfish、start_thinking()のなかでstatesの所有権をstd::moveしてしまうので、コピーしておく。
				// ※　start_thinking()でownership transferするの、こういうコードが書きにくくなって良くないと思う。
				StateListPtr states0(new StateList(0));
				*states0.get() = *states.get(); // dequeのcopyを行う。

				// 思考時間、nodes_limit、1～4倍の間でランダム化
				Search::LimitsType lm;
				lm.movetime = movetime * (1000 + prng.rand(3000)) / 1000;
				lm.nodes    = nodes_limit * (1000 + prng.rand(3000)) / 1000;

				threads.start_thinking(options, pos, states0 , lm);
				threads.wait_for_search_finished();
				auto& rootMoves = threads.main_thread()->worker->rootMoves;
				// ⚠ best threadから選出したほうがいいかも知れないが、どれがbest threadか、わからない…。

				ASSERT_LV3(rootMoves.size());

				Move m  = rootMoves.at(0).pv[0]; // 1番目に並び変わっているはず。
				Value v = rootMoves.at(0).score;

				if (mateScoreColor == pos.side_to_move() && v < VALUE_MATE)
				{
					// mate scoreをいったん出したのにそうでなくなった。
					std::cout << std::endl << "[Error!:MateColor]" << std::endl; // error!!
				}

				// MateScoreを出したなら、記録しておく。
				if (v >= VALUE_MATE)
				{
					mateScoreColor = pos.side_to_move();
				}

				// verboseモードならば対局棋譜(のsfen)を画面に出力する。
				if (verbose)
					std::cout << " " << m;

				states->emplace_back();
				pos.do_move(m, states->back());
			}

			if (verbose)
				std::cout << std::endl << "result = " << result << std::endl;
			else
				// 1局ごとに結果を出力(進んでいることがわかるように)
				std::cout << result;
		}
	}

#if defined(EVAL_LEARN) && defined(USE_SFEN_PACKER)
	void eval_bin(IEngine& engine, std::istringstream& is)
	{
		auto& pos = engine.get_position();

		std::string input_path;
		std::string output_path;
		uint64_t count = 0;

		std::string token;
		while (is >> token)
		{
			if (token == "input")
				is >> input_path;
			else if (token == "output")
				is >> output_path;
			else if (token == "count")
				is >> count;
		}

		if (input_path.empty() || output_path.empty())
		{
			std::cout << "usage: test evalbin input <psv.bin> output <out.csv> [count N]" << std::endl;
			return;
		}

		std::ifstream ifs(input_path, std::ios::binary);
		if (!ifs)
		{
			std::cout << "Error! : can't open input file : " << input_path << std::endl;
			return;
		}

		std::ofstream ofs(output_path);
		if (!ofs)
		{
			std::cout << "Error! : can't open output file : " << output_path << std::endl;
			return;
		}

		ofs << "index,sfen,orig_score,engine_score,score_diff,abs_score_diff,ply,result\n";

		Learner::PackedSfenValue psv;
		uint64_t index = 0;
		uint64_t written = 0;

		while ((!count || index < count) && ifs.read(reinterpret_cast<char*>(&psv), sizeof(psv)))
		{
			StateInfo si;
			auto result = pos.set_from_packed_sfen(psv.sfen, &si, false, psv.gamePly);
			if (result.is_not_ok())
			{
				std::cout << "Error! : failed to decode record " << index
						  << " : " << result.to_string() << std::endl;
				return;
			}

			const auto sfen = pos.sfen();
			const auto engine_score = static_cast<int>(Eval::evaluate(pos));
			const auto orig_score = static_cast<int>(psv.score);
			const auto score_diff = engine_score - orig_score;
			const auto abs_score_diff = score_diff >= 0 ? score_diff : -score_diff;
			const auto ply = static_cast<unsigned>(psv.gamePly);
			const auto game_result = static_cast<int>(psv.game_result);

			ofs << index
				<< "," << csv_quote(sfen)
				<< "," << orig_score
				<< "," << engine_score
				<< "," << score_diff
				<< "," << abs_score_diff
				<< "," << ply
				<< "," << game_result
				<< "\n";
			++index;
			++written;
		}

		if (!ifs.eof() && ifs.fail())
		{
			std::cout << "Error! : failed while reading input file : " << input_path << std::endl;
			return;
		}

		std::cout << "evalbin done : input = " << input_path
				  << " , output = " << output_path
				  << " , rows = " << written << std::endl;
	}
#else
	void eval_bin([[maybe_unused]] IEngine& engine, [[maybe_unused]] std::istringstream& is)
	{
		std::cout << "Error! : test evalbin requires EVAL_LEARN and USE_SFEN_PACKER." << std::endl;
	}
#endif
} // namespace

// ----------------------------------
//      "test" command Decorator
// ----------------------------------

namespace Test
{
	// 通常のテストコマンド。コマンドを処理した時 trueが返る。
	bool normal_test_cmd(IEngine& engine , std::istringstream& is, const std::string& token)
	{
		if (token == "genmoves")         gen_moves(engine, is);       // 現在の局面に対して指し手生成のテストを行う。
		else if (token == "autoplay")    auto_play(engine, is);       // 連続自己対局を行う。
		else if (token == "evalbin")     eval_bin(engine, is);        // PackedSfenValue .bin を評価して CSV に出力する。
		else return false;									          // どのコマンドも処理することがなかった
			
		// いずれかのコマンドを処理した。
		return true;
	}

} // namespace Test

} // namespace YaneuraOu

#endif // defined(ENABLE_TEST_CMD)
