import argparse
import datetime
import math
import os.path
import random
import subprocess
import sys
import time
import threading
import queue
try:
    import yaml
except ImportError:
    print("PyYAML is not installed. Please install it with 'pip install pyyaml'")
    sys.exit(1)

from enum import Enum, auto

# ======================================================================
# 定数定義
# ======================================================================
class EngineState(Enum):
    INIT = auto()
    WAIT_FOR_READYOK = auto()
    START = auto()
    WAIT_FOR_BESTMOVE = auto()
    WAIT_FOR_ANOTHER_PLAYER = auto()

class GameResult(Enum):
    P1_WIN = auto()
    P2_WIN = auto()
    DRAW = auto()
    NO_RESULT = auto()

MAX_MOVES = 256

# ======================================================================
# グローバル変数
# ======================================================================
win = lose = draw = 0
win_black = lose_black = 0

# レーティングの出力
def output_rating(win,draw,lose,win_black,win_white,opt2):
	total = win + lose
	if total != 0 :
		# 普通の勝率
		win_rate = win / total
		# 先手番/後手番のときの勝率内訳
		win_rate_black = win_black / total
		win_rate_white = win_white / total
	else:
		win_rate = 0
		win_rate_black = 0
		win_rate_white = 0

	if win_rate == 0 or win_rate == 1:
		rating = ""
	else:
		rating = " R" + str(round(-400*math.log(1/win_rate-1,10),2))

	print(opt2 + "," + str(win) + " - " + str(draw) + " - " + str(lose) + \
		"(" + str(round(win_rate*100,2)) + "%" + rating + ")" + \
		" win black : white = " + \
		str(round(win_rate_black*100,2)) + "% : " + \
		str(round(win_rate_white*100,2)) + "%")
	sys.stdout.flush()


# 思考エンジンに対するオプションを生成する。
def create_option(engines,engine_threads,evals,times,hashes,PARAMETERS_LOG_FILE_PATH):

	# 思考エンジンに対するコマンド列を保存する。
	options = []
	# 対局時間設定を保存する。
	options2 = []

	# 時間は.で連結できる。
	times = times.split(".")
	if len(times)==1:
		times.append(times[0])

	for i in range(2):

		rtime = 0
		byoyomi = 0
		inc_time = 0
		total_time = 0
		depth_time = 0

		nodes_time = False

		for b in times[i].split("/"):

			c = b[0]
			# 大文字で指定されていたらnodes_timeモード。
			if c != c.lower():
				c = c.lower()
				nodes_time = True

			t = int(b[1:])
			if c == "r":
				rtime = t
			elif c == "b":
				byoyomi = t
			elif c == "i":
				inc_time = t
			elif c == "t":
				total_time = t
			elif c == "d":
				depth_time = t

		option = []
		if ("Yane" in engines[i]):
			if rtime:
				option.append("go rtime " + str(rtime))
			elif inc_time:
				option.append("go btime REST_TIME wtime REST_TIME inc " + str(inc_time))
			elif depth_time:
				option.append("go depth " + str(depth_time))
			else:
				option.append("go btime REST_TIME wtime REST_TIME byoyomi " + str(byoyomi))

			option.append("setoption name Threads value " + str(engine_threads))
			option.append("setoption name EvalDir value " + evals[i])
			option.append("setoption name Hash value " + str(hashes[i]))
			option.append("setoption name BookFile value no_book")
			option.append("setoption name MinimumThinkingTime value 1000")
			option.append("setoption name NetworkDelay value 0")
			option.append("setoption name NetworkDelay2 value 0")

#			option.append("setoption name EvalShare value false")
			option.append("setoption name EvalShare value true")
