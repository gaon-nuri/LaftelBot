#!/usr/bin python3

"""
비공식 라프텔 텔레그램 봇.

신작, 속편, 차회 알림 지원.

중지는 Ctrl + C.

만든 이 : 시나브로
"""

import os, logging				# 필수 기능
import requests					# HTTP 요청
import html, json, traceback	# 오류 처리
import laftel					# API Wrapper

from typing import Tuple, Dict, Any

# 텔레그램 API
from telegram import (
	Update,
	InlineKeyboardButton,
	InlineKeyboardMarkup,
	ParseMode,				# HTML
)


# PTB 프레임워크
from telegram.ext import (
	Updater,
	CommandHandler,
	MessageHandler,
	Filters,
	CallbackContext,		# 답장
	CallbackQueryHandler,	# 버튼
	ConversationHandler,
)


# 환경 변수
from dotenv import load_dotenv
load_dotenv(verbose=True)


# 웹 크롤링
from bs4 import BeautifulSoup as bs

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s -\
							%(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


# 대화 상태 (1층)
SEL_ACTION, ADD_NEXT, ADD_NEW, DESC_NEW = map(chr, range(4))

# 대화 상태 (2층)
SEL_LENGTH, SEL_TYPE = map(chr, range(4, 6))

# 대화 상태 (입력)
SEL_FEATURE, TYPE_NAME, TYPE_LAPSE, SRCH_NAME = map(chr, range(6, 10))

# 대화 상태 (검색)
PICK_ALERT, CHK_NEW, CHK_EP = map(chr, range(10, 13))

# 메타 상태
STOPPING, SHOWING = map(chr, range(13, 15))

# ConversationHandler.END 준말
END = ConversationHandler.END


# 상수 정의
(
	SEQUEL,
	EPISODE,
	NEXT,
	NEW,
	TYPE,
	NAME,
	LAPSE,
	NOT_FOUND,
	TEST,
	RE_START,
	FEATURES,
	CUR_FEATURE,
	CUR_LEVEL,
) = map(chr, range(15, 28))

DAY = '1일'
WEEK = '1주'
MONTH = '1달'
YEAR = '1년'


# 보조 함수
def _name_switcher(level: str) -> Tuple[str, str]:
	if level == EPISODE:
		return '본편', '외전'
	return '시리즈', '영화'


def edit(query, user_data, text, key=None) -> None:
	if user_data['query_msg_txt'] != text:
		user_data['query_msg_txt'] = text
		query.edit_message_text(text=text, reply_markup=key)
	else:
		query.edit_message_text(text=text+'\n\n(수정 실패)', reply_markup=key)


## 명령어 정의 : update, context 인수 필요

# 1단계 대화 응답
def start(update, context) -> str:
	"""작업 선택 : 알림 추가, 목록 표시, 대화 종료"""

	text = "대화를 중단하려면 '/stop'을 입력해줘."
	btns = [
		[
			InlineKeyboardButton(text='속편/차회', callback_data=str(ADD_NEXT)),
			InlineKeyboardButton(text='신작', callback_data=str(ADD_NEW)),
		],
		[
			InlineKeyboardButton(text='목록', callback_data=str(SHOWING)),
			InlineKeyboardButton(text='완료', callback_data=str(END)),
		],
	]
	key = InlineKeyboardMarkup(btns)
	query = update.callback_query
	user_data = context.user_data

	# 재시작할 때는 새 메시지를 보내지 X
	if query or user_data.get(RE_START):
		query.answer()
		edit(query, user_data, text, key)
	else:
		msg = update.message
		user = msg.from_user
		logger.info("사용자 %s가 대화를 시작.", user.first_name)
		text2 = "안녕, 난 라프텔 알리미야. 신작, 속편, 차회 알림을 설정할 수 있어."
		msg.reply_text(text=text2) # 첫 인사
		msg.reply_text(text=text, reply_markup=key)
		user_data['query_msg_txt'] = text

	user_data[RE_START] = False
	return SEL_ACTION


# 안내
def helps(update, context) -> None:
	"""명령어 안내 메시지 전송"""
	text = "라프텔 알리미 사용법"
	update.message.reply_text(text=text)


# 앵무새
def echo(update, context) -> None:
	update.message.reply_text(update.message.text)

echo_handler = MessageHandler(Filters.text & ~Filters.command, echo)

################### 중첩 대화 시작 ###################

def adding_new_work(update, context) -> str:
	"""사용자에게 신작의 제목을 질문"""
	user_data = context.user_data
	user_data[CUR_LEVEL] = str(NEW)
	btns = [
		[
			InlineKeyboardButton(text='확인', callback_data=str(NEW)),
			InlineKeyboardButton(text='뒤로', callback_data=str(END)),
		]
	]
	key = InlineKeyboardMarkup(btns)

	query = update.callback_query
	query.answer()
	text = "신작 알림을 설정할까?"
	edit(query, user_data, text, key)

	return DESC_NEW


# 목록 표시
def show_data(update, context) -> str:
	"""입력된 정보를 정리해서 출력"""

	def prettyprint(user_data: Dict[str, Any], level: str) -> str:
		alerts = user_data.get(level)
		if not alerts:
			return '\n설정된 알림 없음.'

		text = ''
		if level == NEW:
			for alert in user_data[level]:
				text += f"\n간격: {alert.get(LAPSE, '-')}, 이름: {alert.get(NAME, '-')}"
		else:
			alpha, beta = _name_switcher(level)

			for alert in user_data[level]:
				type = beta if alert[TYPE] == NEW else alpha
				text += f"\n{type} | 간격: {alert.get(LAPSE, '-')}, 이름: {alert.get(NAME, '-')}"
		return text

	user_data = context.user_data
	text = f"신작:{prettyprint(user_data, NEW)}"
	text += f"\n\n속편:{prettyprint(user_data, SEQUEL)}"
	text += f"\n\n차회:{prettyprint(user_data, EPISODE)}"

	btns = [
		[
			InlineKeyboardButton(text='처음으로', callback_data=str(END)),
			InlineKeyboardButton(text='시험', callback_data=str(TEST)),
		]
	]
	key = InlineKeyboardMarkup(btns)

	query = update.callback_query
	query.answer()
	edit(query, user_data, text, key)
	user_data[RE_START] = True

	return SHOWING


## 대화 종료
def stop(update, context) -> int:
	"""명령어 기반, reply 사용"""
	update.message.reply_text('그래, 잘 가.')

	return END


def end(update, context) -> int:
	"""키보드 기반, query 사용"""
	query = update.callback_query
	query.answer()
	
	user_data = context.user_data

	text = "다음에 보자!"
	edit(query, user_data, text)

	return END


# 2단계 대화 응답
def select_length(update, context) -> str:
	"""속편/차회 알림 선택"""
	user_data = context.user_data
	text = "알림 설정, 설정된 알림 확인, 취소 등이 가능해."
	btns = [
		[
			InlineKeyboardButton(text='속편', callback_data=str(SEQUEL)),
			InlineKeyboardButton(text='차회', callback_data=str(EPISODE)),
		],
		[
			InlineKeyboardButton(text='목록', callback_data=str(SHOWING)),
			InlineKeyboardButton(text='뒤로', callback_data=str(END)),
		],
	]
	key = InlineKeyboardMarkup(btns)

	query = update.callback_query
	query.answer()
	edit(query, user_data, text, key)

	return SEL_LENGTH


def select_type(update, context) -> str:
	"""시리즈/영화 또는 본편/외전 선택"""
	query = update.callback_query
	query.answer()
	level = query.data
	
	user_data = context.user_data
	user_data[CUR_LEVEL] = level
	alpha, beta = _name_switcher(level)

	btns = [
		[
			InlineKeyboardButton(text=f'{alpha}', callback_data=str(NEXT)),
			InlineKeyboardButton(text=f'{beta}', callback_data=str(NEW)),
		],
		[
			InlineKeyboardButton(text='목록', callback_data=str(SHOWING)),
			InlineKeyboardButton(text='뒤로', callback_data=str(END)),
		],
	]
	key = InlineKeyboardMarkup(btns)

	text = "어떤 알림을 설정할까?"
	edit(query, user_data, text, key)

	return SEL_TYPE


def end_second_level(update, context) -> int:
	"""1단계 대화로 복귀."""
	context.user_data[RE_START] = True
	start(update, context)

	return END


# 3단계 대화 응답
def select_feature(update, context) -> str:
	"""알림을 받을 작품의 제목과 간격을 질문."""
	btns = [
		[
			InlineKeyboardButton(text='이름', callback_data=str(NAME)),
			InlineKeyboardButton(text='간격', callback_data=str(LAPSE)),
			InlineKeyboardButton(text='완료', callback_data=str(END)),
		]
	]
	key = InlineKeyboardMarkup(btns)
	query = update.callback_query
	user_data = context.user_data

	# 새 알림에 대한 정보를 얻으면 캐시를 지우고 종류를 저장
	if not user_data.get(RE_START):
		query.answer()
		user_data[FEATURES] = {TYPE: query.data}
		
		text = "저장할 항목을 알려줘."
		edit(query, user_data, text, key)

	# 그 다음부터 새 메시지를 전송
	else:
		msg = update.message
		text = "저장했어. 또 도와줄 거 있어?"
		if msg:
			msg.reply_text(text=text, reply_markup=key)
		elif query:
			edit(query, user_data, text, key)

	user_data[RE_START] = False
	return SEL_FEATURE


def ask_for_name(update, context) -> str:
	"""사용자에게 이름을 질문"""
	query = update.callback_query
	query.answer()
	
	user_data = context.user_data
	user_data[CUR_FEATURE] = query.data

	text = "이름을 알려줘."
	edit(query, user_data, text)

	return TYPE_NAME


def ask_for_lapse(update, context) -> str:
	"""사용자에게 간격을 질문"""
	query = update.callback_query
	query.answer()
	user_data = context.user_data
	user_data[CUR_FEATURE] = query.data
	btns = [
		[
			InlineKeyboardButton(text='1일', callback_data=DAY),
			InlineKeyboardButton(text='1주', callback_data=WEEK),
		],
		[
			InlineKeyboardButton(text='1달', callback_data=MONTH),
			InlineKeyboardButton(text='1년', callback_data=YEAR),
		]
	]
	key = InlineKeyboardMarkup(btns)
	text = "간격을 선택해줘."
	edit(query, user_data, text, key)

	return TYPE_LAPSE


def search_name(update, context) -> str:
	"""입력한 제목을 검색한 결과를 출력"""
	msg = update.message
	title = msg.text

	# 라프텔 이름 검색
	items = laftel.sync.searchAnime(title)
	
	# 검색 결과를 버튼으로
	btns = [[
		InlineKeyboardButton(
			text='없음', 
			callback_data=str(NOT_FOUND))
	]]
	for i, item in enumerate(items):
		btns.append([InlineKeyboardButton(
					text=f"{i}. {item.name}\n",
					callback_data=f"#{item.name}"
					)])

	# 원하는 애니를 선택
	key = InlineKeyboardMarkup(btns)
	text = "찾는 애니가 없으면 '없음'을 눌러줘."
	msg.reply_text(text, reply_markup=key)
	
	return SRCH_NAME


def save_name(update, context) -> str:
	"""이름을 저장 후 선택 화면으로 복귀"""
	query = update.callback_query
	query.answer()
	# query.edit_message_text(text="이름 저장함.")

	data = query.data.lstrip('#')
	user_data = context.user_data
	user_data[FEATURES][user_data[CUR_FEATURE]] = data
	user_data[RE_START] = True

	return select_feature(update, context)


def save_lapse(update, context) -> str:
	"""간격을 저장 후 선택 화면으로 복귀"""
	query = update.callback_query
	query.answer()
	# query.edit_message_text(text="간격 저장함.")

	user_data = context.user_data
	user_data[FEATURES][user_data[CUR_FEATURE]] = query.data

	user_data[RE_START] = True

	return select_feature(update, context)


def pick_alert(update, context) -> str:
	"""목록에서 작품을 선택"""
	def data_to_key(user_data: Dict[str, Any]) -> str:
		btns = [[
			InlineKeyboardButton(
				text='처음으로', 
				callback_data=str(NOT_FOUND)
			)
		]]
		alerts = user_data.get(CUR_LEVEL)
		if not alerts:
			return btns

		i = 0
		new_alerts = user_data.get(str(NEW))
		next_alerts = user_data.get(str(NEXT))
		if new_alerts:
			for alert in new_alerts:
				text = f"{i}. {alert.get(NAME, '-')}"
				btns.append([
					InlineKeyboardButton(
						text=text, callback_data=f"{i}"
					)
				])
				i += 1
		if next_alerts:
			for alert in next_alerts:
				text = f"{i}. {alert.get(NAME, '-')}"
				btns.append([
					InlineKeyboardButton(
						text=text, callback_data=f"{i}")
				])
				i += 1
		return btns

	query = update.callback_query
	query.answer()

	text = '하나를 선택해줘.'
	user_data = context.user_data
	btns = data_to_key(user_data)
	key = InlineKeyboardMarkup(btns)
	edit(query, user_data, text, key)
	
	return PICK_ALERT


def test_alert(update, context) -> str:
	"""선택한 작품의 알림을 시험"""
	query = update.callback_query
	query.answer()
	text = "작품 페이지 검색 중..."
	query.edit_message_text(text=text)

	# from datetime import date

	# 라프텔 작품 페이지
	url = items[int(query.data)].url # "https://laftel.net/item/40902"
	res = requests.get(url)

	# HTML 파싱
	soup = bs(res.content, 'html.parser')

	# 회차 정보 추출
	# d = "" # date.today().isoformat().replace("-", ".")

	if user_data[TYPE] == NEW:
		return CHK_NEW
	if user_data[TYPE] == NEXT:
		return CHK_EP


def end_describing(update, context) -> int:
	"""입력을 더 이상 받지 않고 이전 대화로 복귀."""
	user_data = context.user_data
	level = user_data[CUR_LEVEL]
	if not user_data.get(level):
		user_data[level] = []
	user_data[level].append(user_data[FEATURES])

	# 상위 메뉴로 복귀
	if level == NEW:
		user_data[RE_START] = True
		start(update, context)
	else:
		select_length(update, context)

	return END


def stop_nested(update, context) -> str:
	"""중첩된 대화 안에서 대화를 완전히 종료"""
	update.message.reply_text('그래, 잘 가.')

	return STOPPING

#################### 중첩 대화 끝 ####################

# 신작 여부
def check_new(update, context, soup) -> int:
	"한 편도 없으면 꽝, 1화만 있으면 신작, 2화도 있으면 구작"
	eps = soup.select("h5")

	# 한 편도 없음
	if len(eps) < 1:
		s = "은/는 아직이에요."

	# 1화만 있음
	elif len(eps) < 2:
		d = "조금 전"; s = "{D}에 나왔어요!".format(D=d)

	# 2화도 있음
	else:
		d = "오래 전"; s = "{D}에 나왔어요!".format(D=d)

	a = soup.select_one("title").text.rstrip('- 라프텔')
	query.edit_message_text("{A}이/가 {S}".format(A=a, S=s))


# 차회 유무
def check_ep(update, context, soup) -> int:
	"""차회 유무를 확인"""
	eps = soup.select("h5")

	a = soup.select_one("title").text.rstrip('- 라프텔')
	n = 11; t = "{A} {N}화".format(A=a, N=n)

	for ep in eps:
		# 차회 O
		if "{N}화".format(N=n+1) in ep.text:
			s = "나왔어!"
			query.edit_message_text("{T}이/가 {S}".format(T=t, S=s))
			exit()

	# 차회 X
	s = "나오려면 멀었어."
	query.edit_message_text("{T}이/가 {S}".format(T=t, S=s))


# 틀린 명령
def unknown(update, context) -> None:
	update.message.reply_text("잘못된 명령어")


# 오류 처리
def error_handler(update: object, context) -> None:
	"""오류 로그를 전송"""
	logger.error(msg="갱신 처리 중 예외 발생:\n", exc_info=context.error)

	# 파이썬 오류 메시지
	tb_list = traceback.format_exception(None, context.error,\
										 context.error.__traceback__)
	tb_string = ''.join(tb_list)

	up_str = update.to_dict() if isinstance(update, Update) else str(update)

	# 메시지에 마크업과 추가 정보 넣기
	info_list = [
		f"갱신 처리 중 예외 발생",
		f"<pre>update = {html.escape(json.dumps(up_str, indent=2, ensure_ascii=False))}</pre>",
		f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>",
	]
	info_list2 = [
		f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>",
		f"<pre>{html.escape(tb_string)}</pre>",
	]

	chat_id = os.environ.get("DEV_ID")
	mode = ParseMode.HTML

	info = "\n".join(info_list)
	info2 = "\n".join(info_list2)

	# 메시지 전송
	# 너무 길면 나눠서
	if len(info) + len(info2) > 4096:
		context.bot.sendMessage(chat_id=chat_id, text=info,\
								parse_mode=mode)	
		context.bot.sendMessage(chat_id=chat_id, text=info2,\
								parse_mode=mode)
	else:
		info = "\n".join(info_list + info_list2)
		context.bot.sendMessage(chat_id=os.environ.get("DEV_ID"),\
								text=info, parse_mode=mode)


def main() -> None:
	"""봇 실행."""
	# 갱신기 생성, 봇 토큰 전달
	updater = Updater(token=os.environ.get("TOKEN"))

	# 처리기를 등록할 배포기를 정의
	dp = updater.dispatcher

	## 알림
	crawl_conv = ConversationHandler(
		name = "crawl_conv",
		entry_points=[
			CallbackQueryHandler(
				pick_alert,
				pattern='^'+str(TEST)+'$'
			)
		],
		states={
			SHOWING: [
				CallbackQueryHandler(
					end_second_level, pattern='^'+str(END)+'$'
				),
				CallbackQueryHandler(
					pick_alert, pattern='^'+str(TEST)+'$'
				)
			],
			PICK_ALERT: [
				CallbackQueryHandler(
					start, pattern='^'+str(NOT_FOUND)+'$'
				),
				CallbackQueryHandler(
					test_alert, pattern='^\d+$'
				),
			],
			CHK_NEW: [
				CallbackQueryHandler(
					check_new, pattern='^'+str(CHK_NEW)+'$'
				)
			],
			CHK_EP:	[
				CallbackQueryHandler(
					check_ep, pattern='^'+str(CHK_EP)+'$'
				)
			],
		},
		fallbacks=[
			CallbackQueryHandler(end_second_level, pattern='^'+str(END)+'$'),
			CommandHandler('stop', stop_nested),
		],
		map_to_parent={
			# 시작 메뉴로 복귀
			END: SEL_ACTION,
			# 대화 완전 종료
			STOPPING: END,
		},
	)

	## 대화
	# 3단계 대화 처리기를 정의 (이름, 간격)
	desc_conv = ConversationHandler(
		name = "desc_conv",
		entry_points=[
			CallbackQueryHandler(
				select_feature,
				pattern='^'+str(NEXT)+'$|^'+str(NEW)+'$'
			),
		],
		states={
			SEL_FEATURE: [
				CallbackQueryHandler(
					ask_for_name, 
					pattern='^'+str(NAME)+'$'
				),
				CallbackQueryHandler(
					ask_for_lapse,
					pattern='^'+str(LAPSE)+'$'
				),
			],
			TYPE_NAME: [
				MessageHandler(
					Filters.text & ~Filters.command,
					search_name
				),
			],
			TYPE_LAPSE: [
				CallbackQueryHandler(
					save_lapse, pattern='^1'
				)
			],
			SRCH_NAME: [
				CallbackQueryHandler(
					ask_for_name,
					pattern='^'+str(NOT_FOUND)+'$'
				),
				CallbackQueryHandler(
					save_name, pattern='^#'
				),
			]
		},
		fallbacks=[
			CallbackQueryHandler(end_describing, pattern='^'+str(END)+'$'),
			CommandHandler('stop', stop_nested),
		],
		map_to_parent={
			# 2단계 메뉴로 복귀
			END: SEL_LENGTH,
			# 대화 완전 종료
			STOPPING: END,
		},
	)

	# 2단계 대화 처리기를 정의 (알림 종류 선택)
	add_alert_conv = ConversationHandler(
		name = "add_alert_conv",
		entry_points=[
			CallbackQueryHandler(select_length, pattern='^'+str(ADD_NEXT)+'$'),
		],
		states={
			SEL_LENGTH: [
				CallbackQueryHandler(select_type, pattern=f'^{SEQUEL}$|^{EPISODE}$')
			],
			SEL_TYPE: [desc_conv],
		},
		fallbacks=[
			CallbackQueryHandler(show_data, pattern='^'+str(SHOWING)+'$'),
			CallbackQueryHandler(end_second_level, pattern='^'+str(END)+'$'),
			CommandHandler('stop', stop_nested),
		],
		map_to_parent={
			# 목록 표시 후 1단계 메뉴로 복귀
			SHOWING: SHOWING,
			# 1단계 메뉴로 복귀
			END: SEL_ACTION,
			# 대화 완전 종료
			STOPPING: END,
		},
	)

	# 1단계 대화 처리기를 정의 (작업 선택)
	# 3단계 상태가 2단계로 매핑되니 1단계에서도 구현
	selection_handlers = [
		add_alert_conv,
		CallbackQueryHandler(
			adding_new_work, pattern='^'+str(ADD_NEW)+'$'
		),
		CallbackQueryHandler(
			show_data, pattern='^'+str(SHOWING)+'$'
		),
		CallbackQueryHandler(end, pattern='^'+str(END)+'$'),
	]
	conv_handler = ConversationHandler(
		name = "conv_handler",
		entry_points=[CommandHandler('start', start)],
		states={
			SHOWING: [
				crawl_conv,
				CallbackQueryHandler(
					start, pattern='^'+str(END)+'$'
				),
			],
			SEL_ACTION: selection_handlers,
			SEL_LENGTH: selection_handlers,
			DESC_NEW: [
				desc_conv,
				CallbackQueryHandler(
					start, pattern='^'+str(END)+'$'
				)
			],
			STOPPING: [CommandHandler('start', start)],
		},
		fallbacks=[CommandHandler('stop', stop)],
	)

	## 처리기
	dp.add_handler(conv_handler)
	dp.add_handler(echo_handler)

	## 명령어
	dp.add_handler(CommandHandler("start", start))	# 시작
	dp.add_handler(CommandHandler("help", helps))	# 도움

	## 오류 처리
	dp.add_handler(MessageHandler(Filters.command, unknown))
	dp.add_error_handler(error_handler)

	# 봇 시작
	updater.start_polling()

	# Ctrl-C 입력 및 SIGINT, SIGTERM, SIGABRT 신호를 받을 때까지 가동.
	updater.idle()


if __name__ == "__main__": main()