#			if i==0:
#				option.append("setoption name EvalShare value false")
#			else:
#				option.append("setoption name EvalShare value true")
			if nodes_time:
				option.append("setoption name nodestime value 600")
			if PARAMETERS_LOG_FILE_PATH :
				option.append("setoption name PARAMETERS_LOG_FILE_PATH value " + PARAMETERS_LOG_FILE_PATH + "_%%THREAD_NUMBER%%.log")
				# →　仕方ないので%THREAD_NUMBER%のところはのちほど置換する。
		else:
			# ここで対応しているengine一覧
			#  ・技巧(20160606)
			#  ・Silent Majority(V1.1.0)
			if rtime:
				option.append("go rtime " + str(rtime))
				print("Error! " + engines[i] + " doesn't support rtime ")
			elif inc_time:
				option.append("go btime REST_TIME wtime REST_TIME inc " + str(inc_time))
			elif depth_time:
				option.append("go depth " + str(depth_time))
			else:
				option.append("go btime REST_TIME wtime REST_TIME byoyomi " + str(byoyomi))

			option.append("setoption name Threads value " + str(engine_threads))
			option.append("setoption name USI_Hash value " + str(hashes[i]))
#			option.append("setoption name EvalDir value " + evals[i])

			if "SILENT_MAJORITY" in engines[i]:
				option.append("setoption name Byoyomi_Margin value 0")
				option.append("setoption name Minimum_Thinking_Time value 0")
				option.append("setoption name Eval_Dir value " + evals[i])

		options.append(option)

		options2.append([total_time,inc_time,byoyomi,rtime,depth_time])

	options.append(options2[0])
	options.append(options2[1])

	return options

# エンジンからの出力を読み取り、メッセージキューに入れるスレッドのターゲット関数
def read_engine_output(engine_idx, proc, message_queue):
    while True:
        line = proc.stdout.readline()
        if line:
            message_queue.put({'type': 'output', 'engine_idx': engine_idx, 'line': line})
        else:
            # エンジンが終了した場合
            retcode = proc.poll()
            if retcode is not None:
                message_queue.put({'type': 'terminated', 'engine_idx': engine_idx, 'retcode': retcode})
                break
        time.sleep(0.001) # 短いスリープでビジーループを避ける


# engine1とengine2とを対戦させる
#  threads    : この数だけ並列対局
#  cpu        : 実行するプロセッサグループの数
#               1つのプロセッサには threads/cpu だけスレッドを割り当てる
#  book_sfens : 定跡
#  opt2       : 勝敗の表示の先頭にT2,b2000 のように対局条件を文字列化して突っ込む用。
#  book_moves : 定跡の手数
def vs_match(engines_full,options,threads,loop,book_sfens,fileLogging,opt2,book_moves,kifu_format="sfen"):

	win = lose = draw = 0
	win_black = win_white = 0

	# home + "book/records1.sfen

	# 定跡ファイルは1行目から順番に読む。次に読むべき行番号
	# 定跡ファイルは重複除去された、互角の局面集であるものとする。
	sfen_no = 0

	# --- 状態変数の初期化 ---
	# 対局ごとの状態
	sfens = [""] * threads
	eval_values = [""] * threads
	moves = [0] * threads
	turns = [0] * threads

	# エンジンプロセスごとの状態
	procs = [None] * (threads * 2)
	engine_reader_threads = [None] * (threads * 2)
	message_queue = queue.Queue()
	states = [EngineState.INIT] * (threads * 2)
	initial_waits = [True] * (threads * 2)
	rest_times = [0] * (threads * 2)
	go_times = [0] * (threads * 2)
	nodes_str = [""] * (threads * 2)
	nodes = [0] * (threads * 2)
	eval_value_from_thread = [""] * (threads * 2)
	term_procs = [False] * (threads * 2)

	# --- エンジン起動とリーダー・スレッド開始 ---
	for i in range(threads * 2):
		# working directoryを実行ファイルのあるフォルダ直下としてやる。
		# 最後のdirectory separatorを探す
		engine_path = engines_full[i % 2]
		pos = max(engine_path.rfind('\\') , engine_path.rfind('/'))
		if pos <= 0:
			working_dir = ""
		else:
			working_dir = engine_path[:pos]

		# コマンドを構築。Windowsの.exeをWSL2から起動する場合、そのままパスを指定すればよい。
		# shell=False (デフォルト) を利用するため、コマンドはリスト形式で渡す。
		# stdout/stdin/stderrはパイプにして、テキストモードで通信するためencodingとtext=Trueを指定。
		try:
			proc = subprocess.Popen(
				[engines_full[i % 2]],
				cwd=working_dir,
				stdin=subprocess.PIPE,
				stdout=subprocess.PIPE,
				stderr=subprocess.PIPE,
				encoding='utf-8', # テキストモードで通信
				text=True,        # Python 3.7+ では encoding='utf-8' と text=True はほぼ同義
				bufsize=1         # 行バッファリング
			)
			procs[i] = proc

			# エンジンからの出力を読み取るスレッドを起動
			engine_reader_threads[i] = threading.Thread(target=read_engine_output, args=(i, proc, message_queue))
			engine_reader_threads[i].daemon = True # メインスレッド終了時に一緒に終了
			engine_reader_threads[i].start()

		except FileNotFoundError:
			print(f"Error: Engine not found at {engines_full[i % 2]}. Please check the path.")
			sys.exit(1)
		except Exception as e:
			print(f"Error launching engine {engines_full[i % 2]}: {e}")
			sys.exit(1)


	# これをTrueにするとコンソールに思考エンジンとのやりとりを出力する。
#	Logging = True
	Logging = False

	# これをTrueにするとログファイルに思考エンジンとのやりとりを出力する。
#	FileLogging = True
	FileLogging = fileLogging

	# これをTrueにすると棋譜をファイルに書き出すようになる。
	KifOutput = True

	# 現在時刻。ログファイルと棋譜ファイルを同じ名前にしておく。
	now = datetime.datetime.today()
	if FileLogging:
		log_file = open("script_log"+now.strftime("%Y%m%d%H%M%S")+".txt","w")

	kif_file = None
	csa_exporters = None
	kif_base = now.strftime("%Y%m%d%H%M%S") + opt2.replace(",","_")
	if KifOutput:
		if kifu_format == "csa":
			try:
				from cshogi import CSA
			except ImportError:
				print("cshogi is not installed. Please install it with 'pip install cshogi'")
				sys.exit(1)

			csa_exporters = []
			for game_idx in range(threads):
				csa_path = f"{kif_base}_g{game_idx:03d}.csa"
				csa_exporters.append(CSA.Exporter(csa_path, append=False))
		else:
			kif_file = open(kif_base + ".sfen","w")

	def send_cmd(i,s):
		p = procs[i]
		if Logging:
			print("[" + str(i) + "]<" + s)
		if FileLogging:
			log_file.write( "[" + str(i) + "]<" + s + "\n")
		p.stdin.write(s+"\n")

	def isready_cmd(i):
		p = procs[i]
		send_cmd(i,"isready")
		states[i] = EngineState.WAIT_FOR_READYOK
		# rest_time = total_time
		rest_times[i] = options[2 + (i & 1)][0]

	def go_cmd(i):
		p = procs[i]
		# USI "position"
		s = "position startpos"
		if sfens[i//2] != "":
			s += " moves " + sfens[i//2]
		send_cmd(i,s)

		# USI "go"
		cmd = options[i & 1][0]
		cmd = cmd.replace("REST_TIME",str(rest_times[i]))
		send_cmd(i,cmd)

		# changes state
		states[i]   = EngineState.WAIT_FOR_BESTMOVE
		states[i^1] = EngineState.WAIT_FOR_ANOTHER_PLAYER

		go_times[i] = time.time()

	def usinewgame_cmd(i,sfen_no):
		p = procs[i]
		send_cmd(i,"usinewgame")
		sfens[i//2] = book_sfens[sfen_no]
		moves[i//2] = 0
		# 定跡の評価値はよくわからんので0にしとくしかない。
		eval_values[i//2] = "0 "*book_moves

	# ゲームオーバーのハンドラ
	# i : engine index
	# g : GameResult
	def gameover_cmd(i,g):
		p = procs[i]
		
		# エンジンに送る結果文字列を決定
		# g (GameResult) は P1(engine 0)から見た結果
		if g == GameResult.DRAW:
			result = "draw"
		elif (g == GameResult.P1_WIN and i % 2 == 0) or \
		     (g == GameResult.P2_WIN and i % 2 == 1):
			result = "win"
		else:
			result = "lose"

		send_cmd(i,"gameover " + result)
		states[i] = EngineState.INIT

	def outlog(i,line):
		if Logging:
			print("[" + str(i) + "]>" + line.strip())
		if FileLogging:
			log_file.write("[" + str(i) + "]>" + line.strip() + "\n")

	def outstd(i,line):
		print("["+str(i)+"]>" + line.strip())
		sys.stdout.flush()

	def write_csa_game(game_idx, game_result):
		exporter = csa_exporters[game_idx]
		engine_names = [
			os.path.basename(engines_full[0]),
			os.path.basename(engines_full[1]),
		]
		exporter.info(names=engine_names, version="V2")

		try:
			import cshogi
			board = cshogi.Board()
			evals = eval_values[game_idx].split()
			usi_moves = sfens[game_idx].split()
			for ply, usi_move in enumerate(usi_moves):
				move = board.push_usi(usi_move)
				comment = None
				if ply < len(evals):
					comment = f"cp {evals[ply]}"
				exporter.move(move, comment=comment)
		except Exception as e:
			outlog(game_idx * 2, f"CSA write error: {e}")
			exporter.endgame("%CHUDAN")
			return

		if game_result == GameResult.DRAW:
			exporter.endgame("%SENNICHITE")
		else:
			exporter.endgame("%TORYO")


	# set options for each engine
	for i in range(len(states)):
		for j in range(len(options[i % 2])):
			if j != 0 :
				opt = options[i % 2][j]

				# 置換対象文字列が含まれているなら置換しておく。
				opt = opt.replace("%%THREAD_NUMBER%%",str(i))
				send_cmd(i,opt)

	# メインループ: メッセージキューからイベントを処理する
	# このループで、全ての対局の状態が管理される。
	while True:
		update = False # 何か状態が更新されたかどうかのフラグ
		
		try:
			message = message_queue.get(timeout=0.01) # 短いタイムアウトでメッセージを待つ
			engine_idx = message['engine_idx']
			proc = procs[engine_idx]
			
			if message['type'] == 'output':
				line = message['line']
				outlog(engine_idx, line) # ログ出力

				# "Error"か"Display"の文字列が含まれていればそれをそのまま出力する。
				if ("Error" in line) or ("Display" in line) or ("Failed" in line):
					outstd(engine_idx,line)

				# node数計測用
				if "nodes" in line :
					nodes_str[engine_idx] = line
				# 評価値計測用
				if "score" in line :
					eval_value_from_thread[engine_idx] = line

				gameover = GameResult.NO_RESULT # ゲームオーバーフラグ

				if ("readyok" in line) and (states[engine_idx] == EngineState.WAIT_FOR_READYOK):
					# 初回のみこの応答に対して1秒待つことにより、
					# プロセスの初期化タイミングが重複しないようにする。
					if initial_waits[engine_idx]:
						initial_waits[engine_idx] = False
						time.sleep(1)

					states[engine_idx] = EngineState.START
					# 両方のエンジンがstart状態になったら対局開始
					if states[engine_idx^1] == EngineState.START:
						# isreadyで待っていた両方のエンジンに対してusinewgameを送る
						usinewgame_cmd(engine_idx, sfen_no)
						usinewgame_cmd(engine_idx^1, sfen_no)
						sfen_no = (sfen_no + 1) % len(book_sfens)

						# 先手→後手、交互に行う。
						go_cmd((engine_idx & ~1) + turns[engine_idx//2])

				elif ("bestmove" in line) and (states[engine_idx] == EngineState.WAIT_FOR_BESTMOVE):
					# node数計測用(60手目までのみ)
					if moves[engine_idx//2] < 60 :
						ns = nodes_str[engine_idx].split()
						for j in range(len(ns)):
							if ns[j] == "nodes":
								if j+1 < len(ns):
									nodes[engine_idx] += int(ns[j+1])
								break
					
					# 評価値の計測用
					vs = eval_value_from_thread[engine_idx].split()
					for j in range(len(vs)):
						if vs[j] == "score":
							if j+2 < len(vs):
								try:
									v = int(vs[j+2])
								except:
									print(f"Error : score = {eval_value_from_thread[engine_idx]}")
									eval_value_from_thread[engine_idx] = ""

								if vs[j+1] == "cp" :
									eval_value_from_thread[engine_idx] = str(v)
								elif vs[j+1] == "mate" :
									if v >= 0:
										eval_value_from_thread[engine_idx] = str(32000 - v)
									else:
										eval_value_from_thread[engine_idx] = str(-32000 + v)
							else:
								eval_value_from_thread[engine_idx] = "?"
							break

					# if (not random time)
					time_setting = options[2 + (engine_idx & 1)]
					if time_setting[3] == 0:
						elapsed_time = int(math.ceil(time.time() - go_times[engine_idx])*1000)
						r = rest_times[engine_idx] + time_setting[1] - elapsed_time

						if r < 0:
							r += time_setting[2] # byoyomi加算
							if False: # このブロックは常にFalseなので実質無効
								elapsed_time2 = int((time.time() - go_times[engine_idx])*1000)
								r = rest_times[engine_idx] + options[2][1] + options[2][2] - elapsed_time2
								mes = "Error : TimeOver = " + engines[engine_idx & 1] + " overtime = " + str(-r)
								outlog(engine_idx,mes)
								outstd(engine_idx,mes)
								line = "bestmove resign"

							rest_times[engine_idx] = 0
						else:
							rest_times[engine_idx] = r
					
					if "resign" in line:
						if (engine_idx % 2) == 1: # 後手エンジンが投了
							win += 1
							gameover = GameResult.P1_WIN # 1P勝ち (エンジン0勝ち)
						else: # 先手エンジンが投了
							lose += 1
							gameover = GameResult.P2_WIN # 2P勝ち (エンジン1勝ち)
						if (moves[engine_idx//2] & 1) == 1: # 後手番で勝った
							win_black += 1
						else: # 先手番で勝った
							win_white += 1
						update = True
					elif "win" in line: # エンジンが勝利宣言した場合
						if (engine_idx % 2) == 0: # 先手エンジンが勝ち宣言
							win += 1
							gameover = GameResult.P1_WIN # 1P勝ち (エンジン0勝ち)
						else: # 後手エンジンが勝ち宣言
							lose += 1
							gameover = GameResult.P2_WIN # 2P勝ち (エンジン1勝ち)
						if (moves[engine_idx//2] & 1) == 0: # 先手番で勝った
							win_black += 1
						else: # 後手番で勝った
							win_white += 1
						update = True
					else: # 通常のbestmove
						ss = line.split()
						if sfens[engine_idx//2] != "":
							sfens[engine_idx//2] += " "
						try:
							sfens[engine_idx//2] += ss[1] # 指し手を追加
							if KifOutput:
								eval_values[engine_idx//2] += eval_value_from_thread[engine_idx] + " "
						except:
							outlog(engine_idx, "Error! " + line)

						moves[engine_idx//2] += 1
						if moves[engine_idx//2] >= MAX_MOVES: # 256手で引き分け
							draw += 1
							gameover = GameResult.DRAW # Draw
							update = True
						else:
							go_cmd(engine_idx^1) # 相手のエンジンにgoコマンドを送る
				
				if gameover != GameResult.NO_RESULT:
					gameover_cmd(engine_idx, gameover)
					gameover_cmd(engine_idx^1, gameover)
					if KifOutput:
						if kifu_format == "csa":
							write_csa_game(engine_idx//2, gameover)
						else:
							kif_file.write("startpos moves " + sfens[engine_idx//2] + "\n")
							kif_file.write(eval_values[engine_idx//2] + "\n")
					turns[engine_idx//2] = turns[engine_idx//2] ^ 1 # 手番を交代

			elif message['type'] == 'terminated':
				# エンジンが予期せず終了した場合はエラーとしてログ
				retcode = message['retcode']
				if not term_procs[engine_idx]:
					print(f"[{engine_idx}]: Error! Process terminated with code {retcode}.")
					term_procs[engine_idx] = True
				# ターミネートされた場合も試合を終了させるなどのロジックを追加検討可能
				update = True # 状態変化として扱う

		except queue.Empty:
			# キューが空の場合、メインスレッドが行う処理（タイムアウトチェックなど）
			pass

		# 全エンジンの初期化がまだならisreadyを送る
		for i in range(len(states)):
			if states[i] == EngineState.INIT:
				isready_cmd(i)
			
			# goコマンドを送信してから一定時間経過している場合のタイムアウト処理
			if states[i] == EngineState.WAIT_FOR_BESTMOVE \
				and time.time() - go_times[i] >= (300 if "t" in opt2 else 60):
				
				go_times[i] = sys.maxsize # 再度タイムアウトしないように
				mes = f"[{i}]: Error! Engine Timeout."
				outlog(i,mes)
				outstd(i,mes)
				# タイムアウトした場合は、そのエンジンを負けと見なすか、対局を中断するなどの処理
				# ここでは簡易的に相手の勝利とする
				if (i % 2) == 0: # エンジン0がタイムアウト -> エンジン1の勝ち
					lose += 1
				else: # エンジン1がタイムアウト -> エンジン0の勝ち
					win += 1
				update = True # 状態変化として扱う
				# タイムアウトした対局を終了させる
				gameover_cmd(i, GameResult.DRAW)
				gameover_cmd(i^1, GameResult.DRAW)

		# 状態が更新されたら、全体の対局数チェックと途中結果の出力
		if update:
			loop_count = win + lose + draw
			if loop_count >= loop :
				# 指定のloop回数に達したので終了する。
				for p in procs:
					if p and p.poll() is None: # プロセスがまだ実行中なら終了させる
						p.terminate()
				for t in engine_reader_threads: # リーダースレッドが終了するのを待つ (joinはしない、daemonなので自動終了)
					pass # デーモンスレッドなのでjoinは不要だが、念のため

				if FileLogging:
					log_file.close()
				if KifOutput:
					if kifu_format == "csa":
						for exporter in csa_exporters:
							exporter.close()
					else:
						kif_file.close()
				return win, lose, draw, win_black, win_white

			# 一定回数ごとに途中結果を出力
			if loop_count % 10 == 0 :
				output_rating(win,draw,lose,win_black,win_white,opt2)
				if FileLogging:
					for i in range(len(states)):
						log_file.write(f"[{i}] State = {states[i]}\n")
					log_file.flush()
				if KifOutput:
					if kifu_format == "csa":
						for exporter in csa_exporters:
							exporter.f.flush()
					else:
						kif_file.flush()

		# メッセージキューの処理とタイムアウト処理の間で短いスリープを挟む
		time.sleep(0.001)

	# vs_match関数が正常に終了した場合、集計結果を返す
	return win, lose, draw, win_black, win_white


# 省略されたエンジン名に対して、フルパス名を返す
def engine_to_full(e):
	# 技巧
	if e == "gikou":
		e = "gikou_win_20160606/gikou.exe"
	# Silent Majority
	elif e == "SM":
		e = "SM_V110/SILENT_MAJORITY_AVX2_x64.exe"
	# やねうら王2016(Mid)
	elif e == "mid":
		e = "YaneuraOuV357mid.exe"

	return e

# ここからmain()

def main():
	# ======================================================================
	# コマンドラインオプションの定義
	# ======================================================================
	parser = argparse.ArgumentParser(
		description="A script to run self-play matches between two shogi engines.",
		formatter_class=argparse.ArgumentDefaultsHelpFormatter # デフォルト値をヘルプに表示
	)
	
	# --- Basic settings ---
	parser.add_argument('--config', type=str, help="Path to a YAML configuration file.")
	parser.add_argument('--home', type=str, help="Path to the home directory containing 'exe' and 'eval' folders.")
	parser.add_argument('--engine1', type=str, help="Path or name of engine 1.")
	parser.add_argument('--eval1', type=str, help="Name of the evaluation function folder for engine 1.")
	parser.add_argument('--engine2', type=str, help="Path or name of engine 2.")
	parser.add_argument('--eval2', type=str, help="Name of the evaluation function folder for engine 2.")

	# --- Game settings ---
	parser.add_argument('--parallel_games', type=int, default=1, help="Number of games to run in parallel.")
	parser.add_argument('--engine_threads', type=int, default=1, help="Number of threads for each engine process.")
	parser.add_argument('--loop', type=int, default=100, help="Total number of games to play.")
	parser.add_argument('--time', type=str, default="b1000", help="Time control settings (e.g., 'b1000', 'r100', 't300000/i3000').")
	parser.add_argument('--hash1', type=str, default="128", help="Hash size for engine 1 (in MB).")
	parser.add_argument('--hash2', type=str, default="128", help="Hash size for engine 2 (in MB).")

	# --- Opening book settings ---
	parser.add_argument('--book_moves', type=int, default=24, help="Number of moves to follow from the opening book.")
	parser.add_argument('--rand_book', action='store_true', help="Shuffle the opening book entries.")

	# --- Logging settings ---
	parser.add_argument('--log', action='store_true', help="Enable file logging for engine communication.")
	parser.add_argument('--param_log_path', type=str, default="", help="Enable and specify path for parameter logging.")
	parser.add_argument('--kifu_format', type=str, default="sfen", choices=["sfen", "csa"], help="Output format for game records.")
	
	args = parser.parse_args()

	# ======================================================================
	# 設定の読み込みとマージ
	# 優先順位: コマンドライン引数 > 設定ファイル > デフォルト値
	# ======================================================================
	
	# 1. argparseのデフォルト値を含むパース結果を取得
	config = vars(args)

	# 2. 設定ファイルがあれば読み込んでマージ
	if args.config:
		try:
			with open(args.config, 'r') as f:
				config_from_file = yaml.safe_load(f)
			if config_from_file:
				# コマンドライン引数で指定されていない項目のみ、ファイルの値で更新
				# (コマンドライン引数の値がデフォルト値と同じであれば、ファイルの値で上書きする)
				for key, value in config_from_file.items():
					if key in config and config[key] == parser.get_default(key):
						config[key] = value
		except FileNotFoundError:
			print(f"Warning: Config file not found at {args.config}")
		except Exception as e:
			print(f"Warning: Error reading config file: {e}")

	# 3. 必須引数のチェック
	required_args = ['home', 'engine1', 'eval1', 'engine2', 'eval2']
	for arg in required_args:
		if not config.get(arg):
			print(f"Error: Missing required argument: --{arg}. Please specify it via command line or config file.")
			sys.exit(1)

	# ======================================================================
	# 変数の準備
	# ======================================================================

	home = config['home']
	threads = config['parallel_games']
	loop = config['loop']
	engine_threads = config['engine_threads']
	hashes = [config['hash1'], config['hash2']]
	engine1_path = config['engine1']
	engine2_path = config['engine2']
	eval1_path = config['eval1']
	eval2_path = config['eval2']
	book_moves = config['book_moves']
	play_time_list = config['time'].split(",")
	PARAMETERS_LOG_FILE_PATH = config['param_log_path']
	rand_book = config['rand_book']
	fileLogging = config['log']
	kifu_format = config['kifu_format']

	# expand eval_dir
	evaldirs = []
	eval2_root = os.path.join(home, "eval", eval2_path)
	if not os.path.exists(os.path.join(eval2_root, "0")):
		evaldirs.append(eval2_path)
	else:
		i = 0
		while os.path.exists(os.path.join(eval2_root, str(i))):
			evaldirs.append(os.path.join(eval2_path, str(i)))
			i += 1

	print("home           : " , home)
	print("play_time_list : " , play_time_list)
	print("evaldirs       : " , evaldirs)
	print("hash size      : " , hashes)
	print("book_moves     : " , book_moves)
	print("engine_threads : " , engine_threads)
	print("rand_book      : " , rand_book)
	print("kifu_format    : " , kifu_format)
	print("PARAMETERS_LOG_FILE_PATH : " , PARAMETERS_LOG_FILE_PATH)

	total_win = total_lose = total_draw = 0
	total_win_black = total_win_white = 0

	book_file = open(os.path.join(home, "book", "records2016_10818.sfen"),"r")
	book_sfens = []
	count = 1
	for sfen in book_file:
		s = sfen.split()
		sf = ""
		for i in range(book_moves):
			try:
				# skip "startpos moves"
				sf += s[i+2]+" "
			except:
				print("Error! " + " in records2016.sfen line = " + str(count))
		book_sfens.append(sf)
		count += 1
		if count % 100 == 0:
			sys.stdout.write(".")
			sys.stdout.flush()
	book_file.close()
	print()

	# 定跡をシャッフルする
	if rand_book:
		random.shuffle(book_sfens)

	# threadsはparallel_gamesに相当。 engine_threadsはエンジンに渡すスレッド数。
	# 古いthreads = threads // engine_threads の行は不要。

	for evaldir in evaldirs:
		engine1 = engine_to_full(engine1_path)
		engine2 = engine_to_full(engine2_path)

		engines = ( engine1 , engine2 )
		engines_full = ( os.path.join(home, "exe", engines[0]) , os.path.join(home, "exe", engines[1]) )
		evals   = ( eval1_path , evaldir )
		evals_full   = ( os.path.join(home, "eval", eval1_path) , os.path.join(home, "eval", evaldir) )

		for i in range(2):
			print("engine" + str(i+1) + " = " + engines[i] + " , eval = " + evals[i])

		for play_time in play_time_list:
			print("\nthreads = " + str(threads) + " , loop = " + str(loop) + " , play_time = " + play_time)

			options = create_option(engines,engine_threads,evals_full,play_time,hashes,PARAMETERS_LOG_FILE_PATH)

			for i in range(2):
				print("option " + str(i+1) + " = " + ' / '.join(options[i]))
				print("time_setting = (total_time,inc_time,byoyomi,rtime,depth_time) = " + str(options[i+2]))

			sys.stdout.flush()

			# 短くスレッド数と秒読み条件を文字列化
			opt2 = "T"+str(engine_threads) + "," + play_time

			w, l, d, wb, ww = vs_match(
				engines_full,
				options,
				threads,
				loop,
				book_sfens,
				fileLogging,
				opt2,
				book_moves,
				kifu_format=kifu_format,
			)

			total_win += w
			total_lose += l
			total_draw += d
			total_win_black += wb
			total_win_white += ww

			# output final result
			print("\nfinal result : ")
			for i in range(2):
				print("engine" + str(i+1) + " = " + engines[i] + " , eval = " + evals[i])
#			print "play_time = " + play_time + " , " ,
			output_rating(total_win, total_draw, total_lose, total_win_black, total_win_white, opt2)


if __name__ == "__main__":
	main()
